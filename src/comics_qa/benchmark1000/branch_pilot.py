"""Capped two-branch search with independently checked necessity before retention."""
import fcntl
import re
from collections import Counter, defaultdict, deque
from itertools import combinations, product, islice
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from .branch_relations import VERSION, KINDS, FORMATS, compile_recipe, render, parse_question, resolved, labels
from .coverage_windows import Probes, ProbeBudget, window_options
from .family_pilot import catalogue
from .native_wording import speaker
from .native import make
from .native_store import write
from .semantic import execute
from .admission import same_answer
from .io import stable, read, publish, digest, separate, verify_manifest, verify_snapshot


class DependencyBudget(Exception): pass


class CheckedQueries:
    def __init__(self,g,v,r,limit):
        self.g,self.v,self.r=g,v,r;self.limit=limit;self.used=0;self.hits=0;self.cache={};self.records=[];self.outcomes=Counter();self.exhausted=False

    def query(self,program):
        key=stable(program)
        if key in self.cache:self.hits+=1;return self.cache[key]
        if self.used>=self.limit:self.exhausted=True;raise DependencyBudget()
        self.used+=1;doc,check,known=execute('coverage_recipe',program,self.g,self.v,self.r)
        row={'program_sha256':key,'execution_sha256':stable(doc),'proof_valid':check['proof_valid'],'answer_supported':bool(known),'result':doc['result']}
        self.cache[key]=(doc,row);return doc,row

    def dependencies(self,r,main):
        record={'recipe':r,'main':main,'interventions':[],'passed':False};self.records.append(record)
        try:
            for label in labels(r):
                _,row=self.query(compile_recipe(r,label));value=row['result']
                outcome=('redundant' if same_answer(value,main['result']) else 'necessary' if value['status']=='EMPTY' or value['status']=='OK' and row['answer_supported'] else 'unproved')
                record['interventions'].append({'label':label,'outcome':outcome,**row})
                if outcome!='necessary':record['reason']=outcome+'_dependency';break
            else:record['passed']=True;record['reason']='passed'
        except DependencyBudget:
            record['reason']='dependency_budget_exhausted';self.outcomes[record['reason']]+=1;raise
        finally:record['unchecked_interventions']=len(labels(r))-len(record['interventions'])
        self.outcomes[record['reason']]+=1;return record

    def report(self):
        return {'execution_limit':self.limit,'new_executions':self.used,'cache_hits':self.hits,'budget_exhausted':self.exhausted,
                'outcomes':dict(self.outcomes),'records':self.records,'authority':'preselection only; full native admission still required'}


def references(anchors,budget):
    by_id=defaultdict(list)
    for a in anchors:by_id[a['identity']].append(a)
    streams=deque(iter(product(by_id[a],by_id[b])) for a,b in islice(combinations(sorted(by_id),2),budget))
    n=0
    while streams and n<budget:
        stream=streams.popleft()
        try:refs=next(stream)
        except StopIteration:continue
        yield list(refs);n+=1;streams.append(stream)


def recipes(refs,total,window,min_window,max_shift,max_steps):
    for w in window_options(refs,total,min_window,window,max_shift,'speaking_gap'):
        for steps in sorted(product(range(2,max_steps+1),repeat=2),key=lambda p:(sum(p),p)):
            for kind in KINDS:
                yield {'kind':kind,'references':[{k:x[k] for k in ('quote','page')} for x in refs],
                       'start':w['start'],'end':w['end'],'steps':list(steps),'profile':VERSION}


