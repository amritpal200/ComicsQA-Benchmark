"""Private, proof-scoped Qwen packs above immutable native/legacy/sentence artifacts."""
import copy
import fcntl
from collections import Counter
from pathlib import Path
from .io import stable,read,publish,digest,verify_manifest,verify_snapshot,separate,member,encoded
from .native import execution_evidence
from . import sentence_plans as sentences
from . import qwen_language as language
from .assets import render,box_pixels,image_library

SCHEMA='comics_qa.benchmark1000.qwen_pack.2'
STORE='comics_qa.benchmark1000.qwen_packs.2'
VERSION='qwen_packs.2'


def seed(record,mode):
    if mode=='synthesis':return record['source']
    if record.get('schema')=='comics_qa.benchmark1000.contrast_member.1':return record['pair_certificate']['members'][record['pair_role']]
    return record


def task(item):
    base=item.get('legacy',item)
    return {'engine':'crl' if 'legacy' in item else item['proof_engine'],'program':base['program'],'execution':base['execution'],'context':base['context']}


def sources(root,mode):
    if mode=='synthesis':return sentences.load(root)
    from .store import load
    return load(root)


def hydrate(item,g,v,r,extra_claims=()):
    """Eligible facts only, with explicit external provenance and verified OCR."""
    t=task(item);e=execution_evidence(t['engine'],t['execution'],g,r)
    used=set(e['fact_ids']);cov=set(e['certificate_ids'])
    for c in extra_claims:used.update(c['evidence']['fact_ids']);cov.update(c['evidence']['certificate_ids'])
    lookup={f['fact_id']:f for f in g['facts']};lookup.update({f['id']:f for f in r['facts']} if r else {})
    pending=list(used);external=set()
    while pending:
        f=lookup.get(pending.pop())
        if f is None:raise ValueError('Unresolved proof fact')
        if f['origin'] not in ('H','V') or not f['answer_eligible']:raise ValueError('Unadmitted pack fact')
        for parent in f.get('premises',[]):
            if parent not in lookup:external.add(parent)
            elif parent not in used:used.add(parent);pending.append(parent)
    facts=[copy.deepcopy(lookup[f]) for f in sorted(used)]
    ns={n['id']:n for n in g['nodes']};refs={arg for f in facts for arg in f['args'] if arg in ns}
    refs.update(ns[x]['page_id'] for x in list(refs) if 'page_id' in ns[x])
    readable={x['identity_id']:x['verified_forms'] for x in v['visibility']};nodes=[]
    for ref in sorted(refs):
        n=ns[ref];safe={k:copy.deepcopy(n[k]) for k in ('id','type','origin','page_id','box','width','height','image_sha256','generic','scope','outside_image','geometry_review_required','touches_image_edge') if k in n}
        if n['type']=='Character':safe['readable_name_forms']=readable.get(ref,[])
        nodes.append(safe)
    certs={c['coverage_id']:c for c in g['coverage']};certs.update({c['id']:c for c in r['coverage']} if r else {})
    if cov-certs.keys():raise ValueError('Unresolved proof coverage')
    text_ids={n['id'] for n in nodes if n['type']=='Text'}
    transcripts=[copy.deepcopy(t) for t in (r['transcripts'] if r else []) if t['text_id'] in text_ids and t['status']=='verified' and t['quote_eligible']]
    return {'facts':facts,'nodes':nodes,'coverage':[certs[c] for c in sorted(cov)],'verified_transcripts':transcripts,
            'external_provenance_references':sorted(external),'external_reference_role':'provenance only; not additional admitted facts'}


def crop_specs(evidence,g,scope):
    if scope not in ('full-page','proof-union'):raise ValueError('Unknown evidence crop scope')
    ns={n['id']:n for n in g['nodes']};by_page={}
    for n in evidence['nodes']:
        if n['type'] not in ('Text','Appearance'):continue
        raw=ns[n['id']]
        if scope=='proof-union' and (raw.get('geometry_review_required') or raw.get('outside_image')):raise ValueError('Evidence geometry requires review')
        p=ns[raw['page_id']];box=[0,0,p['width'],p['height']] if scope=='full-page' else box_pixels(raw['box'],p['width'],p['height'])
        by_page.setdefault(p['id'],[]).append(box)
    result=[]
    for pid in g['page_ids']:
        if pid not in by_page:continue
        p=ns[pid];bs=by_page[pid];box=[min(b[0] for b in bs),min(b[1] for b in bs),max(b[2] for b in bs),max(b[3] for b in bs)]
        result.append({'page_id':pid,'page_index':g['page_ids'].index(pid)+1,'source_path':p['image_path'],'source_sha256':p['image_sha256'],'box':box})
    return result


