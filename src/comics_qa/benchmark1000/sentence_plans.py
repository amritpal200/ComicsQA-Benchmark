"""Private source-bound sentence plans; not admitted sentence candidates or Qwen output."""
import copy
import fcntl
from collections import Counter
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from . import claim_programs as cp
from .admission_store import load as load_admitted,validate as validate_source
from .io import stable,read,publish,digest,separate,verify_manifest,verify_snapshot,member

SCHEMA='comics_qa.benchmark1000.sentence_plan.1'
STORE='comics_qa.benchmark1000.sentence_plan_store.1'
STATES={'inference':'not_run','sentence_admission':'pending','human':'pending','release':'pending'}
RUBRIC={'required':'all three final-role/summary claims','optional':'checked intermediate steps and complementary summary',
        'forbidden':'verified-false near misses only; nonexhaustive','extra_assertions':'independently check supported signatures; unparsed/unknown stays held',
        'style':'not scored','sentence_profile':'controlled_claim_sentences.1'}
FIELDS={'schema','plan_id','version','qa_class','source','chapter_id','split','question','short_answer','short_answer_format',
        'reference_answer','claims','claim_order','page_order','verification','rubric','unique_query_count'}



def question(seed):return seed['question']+" In your answer, state each speaker's final speaking page and the result."


def make(seed,g,v,r):
    checker=cp.Checker(seed,g,v,r);specs=cp.expected(seed);cache={};claims={}
    for group,values in specs.items():
        claims[group]=[cp.record(seed,s,g,v,r,cache) for s in values]
        wanted='contradicted' if group=='forbidden' else 'supported'
        if any(checker.check(c)!=wanted for c in claims[group]):raise ValueError('Sentence plan has unresolved or incorrectly classified claims')
    body={'version':cp.VERSION,'qa_class':'claim_backed_sentence_plan','source':copy.deepcopy(seed),'chapter_id':seed['chapter_id'],'split':seed['split'],
          'question':question(seed),'short_answer':copy.deepcopy(seed['answer']),'short_answer_format':seed['answer_format'],
          'reference_answer':' '.join(c['text'] for c in claims['required']),'claims':claims,'claim_order':cp.ordering(seed,specs),
          'page_order':copy.deepcopy(seed['context']['pages']),'verification':copy.deepcopy(STATES),
          'rubric':copy.deepcopy(RUBRIC),'unique_query_count':len(cache)}
    return validate({'schema':SCHEMA,'plan_id':'b1000sentenceplan:'+stable(body),**body})


def validate(p):
    if set(p)!=FIELDS or p.get('schema')!=SCHEMA or p.get('plan_id')!='b1000sentenceplan:'+stable({k:v for k,v in p.items() if k not in ('schema','plan_id')}):raise ValueError('Invalid sentence plan identity')
    seed=validate_source(p['source']);specs=cp.expected(seed)
    if p['version']!=cp.VERSION or p['qa_class']!='claim_backed_sentence_plan' or p['verification']!=STATES or p['rubric']!=RUBRIC:raise ValueError('Sentence plan cannot grant inference/admission/review/release')
    if p['question']!=question(seed) or p['short_answer']!=seed['answer'] or p['short_answer_format']!=seed['answer_format'] or p['page_order']!=seed['context']['pages'] or p['chapter_id']!=seed['chapter_id'] or p['split']!=seed['split']:raise ValueError('Changed sentence source/answer/question scope')
    if set(p['claims'])!={'required','optional','forbidden'}:raise ValueError('Incomplete sentence claim groups')
    for group,values in specs.items():
        rows=p['claims'][group]
        if [c['spec'] for c in rows]!=values:raise ValueError('Claim requirements/near misses were changed')
        for c in rows:
            if c['id']!=cp.identifier(seed,c['spec']) or c['text']!=cp.render(c['spec']) or c['execution_sha256']!=stable(c['execution']):raise ValueError('Claim identity/text/proof binding mismatch')
            if c['verification']!=('contradicted' if group=='forbidden' else 'supported'):raise ValueError('Unproved sentence-plan claim')
    if p['reference_answer']!=' '.join(c['text'] for c in p['claims']['required']) or p['claim_order']!=cp.ordering(seed,specs):raise ValueError('Sentence reference/order mismatch')
    queries={stable(c['program']) for rows in p['claims'].values() for c in rows}
    if p['unique_query_count']!=len(queries):raise ValueError('Claim query count mismatch')
    return p


def check(p,g,v,r):
    validate(p);checker=cp.Checker(p['source'],g,v,r);counts=Counter()
    for group,rows in p['claims'].items():
        for c in rows:
            result=checker.check(c)
            if result!=('contradicted' if group=='forbidden' else 'supported'):raise ValueError('Claim proof cannot establish its required truth status')
            counts[result]+=1
    return {'plan_id':p['plan_id'],'plan_sha256':stable(p),'verified':True,'claims':dict(counts),'source_snapshots':p['source']['source']['snapshots']}


def summarize(results):
    plans=[p for x in results for p in x['plans']]
    return {'schema':'comics_qa.benchmark1000.sentence_plan_report.1',
            'counts':{'chapters':len(results),'plans':len(plans),'required_claims':sum(len(p['claims']['required']) for p in plans),
                      'optional_claims':sum(len(p['claims']['optional']) for p in plans),'forbidden_claims':sum(len(p['claims']['forbidden']) for p in plans)},
            'splits':dict(Counter(p['split'] for p in plans)),'status':'prepared_not_inferred','sentence_admission':'pending','human_review':'deferred until post-Qwen','release':'not_approved'}