def chapter(g,v,rich,pins,per_family=3,search_budget=1000,window=10,min_window=4,max_shift=20,probe_budget=192,dependency_budget=128,max_steps=3):
    probes=Probes(g,v,rich,probe_budget,search_budget);raw,speech,*_=catalogue(g,rich);anchors=[];actors={};
    for a in raw[:search_budget]:
        actor=probes.actor(speaker(a['quote'],a['page']),'_anchors')
        if actor and actor['id']==a['identity']:anchors.append(a);actors[stable([a['quote'],a['page']])]=actor
    trials=deque((refs,iter(recipes(refs,len(g['page_ids']),window,min_window,max_shift,max_steps))) for refs in references(anchors,search_budget))
    queries=CheckedQueries(g,v,rich,dependency_budget);rejected=Counter();items=[];rows=[];counts=Counter();seen=set();tried=0
    while trials and tried<search_budget and any(counts[k]<per_family for k in KINDS):
        refs,stream=trials.popleft()
        try:r=next(stream)
        except StopIteration:continue
        trials.append((refs,stream))
        if counts[r['kind']]>=per_family:continue
        tried+=1;paths=[]
        for ref,steps in zip(refs,r['steps']):
            numbers=sorted(p for p in speech[ref['identity']] if r['start']<=p<=r['end']);paths.append(numbers[:steps])
        if any(len(path)<steps for path,steps in zip(paths,r['steps'])):rejected['no_known_topology']+=1;continue
        expected_ends=[p[-1] for p in paths]
        if expected_ends[0]==expected_ends[1]:rejected['coincident_branch_targets']+=1;continue
        predicted=sorted(expected_ends) if r['kind']=='branch_chain_pages' else abs(expected_ends[0]-expected_ends[1])-1
        if r['kind']=='branch_chain_gap' and (predicted<1 or re.search(r'(?<!\w)'+str(predicted)+r'(?!\w)',render(r))):rejected['zero_gap_or_numeric_overlap']+=1;continue
        try:
            verified=[]
            for ref,steps in zip(refs,r['steps']):
                actor=actors[stable([ref['quote'],ref['page']])];page=r['start']-1;path=[]
                for n in range(steps):
                    page=probes.first(actor,page,r['end'],'branch_discovery')
                    if page is None:break
                    path.append(page)
                verified.append(path)
            if any(len(p)<s for p,s in zip(verified,r['steps'])):rejected['unproved_required_probe']+=1;continue
        except ProbeBudget:rejected['predicate_budget_exhausted']+=1;break
        program=compile_recipe(r)
        try:
            doc,main=queries.query(program)
            if not main['answer_supported']:rejected['main_answer_unproved']+=1;continue
            if doc['result']['display']!=predicted:raise ValueError('Branch discovery/program disagreement')
            stub={'chapter_id':g['chapter_id'],'program':program,'execution':doc,'proof_engine':'coverage_recipe'};pathkey=stable(resolved(stub,parse_question(render(r))))
            if pathkey in seen:rejected['duplicate_resolved_path']+=1;continue
            dependency=queries.dependencies(r,main)
            if not dependency['passed']:rejected[dependency['reason']]+=1;continue
        except DependencyBudget:rejected['dependency_budget_exhausted']+=1;break
        # The final emitted recipe is freshly executed, apart from discovery caches.
        doc,checked,known=execute('coverage_recipe',program,g,v,rich)
        if not known:raise ValueError('Retained branch stopped being supported')
        fmt=FORMATS[r['kind']];answer={'type':fmt,'value':doc['result']['display'],'identity_id':None}
        item=make(g,v,rich,pins,question=render(r),answer=answer,answer_format=fmt,structure='branch_combine',
                  engine='coverage_recipe',program=program,execution=doc,complexity={'meaningful_hops':None,'branch_count':None,'necessary_pages':[],'profile_version':VERSION})
        items.append(item);seen.add(pathkey);counts[r['kind']]+=1
        rows.append({'kind':r['kind'],'recipe':r,'proof_valid':checked['proof_valid'],'answer_proved':True,'result':doc['result'],
                     'dependency_discovery':dependency,'native_item_id':item['item_id']})
    return {'chapter_id':g['chapter_id'],'snapshots':{'graph':stable(g),'visibility':stable(v),'rich':stable(rich)},
            'counts':{'executed':len(rows),'answer_proved':len(rows),'proposals':len(items)},'executions':rows,'proposals':items,
            'search':{'recipes_considered':tried,'search_budget_hit':bool(trials and tried>=search_budget),'source_anchor_budget_hit':len(raw)>search_budget,
                      'anchor_count':len(anchors),'distinct_anchor_identities':len({a['identity'] for a in anchors}),'rejections':dict(rejected),'exhaustive':False},
            'discovery_diagnostics':{'predicates':probes.report(),'dependencies':queries.report()}}


