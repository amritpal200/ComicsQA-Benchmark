"""Resumable CPU generation of private, proof-checked GEN-2 candidate items."""
import argparse
from collections import Counter
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from comics_qa.tasks.graph.crl.artifacts import load_world, digest
from comics_qa.tasks.graph.crl.check_crl import strict_json
from comics_qa.tasks.graph.generation.policy import stable
from comics_qa.tasks.graph.gen2.quality import configure, select, metrics, VERSION
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from comics_qa.tasks.graph.gen2.families import propose
from comics_qa.tasks.graph.gen2.gates import RichGates as Gates


def read(path): return strict_json(Path(path).read_bytes())


def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.gen2-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as handle:
            json.dump(obj,handle,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);handle.write('\n');handle.flush();os.fsync(handle.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def chapter(graph,visibility,rich,policy,sources):
    gate=Gates(graph,visibility,rich,policy,sources);pool=[];rejections=[];attempts=Counter()
    for proposal in propose(graph,visibility,rich,policy):
        attempts[proposal.family]+=1
        item,rejection=gate.assess(proposal)
        if rejection: rejections.append(rejection)
        else: pool.append(item)
    selected,rejected,balance=select(pool,graph,policy);rejections.extend(rejected)
    return {'schema':'comics_qa.gen2.chapter.v1','chapter_id':graph['chapter_id'],'split':graph['split'],
            'inputs_sha256':sources,'items':selected,'rejections':rejections,'balance':balance,
            'counts':{'attempted':sum(attempts.values()),'gates_passed':len(pool),'selected':len(selected),'rejected':len(rejections)},
            'attempts_by_family':dict(sorted(attempts.items())),
            'rejection_reasons':dict(sorted(Counter(r['gate']+':'+r['reason'] for r in rejections).items()))}


def markdown(report,shards):
    lines=['# GEN-2 generation report','',f"Scope: {report['scope']}. Chapters: {report['counts']['chapters']}.",
           f"Attempted: {report['counts']['attempted']}; gate-passed: {report['counts']['gates_passed']}; selected: {report['counts']['selected']}.",'',
           'All selected items have checked proofs and remain pending verbalization/human review. No quotas were relaxed.',
           'Page indices refer to supplied chapter images; spreads count once. No source annotations were modified.','',
           '| Chapter | Attempted | Gate-passed | Selected | Frequent/name | Two-option/all |',
           '|---|---:|---:|---:|---:|---:|']
    for shard in shards:
        c=shard['counts'];s=shard['balance']['selected']
        lines.append(f"| {shard['chapter_id']} | {c['attempted']} | {c['gates_passed']} | {c['selected']} | {s['frequent_name_answers']}/{s['name_answers']} | {s['two_option_answers']}/{s['items']} |")
    q=report['quality']
    lines+=['','## Quality checks','', 'Per-chapter name/two-option quotas and quality caps are enforced without relaxation.',
            'Quality policy: '+json.dumps(q['policy'],sort_keys=True),
            'Selected distribution: '+json.dumps(q['selected'],sort_keys=True),
            'Deduplication uses resolved speaker/page or speaker/text targets, not quote wording. Zero yield is allowed.']
    lines+=['','## Rejections','']+[f'- {k}: {v}' for k,v in report['rejection_reasons'].items()]
    lines+=['','## Examples (private review only)','']
    for shard in shards:
        for item in shard['items'][:5]:
            lines.append(f"- {shard['chapter_id']} [{item['family']}]: {item['question']} Answer: {item['answer']['value']}")
    lines+=['','Zero-yield chapters are retained and reported. The full collection has not been generated unless scope is full_collection.',
            'G9 checks per-model normalized transcript equivalence and representation order. This is not general OCR noise robustness.','']
    return '\n'.join(lines)


def code_hashes():
    root=Path(__file__).resolve().parents[3]
    files=[]
    for sub in ('tasks/graph/gen2','tasks/graph/generation','tasks/graph/crl','evidence/graph','evidence/graph/rich','core'):
        files.extend((root/sub).glob('*.py'))
    return {str(p):digest(p.read_bytes()) for p in sorted(files)}


def run(args):
    graphs=args.graphs.resolve();visibility=args.visibility.resolve();rich_root=args.rich.resolve();out=args.out.resolve();partial=out.with_name(out.name+'.partial')
    policy=configure(read(args.config) if args.config else None)
    for key in ('seed','max_candidates_per_chapter','max_items_per_chapter'):
        value=getattr(args,key)
        if value is not None: policy[key]=value
    policy=configure(policy)
    for target in (out,partial):
        for source in (graphs,visibility,rich_root):
            if target==source or target in source.parents or source in target.parents: raise ValueError('Output overlaps evidence inputs')
        if args.config and (target==args.config.resolve() or target in args.config.resolve().parents): raise ValueError('Output overlaps configuration')
    gm,vm=read(graphs/'manifest.json'),read(visibility/'manifest.json')
    rm=read(rich_root/'manifest.json')
    available=set(gm['config']['chapters'])
    selected=sorted(set(args.chapter) if args.chapter else available)
    if not selected or not set(selected)<=available: raise ValueError('Unknown/empty chapter selection')
    if not set(selected)<=set(rm['config']['chapters']): raise ValueError('Missing CKG-3 chapters')
    if not set(selected)<=set(vm['config']['chapters']): raise ValueError('Missing CKG-2 companions; refusing silent chapter intersection')
    config={'schema':'comics_qa.gen2.build.v1','version':VERSION,'policy':policy,'chapters':selected,
            'scope':'selected_chapters' if args.chapter else 'full_collection',
            'roots':{'graphs':str(graphs),'visibility':str(visibility),'rich':str(rich_root)},
            'dependencies':{str(p):digest(p.read_bytes()) for p in (graphs/'manifest.json',visibility/'manifest.json',rich_root/'manifest.json')},'code_sha256':code_hashes()}
    fingerprint=stable(config)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.with_name(out.name+'.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Another GEN-2 writer holds this output lock')
        if out.exists():
            if not args.resume: raise ValueError('Output already exists; use --resume to verify or choose a new --out')
            manifest=read(out/'manifest.json')
            if manifest['fingerprint']!=fingerprint: raise ValueError('Completed build code/config/dependencies changed; choose a new output')
            for name,sha in manifest['outputs_sha256'].items():
                if digest((out/name).read_bytes())!=sha: raise ValueError('Completed output checksum mismatch: '+name)
            for cid in selected:
                graph,vis,sources=load_world(graphs,visibility,cid)
                load_optional(graphs,visibility,rich_root,cid,sources)
            print(json.dumps({'output':str(out),'status':'verified_completed','counts':manifest['counts']}));return 0
        if partial.exists():
            if not args.resume: raise ValueError('Partial output exists; use --resume')
            if read(partial/'build_config.json')!=config: raise ValueError('Partial build code/config/dependencies changed; choose a new output')
        else:
            partial.mkdir();write(partial/'build_config.json',config)
        shards=[]
        for cid in selected:
            graph,vis,sources=load_world(graphs,visibility,cid)
            rich=load_optional(graphs,visibility,rich_root,cid,sources)
            if rich['decisions']: raise ValueError('GEN-2 v1 supports automatic consensus only; reviewed-world ablation is not defined yet')
            path=partial/'chapters'/(cid+'.json')
            if path.exists():
                saved=read(path);shard=saved['payload']
                if saved['fingerprint']!=fingerprint or saved['payload_sha256']!=stable(shard) or shard['inputs_sha256']!=sources:
                    raise ValueError('Checkpoint checksum/dependency mismatch: '+cid)
            else:
                shard=chapter(graph,vis,rich,policy,sources)
                write(path,{'fingerprint':fingerprint,'payload_sha256':stable(shard),'payload':shard})
            shards.append(shard)
            print(f"{cid}: {shard['counts']}",file=sys.stderr)
        counts={k:sum(s['counts'][k] for s in shards) for k in ('attempted','gates_passed','selected','rejected')};counts['chapters']=len(shards)
        reasons=Counter()
        for shard in shards: reasons.update(shard['rejection_reasons'])
        report={'schema':'comics_qa.gen2.report.v1','scope':config['scope'],'counts':counts,'policy':policy,
                'rejection_reasons':dict(sorted(reasons.items())),
                'quality':{'policy':policy['quality'],'selected':metrics([i for s in shards for i in s['items']])},
                'chapters':[{k:s[k] for k in ('chapter_id','split','counts','balance','attempts_by_family')} for s in shards]}
        write(partial/'report.json',report)
        (partial/'report.md').write_text(markdown(report,shards))
        outputs={p.relative_to(partial).as_posix():digest(p.read_bytes()) for p in sorted(partial.rglob('*')) if p.is_file() and p.name!='manifest.json'}
        write(partial/'manifest.json',{'schema':config['schema'],'fingerprint':fingerprint,'config':config,'counts':counts,'outputs_sha256':outputs})
        partial.rename(out)
    print(json.dumps({'output':str(out),'status':'complete','counts':counts}));return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('graphs','visibility','rich','out'): parser.add_argument('--'+k,type=Path,required=True)
    parser.add_argument('--config',type=Path)
    parser.add_argument('--chapter',action='append',default=[])
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--seed',type=int)
    parser.add_argument('--max-candidates-per-chapter',type=int)
    parser.add_argument('--max-items-per-chapter',type=int)
    args=parser.parse_args(argv)
    try: return run(args)
    except (ValueError,OSError,KeyError,RuntimeError) as exc:
        print('GEN-2 build error: '+str(exc),file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; completed chapter checkpoints retained. Rerun the same command with --resume.',file=sys.stderr);return 130


if __name__=='__main__': raise SystemExit(main())
