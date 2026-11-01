"""Graph-bound visual speaker QA and a separate original-proof/asset checker."""
import hashlib
import json
import re
from pathlib import Path
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.evidence.graph.rich.model import normalize
from .native_wording import speaker
from .visual import bind_reference
from .visual_options import appearances, crop, make_sheet, sheet_bytes
from .assets import image_library
from .admission import World, name_eligibility
from comics_qa.tasks.graph.gen2.quality import normalized
from .io import stable, digest

SCHEMA = 'comics_qa.benchmark1000.visual_choice_pilot.1'
PREFIX = 'Among the four pictured characters, who says '
TAIL = '? Answer A, B, C, or D using the labelled option sheet.'


def question(quote, page): return PREFIX + json.dumps(quote, ensure_ascii=False) + f' on page {page}' + TAIL


def parse_question(text):
    m = re.fullmatch(re.escape(PREFIX) + r'("(?:[^"\\]|\\.)*") on page ([1-9]\d*)' + re.escape(TAIL), text)
    if not m: raise ValueError('Unknown visual-choice wording')
    quote, page = json.loads(m[1]), int(m[2]); return quote, page, speaker(quote, page)


def source_evidence(g, v, r, doc, min_edge):
    result = doc['result']; nodes = {n['id']: n for n in g['nodes']}
    if result['status'] != 'OK' or not result['exact'] or result['type'] != 'Char' or nodes[result['value']]['generic']:
        raise ValueError('No uniquely proved non-generic speaker')
    used = set(doc['proof']['facts']); sources = [f for f in g['facts'] if f['fact_id'] in used and f['rel'] == 'spoken_by' and nodes[f['args'][1]]['type'] == 'Appearance']
    if len(sources) != 1: raise ValueError('Speaker must have one on-page depicted source')
    app = nodes[sources[0]['args'][1]]; transcripts = {t['id']: t for t in r['transcripts']}
    if app['identity_id'] != result['value']: raise ValueError('Speaker depiction identity differs')
    for f in r['facts']:
        if f['id'] in used and f['rel'] == 'transcript':
            t = transcripts[f['premises'][0]]
            if normalize(t['paddle_text']) != normalize(t['magi_text']) or normalize(t['paddle_text']) != t['consensus']:
                raise ValueError('Transcript models disagree')
    return app


def names(g, v, quote):
    text = ' ' + normalized(quote) + ' '
    for node in g['nodes']:
        if node['type'] == 'Character' and not node['generic'] and normalized(node['canonical_name']) and ' ' + normalized(node['canonical_name']) + ' ' in text:
            if name_eligibility(g, v, node['id'], node['canonical_name']): raise ValueError('Quoted character name ineligible')


def public_inputs(g, text, sheet):
    nodes = {n['id']: n for n in g['nodes']}
    _, page, _ = parse_question(text)
    pid = g['page_ids'][page-1]
    return {'question': text, 'answer_format': 'visual_choice',
            'pages': [{'index': page, 'path': nodes[pid]['image_path'], 'sha256': nodes[pid]['image_sha256']}],
            'reference_images': [{'role': 'answer_options', 'labels': list('ABCD'), 'path': sheet['path'], 'sha256': sheet['sha256']} ]}


