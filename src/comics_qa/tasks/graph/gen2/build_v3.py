"""Retain proof-passing GEN-2 pools, then select independently within each split."""
import argparse
from collections import Counter
import fcntl
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from comics_qa.tasks.graph.gen2.build import read,write,code_hashes
from comics_qa.tasks.graph.gen2.quality import configure,target,metrics,usable_name
from comics_qa.tasks.graph.gen2.collection import select,DEFAULT as COLLECTION_DEFAULT
from comics_qa.tasks.graph.gen2.aliases import validate_reviews
from comics_qa.tasks.graph.gen2.gates import RichGates
from comics_qa.tasks.graph.gen2.families import propose
from comics_qa.tasks.graph.generation.balance import frequent_characters,proportions
from comics_qa.tasks.graph.generation.policy import stable
from comics_qa.tasks.graph.crl.artifacts import load_world,digest
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
VERSION='gen2.3'


def verify(root):
    m=read(root/'manifest.json')
    if stable(m['config'])!=m['fingerprint']:raise ValueError('Manifest fingerprint mismatch')
    for name,sha in m['outputs_sha256'].items():
        p=(root/name).resolve()
        if root not in p.parents or digest(p.read_bytes())!=sha:raise ValueError('Output checksum/path mismatch: '+name)
    return m


def collect(g,v,r,policy,sources,reviews):
    gate=RichGates(g,v,r,policy,sources,alias_reviews=reviews);pool=[];rejected=[];attempts=Counter()
    for q in propose(g,v,r,policy):
        attempts[q.family]+=1;i,rejection=gate.assess(q)
        if rejection:rejected.append(rejection);continue
        i['item_id']='gen2v3:'+stable([VERSION,i['item_id'],reviews])
        i['versions']['generator']=VERSION
        i['quality']={**target(i,g),'policy_version':VERSION}
        pool.append(i)
    frequent,_=frequent_characters(g,policy)
    return {'schema':'comics_qa.gen2.candidate_pool.v1','chapter_id':g['chapter_id'],'split':g['split'],
            'inputs_sha256':sources,'candidates':pool,'gate_rejections':rejected,'frequent_ids':sorted(frequent),
            'alias_reviews':reviews,'attempts_by_family':dict(attempts),
            'counts':{'attempted':sum(attempts.values()),'gates_passed':len(pool),'gate_rejected':len(rejected)}}


def validate_pool(pool,g,v,r,sources,policy):
    if pool['chapter_id']!=g['chapter_id'] or pool['split']!=g['split'] or pool['inputs_sha256']!=sources:raise ValueError('Pool dependency mismatch')
    frequent,_=frequent_characters(g,policy)
    if sorted(frequent)!=pool['frequent_ids']:raise ValueError('Pool frequency metadata mismatch')
    c=pool['counts'];items=pool['candidates'];ids=set()
    if c['gates_passed']!=len(items) or c['gate_rejected']!=len(pool['gate_rejections']) or c['attempted']!=len(items)+len(pool['gate_rejections']):raise ValueError('Pool counts mismatch')
    checker=ProofChecker(g,v,rich=r)
    for i in items:
        if i['item_id'] in ids or i['chapter_id']!=g['chapter_id'] or i['split']!=g['split']:raise ValueError('Pool item identity mismatch')
        ids.add(i['item_id'])
        if not checker.check(i['execution'])['accepted_for_generation'] or i['answer']['value']!=i['execution']['result']['display']:raise ValueError('Reused pool proof/answer invalid')
        if i['proof_check']['execution_sha256']!=stable(i['execution']) or i['execution']['inputs_sha256']!=sources:raise ValueError('Reused pool proof binding invalid')
        if i['quality']!={**target(i,g),'policy_version':VERSION}:raise ValueError('Pool semantic target mismatch')
        expected={'Int':'int','Char':'char','Page':'page'}.get(i['execution']['result']['type'])
        if i['answer']['type']!=expected:raise ValueError('Pool answer type mismatch')
        if i['canonical']!=i['execution']['canonical'] or i['program_sha256']!=i['execution']['program_sha256']:raise ValueError('Pool program binding mismatch')
        if not all(usable_name(g,v,n['identity_id'],n['form'],pool['alias_reviews']) for n in i['names_in_question']):raise ValueError('Pool question name eligibility mismatch')
        if expected=='char' and not all(usable_name(g,v,i['answer']['identity_id'],f,pool['alias_reviews']) for f in [i['answer']['value'],*i['answer']['accepted_forms']]):raise ValueError('Pool answer name eligibility mismatch')


