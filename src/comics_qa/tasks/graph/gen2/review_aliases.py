"""Write pending alias reviews with exact source pins; never approve automatically."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from comics_qa.tasks.graph.crl.artifacts import load_world,digest,write_new
from comics_qa.tasks.graph.gen2.quality import normalized
from comics_qa.tasks.graph.gen2.build import read


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('graphs','visibility','out'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--chapter',action='append',default=[]);args=p.parse_args(argv)
    try:
        roots=[args.graphs.resolve(),args.visibility.resolve()];out=args.out.resolve()
        if any(out==r or r in out.parents or out in r.parents for r in roots):raise ValueError('Review output overlaps evidence')
        available=read(roots[0]/'manifest.json')['config']['chapters'];chapters=sorted(set(args.chapter or available))
        if not set(chapters)<=set(available):raise ValueError('Unknown chapter')
        rows=[]
        for cid in chapters:
            g,v,_=load_world(*roots,cid);pages={n['id']:n for n in g['nodes'] if n['type']=='Page'}
            align={a['alignment_id']:a for a in v['alignments']}
            for n in g['nodes']:
                if n['type']!='Character' or n['generic']:continue
                forms=sorted({e['form'] for e in v['evidence'] if e['identity_id']==n['id'] and e['status']=='verified' and normalized(e['form'])!=normalized(n['canonical_name'])})
                for form in forms:
                    ev=[e for e in v['evidence'] if e['identity_id']==n['id'] and e['status']=='verified' and normalized(e['form'])==normalized(form)]
                    rows.append({'chapter_id':cid,'identity_id':n['id'],'canonical_name':n['canonical_name'],'form':form,
                        'graph_sha256':digest((roots[0]/'chapters'/f'{cid}.json').read_bytes()),
                        'visibility_sha256':digest((roots[1]/'chapters'/f'{cid}.json').read_bytes()),
                        'decision':'pending','name_use':'unreviewed','reviewer':'','note':'',
                        'evidence_ids':[e['evidence_id'] for e in ev],
                        'evidence_context':[{'evidence_id':e['evidence_id'],'page_id':e['page_id'],'relative_image_path':pages[e['page_id']]['relative_path'],
                                             'paddle_text':align[e['alignment_id']]['paddle_text'],'magi_text':align[e['alignment_id']]['magi_text']} for e in ev]})
        write_new(out,json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'output':str(out),'pending_aliases':len(rows),'approved':0}));return 0
    except (OSError,KeyError,ValueError,TypeError) as exc:print('Alias review error: '+str(exc),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