def produce(g, v, r, quote, page, option_aids, out, min_edge=48):
    if r['decisions']: raise ValueError('Reviewed-rich ablation requires a separate profile')
    if len(option_aids)!=4 or len(set(option_aids))!=4: raise ValueError('Four distinct option appearances required')
    program = speaker(quote, page); doc = Interpreter(g, v, rich=r).execute(program)
    app = source_evidence(g, v, r, doc, min_edge); names(g,v,quote)
    refs = [crop(g, aid, out) for aid in option_aids]
    if len({x['crop_sha256'] for x in refs}) != 4: raise ValueError('Identical option pixels')
    # Repeated art copied to another page is still a same-crop shortcut.
    Image, _ = image_library(); nodes = {n['id']: n for n in g['nodes']}; source_page = nodes[app['page_id']]
    from .assets import box_pixels
    with Image.open(source_page['image_path']) as image: source = image.convert('RGB').crop(box_pixels(app['box'],image.width,image.height))
    correct = next(x for x in refs if x['identity_id'] == doc['result']['value'])
    with Image.open(correct['crop_path']) as image:
        if image.size == source.size and image.convert('RGB').tobytes() == source.tobytes(): raise ValueError('Same-crop reference shortcut')
    sheet = make_sheet(refs, out); world = World(g,v,r)
    controls = {}
    for label, args in [('source_page', ([app['page_id']], False)), ('ocr_only', (g['page_ids'], True))]:
        ag,av,ar = world.changed(*args); controls[label] = Interpreter(ag,av,rich=ar).execute(program)
    body = {'schema': SCHEMA, 'chapter_id': g['chapter_id'], 'split': g['split'],
            'question_type': 'visual_quote_speaker', 'evidence_class': 'executed', 'generation_mode': 'template', 'answer_format': 'visual_choice',
            'source': {'graph_sha256': stable(g), 'visibility_sha256': stable(v), 'rich_sha256': stable(r)},
            'program': program, 'execution': doc, 'options': [{'label': label, 'reference': ref} for label,ref in zip('ABCD',refs)],
            'answer': {'type': 'visual_choice', 'value': 'ABCD'[refs.index(correct)], 'identity_id': doc['result']['value']},
            'choice_proof': [{'label':label,'relation':'identity_equals_verified_speaker','value':ref['identity_id']==doc['result']['value'],
                              'speaker_execution_sha256':stable(doc),'reference_identity_fact_id':ref['identity_fact_id']} for label,ref in zip('ABCD',refs)],
            'source_appearance_id': app['id'], 'option_sheet': sheet, 'min_edge': min_edge, 'controls': controls,
            'public': public_inputs(g,question(quote,page),sheet),
            'verification': {'proof': 'independent_check_required', 'distractors': 'pending_human_review', 'human': 'pending', 'release': 'pending'},
            'admission': 'visual_pilot_not_native_admitted', 'evaluation': 'exact_A_to_D'}
    body['item_id'] = 'b1000v:' + stable(body)
    return body