def run(args):
    roots=[getattr(args,k).resolve() for k in ('graphs','visibility','rich')]
    out=args.out.resolve();partial=out.with_name(out.name+'.partial')
    source=args.pool_source.resolve() if args.pool_source else None
    for dest in (out,partial):
        for root in roots+([source] if source else []):
            if dest==root or dest in root.parents or root in dest.parents:raise ValueError('Output overlaps inputs')
        for file in (args.config,args.alias_reviews):
            if file and (dest==file.resolve() or dest in file.resolve().parents):raise ValueError('Output overlaps policy/review file')
    raw=read(args.config) if args.config else {};collection=raw.pop('collection',COLLECTION_DEFAULT)
    policy=configure(raw)
    for k in ('seed','max_candidates_per_chapter','max_items_per_chapter'):
        if getattr(args,k) is not None:policy[k]=getattr(args,k)
    policy=configure(policy);select([],policy,collection)
    generation_policy={k:v for k,v in policy.items() if k!='quality'}
    manifests=[read(root/'manifest.json') for root in roots]
    available=set(manifests[0]['config']['chapters']);chapters=sorted(set(args.chapter) if args.chapter else available)
    if not chapters or not set(chapters)<=available or any(not set(chapters)<=set(m['config']['chapters']) for m in manifests):raise ValueError('Unknown/missing chapter')
    reviews=read(args.alias_reviews) if args.alias_reviews else []
    if not isinstance(reviews,list) or any(not isinstance(r,dict) or r.get('chapter_id') not in available for r in reviews):raise ValueError('Invalid alias-review list/chapter')
    deps={str(root/'manifest.json'):digest((root/'manifest.json').read_bytes()) for root in roots}
    pool_config={'version':VERSION,'generation_policy':generation_policy,'code_sha256':code_hashes(),
                 'dependencies':deps,'alias_reviews_sha256':stable(reviews),'name_policy':'visible_canonical_or_explicit_reviewed'}
    pool_fp=stable(pool_config)
    config={'schema':'comics_qa.gen2.build.v1','version':VERSION,'pool_config':pool_config,'pool_fingerprint':pool_fp,
            'chapters':chapters,'policy':policy,'collection':collection,'scope':'selected_chapters' if args.chapter else 'full_collection'}
    source_manifest=verify(source) if source else None
    if source:
        if source_manifest['config'].get('pool_fingerprint')!=pool_fp:raise ValueError('Pool source generation dependencies changed')
        config['pool_source_manifest_sha256']=digest((source/'manifest.json').read_bytes())
    fp=stable(config);out.parent.mkdir(parents=True,exist_ok=True)
    with out.with_name(out.name+'.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another GEN-2 writer holds the lock')
        completed=out.exists()
        if completed:
            saved=verify(out)
            if not args.resume or saved['fingerprint']!=fp:raise ValueError('Existing output requires matching --resume; otherwise use a new output')
        elif partial.exists():
            if not args.resume or read(partial/'build_config.json')!=config:raise ValueError('Partial build requires unchanged --resume')
        else:partial.mkdir();write(partial/'build_config.json',config)
        pools=[]
        for cid in chapters:
            g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins)
            if r['decisions']:raise ValueError('Reviewed CKG-3 ablation remains unsupported')
            approved=validate_reviews(reviews,g,v,digest((roots[0]/'chapters'/f'{cid}.json').read_bytes()),digest((roots[1]/'chapters'/f'{cid}.json').read_bytes()))
            name='candidate_pools/'+cid+'.json';dest=(out if completed else partial)/name
            existing=dest if dest.exists() else source/name if source and name in source_manifest['outputs_sha256'] else None
            if existing:
                wrapper=read(existing);pool=wrapper['payload']
                if wrapper['pool_fingerprint']!=pool_fp or wrapper['payload_sha256']!=stable(pool):raise ValueError('Candidate checkpoint mismatch')
                if pool['alias_reviews']!=approved:raise ValueError('Alias review binding mismatch')
                validate_pool(pool,g,v,r,pins,generation_policy)
            else:
                if completed or source:raise ValueError('Missing retained candidate pool: '+cid)
                pool=collect(g,v,r,generation_policy,pins,approved)
            if not completed and not dest.exists():write(dest,{'pool_fingerprint':pool_fp,'payload_sha256':stable(pool),'payload':pool})
            pools.append(pool)
            print(f"{cid}: {len(pool['candidates'])} proof-passing candidates retained",file=sys.stderr)
        if completed:
            print(json.dumps({'output':str(out),'status':'verified_completed','counts':saved['counts']}));return 0
        items,rejected,selection=select(pools,policy,collection);shards=[]
        for pool in pools:
            cid=pool['chapter_id'];chosen=[i for i in items if i['chapter_id']==cid]
            failures=list(pool['gate_rejections'])
            failures += [{'gate':'collection_selection','reason':rejected[i['item_id']],'item_id':i['item_id'],
                          'family':i['family'],'program':i['canonical'],'program_sha256':i['program_sha256'],'answer':i['answer']}
                         for i in pool['candidates'] if i['item_id'] in rejected]
            c=pool['counts'];frequent=set(pool['frequent_ids'])
            shard={'schema':'comics_qa.gen2.chapter.v1','chapter_id':cid,'split':pool['split'],'inputs_sha256':pool['inputs_sha256'],
                   'items':chosen,'rejections':failures,'attempts_by_family':pool['attempts_by_family'],
                   'candidate_pool':'candidate_pools/'+cid+'.json',
                   'balance':{'selected':proportions(chosen,frequent),'pool':proportions(pool['candidates'],frequent),'limits_relaxed':False,'quality_scope':'split'},
                   'counts':{'attempted':c['attempted'],'gates_passed':c['gates_passed'],'selected':len(chosen),'rejected':len(failures)}}
            shard['rejection_reasons']=dict(Counter(x['gate']+':'+x['reason'] for x in failures))
            write(partial/'chapters'/f'{cid}.json',{'fingerprint':fp,'payload_sha256':stable(shard),'payload':shard});shards.append(shard)
        counts={k:sum(s['counts'][k] for s in shards) for k in ('attempted','gates_passed','selected','rejected')};counts['chapters']=len(shards)
        report={'schema':'comics_qa.gen2.report.v1','version':VERSION,'scope':config['scope'],'counts':counts,
                'policy':policy,'selection':selection,'candidate_pools_retained':True,'name_policy':pool_config['name_policy'],'alias_approvals':sum(len(p['alias_reviews']) for p in pools),
                'rejection_reasons':dict(sum((Counter(s['rejection_reasons']) for s in shards),Counter())),
                'chapters':[{k:s[k] for k in ('chapter_id','split','counts','balance')} for s in shards]}
        write(partial/'report.json',report)
        lines=['# GEN-2 v3 report','',json.dumps(counts,sort_keys=True),'',
               'All proof-passing candidates are retained separately. Selection is within each split; existing name/two-option limits remain per chapter.',
               'No quotas are relaxed. Empty selection means insufficient retained diversity, not a proof that no feasible subset exists.',
               'Human review and Qwen remain pending.','', '## Split selection','',json.dumps(selection,ensure_ascii=False,indent=2)]
        (partial/'report.md').write_text('\n'.join(lines)+'\n')
        outputs={p.relative_to(partial).as_posix():digest(p.read_bytes()) for p in sorted(partial.rglob('*')) if p.is_file() and p.name!='manifest.json'}
        write(partial/'manifest.json',{'schema':config['schema'],'fingerprint':fp,'config':config,'counts':counts,'outputs_sha256':outputs})
        partial.rename(out)
    print(json.dumps({'output':str(out),'status':'complete','counts':counts}));return 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('graphs','visibility','rich','out'):p.add_argument('--'+k,type=Path,required=True)
    for k in ('config','alias-reviews','pool-source'):p.add_argument('--'+k,type=Path)
    p.add_argument('--chapter',action='append',default=[]);p.add_argument('--resume',action='store_true')
    for k in ('seed','max-candidates-per-chapter','max-items-per-chapter'):p.add_argument('--'+k,type=int)
    args=p.parse_args(argv)
    try:return run(args)
    except (ValueError,OSError,KeyError,TypeError,RuntimeError) as exc:print('GEN-2 v3 error: '+str(exc),file=sys.stderr);return 2
    except KeyboardInterrupt:print('Interrupted; completed candidate pools retained. Repeat with --resume.',file=sys.stderr);return 130

if __name__=='__main__':raise SystemExit(main())
