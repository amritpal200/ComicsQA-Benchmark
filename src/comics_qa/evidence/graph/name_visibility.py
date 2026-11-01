"""Conservative OCR alignment and exact-form name readability; stdlib only."""
from collections import defaultdict
import re
import unicodedata

from audit_ckg0 import name_kind, valid_box
from ckg_schema import stable_id

SCHEMA = 'comics_qa.name_visibility.v1'
VERSION = 'ckg2.1'
DEFAULT_POLICY = {'min_iou': 0.5, 'ambiguity_overlap': 0.5, 'min_auto_characters': 3,
                  'normalization': 'NFKC+casefold+word_tokens+apostrophe_normalization; no fuzzy or word-order changes'}


def tokens(text):
    if not isinstance(text, str):
        return []
    text = unicodedata.normalize('NFKC', text).casefold().replace('’', "'")
    # Preserve apostrophes inside words; punctuation/line breaks separate tokens.
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", text, flags=re.UNICODE)


def normalized(text):
    return ' '.join(tokens(text))


def overlap(a, b):
    if not valid_box(a) or not valid_box(b):
        return 0.0, 0.0
    inter = max(0, min(a[2],b[2])-max(a[0],b[0])) * max(0, min(a[3],b[3])-max(a[1],b[1]))
    aa, ab = (a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])
    return inter/(aa+ab-inter), inter/min(aa,ab)


def align_boxes(paddle, magi, policy):
    scores = [[overlap(a,b) for b in magi] for a in paddle]
    out = []
    for i, row in enumerate(scores):
        overlaps = [{'magi_index':j,'iou':iou,'intersection_over_smaller':small}
                    for j,(iou,small) in enumerate(row) if iou > 0]
        overlaps.sort(key=lambda x:(-x['iou'],x['magi_index']))
        match = None
        state = 'invalid_box' if not valid_box(paddle[i]) else 'no_overlap'
        if overlaps:
            best = overlaps[0]; j = best['magi_index']
            # A second substantially contained region indicates a split/merge even with low IoU.
            rivals = [k for k,(_,small) in enumerate(row) if small >= policy['ambiguity_overlap']]
            reverse = [k for k in range(len(paddle)) if scores[k][j][1] >= policy['ambiguity_overlap']]
            if len(rivals)>1 or len(reverse)>1:
                state = 'ambiguous'
            elif best['iou'] < policy['min_iou']:
                state = 'low_overlap'
            elif rivals == [j] and reverse == [i]:
                state,match = 'aligned',j
            else:
                state = 'ambiguous'
        out.append({'paddle_index':i, 'magi_index':match, 'status':state, 'overlaps':overlaps})
    return out


def alias_catalog(graph, identities):
    chapter_chars = {n['id']:n for n in graph['nodes'] if n['type']=='Character' and not n['generic']}
    series = next(n['series'] for n in graph['nodes'] if n['type']=='Chapter')
    records, owners = {}, defaultdict(set)
    for ident in identities.values():
        if ident.get('series')!=series or ident.get('kind')!='named' or name_kind(ident.get('name'))!='named':
            continue
        entries = [{'text':ident['name'],'ambiguous':False,'kind':'full_name'}, *ident.get('aliases',[])]
        for entry in entries:
            key = normalized(entry['text'])
            if not key:
                continue
            cid = ident['identity_id']; owners[key].add(cid)
            rkey = cid,entry['text']
            row = records.setdefault(rkey, {'identity_id':cid,'form':entry['text'],'normalized_form':key,
                'canonical': entry['text']==ident['name'], 'ambiguous':False, 'in_chapter':cid in chapter_chars})
            row['ambiguous'] |= bool(entry.get('ambiguous'))
    for row in records.values():
        row['ambiguous'] |= len(owners[row['normalized_form']]) != 1
        # Only forms carried by the actual graph may be approved automatically.
        node = chapter_chars.get(row['identity_id'])
        row['allowed'] = bool(node and not row['ambiguous'] and row['form'] in [node['canonical_name'], *node['aliases']])
    return sorted(records.values(),key=lambda r:(r['identity_id'],r['form']))