def run(source,root,out,chapters=None):
    source=Path(source).resolve();root=Path(root).resolve();parent=verify_manifest(source);seeds=load_admitted(source)
    chosen=sorted(set(chapters) if chapters else parent['config']['chapters'])
    if not chosen or not set(chosen)<=set(parent['config']['chapters']):raise ValueError('Unknown sentence chapter scope')
    seeds=[s for s in seeds if s['chapter_id'] in chosen]
    for s in seeds:cp.parse_question(s['question'])
    roots=[root/x for x in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    for p in roots:verify_manifest(p)
    out=separate(out,[source,*roots,root/'core']);repo=Path(__file__).resolve().parents[3];baseline=repo/'configs/benchmark1000/legacy_baseline_v1.json';verify_snapshot(repo,read(baseline)['files'])
    config={'version':cp.VERSION,'source_root':str(source),'source_manifest_sha256':digest(source/'manifest.json'),'chapters':chosen,
            'seed_hashes':{s['item_id']:stable(s) for s in seeds},'source_manifests_sha256':{str(p):digest(p/'manifest.json') for p in roots},
            'legacy_baseline_sha256':digest(baseline),'code_sha256':{p.name:digest(p) for p in Path(__file__).parent.glob('*.py')}}
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.sentence-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);results=[];outputs={}
        for cid in chosen:
            scoped=[s for s in seeds if s['chapter_id']==cid];path=out/'chapters'/f'{cid}.json';snapshots=None
            if scoped:
                g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins)
                if r is None or r['decisions']:raise ValueError('Reviewed rich-world sentence profiles are pending')
                snapshots={'graph':stable(g),'visibility':stable(v),'rich':stable(r)}
            if path.exists():
                wrapper=read(path);payload=wrapper['payload']
                if wrapper['config_sha256']!=stable(config) or wrapper['payload_sha256']!=stable(payload) or payload['snapshots']!=snapshots:raise ValueError('Stale sentence checkpoint')
                for p in payload['plans']:check(p,g,v,r)
            else:
                if scoped:
                    from .verification import revalidate
                    source_checks=revalidate(scoped,root)
                    if source_checks['rejected']:raise ValueError('Sentence source admission no longer reproduces')
                    plans=[make(s,g,v,r) for s in scoped]
                else:source_checks={'items':[],'verified':0,'rejected':0};plans=[]
                payload={'chapter_id':cid,'snapshots':snapshots,'source_checks':source_checks,'plans':plans}
                publish(path,{'config_sha256':stable(config),'payload_sha256':stable(payload),'payload':payload})
            results.append(payload);outputs[str(path.relative_to(out))]=digest(path)
            for p in payload['plans']:
                name='plans/'+stable(p['plan_id'])+'.json';publish(out/name,p);outputs[name]=digest(out/name)
            print(f"{cid}: sentence_plans={len(payload['plans'])}",flush=True)
        report=summarize(results);publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
        publish(out/'manifest.json',{'schema':STORE,'config':config,'config_sha256':stable(config),'outputs_sha256':outputs,'counts':report['counts']})
    return report


def load(root):
    root=Path(root).resolve();m=verify_manifest(root);cfg=m['config']
    if m.get('schema')!=STORE or read(root/'config.json')!=cfg or stable(cfg)!=m['config_sha256']:raise ValueError('Invalid sentence store')
    checkpoints=[read(member(root,p)) for p in sorted(m['outputs_sha256']) if p.startswith('chapters/')];results=[]
    if sorted(c['payload']['chapter_id'] for c in checkpoints)!=cfg['chapters']:raise ValueError('Incomplete sentence chapter scope')
    for c in checkpoints:
        if c['config_sha256']!=m['config_sha256'] or c['payload_sha256']!=stable(c['payload']):raise ValueError('Sentence checkpoint mismatch')
        payload=c['payload'];results.append(payload);checks=payload['source_checks'];rows={x['item_id']:x for x in checks['items']}
        if len(rows)!=len(payload['plans']) or checks['verified']!=len(rows) or checks['rejected']:raise ValueError('Missing source proof replay')
        for p in payload['plans']:
            s=p['source'];row=rows[s['item_id']]
            if cfg['seed_hashes'].get(s['item_id'])!=stable(s) or row['item_sha256']!=stable(s) or row['proof']!='verified' or not all(row['check'].values()) or s['source']['snapshots']!=payload['snapshots'] or s['chapter_id']!=payload['chapter_id']:raise ValueError('Unbound sentence source plan')
    plans=[validate(read(member(root,p))) for p in sorted(m['outputs_sha256']) if p.startswith('plans/')]
    expected=[p for result in results for p in result['plans']]
    if len({p['plan_id'] for p in plans})!=len(plans) or {p['plan_id']:p for p in plans}!={p['plan_id']:p for p in expected}:raise ValueError('Sentence plan/checkpoint mismatch')
    if {p['source']['item_id'] for p in plans}!=set(cfg['seed_hashes']):raise ValueError('Missing sentence seed')
    report=summarize(results)
    if report!=read(root/'report.json') or report['counts']!=m['counts']:raise ValueError('Sentence report/count mismatch')
    return plans


def verify(root,bench_root):
    plans=load(root);bench_root=Path(bench_root);worlds={};rows=[]
    roots=[bench_root/x for x in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    for p in plans:
        cid=p['chapter_id']
        if cid not in worlds:
            g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins);worlds[cid]=(g,v,r)
        rows.append(check(p,*worlds[cid]))
    return {'schema':'comics_qa.benchmark1000.sentence_plan_check.1','store_manifest_sha256':digest(Path(root)/'manifest.json'),
            'verified':len(rows),'rejected':0,'items':rows,'status':'claim_plans_verified_not_sentence_admission'}
