"""Executable GEN-1 gates; all original and counterfactual answers are checked."""
import copy
import re
from collections import OrderedDict
from ..crl import Interpreter
from ..crl.proof_checker import ProofChecker
from ..crl.language import canonical, program_hash, VERSION as CRL_VERSION
from name_visibility import form_is_visible, summarize, normalized
from .policy import VERSION, stable

VISUAL = {'on_page','is_char','present','spoken_by','is_line','speaks_on','co_present','has_tail'}
STRUCTURE = {'page_in','next_page'}
PROFILE_OPS = {'count','texts','apps','line_count','char','page','ctx','speaker_char','the',
               'lines','page_of','next_app','pages_with','at_least','apps_of','compare',
               'filter','is_named','distinct','map','chars','intersect'}


def operations(node):
    if not isinstance(node,dict): return set()
    found={node['op']} if 'op' in node else set()
    for value in node.values():
        if isinstance(value,dict): found.update(operations(value))
        elif isinstance(value,list):
            for child in value: found.update(operations(child))
    return found


def without_pages(graph, visibility, removed, keep_visibility=False):
    """Hide visual evidence, retaining chapter positions (blank placeholders).

    Deleting facts also deletes every derived dependent fact. This is a private
    ablation world, never written over the input graph. Coverage becomes absent.
    """
    g=copy.deepcopy(graph);v=copy.deepcopy(visibility);removed=set(removed)
    deleted={f['fact_id'] for f in g['facts'] if f['rel'] not in STRUCTURE and set(f['page_ids']) & removed}
    while True:
        extended=deleted | {f['fact_id'] for f in g['facts'] if set(f['premises']) & deleted}
        if extended==deleted: break
        deleted=extended
    g['facts']=[f for f in g['facts'] if f['fact_id'] not in deleted]
    for c in g['coverage']:
        if c['page_id'] in removed and c['family']!='page_sequence': c['status']='absent'
    if not keep_visibility:
        v['evidence']=[e for e in v['evidence'] if e['page_id'] not in removed]
        v['visibility']=summarize(g,v['evidence'])
    return g,v


def same_answer(a,b):
    return b['status']=='OK' and b['exact']==a['exact'] and b['type']==a['type'] and b['value']==a['value']