def run(root,out,chapters=None,per_family=3,search_budget=1000,window=10,min_window=4,max_shift=20,probe_budget=192,dependency_budget=128,max_steps=3):
    if any(type(x) is not int or x<1 for x in (per_family,search_budget,window,min_window,probe_budget,dependency_budget)) or not 4<=min_window<=window or type(max_shift) is not int or max_shift<0 or type(max_steps) is not int or max_steps not in (2,3):raise ValueError('Invalid branch pilot budgets')
    root=Path(root).resolve();roots=[root/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')];parents=[verify_manifest(p) for p in roots]
    chosen=sorted(set(chapters) if chapters else parents[0]['config']['chapters'])
    if not chosen or any(not set(chosen)<=set(m['config']['chapters']) for m in parents):raise ValueError('Invalid branch chapter scope')
    out=separate(out,roots+[root/'core']);repo=Path(__file__).resolve().parents[3];baseline=repo/'configs/benchmark1000/legacy_baseline_v1.json';verify_snapshot(repo,read(baseline)['files'])
    config={'version':VERSION,'chapters':chosen,'per_family':per_family,'search_budget':search_budget,'window':window,'min_window':min_window,
            'max_shift':max_shift,'probe_budget':probe_budget,'dependency_budget':dependency_budget,'max_steps':max_steps,
            'source_manifests_sha256':{str(p):digest(p/'manifest.json') for p in roots},'legacy_baseline_sha256':digest(baseline),
            'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.branch-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);outputs={};results=[];items=[]
        for cid in chosen:
            g,v,pins=load_world(roots[0],roots[1],cid);rich=load_optional(*roots,cid,pins)
            if rich is None or rich['decisions']:raise ValueError('Reviewed rich worlds need a separate ablation profile')
            path=out/'chapters'/f'{cid}.json'
            if path.exists():
                w=read(path);payload=w['payload']
                if w['config_sha256']!=stable(config) or w['payload_sha256']!=stable(payload) or payload['snapshots']!={'graph':stable(g),'visibility':stable(v),'rich':stable(rich)}:raise ValueError('Stale branch checkpoint')
                for i in payload['proposals']:
                    from .native import check_answer
                    if not check_answer(i,g,v,rich)['answer_supported']:raise ValueError('Cached branch proof changed')
            else:
                payload=chapter(g,v,rich,pins,per_family,search_budget,window,min_window,max_shift,probe_budget,dependency_budget,max_steps)
                publish(path,{'config_sha256':stable(config),'payload_sha256':stable(payload),'payload':payload})
            outputs[str(path.relative_to(out))]=digest(path);results.append(payload);items.extend(payload['proposals'])
            print(f"{cid}: branches={payload['counts']['proposals']}, dependency_queries={payload['discovery_diagnostics']['dependencies']['new_executions']}",flush=True)
        write(items,out/'native_store',{'version':VERSION,'parent_config_sha256':stable(config)},protected=roots);outputs['native_store/manifest.json']=digest(out/'native_store/manifest.json')
        report={'schema':'comics_qa.benchmark1000.branch_report.1','counts':{k:sum(r['counts'][k] for r in results) for k in ('executed','answer_proved','proposals')},
                'families':dict(Counter(r['kind'] for x in results for r in x['executions'])),
                'search_rejections':dict(sum((Counter(r['search']['rejections']) for r in results),Counter())),
                'dependency_executions':sum(r['discovery_diagnostics']['dependencies']['new_executions'] for r in results),
                'dependency_budget_hit_chapters':[r['chapter_id'] for r in results if r['discovery_diagnostics']['dependencies']['budget_exhausted']],
                'search_budget_hit_chapters':[r['chapter_id'] for r in results if r['search']['search_budget_hit']],
                'release_status':'not_approved','human_review':'deferred until post-Qwen final stage','long_relational':'only measured after full native admission'}
        publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
        publish(out/'manifest.json',{'schema':'comics_qa.benchmark1000.family_artifacts.1','config':config,'config_sha256':stable(config),'outputs_sha256':outputs})
    return report
