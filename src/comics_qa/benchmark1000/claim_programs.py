"""Source-bound typed propositions; false requires a known exact executed value."""
import copy
from comics_qa.tasks.graph.crl.language import program_hash,parse
from .branch_relations import parse_question,compile_recipe
from .complexity import bindings
from .native import execution_evidence,check_answer
from .admission_store import validate as admitted
from .recipe_engine import RecipeChecker
from .io import stable

VERSION='branch_claims.1'


def validate_spec(seed,s):
    if not isinstance(s,dict):raise ValueError('Claim signature must be an object')
    r=parse_question(seed['question'])['recipe'];kind=s.get('kind');fields={'kind','relation'}
    if kind in ('branch_final','branch_step'):
        fields|={'role','page'}
        if kind=='branch_step':fields.add('step')
        if type(s.get('role')) is not int or s['role'] not in (0,1):raise ValueError('Unknown speaker role')
        if kind=='branch_step' and (type(s.get('step')) is not int or not 1<=s['step']<=r['steps'][s['role']]):raise ValueError('Step outside declared branch scope')
        pages=[s.get('page')]
    elif kind=='final_pages':fields.add('pages');pages=s.get('pages')
    elif kind=='final_gap':fields.add('count');pages=[]
    else:raise ValueError('Unsupported claim predicate')
    if set(s)!=fields or s['relation'] not in ('eq','neq'):raise ValueError('Malformed claim signature')
    if not isinstance(pages,list) or (kind=='final_pages' and len(pages)!=2) or any(type(p) is not int or not 1<=p<=len(seed['context']['pages']) for p in pages):raise ValueError('Page argument outside supplied chapter')
    if kind=='final_gap' and (type(s['count']) is not int or s['count']<0):raise ValueError('Invalid gap argument')
    return s


def query(seed,s):
    validate_spec(seed,s);r=parse_question(seed['question'])['recipe'];kind=s['kind']
    if kind in ('branch_final','branch_step'):
        p=compile_recipe(r);step=r['steps'][s['role']] if kind=='branch_final' else s['step'];p['in']={'var':f"p{s['role']}_{step-1}"};return p
    r={**r,'kind':'branch_chain_pages' if kind=='final_pages' else 'branch_chain_gap'}
    return compile_recipe(r)


def render(s):
    neg='not ' if s['relation']=='neq' else '';role='first' if s.get('role')==0 else 'second'
    if s['kind']=='branch_final':return f"The {role} speaker's final speaking page is {neg}page {s['page']}."
    if s['kind']=='branch_step':return f"For the {role} speaker, speaking-search step {s['step']} {'does not find' if neg else 'finds'} page {s['page']}."
    if s['kind']=='final_pages':return f"The final pages in chronological order are {neg}pages {s['pages'][0]} and {s['pages'][1]}."
    return f"The number of pages strictly between the final pages is {neg}{s['count']}."


def identifier(seed,s):return 'b1000claim:'+stable([seed['item_id'],s])


def expected(seed):
    """Canonical required/optional/near-miss lists, determined before prose generation."""
    r=parse_question(seed['question'])['recipe'];v=bindings(seed);order={p['page_id']:p['index'] for p in seed['context']['pages']}
    ends=[order[v[f'p{b}_{r["steps"][b]-1}']['value']] for b in (0,1)]
    final=[{'kind':'branch_final','role':b,'page':ends[b],'relation':'eq'} for b in (0,1)]
    seq={'kind':'final_pages','pages':sorted(ends),'relation':'eq'};gap={'kind':'final_gap','count':abs(ends[0]-ends[1])-1,'relation':'eq'}
    summary,other=(seq,gap) if r['kind']=='branch_chain_pages' else (gap,seq)
    middle=[{'kind':'branch_step','role':b,'step':n+1,'page':order[v[f'p{b}_{n}']['value']],'relation':'eq'} for b in (0,1) for n in range(r['steps'][b]-1)]
    false=[{**final[b],'page':ends[1-b]} for b in (0,1)]+[{**final[0],'relation':'neq'},
           {**seq,'pages':list(reversed(seq['pages']))},{**gap,'count':gap['count']+1}]
    return {'required':final+[summary],'optional':middle+[other],'forbidden':false}


def ordering(seed,specs):
    r=parse_question(seed['question'])['recipe'];ordered=[]
    for b in (0,1):
        ordered.extend(s for s in specs['optional'] if s['kind']=='branch_step' and s['role']==b)
        ordered.append(specs['required'][b])
    ordered+=specs['required'][2:]+[s for s in specs['optional'] if s['kind']!='branch_step']+specs['forbidden']
    return [identifier(seed,s) for s in ordered]


def target(s):
    if s['kind'] in ('branch_final','branch_step'):return s['page']
    return s['pages'] if s['kind']=='final_pages' else s['count']


def truth(s,doc):
    result=doc['result']
    if result['status']!='OK' or not result['exact']:return 'unresolved'
    equal=stable(result['display'])==stable(target(s))
    return 'supported' if equal==(s['relation']=='eq') else 'contradicted'


def record(seed,s,g,v,r,cache):
    from .semantic import execute
    p=query(seed,s);key=stable(p)
    if key not in cache:
        doc,checked,_=execute('coverage_recipe',p,g,v,r)
        if not checked['proof_valid']:raise ValueError('Claim interpreter/checker disagreement')
        cache[key]=doc
    doc=cache[key]
    return {'id':identifier(seed,s),'spec':copy.deepcopy(s),'text':render(s),'engine':'coverage_recipe','program':p,
            'execution':copy.deepcopy(doc),'execution_sha256':stable(doc),'verification':truth(s,doc),
            'evidence':execution_evidence('coverage_recipe',doc,g,r)}


class Checker:
    """Never invokes the claim producer, semantic.execute or RecipeEngine."""
    def __init__(self,seed,g,v,r):
        admitted(seed)
        if not check_answer(seed['proposal'],g,v,r)['answer_supported']:raise ValueError('Sentence source answer fails independent checking')
        self.seed,self.g,self.r=seed,g,r;self.checker=RecipeChecker(g,v,r,True);self.cache={}

    def check(self,c):
        s=validate_spec(self.seed,c['spec']);p=query(self.seed,s)
        if set(c)!={'id','spec','text','engine','program','execution','execution_sha256','verification','evidence'}:raise ValueError('Malformed executable claim')
        if c['id']!=identifier(self.seed,s) or c['text']!=render(s) or c['engine']!='coverage_recipe':raise ValueError('Claim wording/identity mismatch')
        if program_hash(parse(p))!=program_hash(parse(c['program'])) or stable(c['execution'])!=c['execution_sha256']:raise ValueError('Claim program/execution binding mismatch')
        key=stable([p,c['execution']])
        if key not in self.cache:self.cache[key]=self.checker.check(c['execution'],p)
        checked=self.cache[key]
        if not checked['proof_valid']:raise ValueError('Invalid claim proof')
        value=c['execution']['result'];status='unresolved'
        if value['status']=='OK' and value['exact']:
            same=stable(value['display'])==stable(target(s))
            status=('supported' if same else 'contradicted') if s['relation']=='eq' else ('contradicted' if same else 'supported')
        if c['verification']!=status or c['evidence']!=execution_evidence('coverage_recipe',c['execution'],self.g,self.r):raise ValueError('Claim truth/provenance mismatch')
        return status
