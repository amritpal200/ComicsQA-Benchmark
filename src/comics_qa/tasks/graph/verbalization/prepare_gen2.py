"""CPU-only GEN-2 paraphrase requests plus private pinned evidence packs."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from comics_qa.tasks.graph.verbalization import prepare as base
from comics_qa.tasks.graph.verbalization.gen2_gloss import parse_gloss
from comics_qa.tasks.graph.crl.artifacts import load_world, digest
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.tasks.graph.crl.language import canonical
from comics_qa.tasks.graph.generation.policy import stable

SYSTEM=base.SYSTEM+'''
For GEN-2, preserve quoted text and literal name forms exactly, including punctuation.
Full-text quote lookup is not a substring search. A literal name occurrence is not a
semantic mention of that person. Keep each page scope; do not turn page-local
uniqueness into chapter-wide uniqueness. Next drawn means after the entire anchor
page, not the next panel or guaranteed immediately following page.''' 


def validate_rewrite(item,response):
    """Closed-grammar semantic comparison; never accept a model's echoed program."""
    base.make_record(item,parser=parse_gloss)
    if not isinstance(response,dict) or set(response)!={'question'} or not isinstance(response['question'],str) or not response['question'].strip():
        return {'status':'rejected','reason':'response_contract','g10':'pending','human_review':'pending'}
    try:ast=parse_gloss(response['question'])
    except ValueError:
        return {'status':'needs_blind_parse_back','reason':'outside_closed_grammar','g10':'pending','human_review':'pending'}
    if canonical(ast)!=item['canonical']:
        return {'status':'rejected','reason':'semantic_drift','g10':'pending','human_review':'pending'}
    return {'status':'closed_grammar_match','answer_preserved':True,'g10':'pending_human_language_review',
            'human_review':'pending','question_sha256':stable(response['question'])}


class Profile:
    version='verb1.gen2.prepare.1'
    source_schema='comics_qa.gen2.build.v1'
    output_schema='comics_qa.verb1.gen2.preparation.v1'
    proof_validation='independent CRL checker against pinned CKG-1/2/3; template round trip'

    def __init__(self,args):
        self.roots=[args.graphs.resolve(),args.visibility.resolve(),args.rich.resolve()]
        # Protect evidence inputs too, including ancestors and partial destinations.
        for dest in (args.out.resolve(),args.out.resolve().with_name(args.out.name+'.partial')):
            for root in self.roots:
                if dest==root or dest in root.parents or root in dest.parents:raise ValueError('Output overlaps evidence input')

    def code_hashes(self):
        root=Path(__file__).resolve().parents[3]
        paths=[p for folder in ('tasks/graph/crl','evidence/graph','evidence/graph/rich','core') for p in (root/folder).glob('*.py')]
        return {p.relative_to(root).as_posix():digest(p.read_bytes()) for p in sorted(paths)}

    def dependencies(self):
        deps={}
        for key,root in zip(('graph','visibility','rich'),self.roots):
            base.verify_manifest(root)
            deps[key]=digest((root/'manifest.json').read_bytes())
        return deps

    def prepare_chapter(self,cid,shard):
        self.g,self.v,self.pins=load_world(*self.roots[:2],cid)
        self.r=load_optional(*self.roots,cid,self.pins)
        if self.pins!=shard['inputs_sha256']:
            # Content pins survive relocation, as in the public checker CLI.
            from comics_qa.tasks.graph.crl.check_crl import verify_input_pins
            verify_input_pins({'inputs_sha256':shard['inputs_sha256']},self.pins)
        self.checker=ProofChecker(self.g,self.v,rich=self.r)
        self.facts={f['fact_id']:f for f in self.g['facts']}
        self.facts.update({f['id']:f for f in self.r['facts']})
        self.certs={c['coverage_id']:c for c in self.g['coverage']}
        self.certs.update({c['id']:c for c in self.r['coverage']})

    def make_record(self,item):
        if item.get('question_type')!='graph_verified':raise ValueError('Only graph_verified GEN-2 items supported')
        request,private=base.make_record(item,parser=parse_gloss)
        expected_type={'Int':'int','Char':'char','Page':'page'}.get(item['execution']['result'].get('type'))
        if expected_type!=item['answer']['type']:raise ValueError('Answer type mismatch')
        nodes={n['id']:n for n in self.g['nodes']}
        expected_context=[{'index':i+1,'page_id':pid,'image_path':nodes[pid]['image_path'],
                           'relative_path':nodes[pid]['relative_path'],'image_sha256':nodes[pid]['image_sha256']}
                          for i,pid in enumerate(self.g['page_ids'])]
        # Absolute source paths may differ after relocation; relative paths and hashes must agree.
        fields=('index','page_id','relative_path','image_sha256')
        if [{k:p[k] for k in fields} for p in item['context']['pages']]!=[{k:p[k] for k in fields} for p in expected_context]:
            raise ValueError('Full chapter context/image binding mismatch')
        check=self.checker.check(item['execution'])
        if not check['accepted_for_generation']:raise ValueError('Independent proof check failed: '+item['item_id'])
        proof=item['execution']['proof'];facts=[self.facts[k] for k in proof['facts']]
        premises={p for f in facts for p in f['premises']}
        mentions=[m for m in self.r['mentions'] if m['id'] in premises]
        transcript_ids=premises|{m['transcript_id'] for m in mentions}
        transcripts=[t for t in self.r['transcripts'] if t['id'] in transcript_ids]
        visibility_ids=set(proof['visibility_evidence'])|premises
        visibility=[e for e in self.v['evidence'] if e['evidence_id'] in visibility_ids]
        alignment_ids={t['alignment_id'] for t in transcripts}|{e['alignment_id'] for e in visibility}
        refs=set(proof['node_refs']) if 'node_refs' in proof else set()
        refs.update(a for f in facts for a in f['args'] if isinstance(a,str))
        evidence={'fixed_answer':item['answer'],'program':item['program'],'canonical_program':item['canonical'],
            'input_artifact_hashes':{key:digest((root/'manifest.json').read_bytes()) for key,root in zip(('graph','visibility','rich'),self.roots)},
            'facts':facts,'coverage':[self.certs[k] for k in proof['certificates']],
            'visibility_evidence':visibility,
            'rich_records':transcripts+mentions,
            'alignments':[a for a in self.v['alignments'] if a['alignment_id'] in alignment_ids],
            'nodes':[n for n in self.g['nodes'] if n['id'] in refs],
            'context_images':[{'index':p['index'],'page_id':p['page_id'],'relative_path':p['relative_path'],'image_sha256':p['image_sha256']} for p in item['context']['pages']]}
        request['messages'][0]['content']=SYSTEM
        rid='verb2:'+stable([self.version,private['source_item_sha256'],request['messages'],evidence])
        request.update(request_id=rid,question_type='graph_verified',verbalization_type='qwen_paraphrase')
        private.update(request_id=rid,evidence_pack=evidence,evidence_pack_sha256=stable(evidence),independent_proof_check=check)
        return request,private


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('source','out','graphs','visibility','rich'):parser.add_argument('--'+k,type=Path,required=True)
    parser.add_argument('--chapter',action='append',default=[]);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args(argv)
    try:return base.run(args,profile=Profile(args))
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print('GEN-2 preparation error: '+str(exc),file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('Interrupted; repeat with --resume. Completed chapters retained.',file=sys.stderr);return 130

if __name__=='__main__':raise SystemExit(main())
