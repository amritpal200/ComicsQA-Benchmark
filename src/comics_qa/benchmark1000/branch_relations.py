"""Two independently necessary speaking chains, with explicit relational clauses."""
import json
import re
from comics_qa.tasks.graph.crl.language import call, infer
from .native_wording import speaker
from .io import stable

VERSION = 'branch_relations.1'
KINDS = ('branch_chain_pages', 'branch_chain_gap')
FORMATS = {'branch_chain_pages':'sequence','branch_chain_gap':'count'}
J = r'("(?:[^"\\]|\\.)*")'
WORDS = ('one','two','three','four','five','six')


def syntax(r):
    if not isinstance(r,dict) or set(r)!={'kind','references','start','end','steps','profile'} or r['profile']!=VERSION or r['kind'] not in KINDS:
        raise ValueError('Unknown branch recipe')
    if not isinstance(r['references'],list) or not isinstance(r['steps'],list) or len(r['references'])!=2 or len(r['steps'])!=2 or any(type(s) is not int or s not in (2,3) for s in r['steps']): raise ValueError('Two branches of two/three navigations required')
    for ref in r['references']:
        if not isinstance(ref,dict) or set(ref)!={'quote','page'} or not isinstance(ref['quote'],str) or not ref['quote'].strip() or type(ref['page']) is not int or ref['page']<1: raise ValueError('Invalid branch quote reference')
    if any(type(r[k]) is not int for k in ('start','end')) or r['start']<=max(x['page'] for x in r['references']) or r['end']<r['start']: raise ValueError('Invalid branch range')
    return r


def labels(r):
    return ['branch:0','branch:1']+[f'navigate:{b}:{n}' for b,steps in enumerate(r['steps']) for n in range(steps)]


def compile_recipe(recipe,bypass=None):
    r=syntax(recipe)
    if bypass is not None and bypass not in labels(r): raise ValueError('Unknown branch intervention')
    bindings=[]
    def bind(name,expr):bindings.append({'name':name,'value':expr});return {'var':name}
    chars=[bind('c'+str(n),speaker(ref['quote'],ref['page'])) for n,ref in enumerate(r['references'])]
    end=[];span=call('pages',r['start'],r['end'])
    for b,steps in enumerate(r['steps']):
        previous=call('page',r['start']-1)
        for n in range(steps):
            expr=previous if bypass==f'navigate:{b}:{n}' else call('first',call('pages_speaking',chars[b],call('span_after',previous,within=span)))
            previous=bind(f'p{b}_{n}',expr)
        end.append(previous)
    a,b=end
    if bypass=='branch:0':a=b
    if bypass=='branch:1':b=a
    result=(call('filter',span,{'lambda':{'param':'p','body':call('or',call('eq',{'var':'p'},a),call('eq',{'var':'p'},b))}})
            if r['kind']=='branch_chain_pages' else call('gap',a,b))
    program={'let':bindings,'in':result};infer(program);return program


def render(recipe):
    r=syntax(recipe);a,b=r['references']
    intro=f'Identify the speakers of the texts {json.dumps(a["quote"],ensure_ascii=False)} on page {a["page"]} and {json.dumps(b["quote"],ensure_ascii=False)} on page {b["page"]}, respectively. '
    intro+=f'Search only the inclusive range from page {r["start"]} to page {r["end"]}. Keep the first and second person’s searches separate. '
    clauses=[];at=0
    for branch,steps in enumerate(r['steps']):
        who='first' if branch==0 else 'second'
        for n in range(steps):
            prefix=f'Condition {WORDS[at]}: for the {who} person, '
            text=(f'start immediately before page {r["start"]} and find their first speaking page inside the range.' if n==0 else
                  f'start strictly after the page found in condition {WORDS[at-1]} and find that same person’s next speaking page inside the range.')
            clauses.append(prefix+text);at+=1
    tail=('give the two distinct final page positions in increasing chapter order.' if r['kind']=='branch_chain_pages' else 'how many pages lie strictly between the two final pages?')
    return intro+' '.join(clauses)+' After both searches finish, '+tail


def parse_question(question):
    intro=re.match(r'Identify the speakers of the texts '+J+r' on page ([1-9]\d*) and '+J+r' on page ([1-9]\d*), respectively\. Search only the inclusive range from page ([1-9]\d*) to page ([1-9]\d*)\. Keep the first and second person’s searches separate\. ',question)
    if not intro: raise ValueError('Unknown branch wording')
    refs=[{'quote':json.loads(intro[1]),'page':int(intro[2])},{'quote':json.loads(intro[3]),'page':int(intro[4])}]
    for kind in KINDS:
        for steps in ([2,2],[2,3],[3,2],[3,3]):
            r={'kind':kind,'references':refs,'start':int(intro[5]),'end':int(intro[6]),'steps':steps,'profile':VERSION}
            try:
                if render(r)!=question:continue
            except ValueError:continue
            ls=labels(r)
            return {'kind':kind,'engine':'coverage_recipe','program':compile_recipe(r),'recipe':r,'profile_version':VERSION,
                    'relaxation_labels':ls,'relaxations':[('coverage_recipe',compile_recipe(r,label)) for label in ls],
                    'alternative_relaxations':[],'allow_ambiguous_relaxations':False,'min_pages':3}
    raise ValueError('Unknown branch condition/scope/order')


def resolved(item,parsed):
    from .complexity import bindings
    values=bindings(item);r=parsed['recipe'];entries=[]
    for b,ref in enumerate(r['references']):
        path=[values[f'p{b}_{n}']['value'] for n in range(r['steps'][b])]
        entries.append([ref['page'],values['c'+str(b)]['value'],r['steps'][b],path])
    return [item['chapter_id'],r['kind'],sorted(entries),r['start'],item['execution']['result']['value']]


def certificate(item,parsed,checks):
    r=parsed['recipe'];ls=parsed['relaxation_labels'];rows=checks['clause_removals']
    if len(rows)!=len(ls):raise ValueError('Incomplete branch dependency checks')
    required=all(x['necessary'] and x['result']['status'] in ('OK','EMPTY') for x in rows)
    pages=checks['necessary_pages'];visual=checks['necessary_visual_pages'];order={p['page_id']:p['index'] for p in item['context']['pages']}
    span=max((order[p] for p in pages),default=0)-min((order[p] for p in pages),default=0)
    words=len(item['question'].split());nav=sum(r['steps']);ok=required and len(visual)>=3
    long={'eligible':ok and nav>=3 and len(set(pages))>=3 and span>=5 and words>=81,
          'necessary_clauses':nav if required else 0,'necessary_pages':pages,'page_span':span,'word_count':words,
          'length_class':'XL' if words>250 else 'L' if words>=81 else 'short',
          'certificate_method':'checked_navigation_and_branch_bypasses_plus_visual_ablation.1'}
    return {'version':VERSION,'method':'parallel_chain_dependency_and_visual_ablation.1','certified':ok,
            'meaningful_hops':max(r['steps']) if required else None,'branch_count':2 if required else None,
            'branch_depths':list(r['steps']),'combine_count':1,'necessary_steps':ls if required else [],
            'necessary_pages':pages,'necessary_visual_pages':visual,'page_span':span,'word_count':words,
            'primary_group':'branch_combine','bypass_checks_sha256':stable(rows),'long_relational':long,
            'definition':'Maximum independently necessary branch navigation depth; parallel lengths are not added. Combine and navigation totals are separate.',
            'limitations':'Operational bypass and visual-support certificates, not universal cognitive difficulty or narrative entailment.'}
