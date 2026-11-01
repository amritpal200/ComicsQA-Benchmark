"""Budgeted immutable contrast generation over already admitted branch questions."""
import copy
import fcntl
from collections import Counter
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from comics_qa.tasks.graph.gen2.aliases import validate_reviews
from . import contrast
from .admission import World,assess
from .admission_store import load as load_admitted,admitted
from .branch_relations import parse_question,compile_recipe,render
from .native import make
from .semantic import execute
from .io import read,publish,stable,digest,verify_manifest,verify_snapshot,separate,member


def approvals(seed,world,roots):
    rows=[{k:v for k,v in r.items() if k!='review_sha256'} for r in seed['admission_receipt']['checks']['alias_reviews']]
    return validate_reviews(rows,world.g,world.v,digest(roots[0]/'chapters'/(world.g['chapter_id']+'.json')),digest(roots[1]/'chapters'/(world.g['chapter_id']+'.json')))


def generate(seeds,world,pins,approved,max_pairs,max_variants,budget):
    pairs=[];trials=[];used=set();attempted=0;seen=set()
    for seed in sorted(seeds,key=lambda x:x['item_id']):
        if len(pairs)>=max_pairs or attempted>=max_variants:break
        recipe=parse_question(seed['question'])['recipe']
        saved={k:v for k,v in seed['admission_receipt'].items() if k!='run_config_sha256'}
        base=assess(seed['proposal'],world,approved[seed['item_id']],max(8,len(saved['checks']['page_removals'])))
        if not base['passed'] or base!=saved:raise ValueError('Source admission no longer reproduces')
        if seed['features']['semantic_target'] in used:continue
        variants=[]
        for branch in range(2):
            r=copy.deepcopy(recipe);r['steps'][branch]=5-r['steps'][branch]
            variants.append((r,{'path':['steps',branch],'before':recipe['steps'][branch],'after':r['steps'][branch]}))
        from .complexity import bindings
        values=bindings(seed);order={p['page_id']:p['index'] for p in seed['context']['pages']}
        start=min(order[values[f'p{b}_0']['value']] for b in (0,1))+1
        if start<=recipe['end']:
            r=copy.deepcopy(recipe);r['start']=start
            variants.append((r,{'path':['start'],'before':recipe['start'],'after':start}))
        for r,change in variants:
            if attempted>=max_variants:break
            attempted+=1
            row={'seed_id':seed['item_id'],'delta':change}
            trials.append(row);program=compile_recipe(r);doc,check,known=execute('coverage_recipe',program,world.g,world.v,world.r)
            row.update(result=doc['result'],execution_sha256=stable(doc),proof_valid=check['proof_valid'])
            if not known:row['status']='answer_unproved';continue
            if seed['answer_format']=='sequence' and len(doc['result']['display'])!=2:row['status']='non_distinct_endpoints';continue
            if seed['answer_format']=='count' and doc['result']['display']<1:row['status']='trivial_zero_gap';continue
            if doc['result']['display']==seed['answer']['value']:row['status']='unchanged_answer';continue
            proposal=make(world.g,world.v,world.r,pins,question=render(r),answer={'type':seed['answer_format'],'value':doc['result']['display'],'identity_id':None},answer_format=seed['answer_format'],structure='branch_combine',engine='coverage_recipe',program=program,execution=doc)
            receipt=assess(proposal,world,approved[seed['item_id']],budget);row['admission_receipt']=receipt
            if not receipt['passed']:row['status']='held';continue
            variant=admitted(proposal,receipt);key=stable(sorted([seed['features']['semantic_target'],variant['features']['semantic_target']]))
            if key in seen or variant['features']['semantic_target'] in used:row['status']='duplicate_or_reused_path';continue
            pair=contrast.build(seed,variant);pairs.append(pair);seen.add(key);used.update(x['features']['semantic_target'] for x in pair['members'])
            row.update(status='paired',pair_id=pair['pair_id']);break
    return {'pairs':pairs,'trials':trials,'counts':{'pairs':len(pairs),'members':2*len(pairs),'attempted':attempted},
            'budget_hit':len(pairs)<max_pairs and attempted>=max_variants,'cap_reached':len(pairs)>=max_pairs}