def crops(evidence,g,out,scope):
    ns={n['id']:n for n in g['nodes']};result=[]
    for spec in crop_specs(evidence,g,scope):
        p=ns[spec['page_id']];box=spec['box'];path=Path(out)/'assets'/(stable([p['image_sha256'],box,VERSION])+'.png')
        Image,_=image_library()
        with Image.open(p['image_path']) as image:
            if image.size!=(p['width'],p['height']):raise ValueError('Page dimensions changed')
        transform=render(p['image_path'],p['image_sha256'],[box],path,'crop')
        result.append({**spec,'path':str(path.resolve()),'sha256':transform['image_sha256'],'size':transform['output_size'],'transform':transform})
    if not result:raise ValueError('Synthesis needs actual evidence crops')
    return result


def dependencies(t):
    def refs(x):
        if isinstance(x,dict):return ({x['var']} if 'var' in x else set().union(*(refs(v) for v in x.values())))
        if isinstance(x,list):return set().union(*(refs(v) for v in x))
        return set()
    if t['engine'] in ('recipe','coverage_recipe'):
        from .recipe_engine import result
        values={x['name']:result(x) for x in t['execution']['stages']};names={b['name'] for b in t['program']['let']}
        return [{'node':b['name'],'expression':b['value'],'depends_on':sorted(refs(b['value'])&names),'result':values.get(b['name'])} for b in t['program']['let']]+[
            {'node':'__result__','expression':t['program']['in'],'depends_on':sorted(refs(t['program']['in'])&names),'result':t['execution']['result']}]
    if t['engine']=='crl':return [{k:x[k] for k in ('nid','op','children','type','value','status','exact','facts') if k in x} for x in t['execution']['proof']['steps']]
    return [{'node':i,'engine':x['engine'],'result':x['execution']['result']} for i,x in enumerate(t['execution'].get('stages',[]))]


def model_context(p):
    target=p['target']
    if p['mode']=='synthesis':
        target={**target,'claims':{group:[{k:c[k] for k in ('id','spec','text','verification','evidence')} for c in rows] for group,rows in target['claims'].items()}}
    e=p['evidence']
    facts=[{k:f[k] for k in ('fact_id','id','rel','args','origin','rule_id','premises','page_ids','page_id','coverage_refs','answer_eligible') if k in f} for f in e['facts']]
    coverage=[{k:c[k] for k in ('coverage_id','id','page_id','family','status','basis','scope') if k in c} for c in e['coverage']]
    transcripts=[{k:t[k] for k in ('id','text_id','page_id','consensus','origin','status','verification') if k in t} for t in e['verified_transcripts']]
    return {'template_question':p['template_question'],'controlled_question_example':p['controlled_question_example'],'target':target,
            'page_order':[{'page_id':x['page_id'],'index':x['index']} for x in p['page_order']],
            'dependency_order':p['dependency_order'],'evidence':{'facts':facts,'nodes':e['nodes'],'coverage':coverage,'verified_transcripts':transcripts},'boundaries':p['boundaries']}


def make(record,mode,g,v,r,out,max_bytes=1000000,max_images=16,crop_scope='full-page'):
    s=seed(record,mode);t=task(s)
    if mode=='synthesis':sentences.check(record,g,v,r)
    extra=[c for rows in record['claims'].values() for c in rows] if mode=='synthesis' else []
    evidence=hydrate(s,g,v,r,extra);assets=crops(evidence,g,out,crop_scope) if mode=='synthesis' else []
    if len(assets)>max_images:raise ValueError('Image budget exceeded; no evidence truncation')
    dependency=dependencies(t)
    alternatives=language.alternatives(s['question'],mode=='synthesis')
    body={'version':VERSION,'mode':mode,'source_record':copy.deepcopy(record),'source_sha256':stable(record),'chapter_id':s['chapter_id'],'split':s['split'],
          'page_order':copy.deepcopy(t['context']['pages']),'dependency_order':copy.deepcopy(dependency),'evidence':evidence,'evidence_crops':assets,'crop_scope':crop_scope,
          'template_question':record['question'],'controlled_question_example':alternatives,
          'target':{'engine':t['engine'],'program':t['program'],'answer':s['answer']} if mode=='paraphrase' else {'claims':record['claims'],'claim_order':record['claim_order'],'short_answer':record['short_answer']},
          'boundaries':['Preserve every clause, reference, role, search scope and strict navigation','All facts concern the specified searches, not chapter-final events',
                        'Only H/V facts and verified OCR are answer evidence; no invented motives or causality','Return JSON only; do not return a self-certified program or review decision',
                        'Question outside the independent grammar or unsupported prose is held','Page order and dependency order are distinct'],
          'status':'prepared_not_inferred','human_review':'pending','release':'not_approved'}
    if len(encoded(model_context(body)).encode())>max_bytes:raise ValueError('Pack byte budget exceeded; no silent truncation')
    return validate({'schema':SCHEMA,'pack_id':'b1000qwenpack:'+stable(body),**body})


