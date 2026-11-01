"""Reuse GEN-1 acceptance gates with explicit rich evidence and OCR-aware ablation."""
import copy
from dataclasses import replace
from ..generation.gates import Gates, PROFILE_OPS, without_pages
from ..generation.policy import stable
from ..crl import Interpreter
from ..crl.proof_checker import ProofChecker
from comics_qa.evidence.graph.rich.model import build, normalize
from name_visibility import form_is_visible, normalized
from .quality import usable_name, VERSION


class RichGates(Gates):
    profile_ops=PROFILE_OPS|{'quote','name_texts'}

    def __init__(self,graph,visibility,rich,policy,sources,alias_reviews=()):
        self.alias_reviews=alias_reviews
        self.rich=rich
        super().__init__(graph,visibility,policy,sources)

    def engine(self,g,v):
        # Every altered world recomputes its evidence; no stale OCR certificate reuse.
        r=self.rich if g is self.g and v is self.v else build(g,v,self.rich['sources'],self.rich['decisions'])
        return (Interpreter(g,v,max_steps=self.p['max_steps'],allow_closed_assumed=self.p['allow_closed_assumed'],rich=r),
                ProofChecker(g,v,max_steps=self.p['max_steps'],allow_closed_assumed=self.p['allow_closed_assumed'],rich=r))

    def world(self,pages,keep_visibility=False):
        key=(tuple(sorted(pages)),keep_visibility)
        if key not in self.world_cache:
            g,v=without_pages(self.g,self.v,pages,keep_visibility)
            if keep_visibility:
                # OCR-only baseline retains text locations and lexical name mappings,
                # but removes character depictions and human speaker associations.
                existing={f['fact_id'] for f in g['facts']}
                for f in self.g['facts']:
                    preserve=f['rel'] in ('named','alias') or f['rel']=='on_page' and self.nodes[f['args'][0]]['type']=='Text'
                    if preserve and f['fact_id'] not in existing:g['facts'].append(copy.deepcopy(f))
                original={(c['page_id'],c['family']):c for c in self.g['coverage']}
                for i,c in enumerate(g['coverage']):
                    if c['family']=='text_boxes':g['coverage'][i]=copy.deepcopy(original[c['page_id'],c['family']])
            else:
                v['alignments']=[a for a in v['alignments'] if a['page_id'] not in pages]
            # v1 families target automatic consensus; reviewed companions are rejected
            # by the builder until their counterfactual decision semantics are defined.
            self.world_cache[key]=self.engine(g,v)
            if len(self.world_cache)>8:self.world_cache.popitem(last=False)
        return self.world_cache[key]

    def name_allowed(self,cid,form):
        return usable_name(self.g,self.v,cid,form,self.alias_reviews)

    def assess(self,q):
        # Names appearing inside quoted text are still subject to the visibility rule.
        for cid,form in q.names:
            if not self.name_allowed(cid,form):
                return None,{'gate':'names','reason':'ineligible_question_name_form','family':q.family,'program':q.ast}
        question=' '+normalized(q.question)+' '
        name_refs=set(q.names)
        for n in self.nodes.values():
            if n['type']=='Character' and not n['generic']:
                for form in [n['canonical_name'],*[r['form'] for r in self.alias_reviews if r['identity_id']==n['id']]]:
                    if ' '+normalized(form)+' ' in question:
                        if not form_is_visible(self.v,n['id'],form):
                            return None,{'gate':'names','reason':'unreadable_embedded_form','family':q.family,'program':q.ast}
                        name_refs.add((n['id'],form))
        q=replace(q,names=sorted(name_refs))
        item,rejection=super().assess(q)
        if rejection:return item,rejection
        answer=item['answer']
        if answer['type']=='char':
            if not self.name_allowed(answer['identity_id'],answer['value']):
                return None,{'gate':'names','reason':'ineligible_answer_name_form','family':q.family,'program':q.ast}
            answer['accepted_forms']=[f for f in answer['accepted_forms'] if self.name_allowed(answer['identity_id'],f)]
        item['name_form_policy']='visible_canonical_or_reviewed' if self.alias_reviews else 'visible_canonical_only'
        item['alias_reviews']=list(self.alias_reviews)
        # Verify W4's actually applicable scope: every used transcript is backed by
        # equivalent full normalized Paddle/MAGI text. This is not general noise robustness.
        used=set(item['execution']['proof']['facts'])
        facts={f['id']:f for f in self.rich['facts']}
        transcripts={t['id']:t for t in self.rich['transcripts']}
        tested=[]
        for fid in used:
            f=facts.get(fid)
            if not f or f['rel']!='transcript':continue
            t=transcripts[f['premises'][0]]
            if not (normalize(t['paddle_text'])==normalize(t['magi_text'])==t['consensus']):
                return None,{'gate':'G9','reason':'per_model_transcript_disagreement','family':q.family,'program':q.ast}
            tested.append(t['id'])
        item['question_type']='graph_verified'
        item['item_id']='gen2:'+stable([VERSION,item['item_id'],self.rich['sources']])
        item['versions']['generator']=VERSION
        item['verbalization']={'mode':'template','version':VERSION}
        item['gates']['G1']['profile']='page_core_plus_verified_ocr_lexical'
        item['gates']['G8']['text_only_definition']='CKG-3 OCR/text locations and CKG-2 lexical mappings retained; character/speaker facts removed'
        item['gates']['G9']['not_applicable'].pop('W4',None)
        item['gates']['G9']['W4']={'status':'pass','method':'full normalized per-model transcript equality','transcripts':sorted(tested),
                                 'limitation':'No claim about arbitrary OCR noise; no unverified model transcript is promoted'}
        return item,None