def summarize(results):
    return {'schema':'comics_qa.benchmark1000.contrast_report.1','counts':{k:sum(r['counts'][k] for r in results) for k in ('pairs','members','attempted')},
            'outcomes':dict(Counter(t['status'] for r in results for t in r['trials'])),'budget_hit_chapters':[r['chapter_id'] for r in results if r['budget_hit']],
            'cap_reached_chapters':[r['chapter_id'] for r in results if r['cap_reached']],
            'human_review':'deferred until post-Qwen','release_status':'not_approved','masked_inputs':'not_implemented_by_this_profile'}


def run(source,root,out,chapters=None,max_pairs=2,max_variants=8,max_ablation_pages=16):
    if any(type(x) is not int or x<1 for x in (max_pairs,max_variants,max_ablation_pages)):raise ValueError('Positive contrast budgets required')
    source=Path(source).resolve();root=Path(root).resolve();parent=verify_manifest(source);seeds=load_admitted(source)
    roots=[root/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    for p in roots:verify_manifest(p)
    chosen=sorted(set(chapters) if chapters else parent['config']['chapters'])
    if not chosen or not set(chosen)<=set(parent['config']['chapters']):raise ValueError('Unknown contrast chapter scope')
    # This version admits only the independently parsed branch profile.
    seeds=[s for s in seeds if s['chapter_id'] in chosen]
    for s in seeds:parse_question(s['question'])
    out=separate(out,[source,*roots,root/'core']);repo=Path(__file__).resolve().parents[3];baseline=repo/'configs/benchmark1000/legacy_baseline_v1.json';verify_snapshot(repo,read(baseline)['files'])
    config={'version':'one_clause_contrast.1','chapters':chosen,'source_root':str(source),'source_manifest_sha256':digest(source/'manifest.json'),
            'seed_hashes':{s['item_id']:stable(s) for s in seeds},'source_manifests_sha256':{str(p):digest(p/'manifest.json') for p in roots},
            'max_pairs_per_chapter':max_pairs,'max_variants_per_chapter':max_variants,'max_ablation_pages':max_ablation_pages,
            'legacy_baseline_sha256':digest(baseline),'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.contrast-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);outputs={};results=[]
        for cid in chosen:
            scoped=[s for s in seeds if s['chapter_id']==cid];path=out/'chapters'/f'{cid}.json'
            if scoped:
                g,v,pins=load_world(roots[0],roots[1],cid);r=load_optional(*roots,cid,pins);world=World(g,v,r)
                if r is None or r['decisions']:raise ValueError('Reviewed worlds need a separate contrast ablation profile')
                snapshots={'graph':stable(g),'visibility':stable(v),'rich':stable(r)}
                if any(s['source']['snapshots']!=snapshots for s in scoped):raise ValueError('Contrast source world changed')
            else:snapshots=None
            if path.exists():
                checkpoint=read(path);payload=checkpoint['payload']
                if checkpoint['config_sha256']!=stable(config) or checkpoint['payload_sha256']!=stable(payload) or payload['snapshots']!=snapshots:raise ValueError('Stale contrast checkpoint')
                for pair in payload['pairs']:contrast.validate_pair(pair)
            else:
                payload=generate(scoped,world,pins,{s['item_id']:approvals(s,world,roots) for s in scoped},max_pairs,max_variants,max_ablation_pages) if scoped else {'pairs':[],'trials':[],'counts':{'pairs':0,'members':0,'attempted':0},'budget_hit':False,'cap_reached':False}
                payload.update(chapter_id=cid,snapshots=snapshots)
                publish(path,{'config_sha256':stable(config),'payload_sha256':stable(payload),'payload':payload})
            results.append(payload);outputs[str(path.relative_to(out))]=digest(path)
            print(f"{cid}: pairs={payload['counts']['pairs']}, attempted={payload['counts']['attempted']}",flush=True)
        pairs=[p for r in results for p in r['pairs']];seen=set()
        for pair in pairs:
            contrast.validate_pair(pair)
            for item in pair['members']:
                task=stable([item['chapter_id'],item['source']['snapshots'],item['features']['semantic_target']])
                if task in seen:raise ValueError('Repeated contrast task across pairs')
                seen.add(task)
            name='pairs/'+stable(pair['pair_id'])+'.json';publish(out/name,pair);outputs[name]=digest(out/name)
            for role in (0,1):
                item=contrast.member(pair,role);name='candidates/'+stable(item['item_id'])+'.json';publish(out/name,item);outputs[name]=digest(out/name)
        report=summarize(results)
        publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
        publish(out/'manifest.json',{'schema':contrast.STORE,'config':config,'config_sha256':stable(config),'counts':report['counts'],'outputs_sha256':outputs})
    return report


def load(root):
    root=Path(root).resolve();m=verify_manifest(root)
    if m.get('schema')!=contrast.STORE or read(root/'config.json')!=m['config'] or stable(m['config'])!=m['config_sha256']:raise ValueError('Invalid contrast store config')
    pairs=[contrast.validate_pair(read(member(root,p))) for p in sorted(m['outputs_sha256']) if p.startswith('pairs/')]
    items=[contrast.validate_member(read(member(root,p))) for p in sorted(m['outputs_sha256']) if p.startswith('candidates/')]
    if len({p['pair_id'] for p in pairs})!=len(pairs) or len({x['item_id'] for x in items})!=len(items):raise ValueError('Duplicate contrast identity')
    expected={contrast.member(p,n)['item_id']:contrast.member(p,n) for p in pairs for n in (0,1)}
    if {x['item_id']:x for x in items}!=expected:raise ValueError('Contrast members do not match paired store')
    contrast.units(items)
    for p in pairs:
        seed=p['members'][0]
        if m['config']['seed_hashes'].get(seed['item_id'])!=stable(seed):raise ValueError('Contrast seed is not source-bound')
    checkpoints=[read(member(root,p)) for p in sorted(m['outputs_sha256']) if p.startswith('chapters/')]
    if len(checkpoints)!=len(m['config']['chapters']):raise ValueError('Missing contrast checkpoint')
    if sorted(c['payload']['chapter_id'] for c in checkpoints)!=m['config']['chapters']:raise ValueError('Contrast chapter scope mismatch')
    for c in checkpoints:
        p=c['payload']
        if p['counts']!={'pairs':len(p['pairs']),'members':2*len(p['pairs']),'attempted':len(p['trials'])}:raise ValueError('Contrast chapter totals mismatch')
        paired={t['pair_id']:t['seed_id'] for t in p['trials'] if t['status']=='paired'}
        if paired!={x['pair_id']:x['members'][0]['item_id'] for x in p['pairs']}:raise ValueError('Contrast decisions do not match pairs')
        if any(x['members'][0]['source']['snapshots']!=p['snapshots'] or x['members'][0]['chapter_id']!=p['chapter_id'] for x in p['pairs']):raise ValueError('Contrast checkpoint world mismatch')
        if c['config_sha256']!=m['config_sha256'] or c['payload_sha256']!=stable(c['payload']):raise ValueError('Invalid contrast checkpoint')
    if {p['pair_id']:p for c in checkpoints for p in c['payload']['pairs']}!={p['pair_id']:p for p in pairs}:raise ValueError('Contrast checkpoint/pair mismatch')
    report=read(root/'report.json');counts={k:sum(c['payload']['counts'][k] for c in checkpoints) for k in ('pairs','members','attempted')}
    if report!=summarize([c['payload'] for c in checkpoints]):raise ValueError('Contrast summary does not reproduce')
    if counts!=m['counts'] or counts!=report['counts'] or counts['pairs']!=len(pairs) or counts['members']!=len(items):raise ValueError('Contrast totals mismatch')
    if contrast.conflict_groups(items):raise ValueError('Contrast tasks reused across pairs')
    return items
