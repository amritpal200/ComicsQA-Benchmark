"""Checkpointed visual feasibility and review-pending option-sheet QA pilots."""
import base64
import fcntl
import html
import json
import random
from collections import Counter
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from .io import read, publish, digest, stable, separate, verify_manifest, verify_snapshot, member
from .assets import binary_publish
from .family_pilot import catalogue
from .native_wording import speaker
from .semantic import execute
from .visual_options import appearances
from .visual_choice import produce, check, source_evidence, names, parse_question

PREFLIGHT = 'comics_qa.benchmark1000.visual_preflight.1'
PILOT = 'comics_qa.benchmark1000.visual_pilot.1'


def world(root, chapter):
    gr,vr,rr = [Path(root)/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    g,v,pins=load_world(gr,vr,chapter); r=load_optional(gr,vr,rr,chapter,pins)
    if r is None or r['decisions']: raise ValueError('Unreviewed baseline rich sources required; reviews are not dropped')
    return g,v,r


def snapshots(g,v,r): return {'graph':stable(g),'visibility':stable(v),'rich':stable(r)}


def cross_page_options(g, available, target, page):
    nodes={n['id']:n for n in g['nodes']}
    eligible={cid:[a for a in aids if nodes[a]['page_id']!=g['page_ids'][page-1]] for cid,aids in available.items()}
    return {cid:aids for cid,aids in eligible.items() if aids} if eligible.get(target) else {}


def chapter_preflight(g,v,r,min_edge=48,quote_budget=128):
    available,rejections=appearances(g,min_edge); nodes={n['id']:n for n in g['nodes']}
    raw,*_=catalogue(g,r); verified=[]; blocked=Counter(); checked=0
    for anchor in raw[:quote_budget]:
        refs=cross_page_options(g,available,anchor['identity'],anchor['page'])
        if len(refs)<4: blocked['no_four_cross_page_options']+=1; continue
        doc,_,known=execute('crl',speaker(anchor['quote'],anchor['page']),g,v,r); checked+=1
        try:
            if not known: raise ValueError('speaker_unproved')
            source_evidence(g,v,r,doc,min_edge); names(g,v,anchor['quote'])
            if doc['result']['value']!=anchor['identity']: raise ValueError('speaker_identity_differs')
        except ValueError as error: blocked[str(error)]+=1; continue
        verified.append({**anchor,'program_sha256':stable(doc['program']),'execution_sha256':stable(doc)})
    all_links={}
    for f in g['facts']:
        if f['rel']=='is_char' and f['origin'] in ('H','V') and f['answer_eligible'] and not nodes[f['args'][1]]['generic']:
            all_links.setdefault(f['args'][1],set()).add(nodes[f['args'][0]]['page_id'])
    return {'chapter_id':g['chapter_id'],'split':g['split'],'snapshots':snapshots(g,v,r),'available_references':available,
            'verified_anchors':verified,'counts':{'trusted_identity_ids':len(all_links),'trusted_cross_page_ids':sum(len(p)>1 for p in all_links.values()),
            'usable_reference_ids':len(available),'verified_target_ids':len({a['identity'] for a in verified}),
            'raw_quote_anchors':len(raw),'considered_quote_anchors':min(len(raw),quote_budget),'checked_quote_programs':checked,
            'verified_quote_anchors':len(verified)},'reference_rejections':rejections,'anchor_rejections':dict(blocked),
            'anchor_budget_exhausted':len(raw)>quote_budget,'image_validation':'metadata/existence only; hashes/pixels verified during pilot',
            'distractor_fairness':'not_established; human pilot required'}


def preflight(root,out,chapters=None,min_edge=48,quote_budget=128):
    if type(quote_budget) is not int or quote_budget<1 or type(min_edge) is not int or min_edge<1: raise ValueError('Positive visual budgets required')
    root=Path(root).resolve(); inputs=[root/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    manifests=[verify_manifest(p) for p in inputs]; available=set(manifests[0]['config']['chapters'])
    chosen=sorted(set(chapters) if chapters else available)
    if not chosen or any(not set(chosen)<=set(m['config']['chapters']) for m in manifests): raise ValueError('Unknown visual chapter scope')
    out=separate(out,inputs+[root/'core']); repo=Path(__file__).resolve().parents[3]
    verify_snapshot(repo,read(repo/'configs/benchmark1000/legacy_baseline_v1.json')['files'])
    config={'version':'visual_preflight.1','chapters':chosen,'min_edge':min_edge,'quote_budget':quote_budget,
            'source_manifests':{str(p):digest(p/'manifest.json') for p in inputs},'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.visual-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);outputs={};results=[]
        for cid in chosen:
            g,v,r=world(root,cid);path=out/'chapters'/f'{cid}.json'
            if path.exists():
                wrapper=read(path);payload=wrapper['payload']
                if wrapper['config_sha256']!=stable(config) or wrapper['payload_sha256']!=stable(payload) or payload['snapshots']!=snapshots(g,v,r): raise ValueError('Stale visual checkpoint')
            else:
                payload=chapter_preflight(g,v,r,min_edge,quote_budget);publish(path,{'config_sha256':stable(config),'payload_sha256':stable(payload),'payload':payload})
            outputs[str(path.relative_to(out))]=digest(path);results.append(payload)
            print(f"{cid}: reference_ids={payload['counts']['usable_reference_ids']}, verified_targets={payload['counts']['verified_target_ids']}",flush=True)
        targets={a['identity'] for x in results for a in x['verified_anchors']}
        report={'schema':PREFLIGHT,'chapters':len(results),'counts':dict(sum((Counter(x['counts']) for x in results),Counter())),
                'unique_reference_ids':len({c for x in results for c in x['available_references']}),'unique_verified_target_ids':len(targets),
                'target_identity_ids':sorted(targets),'budget_hit_chapters':[x['chapter_id'] for x in results if x['anchor_budget_exhausted']],
                'meaning':'Identity IDs are trusted source links; no human visual-distinguishability or release claim', 'release_status':'not_approved'}
        publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
        publish(out/'manifest.json',{'schema':PREFLIGHT,'config':config,'config_sha256':stable(config),'outputs_sha256':outputs})
    return report


def private_review(items):
    sections=[]
    for item in items:
        source=item['public']['pages'][0] # public context is just the question's normal page
        path=Path(source['path']);data=base64.b64encode(path.read_bytes()).decode();mime='image/png' if path.suffix.lower()=='.png' else 'image/jpeg'
        sheet=base64.b64encode(Path(item['option_sheet']['path']).read_bytes()).decode()
        sections.append('<section><h2>'+html.escape(item['item_id'])+'</h2><p>'+html.escape(item['public']['question'])+'</p><p>Private gold: '+item['answer']['value']+'; human identity/crop/distractor review pending.</p><img style="max-width:600px" src="data:'+mime+';base64,'+data+'"><img style="max-width:640px" src="data:image/png;base64,'+sheet+'"></section>')
    return ('<!doctype html><meta charset="utf-8"><title>Visual pilot review</title><h1>Private visual-choice review</h1><p>Check identity agreement, crop quality, distinct distractors and label fairness. This page does not record approval.</p>'+''.join(sections)).encode()


def pilot(root,preflight_root,out,chapters=None,per_chapter=4,max_attempts=32,seed=42):
    if any(type(x) is not int or x<1 for x in (per_chapter,max_attempts)) or max_attempts<per_chapter or type(seed) is not int: raise ValueError('Invalid visual pilot budgets/seed')
    root=Path(root).resolve();src=Path(preflight_root).resolve();m=verify_manifest(src)
    if m['schema']!=PREFLIGHT or stable(m['config'])!=m['config_sha256'] or read(src/'config.json')!=m['config']: raise ValueError('Expected pinned visual preflight')
    chosen=sorted(set(chapters) if chapters else m['config']['chapters'])
    if not chosen or not set(chosen)<=set(m['config']['chapters']): raise ValueError('Unknown pilot chapter scope')
    out=separate(out,[src,root/'evidence',root/'core',root/'PopManga_Test']);out.mkdir(parents=True,exist_ok=True)
    import PIL
    config={'version':'visual_pilot.1','preflight_manifest_sha256':digest(src/'manifest.json'),'chapters':chosen,
            'per_chapter':per_chapter,'max_attempts':max_attempts,'seed':seed,'pillow':PIL.__version__,'min_edge':m['config']['min_edge'],
            'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    with (out/'.visual-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);items=[];outputs={};failures=[]
        for cid in chosen:
            g,v,r=world(root,cid);wrapper=read(member(src,'chapters/'+cid+'.json'));pre=wrapper['payload']
            if wrapper['payload_sha256']!=stable(pre) or wrapper['config_sha256']!=m['config_sha256'] or pre['snapshots']!=snapshots(g,v,r): raise ValueError('Preflight sources changed')
            path=out/'chapters'/f'{cid}.json'
            if path.exists():
                checkpoint=read(path);payload=checkpoint['payload']
                if checkpoint['config_sha256']!=stable(config) or checkpoint['payload_sha256']!=stable(payload) or payload['snapshots']!=snapshots(g,v,r): raise ValueError('Stale pilot checkpoint')
                if any(i['min_edge']!=config['min_edge'] or not check(g,v,r,i)['proof_valid'] for i in payload['items']): raise ValueError('Checkpoint visual proof/assets changed')
            else:
                pending=list(pre['verified_anchors']);selected=[];rejected=[];attempts=0;used=Counter(i['answer']['identity_id'] for i in items)
                while pending and len(selected)<per_chapter and attempts<max_attempts:
                    at=min(range(len(pending)),key=lambda n:(used[pending[n]['identity']],stable(pending[n])));a=pending.pop(at);attempts+=1
                    refs=cross_page_options(g,pre['available_references'],a['identity'],a['page']);rng=random.Random(stable([seed,cid,a]))
                    distractors=sorted(c for c in refs if c!=a['identity']);rng.shuffle(distractors)
                    source_page=g['page_ids'][a['page']-1]
                    same_speech={f['args'][0] for f in g['facts'] if f['rel']=='speaks_on' and f['args'][1]==source_page and f['origin'] in ('H','V') and f['answer_eligible']}
                    same_presence={f['args'][0] for f in g['facts'] if f['rel']=='present' and f['args'][1]==source_page and f['origin'] in ('H','V') and f['answer_eligible']}
                    distractors.sort(key=lambda c:0 if c in same_speech else 1 if c in same_presence else 2)
                    ids=distractors[:3];position=(seed+len(items)+len(selected))%4;ids.insert(position,a['identity']);aids=[refs[c][0] for c in ids]
                    try:
                        item=produce(g,v,r,a['quote'],a['page'],aids,out,m['config']['min_edge']);result=check(g,v,r,item)
                        if not result['proof_valid']: raise ValueError('Pilot validation: '+result.get('error','unknown'))
                    except ValueError as error:
                        if 'hash' in str(error).lower() or 'dimensions changed' in str(error).lower(): raise
                        rejected.append({'quote':a['quote'],'page':a['page'],'reason':str(error)});continue
                    selected.append(item);used[a['identity']]+=1
                payload={'chapter_id':cid,'snapshots':snapshots(g,v,r),'items':selected,'rejected':rejected,'attempts':attempts,
                         'search_truncated':bool(pending and attempts>=max_attempts)}
                publish(path,{'config_sha256':stable(config),'payload_sha256':stable(payload),'payload':payload})
            items.extend(payload['items']);failures.extend(payload['rejected']);outputs[str(path.relative_to(out))]=digest(path)
            print(f"{cid}: visual_pilot_items={len(payload['items'])}, rejected={len(payload['rejected'])}",flush=True)
        for item in items:
            assets=[item['option_sheet']['path']]+[o['reference']['crop_path'] for o in item['options']]
            for name in assets:
                path=Path(name).resolve()
                if out not in path.parents: raise ValueError('Asset outside pilot root')
                outputs[str(path.relative_to(out))]=digest(path)
                side=path.with_suffix(path.suffix+'.json')
                if side.exists():outputs[str(side.relative_to(out))]=digest(side)
        public=[{'item_id':i['item_id'],**i['public']} for i in items]
        review=[{'item_id':i['item_id'],'item_sha256':stable(i),'reviewer':'','reviewer_type':'human','decision':'flag',
                 'reason':'Pending identity, crop and distractor fairness inspection','review_version':'visual_pilot.1'} for i in items]
        report={'schema':PILOT,'items':len(items),'unique_target_ids':len({i['answer']['identity_id'] for i in items}),
                'correct_labels':dict(Counter(i['answer']['value'] for i in items)),'rejected':len(failures),
                'rejection_reasons':dict(Counter(x['reason'] for x in failures)), 'human_review':'pending; no automatic native admission',
                'release_status':'not_approved','graph_proofs':'independently_checked','question_type':'visual_quote_speaker'}
        for name,body in [('model_inputs.json',public),('scoring.json',[{'item_id':i['item_id'],'answer':i['answer']['value'],'evaluation':'exact_A_to_D'} for i in items]),('review_requests.json',review),('report.json',report)]:
            publish(out/name,body);outputs[name]=digest(out/name)
        binary_publish(out/'review.html',private_review(items));outputs['review.html']=digest(out/'review.html')
        publish(out/'manifest.json',{'schema':PILOT,'config':config,'config_sha256':stable(config),'outputs_sha256':outputs})
    return report


def verify_pilot(root,store):
    store=Path(store).resolve();m=verify_manifest(store)
    if m['schema']!=PILOT or read(store/'config.json')!=m['config'] or stable(m['config'])!=m['config_sha256']: raise ValueError('Invalid visual pilot manifest')
    required={'model_inputs.json','scoring.json','review_requests.json','report.json','review.html'}|{'chapters/'+c+'.json' for c in m['config']['chapters']}
    if not required<=set(m['outputs_sha256']): raise ValueError('Missing manifest-backed visual outputs')
    rows=[];items=[];rejections=[]
    for cid in m['config']['chapters']:
        g,v,r=world(root,cid);wrapper=read(member(store,'chapters/'+cid+'.json'));payload=wrapper['payload']
        if wrapper['config_sha256']!=m['config_sha256'] or wrapper['payload_sha256']!=stable(payload) or payload['snapshots']!=snapshots(g,v,r): raise ValueError('Visual checkpoint binding mismatch')
        rejections.extend(payload['rejected'])
        for i in payload['items']:
            if i['min_edge']!=m['config']['min_edge']: raise ValueError('Visual crop policy changed')
            if i['answer']['value']!='ABCD'[(m['config']['seed']+len(items))%4]: raise ValueError('Label scheduling changed')
            for path in [i['option_sheet']['path']]+[o['reference']['crop_path'] for o in i['options']]:
                path=Path(path).resolve()
                if store not in path.parents or str(path.relative_to(store)) not in m['outputs_sha256']: raise ValueError('Unpinned visual asset')
                if str(path.relative_to(store))!=str(Path(i['option_sheet']['path']).resolve().relative_to(store)) and str(path.with_suffix(path.suffix+'.json').relative_to(store)) not in m['outputs_sha256']: raise ValueError('Unpinned crop transform')
            rows.append({'item_id':i['item_id'],**check(g,v,r,i)});items.append(i)
    if read(store/'model_inputs.json')!=[{'item_id':i['item_id'],**i['public']} for i in items]: raise ValueError('Public input binding changed')
    if read(store/'scoring.json')!=[{'item_id':i['item_id'],'answer':i['answer']['value'],'evaluation':'exact_A_to_D'} for i in items]: raise ValueError('Scoring binding changed')
    report=read(store/'report.json')
    expected={'items':len(items),'unique_target_ids':len({i['answer']['identity_id'] for i in items}),
              'correct_labels':dict(Counter(i['answer']['value'] for i in items)),'rejected':len(rejections),
              'rejection_reasons':dict(Counter(x['reason'] for x in rejections))}
    if any(report[k]!=value for k,value in expected.items()) or report['release_status']!='not_approved': raise ValueError('Visual report counts/status changed')
    queue=read(store/'review_requests.json')
    if len(queue)!=len(items) or any(q['item_id']!=i['item_id'] or q['item_sha256']!=stable(i) or q['decision']!='flag' for q,i in zip(queue,items)): raise ValueError('Visual review queue binding changed')
    return {'verified':sum(r['proof_valid'] for r in rows),'rejected':sum(not r['proof_valid'] for r in rows),'items':rows,'release_status':'not_approved','human_review':'pending'}
