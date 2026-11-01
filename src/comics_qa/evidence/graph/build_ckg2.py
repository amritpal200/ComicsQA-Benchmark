"""Build immutable CKG-2 name-visibility companions for complete CKG-1 chapters."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import sys

import build_ckg1 as graph_builder
from build_ckg1 import check, checksum
import audit_ckg0 as audit
import review_ckg0 as review
from ckg_schema import stable_id, validate_graph
import name_visibility as visibility


def build_chapter(graph, documents, inp, graph_path, policy, decisions, decision_source):
    catalog=visibility.alias_catalog(graph,inp.identities)
    graph_digest=checksum(graph_path)
    nodes={n['id']:n for n in graph['nodes']}
    alignments=[]; evidence=[]
    for pid in graph['page_ids']:
        page=nodes[pid]; docs=documents[pid]
        # Category indices may exceed two digits; use the original core order rather than lexical IDs.
        ordered_ids=[r['text_id'] for r in inp.pages[pid]['texts']]
        texts=[nodes[tid] for tid in ordered_ids]
        observations=visibility.page_observations(page,texts,docs['ocr'],docs['magi3'],policy)
        ppath=audit.safe_path(inp.args.ocr,page['relative_path']+'.json')
        mpath=audit.safe_path(inp.args.magi3,page['relative_path']+'.json')
        image=audit.safe_path(inp.args.images,page['relative_path'])
        for obs in observations:
            sources=[visibility.source(graph_path,graph_digest,'/nodes'),inp.pointer(image)]
            if obs['paddle_index'] is not None:
                sources.append(inp.pointer(ppath,f"/ocr/texts/{obs['paddle_index']}"))
            if obs['magi_index'] is not None:
                j=obs['magi_index']
                sources += [inp.pointer(mpath,f'/magi3/ocr/ocr_texts/{j}'),inp.pointer(mpath,f'/magi3/ocr/bboxes/{j}')]
            obs['sources']=sources
            # Input source hashes participate in the stable alignment/evidence identity.
            obs['alignment_id']=stable_id('align:',{**obs,'policy':policy})
            alignments.append(obs)
            matches=visibility.name_evidence(graph['chapter_id'],obs,catalog,sources,policy)
            for row in matches:
                row['identity_source']=inp.core_pointer('characters','identity_id',row['identity_id'])
            evidence.extend(matches)
    visibility.apply_decisions(evidence,decisions,decision_source)
    chapter={'schema':visibility.SCHEMA,'policy_version':visibility.VERSION,'chapter_id':graph['chapter_id'],
        'page_ids':graph['page_ids'],'graph_source':visibility.source(graph_path,graph_digest,''),
        'policy':policy,'alignments':alignments,'evidence':evidence,'visibility':visibility.summarize(graph,evidence),
        'coverage_effect':'none; all CKG-1 coverage certificates are preserved',
        'semantics':'lexical readability of the exact form; does not establish speaker, addressee or mention referent'}
    validate_companion(chapter,graph)
    return chapter


def validate_companion(chapter,graph):
    check(chapter['schema']==visibility.SCHEMA and chapter['page_ids']==graph['page_ids'],'Visibility scope mismatch')
    alignments={a['alignment_id']:a for a in chapter['alignments']}
    check(len(alignments)==len(chapter['alignments']),'Duplicate alignment ID')
    evidence=chapter['evidence']; nodes={n['id']:n for n in graph['nodes']}
    check(len({e['evidence_id'] for e in evidence})==len(evidence),'Duplicate visibility evidence')
    for row in evidence:
        check(row['alignment_id'] in alignments and row['page_id'] in graph['page_ids'],'Dangling visibility evidence')
        check(row['identity_id'] in nodes and not nodes[row['identity_id']]['generic'],'Visibility targets a generic/missing identity')
        check(row['status'] in ('verified','candidate','rejected'),'Invalid evidence status')
        check(row['origin']==('V' if row['status']=='verified' else 'M'),'Visibility trust mismatch')
        if row['status']=='verified' and row['verification_method']=='two_model_name_span_agreement':
            check(not row['reasons'] and row['paddle_token_spans'] and row['magi_token_spans'],'Unjustified OCR verification')
        if row['text_id'] is not None:
            check(row['text_id'] in nodes and nodes[row['text_id']]['type']=='Text' and nodes[row['text_id']]['page_id']==row['page_id'],
                  'Visibility text reference mismatch')
    check(visibility.summarize(graph,evidence)==chapter['visibility'],'Visibility summary differs from evidence')


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('graphs','core','audit','review','images','human','magi3','ocr','out'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--chapter',action='append',default=[])
    p.add_argument('--decisions',type=Path,help='Explicit individual visual-review decisions JSONL')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--min-iou',type=float,default=0.5)
    p.add_argument('--ambiguity-overlap',type=float,default=0.5)
    args=p.parse_args(argv)
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.expanduser().resolve())
    check(0.5<=args.min_iou<=1 and 0<args.ambiguity_overlap<=0.5,'Require IoU >= 0.5 and ambiguity overlap <= 0.5')
    for target in (args.out,args.out.with_name(args.out.name+'.partial')):
        for key in ('graphs','core','audit','review','images','human','magi3','ocr'):
            root=getattr(args,key)
            check(target!=root and root not in target.parents and target not in root.parents,f'Output overlaps --{key}')
        if args.decisions:
            check(target!=args.decisions and target not in args.decisions.parents,'Output overlaps review decisions')
    return args


def report_markdown(report):
    c=report['counts']
    lines=['# CKG-2 name visibility','',f"Scope: {report['scope']}; {c.get('chapters',0)} chapters / {c.get('pages',0)} pages.",'',
        '| Measurement | Count |','|---|---:|']
    lines += [f'| {k} | {v} |' for k,v in sorted(c.items())]
    lines += ['', '## Verification limits','',
        '- Verified forms have aligned two-model name-span agreement or an explicit recorded visual review.',
        '- A readable alias does not automatically certify the full canonical name. GEN-1 must check its rendered form.',
        '- Short names, ambiguous aliases, uncertain alignment and truncated OCR require review or remain unusable.',
        '- Not verified does not mean absent from the chapter. All original coverage restrictions remain.',
        '- A name match establishes lexical readability; it does not determine who is mentioned or who is speaking.',
        '- Name-span agreement does not verify the full OCR transcript for quote questions.','',
        'Alignment statuses: '+json.dumps(report['alignment_statuses'],sort_keys=True),'',
        'Candidate reasons (overlapping counts): '+json.dumps(report['candidate_reasons'],sort_keys=True),'']
    return '\n'.join(lines)


def main(argv=None):
    args=parse_args(argv);inp=graph_builder.Inputs(args)
    gm=review.read_json(args.graphs/'manifest.json')
    check(gm['schema']=='comics_qa.ckg.v1','Expected CKG-1 manifest')
    gconfig=gm['config']; old=gconfig['arguments']
    expected={str(Path(old['core'])/name):checksum(args.core/name) for name in ('pages.jsonl','chapters.jsonl','characters.jsonl','manifest.json')}
    expected.update({str(Path(old[k])/'manifest.json'):checksum(getattr(args,k)/'manifest.json') for k in ('audit','review')})
    check(gconfig['dependencies']==expected,'CKG-1 does not pin the supplied core/audit/review')
    for name in ('report.json','build_config.json','inputs.jsonl','relations.json'):
        check(checksum(args.graphs/name)==gm['outputs_sha256'][name],f'CKG-1 checksum mismatch: {name}')
    check(review.read_json(args.graphs/'build_config.json')==gconfig,'CKG-1 configuration mismatch')
    selected=sorted(set(args.chapter) or set(gconfig['chapters']))
    check(set(selected)<=set(gconfig['chapters']),'Selected chapter not in CKG-1 build')
    decisions=review.read_rows(args.decisions) if args.decisions else []
    check(len({d['evidence_id'] for d in decisions})==len(decisions),'Duplicate review decisions')
    check(all(d['chapter_id'] in gconfig['chapters'] for d in decisions),'Decision chapter outside graph collection')
    decision_source=visibility.source(args.decisions,checksum(args.decisions),'') if args.decisions else None
    policy={**visibility.DEFAULT_POLICY,'min_iou':args.min_iou,'ambiguity_overlap':args.ambiguity_overlap}
    code=[Path(__file__),Path(visibility.__file__),Path(graph_builder.__file__),Path(review.__file__),Path(audit.__file__),
          Path(__file__).with_name('ckg_schema.py'),audit.CORE/'build_core.py',audit.CORE/'geometry.py']
    config={'schema':visibility.SCHEMA,'version':visibility.VERSION,'policy':policy,'chapters':selected,
        'scope':'selected_chapters' if args.chapter or gconfig['scope']!='full_collection' else 'full_collection',
        'arguments':{k:str(v) for k,v in vars(args).items() if k not in ('resume','out','chapter')},
        'dependencies':{**inp.dependencies,str(args.graphs/'manifest.json'):checksum(args.graphs/'manifest.json')},
        'decisions_source':decision_source,'code_sha256':{str(p):checksum(p) for p in code}}
    fingerprint=stable_id('',config);partial=args.out.with_name(args.out.name+'.partial')
    check(not partial.is_symlink(),'Partial output must not be a symlink')
    complete=args.out.exists()
    check(args.resume or not complete and not partial.exists(),'Output/.partial exists; use --resume or a new --out')
    check(not(complete and partial.exists()),'Both output and partial exist')
    root=args.out if complete else partial
    if complete:
        manifest=review.read_json(root/'manifest.json')
        check(manifest['fingerprint']==fingerprint,'Completed configuration/dependencies changed')
        graph_builder.verify_outputs(root,manifest)
    else:root.mkdir(parents=True,exist_ok=args.resume)
    for name in ('.build.lock','chapters','checkpoints','build_config.json'):
        check(not(root/name).is_symlink(),'Output entries must not be symlinks')
    with (root/'.build.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=root/'build_config.json'
        if state.exists():check(review.read_json(state)==config,'Partial configuration changed; use a new --out')
        else:
            check(not complete,'Completed output missing config');audit.write_json(state,config)
        for folder in ('chapters','checkpoints'):(root/folder).mkdir(exist_ok=True)
        counts=Counter();alignment_counts=Counter();reasons=Counter();input_files={}
        for idx,cid in enumerate(selected,1):
            gpath=audit.safe_path(args.graphs,f'chapters/{cid}.json');digest=checksum(gpath)
            check(digest==gm['outputs_sha256'][f'chapters/{cid}.json'],f'CKG-1 chapter checksum mismatch: {cid}')
            graph=review.read_json(gpath);validate_graph(graph)
            check(graph['page_ids']==inp.chapters[cid]['page_ids'],'Graph chapter scope differs from core')
            sources,documents=inp.chapter_sources(inp.chapters[cid]);input_files.update({r['path']:r for r in sources})
            target=root/'chapters'/(cid+'.json');marker=root/'checkpoints'/(cid+'.json')
            if marker.exists():
                cp=review.read_json(marker)
                check(cp['fingerprint']==fingerprint and cp['sources']==sources and cp['graph_sha256']==digest,'Checkpoint inputs changed')
                check(checksum(target)==cp['sha256'],'Visibility chapter checksum mismatch')
                chapter=review.read_json(target);validate_companion(chapter,graph)
                action='Verified/reused'
            else:
                check(not complete,'Completed output missing checkpoint')
                chapter=build_chapter(graph,documents,inp,gpath,policy,[d for d in decisions if d['chapter_id']==cid],decision_source)
                audit.write_json(target,chapter)
                audit.write_json(marker,{'fingerprint':fingerprint,'graph_sha256':digest,'sources':sources,'sha256':checksum(target)})
                action='Built'
            named=[v for v in chapter['visibility'] if not v['generic']]
            counts.update(chapters=1,pages=len(chapter['page_ids']),named_chapter_identities=len(named),
                identities_with_verified_form=sum(v['status']=='verified' for v in named),
                identities_with_verified_canonical=sum(v['canonical_visible'] for v in named),
                identities_not_verified=sum(v['status']=='not_verified' for v in named),
                verified_forms=sum(len(v['verified_forms']) for v in named),evidence=len(chapter['evidence']),
                verified_evidence=sum(e['status']=='verified' for e in chapter['evidence']),
                candidate_evidence=sum(e['status']=='candidate' for e in chapter['evidence']),
                rejected_evidence=sum(e['status']=='rejected' for e in chapter['evidence']),
                verified_on_unannotated_pages=sum(e['status']=='verified' and e['text_id'] is None for e in chapter['evidence']))
            alignment_counts.update(a['status'] for a in chapter['alignments'])
            reasons.update(r for e in chapter['evidence'] if e['status']=='candidate' for r in e['reasons'])
            print(f'{action} visibility {cid} ({idx}/{len(selected)})',file=sys.stderr,flush=True)
        if not complete:
            report={'schema':visibility.SCHEMA,'scope':config['scope'],'counts':dict(counts),
                    'alignment_statuses':dict(alignment_counts),'candidate_reasons':dict(reasons),'policy':policy}
            audit.write_json(root/'report.json',report)
            (root/'report.md').write_text(report_markdown(report),encoding='utf-8')
            audit.write_jsonl(root/'inputs.jsonl',[input_files[k] for k in sorted(input_files)])
            audit.write_json(root/'manifest.json',{'schema':visibility.SCHEMA,'created_at':datetime.now(timezone.utc).isoformat(),
                'fingerprint':fingerprint,'config':config,'outputs_sha256':{p.relative_to(root).as_posix():checksum(p)
                    for p in sorted(root.rglob('*')) if p.is_file() and not p.name.startswith('.') and p.name!='manifest.json'}})
            check(not args.out.exists(),'Output appeared during build');root.rename(args.out)
    print(f"Visibility report: {args.out/'report.md'}")
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,OSError,KeyError,TypeError,IndexError) as exc:
        print(f'CKG-2 could not complete: {exc}',file=sys.stderr);sys.exit(1)