def validate(p):
    if p.get('schema')!=SCHEMA or p['pack_id']!='b1000qwenpack:'+stable({k:v for k,v in p.items() if k not in ('schema','pack_id')}):raise ValueError('Invalid Qwen pack identity')
    if p['source_sha256']!=stable(p['source_record']) or p['mode'] not in ('paraphrase','synthesis') or p['status']!='prepared_not_inferred' or p['human_review']!='pending' or p['release']!='not_approved':raise ValueError('Invalid pack source/status')
    s=seed(p['source_record'],p['mode']);t=task(s)
    if p['page_order']!=t['context']['pages'] or p['chapter_id']!=s['chapter_id'] or p['split']!=s['split'] or p['template_question']!=p['source_record']['question']:raise ValueError('Pack changed its task scope')
    if p['mode']=='paraphrase':
        from .contract import validate as source_valid
        source_valid(p['source_record'])
        if p['evidence_crops'] or p['target']!={'engine':t['engine'],'program':t['program'],'answer':s['answer']}:raise ValueError('Paraphrase must be text-only with fixed semantics')
    else:
        sentences.validate(p['source_record'])
        if not p['evidence_crops'] or p['target']!={'claims':p['source_record']['claims'],'claim_order':p['source_record']['claim_order'],'short_answer':p['source_record']['short_answer']}:raise ValueError('Invalid synthesis evidence/claims')
    return p


def check(p,g,v,r):
    validate(p);s=seed(p['source_record'],p['mode']);extra=[c for rows in p['source_record']['claims'].values() for c in rows] if p['mode']=='synthesis' else []
    if p['dependency_order']!=dependencies(task(s)):raise ValueError('Qwen dependency graph mismatch')
    if p['mode']=='paraphrase':
        if 'legacy' in s:
            from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
            t=task(s);rich=r if t['execution'].get('rich_evidence_sha256') else None
            if not ProofChecker(g,v,rich=rich).check(t['execution'],t['program'])['accepted_for_generation']:raise ValueError('Qwen source proof failed')
        else:
            from .native import check_answer
            if not check_answer(s['proposal'],g,v,r)['answer_supported']:raise ValueError('Qwen source proof failed')
    if p['evidence']!=hydrate(s,g,v,r,extra):raise ValueError('Qwen evidence hydration mismatch')
    if p['mode']=='synthesis':sentences.check(p['source_record'],g,v,r)
    from .assets import image_library
    expected_specs=crop_specs(p['evidence'],g,p['crop_scope']) if p['mode']=='synthesis' else []
    actual_specs=[{k:a[k] for k in ('page_id','page_index','source_path','source_sha256','box')} for a in p['evidence_crops']]
    if actual_specs!=expected_specs:raise ValueError('Missing or altered required evidence crops')
    for asset in p['evidence_crops']:
        if digest(asset['path'])!=asset['sha256'] or digest(asset['source_path'])!=asset['source_sha256']:raise ValueError('Qwen image changed')
        Image,_=image_library()
        with Image.open(asset['source_path']) as image:expected=image.convert('RGB').crop(tuple(asset['box']))
        with Image.open(asset['path']) as image:
            if image.convert('RGB').tobytes()!=expected.tobytes() or image.size!=expected.size:raise ValueError('Qwen crop is not exact')
    return {'pack_id':p['pack_id'],'pack_sha256':stable(p),'verified':True,'status':'pack_verified_not_inferred'}