def find_matches(text, catalog):
    words=tokens(text); matches=[]
    for alias in catalog:
        needle=alias['normalized_form'].split()
        for start in range(len(words)-len(needle)+1):
            if words[start:start+len(needle)]==needle:
                matches.append({**alias,'span':[start,start+len(needle)]})
    for hit in matches:
        a,b=hit['span']
        # An alias of one person inside a longer name of another must not identify the first.
        hit['shadowed'] = any(other['identity_id']!=hit['identity_id'] and other['span'][0]<=a
            and other['span'][1]>=b and other['span']!=hit['span'] for other in matches)
    return matches


def source(path, digest, pointer):
    return {'file':str(path),'sha256':digest,'pointer':pointer}


def page_observations(page, graph_texts, paddle_doc, magi_doc, policy):
    """Return geometric observations, retaining unmatched regions from either OCR."""
    paddle = paddle_doc['ocr']['texts'] if paddle_doc else []
    magi = magi_doc['magi3']
    ocr = magi['ocr']; boxes, transcripts = ocr['bboxes'], ocr['ocr_texts']
    if len(boxes)!=len(transcripts) or any(not isinstance(t,str) for t in transcripts):
        raise ValueError(f"Malformed MAGI OCR arrays: {page['id']}")
    if any(type(t.get('index')) is not int or t['index']!=i for i,t in enumerate(paddle)):
        raise ValueError(f"PaddleOCR indices differ from source order: {page['id']}")
    expected = [t['box'] for t in graph_texts] if page['annotated'] else magi['texts']
    if paddle_doc:
        expected_source = 'human' if page['annotated'] else 'model:magi3'
        if paddle_doc['ocr']['boxes_source']!=expected_source or [t['box'] for t in paddle]!=expected:
            raise ValueError(f"PaddleOCR box coverage differs from graph/source: {page['id']}")
    rows=align_boxes([t['box'] for t in paddle],boxes,policy)
    used={r['magi_index'] for r in rows if r['magi_index'] is not None}
    rows += [{'paddle_index':None,'magi_index':j,'status':'magi_only','overlaps':[]} for j in range(len(boxes)) if j not in used]
    magi_ok = magi.get('_meta',{}).get('status')=='complete' and magi.get('generation',{}).get('ocr',{}).get('possibly_truncated') is False
    for row in rows:
        i,j=row['paddle_index'],row['magi_index']
        p=paddle[i] if i is not None else None
        row.update(page_id=page['id'], image_sha256=page['image_sha256'],
            text_id=graph_texts[i]['id'] if page['annotated'] and i is not None else None,
            region_id=f"{page['id']}__pocr{i:03d}" if i is not None else f"{page['id']}__mocr{j:03d}",
            paddle_text=p.get('text','') if p else '', magi_text=transcripts[j] if j is not None else '',
            paddle_box=p['box'] if p else None, magi_box=boxes[j] if j is not None else None,
            paddle_status=p.get('status') if p else None,
            paddle_ok=bool(p and paddle_doc['ocr'].get('_meta',{}).get('status')=='complete'
                and p.get('status')=='ok' and p.get('truncated') is False and tokens(p.get('text'))),
            magi_ok=bool(j is not None and magi_ok and valid_box(boxes[j]) and tokens(transcripts[j])),
            full_transcript_agreement=bool(p and j is not None and tokens(p.get('text')) and tokens(p.get('text'))==tokens(transcripts[j])))
        row['alignment_id']=stable_id('align:',{'page':page['id'],'region':row['region_id'],'magi_index':j,'policy':policy})
    return rows