class Gates:
    def __init__(self,graph,visibility,policy,sources):
        self.g=graph;self.v=visibility;self.p=policy;self.sources=sources
        self.base=self.engine(graph,visibility);self.world_cache=OrderedDict()
        self.nodes={n['id']:n for n in graph['nodes']};self.facts=self.base[0].facts

    def engine(self,g,v):
        return (Interpreter(g,v,max_steps=self.p['max_steps'],allow_closed_assumed=self.p['allow_closed_assumed']),
                ProofChecker(g,v,max_steps=self.p['max_steps'],allow_closed_assumed=self.p['allow_closed_assumed']))

    def run(self,ast,engine=None):
        engine=engine or self.base
        doc=engine[0].execute(ast)
        if doc['result']['status']=='ERROR': raise RuntimeError('Generated program execution error: '+canonical(ast)+' '+doc['result']['reason'])
        check=engine[1].check(doc)
        if not check['proof_valid']: raise RuntimeError('CRL disagreement blocks generation: '+str(check['errors']))
        return doc,check

    def world(self,pages,keep_visibility=False):
        key=(tuple(sorted(pages)),keep_visibility)
        if key not in self.world_cache:
            self.world_cache[key]=self.engine(*without_pages(self.g,self.v,pages,keep_visibility))
            if len(self.world_cache)>8: self.world_cache.popitem(last=False)
        return self.world_cache[key]

    def assess(self,q):
        key=program_hash(q.ast);gates={}
        def reject(gate,reason,**data):
            return None,{'program_sha256':key,'program':canonical(q.ast),'family':q.family,'strategy':q.strategy,
                         'gate':gate,'reason':reason,**data}
        if not operations(q.ast)<=getattr(self,'profile_ops',PROFILE_OPS): return reject('G1','operation_outside_generation_profile')
        if q.level not in ('L1','L2') or len(q.clauses)!=len(q.relaxations): return reject('G1','invalid_shape_contract')
        doc,check=self.run(q.ast);answer=doc['result'];proof=doc['proof']
        gates['G1']={'status':'pass','profile':'page_core_HV'}
        if not check['accepted_for_generation']: return reject('G2',answer['status'] if answer['status']!='OK' else 'ineligible_answer')
        gates['G2']={'status':'pass','exact':answer['exact']}
        gates['G3']={'status':'pass','basis':'checked selection/margin or scalar value'}
        gates['G4']={'status':'pass','checker_version':check['checker_version']}
        gates['G5']={'status':'pass','certificate_ids':proof['certificates']}
        for cid,form in q.names:
            if not form_is_visible(self.v,cid,form): return reject('names','unreadable_question_form')
            anchor_doc,_=self.run({'op':'char','args':[form]});anchor=anchor_doc['result']
            if anchor['status']!='OK' or anchor['value']!=cid: return reject('names','ambiguous_question_form')
        if answer['type']=='Char' and not form_is_visible(self.v,answer['value'],answer['display']): return reject('names','unreadable_answer_form')
        if q.target_answer is not None and answer['value']!=q.target_answer: return reject('G2','answer_first_target_mismatch')
        if answer['type']=='Char' and any(cid==answer['value'] for cid,_ in q.names): return reject('G8','answer_is_input_identity')
        if answer['type']=='Char' and (' '+normalized(answer['display'])+' ') in (' '+normalized(q.question)+' '): return reject('G8','answer_name_in_question')
        if answer['type'] in ('Int','Page') and re.search(r'(?<!\w)'+re.escape(str(answer['display']))+r'(?!\w)',q.question):
            return reject('G8','answer_number_in_question')
        if answer['type']=='Int' and answer['value'] not in self.p['count_targets']: return reject('G8','count_outside_target_distribution')
        necessity=[]
        for label,relaxed in zip(q.clauses,q.relaxations):
            relaxed_doc,_=self.run(relaxed);value=relaxed_doc['result']
            if same_answer(answer,value): return reject('G6','redundant_clause',clause=label)
            # An open relaxed domain cannot establish that the clause was necessary.
            if value['status']=='UNKNOWN': return reject('G6','unverifiable_clause_necessity',clause=label)
            necessity.append({'removed_clause':label,'program':canonical(relaxed),'result':value})
        gates['G6']={'status':'pass','mode':'clause_removal' if q.clauses else 'atomic_query_shape',
                     'removals':necessity,'elimination_profile':q.elimination}
        visual_pages=sorted({p for fid in proof['facts'] if self.facts[fid]['rel'] in VISUAL for p in self.facts[fid]['page_ids']},key=self.g['page_ids'].index)
        if not visual_pages: return reject('G8','no_visual_support')
        if q.level!='L1' and len(visual_pages)<2: return reject('G8','single_page_multi_step_shortcut')
        if not set(proof['key_support_pages'])<=set(self.g['page_ids']): return reject('G7','support_outside_context')
        # Range certificates also carry necessary negative evidence; test them too.
        cov={c['coverage_id']:c for c in self.base[0].certs.values()}
        evidence_pages=set(proof['key_support_pages']) | {cov[c]['page_id'] for c in proof['certificates'] if cov[c]['family']!='page_sequence'}
        if len(evidence_pages)>self.p['max_worlds']: return reject('G7','ablation_world_budget')
        ablations=[];necessary=[]
        for pid in sorted(evidence_pages,key=self.g['page_ids'].index):
            variant,_=self.run(q.ast,self.world([pid]));changed=not same_answer(answer,variant['result'])
            ablations.append({'removed_page_id':pid,'result':variant['result'],'answer_changes_or_unknown':changed})
            if changed: necessary.append(pid)
        if not necessary: return reject('G7','no_necessary_page')
        if q.level!='L1' and len(set(necessary)&set(visual_pages))<2: return reject('G7','fewer_than_two_necessary_visual_pages')
        gates['G7']={'status':'pass','page_ablations':ablations,'necessary_pages':necessary,
                     'redundant_pages':[p for p in sorted(evidence_pages,key=self.g['page_ids'].index) if p not in necessary],
                     'context_policy':'full chapter; visual ablation retains page positions'}
        anchor_tests=[]
        if q.level!='L1':
            for index in sorted(set(q.anchors)):
                pid=self.g['page_ids'][index-1]
                variant,_=self.run(q.ast,self.world([p for p in self.g['page_ids'] if p!=pid],True))
                if same_answer(answer,variant['result']): return reject('G8','anchor_page_alone_solves')
                anchor_tests.append({'anchor_page_id':pid,'result':variant['result']})
        text_only,_=self.run(q.ast,self.world(self.g['page_ids'],True))
        if same_answer(answer,text_only['result']): return reject('G8','lexical_evidence_alone_solves')
        gates['G8']={'status':'pass','anchor_only':anchor_tests,'text_only':text_only['result'],
                     'text_only_definition':'CKG-2 lexical readability retained; human visual relations removed',
                     'two_option_and_frequency':'enforced by selection'}
        # The core profile has no uncertain linker/order/panel/quote/spatial facts.
        # Do not invent perturbations of data that is absent. Check representation
        # invariance separately; record W1-W6 as inapplicable, not sampled noise worlds.
        shuffled=copy.deepcopy(self.g)
        for field in ('facts','nodes','coverage'): shuffled[field]=list(reversed(shuffled[field]))
        robust,_=self.run(q.ast,self.engine(shuffled,self.v))
        if not same_answer(answer,robust['result']): return reject('G9','representation_order_instability')
        gates['G9']={'status':'pass','applicable_noise_worlds':0,'noise_invariance_fraction':None,
                     'not_applicable':{'W1':'exact human identities only','W2':'no within-page order',
                      'W3':'no panel assignments','W4':'no quote/transcript anchors; exact lexical visibility checked by CKG-2',
                      'W5':'no A/M support facts','W6':'no spatial comparisons'},
                     'representation_worlds':1,'representation_invariance_fraction':1.0}
        # Canonical AST is tied to a fixed, versioned template; Qwen round-trip is VERB-1.
        gates['G10']={'status':'pending_VERB-1','mode':'deterministic_template'}
        gates['G11']={'status':'pending_selection'};gates['G12']={'status':'pending_human_review'}
        displayed=answer['display'];typ={'Int':'int','Page':'page','Char':'char','Bool3':'bool','Cmp':'cmp'}[answer['type']]
        aliases=[]
        if typ=='char': aliases=next(v['verified_forms'] for v in self.v['visibility'] if v['identity_id']==answer['value'])
        domain=len(self.g['page_ids']) if typ=='page' else len(self.p['count_targets']) if typ=='int' else 2 if typ=='bool' else 3 if typ=='cmp' else sum(bool(v['verified_forms']) for v in self.v['visibility'])
        item_id='q:'+stable([VERSION,key,self.sources,self.p,self.g['page_ids'],q.question])
        doc['inputs_sha256']=self.sources
        check['execution_sha256']=stable(doc)
        context=[{'index':i+1,'page_id':pid,'image_path':self.nodes[pid]['image_path'],
                  'relative_path':self.nodes[pid]['relative_path'],'image_sha256':self.nodes[pid]['image_sha256']} for i,pid in enumerate(self.g['page_ids'])]
        item={'item_id':item_id,'chapter_id':self.g['chapter_id'],'split':self.g['split'],'family':q.family,
              'strategy':q.strategy,'level':None,'scope_tier':'single_page' if q.level=='L1' else 'multi_page','context':{'pages':context,'page_indexing':'1-based context images; spread counts once'},
              'question':q.question,'answer':{'type':typ,'value':displayed,'identity_id':answer['value'] if typ=='char' else None,'accepted_forms':aliases},
              'evaluation':{'method':'normalized_exact' if typ=='char' else 'exact','normalization':'CKG-2 name normalization' if typ=='char' else None,
                            'answer_space_size':domain,'chance_level':1/domain if domain else None,'chance_model':'uniform configured typed domain'},
              'two_option':domain==2,'program':doc['program'],'canonical':doc['canonical'],'program_sha256':key,
              'execution':doc,'proof_check':check,'gates':gates,'names_in_question':[{'identity_id':c,'form':f} for c,f in q.names],
              'dimensions':{'visual_support_pages':visual_pages,'necessary_pages':necessary,'context_pages':len(context),
                            'trust_min':proof['trust_min'],'clause_count':len(q.clauses),'operation_steps':len(proof['steps']),
                            'visual_page_span':max(self.g['page_ids'].index(p) for p in visual_pages)-min(self.g['page_ids'].index(p) for p in visual_pages)+1},
              'review':{'status':'pending','reviewers':[]},'verbalization':{'mode':'template','version':VERSION},
              'versions':{'generator':VERSION,'crl':CRL_VERSION,'checker':check['checker_version']}}
        return item,None