def run(source,bench_root,out,mode='paraphrase',chapters=None,max_bytes=1000000,max_images=16,crop_scope='full-page'):
    if mode not in ('paraphrase','synthesis') or crop_scope not in ('full-page','proof-union') or type(max_bytes) is not int or max_bytes<1 or type(max_images) is not int or max_images<1:raise ValueError('Invalid Qwen preparation settings')
    source=Path(source).resolve();root=Path(bench_root).resolve();parent=verify_manifest(source);records=sources(source,mode)
    declared=set(parent['config'].get('chapters') or [r['chapter_id'] for r in records]);chosen=sorted(set(chapters) if chapters else declared)
    if not chosen or not set(chosen)<=declared:raise ValueError('Unknown Qwen chapter scope')
    records=[r for r in records if r['chapter_id'] in chosen];roots=[root/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    out=separate(out,[source,*roots,root/'core']);repo=Path(__file__).resolve().parents[3];baseline=repo/'configs/benchmark1000/legacy_baseline_v1.json';verify_snapshot(repo,read(baseline)['files'])
    for p in roots:verify_manifest(p)
    config={'version':VERSION,'mode':mode,'chapters':chosen,'source_root':str(source),'source_manifest_sha256':digest(source/'manifest.json'),
            'record_hashes':{(r.get('plan_id') or r['item_id']):stable(r) for r in records},'source_manifests_sha256':{str(p):digest(p/'manifest.json') for p in roots},
            'max_pack_bytes':max_bytes,'max_images':max_images,'crop_scope':crop_scope,'legacy_baseline_sha256':digest(baseline),'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    from .verification import revalidate
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.qwen-pack-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);outputs={};decisions=[]
        for cid in chosen:
            scoped=[x for x in records if x['chapter_id']==cid]
            if not scoped:continue
            g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins)
            if mode=='paraphrase':
                replay=revalidate(scoped,root)
                if replay['rejected']:raise ValueError('Qwen source proof replay failed')
            for record in scoped:
                rid=record.get('plan_id') or record['item_id'];path=out/'checks'/(stable(rid)+'.json')
                if path.exists():
                    row=read(path)
                    if row['config_sha256']!=stable(config) or row['source_sha256']!=stable(record):raise ValueError('Stale Qwen preparation checkpoint')
                    if row['status']=='prepared':check(read(member(out,row['pack_path'])),g,v,r)
                else:
                    try:
                        p=make(record,mode,g,v,r,out,max_bytes,max_images,crop_scope);check(p,g,v,r);name='packs/'+stable(p['pack_id'])+'.json';publish(out/name,p)
                        row={'status':'prepared','pack_path':name,'pack_id':p['pack_id']}
                    except ValueError as e:row={'status':'held','reason':str(e)}
                    row.update(source_id=rid,source_sha256=stable(record),config_sha256=stable(config));publish(path,row)
                decisions.append(row);outputs[str(path.relative_to(out))]=digest(path)
                if row['status']=='prepared':outputs[row['pack_path']]=digest(out/row['pack_path'])
            print(f'{cid}: packs checked',flush=True)
        for p in (out/'assets').glob('*') if (out/'assets').exists() else []:outputs[str(p.relative_to(out))]=digest(p)
        report={'schema':'comics_qa.benchmark1000.qwen_pack_report.2','counts':dict(Counter(d['status'] for d in decisions)),
                'held_reasons':dict(Counter(d['reason'] for d in decisions if d['status']=='held')),'records':len(records),'mode':mode,'status':'prepared_not_inferred','human_review':'pending','release':'not_approved'}
        publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
        publish(out/'manifest.json',{'schema':STORE,'config':config,'config_sha256':stable(config),'outputs_sha256':outputs})
    return report


def load(root):
    root=Path(root).resolve();m=verify_manifest(root)
    if m.get('schema')!=STORE or read(root/'config.json')!=m['config'] or stable(m['config'])!=m['config_sha256']:raise ValueError('Invalid Qwen pack store')
    ps=[validate(read(member(root,p))) for p in sorted(m['outputs_sha256']) if p.startswith('packs/')]
    rows=[read(member(root,p)) for p in sorted(m['outputs_sha256']) if p.startswith('checks/')]
    if {d['source_id']:d['source_sha256'] for d in rows}!=m['config']['record_hashes'] or any(d['config_sha256']!=m['config_sha256'] for d in rows):raise ValueError('Missing Qwen source/checkpoint')
    if {d['pack_id'] for d in rows if d['status']=='prepared'}!={p['pack_id'] for p in ps} or len({p['pack_id'] for p in ps})!=len(ps):raise ValueError('Qwen pack totals/bindings mismatch')
    for p in ps:
        record=p['source_record'];rid=record.get('plan_id') or record['item_id']
        if m['config']['record_hashes'][rid]!=stable(record) or p['mode']!=m['config']['mode']:raise ValueError('Qwen source record changed')
    report=read(root/'report.json')
    if report['counts']!=dict(Counter(d['status'] for d in rows)) or report['records']!=len(rows):raise ValueError('Qwen report mismatch')
    return ps


def verify(root,bench_root):
    ps=load(root);root=Path(root);bench_root=Path(bench_root);worlds={};rows=[]
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    roots=[bench_root/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    for p in ps:
        cid=p['chapter_id']
        if cid not in worlds:
            g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins);worlds[cid]=(g,v,r)
        rows.append(check(p,*worlds[cid]))
    return {'schema':'comics_qa.benchmark1000.qwen_pack_check.2','store_manifest_sha256':digest(root/'manifest.json'),
            'verified':len(rows),'held_sources':read(root/'report.json')['counts'].get('held',0),'items':rows,
            'status':'packs_checked_not_inferred','human_review':'pending','release':'not_approved'}