def check(g, v, r, item):
    """Never invokes produce(), Interpreter.execute(), or the option selector."""
    try:
        if item['schema'] != SCHEMA or item['item_id'] != 'b1000v:' + stable({k:v for k,v in item.items() if k!='item_id'}): raise ValueError('Visual item binding mismatch')
        if item['source'] != {'graph_sha256':stable(g),'visibility_sha256':stable(v),'rich_sha256':stable(r)}: raise ValueError('Visual sources changed')
        if item['chapter_id'] != g['chapter_id'] or item['split'] != g['split']: raise ValueError('Visual chapter/split mismatch')
        if item['verification'] != {'proof':'independent_check_required','distractors':'pending_human_review','human':'pending','release':'pending'} or item['admission'] != 'visual_pilot_not_native_admitted': raise ValueError('Visual pilot cannot self-promote')
        if r['decisions'] or (item['question_type'],item['evidence_class'],item['generation_mode'],item['answer_format'],item['evaluation']) != ('visual_quote_speaker','executed','template','visual_choice','exact_A_to_D'): raise ValueError('Wrong visual pilot profile')
        quote,page,expected = parse_question(item['public']['question']); names(g,v,quote)
        if expected != item['program'] or not ProofChecker(g,v,rich=r).check(item['execution'],expected)['proof_valid']: raise ValueError('Invalid speaker program/proof')
        app = source_evidence(g,v,r,item['execution'],item['min_edge'])
        if app['id'] != item['source_appearance_id'] or g['page_ids'][page-1] != app['page_id']: raise ValueError('Wrong source depiction/page')
        available,_ = appearances(g,item['min_edge']); eligible = {a for aids in available.values() for a in aids}
        options = item['options']
        if len(options)!=4 or [o['label'] for o in options] != list('ABCD'): raise ValueError('Four ordered labels required')
        refs=[]; pixel_keys=set(); checker=ProofChecker(g,v,rich=r)
        for option in options:
            ref=option['reference']
            if ref['appearance_id'] not in eligible or bind_reference(g,ref['appearance_id'],ref['crop_path'])!=ref or ref['reference_page']==app['page_id']:
                raise ValueError('Invalid cross-page option reference')
            checker.check_derivations([ref['identity_fact_id']]); refs.append(ref)
            Image,_=image_library()
            with Image.open(ref['crop_path']) as image:
                pixel_keys.add(stable([list(image.size),hashlib.sha256(image.convert('RGB').tobytes()).hexdigest()]))
        if len({x['identity_id'] for x in refs})!=4 or len(pixel_keys)!=4: raise ValueError('Options not distinct')
        gold=[o['label'] for o in options if o['reference']['identity_id']==item['execution']['result']['value']]
        if len(gold)!=1 or item['answer']!={'type':'visual_choice','value':gold[0],'identity_id':item['execution']['result']['value']}: raise ValueError('Wrong label/identity answer')
        comparison=[{'label':o['label'],'relation':'identity_equals_verified_speaker','value':o['reference']['identity_id']==item['execution']['result']['value'],
                     'speaker_execution_sha256':stable(item['execution']),'reference_identity_fact_id':o['reference']['identity_fact_id']} for o in options]
        if item['choice_proof']!=comparison: raise ValueError('Invalid graph-derived option comparison')
        sheet=item['option_sheet']
        if sheet['layout']!='AB-CD-contain-320x380.1' or digest(sheet['path'])!=sheet['sha256'] or Path(sheet['path']).read_bytes()!=sheet_bytes(refs): raise ValueError('Option sheet pixels/order differ')
        if item['public']!=public_inputs(g,item['public']['question'],sheet): raise ValueError('Unexpected public metadata')
        # Verify source pixels and prohibit exact same-art reuse independently.
        Image,_=image_library(); nodes={n['id']:n for n in g['nodes']}; source_page=nodes[app['page_id']]
        if digest(source_page['image_path'])!=source_page['image_sha256']: raise ValueError('Source page changed')
        from .assets import box_pixels
        with Image.open(source_page['image_path']) as image:
            if image.size!=(source_page['width'],source_page['height']): raise ValueError('Source dimensions changed')
            source=image.convert('RGB').crop(box_pixels(app['box'],image.width,image.height))
        with Image.open(options['ABCD'.index(gold[0])]['reference']['crop_path']) as image:
            if image.size==source.size and image.convert('RGB').tobytes()==source.tobytes(): raise ValueError('Same-art answer shortcut')
        world=World(g,v,r)
        for label,args in [('source_page',([app['page_id']],False)),('ocr_only',(g['page_ids'],True))]:
            ag,av,ar=world.changed(*args); control=item['controls'][label]
            if not ProofChecker(ag,av,rich=ar).check(control,expected)['proof_valid']: raise ValueError('Invalid ablation proof')
            value=control['result']
            if value['status']=='OK' and value['exact'] and value['value']==item['answer']['identity_id']: raise ValueError('Source visual dependence not established')
        return {'proof_valid':True,'answer_supported':True,'graph_source_visual_required':True,
                'distractor_distinguishability':'pending_human_review','release_eligible':False}
    except (ValueError,KeyError,TypeError,IndexError,OSError,AttributeError) as exc:
        return {'proof_valid':False,'answer_supported':False,'error':str(exc),'release_eligible':False}


def exact_label(predicted, expected):
    return isinstance(predicted,str) and isinstance(expected,str) and expected in 'ABCD' and len(expected)==1 and predicted.strip().upper()==expected