def name_evidence(chapter_id, observation, catalog, sources, policy):
    left=find_matches(observation['paddle_text'],catalog);right=find_matches(observation['magi_text'],catalog)
    keys=sorted({(m['identity_id'],m['form']) for m in left+right if m['in_chapter']})
    out=[]
    for cid,form in keys:
        a=[m for m in left if (m['identity_id'],m['form'])==(cid,form)]
        b=[m for m in right if (m['identity_id'],m['form'])==(cid,form)]
        alias=(a or b)[0]; reasons=[]
        if not alias['allowed']:reasons.append('ambiguous_or_disallowed_alias')
        if (a and all(m['shadowed'] for m in a)) or (b and all(m['shadowed'] for m in b)):
            reasons.append('inside_other_identity_name')
        if sum(c.isalnum() for c in alias['normalized_form'])<policy['min_auto_characters']:
            reasons.append('short_form_requires_visual_review')
        if observation['status']!='aligned':reasons.append('alignment_'+observation['status'])
        if not a or not b:reasons.append('single_model_match')
        if not observation['paddle_ok']:reasons.append('paddle_incomplete_or_unusable')
        if not observation['magi_ok']:reasons.append('magi_incomplete_or_unusable')
        verified=not reasons
        row={'chapter_id':chapter_id,'page_id':observation['page_id'],'image_sha256':observation['image_sha256'],
            'text_id':observation['text_id'],'region_id':observation['region_id'],'alignment_id':observation['alignment_id'],
            'identity_id':cid,'form':form,'normalized_form':alias['normalized_form'],'is_canonical':alias['canonical'],
            'status':'verified' if verified else 'candidate','origin':'V' if verified else 'M',
            'verification_method':'two_model_name_span_agreement' if verified else None,
            'agreement_scope':'name_span_only','full_transcript_agreement':observation['full_transcript_agreement'],
            'reasons':reasons,'paddle_token_spans':[m['span'] for m in a], 'magi_token_spans':[m['span'] for m in b],
            'paddle_text':observation['paddle_text'],'magi_text':observation['magi_text'],
            'paddle_box':observation['paddle_box'],'magi_box':observation['magi_box'],'sources':sources,'policy_version':VERSION}
        row['evidence_id']=stable_id('namevis:',{**row,'policy':policy})
        out.append(row)
    return out


def apply_decisions(evidence, decisions, decision_source):
    by_id={e['evidence_id']:e for e in evidence}
    if len({d['evidence_id'] for d in decisions})!=len(decisions):raise ValueError('Duplicate review decision')
    for d in decisions:
        if d['evidence_id'] not in by_id:raise ValueError('Review decision targets unknown/stale evidence')
        e=by_id[d['evidence_id']]
        if d['chapter_id']!=e['chapter_id'] or d['image_sha256']!=e['image_sha256']:
            raise ValueError('Review decision has wrong chapter/image hash')
        if d['status'] not in ('verified','rejected') or any(not isinstance(d.get(k),str) or not d[k].strip() for k in ('reviewer','note')):
            raise ValueError('Review requires verdict, reviewer and note')
        if d['status']=='verified':
            if any(r in e['reasons'] for r in ('ambiguous_or_disallowed_alias','inside_other_identity_name')):
                raise ValueError('Visual review cannot override an ambiguous identity alias')
            words=tokens(d.get('transcription')); needle=e['normalized_form'].split()
            if not any(words[i:i+len(needle)]==needle for i in range(len(words)-len(needle)+1)):
                raise ValueError('Reviewed transcription must contain the exact form')
        e['automatic_status']=e['status'];e['status']=d['status']
        e['origin']='V' if d['status']=='verified' else 'M'
        e['verification_method']='individual_visual_review' if d['status']=='verified' else 'individual_visual_rejection'
        e['review']={**d,'source':decision_source}


def summarize(graph, evidence):
    by_identity=defaultdict(list)
    for row in evidence:by_identity[row['identity_id']].append(row)
    results=[]
    for node in sorted(graph['nodes'],key=lambda n:n['id']):
        if node['type']!='Character':continue
        rows=by_identity[node['id']];verified=[r for r in rows if r['status']=='verified']
        forms=sorted({r['form'] for r in verified})
        results.append({'identity_id':node['id'],'chapter_id':graph['chapter_id'],'canonical_name':node['canonical_name'],
            'generic':node['generic'],'status':'generic_excluded' if node['generic'] else 'verified' if verified else 'not_verified',
            'canonical_visible':not node['generic'] and any(r['is_canonical'] for r in verified),
            'verified_forms':forms,'verified_normalized_forms':sorted({r['normalized_form'] for r in verified}),
            'verified_evidence_ids':[r['evidence_id'] for r in verified],
            'candidate_evidence_ids':[r['evidence_id'] for r in rows if r['status']=='candidate'],
            'rejected_evidence_ids':[r['evidence_id'] for r in rows if r['status']=='rejected'],
            'visible_on_pages':sorted({r['page_id'] for r in verified})})
    return results


def form_is_visible(chapter, identity_id, rendered_form):
    """GEN-1 must call with the actual name string it plans to render."""
    return any(r['identity_id']==identity_id and not r['generic'] and normalized(rendered_form) in r['verified_normalized_forms']
               for r in chapter['visibility'])
