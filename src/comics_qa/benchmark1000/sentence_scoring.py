"""Independent bounded claim extraction and proof-backed answer scoring; no LLM judge."""
import re
import unicodedata
from pathlib import Path
from . import claim_programs as cp
from . import sentence_plans as plans
from .evaluation import exact
from .io import stable,read,digest

ROLES={'first':0,'second':1}
R=r'(first|second)'


def extract(clause):
    """No expected answer/claim list is supplied to this parser."""
    t=unicodedata.normalize('NFKC',clause).replace('’',"'").strip().casefold().rstrip('.!?').strip()
    patterns=[r"the "+R+r" speaker's final speaking page is (not )?page ([1-9]\d*)",
              r'the final speaking page for the '+R+r' speaker is (not )?page ([1-9]\d*)',
              r'for the '+R+r' speaker, the final speaking page is (not )?page ([1-9]\d*)']
    for pattern in patterns:
        m=re.fullmatch(pattern,t)
        if m:return {'kind':'branch_final','role':ROLES[m[1]],'relation':'neq' if m[2] else 'eq','page':int(m[3])}
    m=re.fullmatch(r'for the '+R+r' speaker, speaking-search step ([1-9]\d*) (finds|does not find) page ([1-9]\d*)',t)
    if m:return {'kind':'branch_step','role':ROLES[m[1]],'step':int(m[2]),'relation':'neq' if m[3]=='does not find' else 'eq','page':int(m[4])}
    m=re.fullmatch(r'the final pages in chronological order are (not )?pages ([1-9]\d*) and ([1-9]\d*)',t)
    if m:return {'kind':'final_pages','relation':'neq' if m[1] else 'eq','pages':[int(m[2]),int(m[3])]}
    m=re.fullmatch(r'chronologically, the final pages are (not )?([1-9]\d*) and ([1-9]\d*)',t)
    if m:return {'kind':'final_pages','relation':'neq' if m[1] else 'eq','pages':[int(m[2]),int(m[3])]}
    m=re.fullmatch(r'the number of pages strictly between the final pages is (not )?(\d+)',t)
    if m:return {'kind':'final_gap','relation':'neq' if m[1] else 'eq','count':int(m[2])}
    m=re.fullmatch(r'there are (\d+) pages strictly between the final pages',t)
    if m:return {'kind':'final_gap','relation':'eq','count':int(m[1])}
    return None


def score(p,text,short_answer,g,v,r):
    checked=plans.check(p,g,v,r)
    if not isinstance(text,str):raise ValueError('Sentence answer must be text')
    seed=p['source'];known={stable(c['program']):c['execution'] for rows in p['claims'].values() for c in rows}
    assertions=[];unresolved=[];supported=set();stated=set();false=0
    for clause in [c.strip() for c in re.split(r'(?<=[.!?])\s+|[\r\n]+',text) if c.strip()]:
        s=extract(clause)
        if s is None:unresolved.append({'text':clause,'reason':'outside_controlled_claim_grammar'});continue
        # The declared last search step is an answer-independent alias for final.
        if s['kind']=='branch_step' and s['step']==cp.parse_question(seed['question'])['recipe']['steps'][s['role']]:
            s={k:v for k,v in s.items() if k!='step'};s['kind']='branch_final'
        try:
            q=cp.query(seed,s);doc=known.get(stable(q))
            if doc is None:raise ValueError('No checked query for assertion')
        except ValueError as e:unresolved.append({'text':clause,'reason':str(e)});continue
        status=cp.truth(s,doc);key=stable(s);stated.add(key)
        assertions.append({'text':clause,'spec':s,'status':status,'query_execution_sha256':stable(doc)})
        if status=='supported':supported.add(key)
        elif status=='contradicted':false+=1
        else:unresolved.append({'text':clause,'reason':'query_value_unresolved'})
    required={stable(c['spec']) for c in p['claims']['required']};optional={stable(c['spec']) for c in p['claims']['optional']};forbidden={stable(c['spec']) for c in p['claims']['forbidden']}
    short_ok=exact(p['short_answer_format'],short_answer,p['short_answer']['value'])
    complete=required<=supported;accepted=short_ok and complete and false==0 and not unresolved
    return {'plan_id':p['plan_id'],'plan_sha256':stable(p),'answer_sha256':stable(text),'submitted_short_answer_sha256':stable(short_answer),
            'short_answer_correct':short_ok,'required_claim_recall':len(required&supported)/len(required),
            'optional_claims_covered':len(optional&supported),'all_required_correct':complete,
            'forbidden_claims_stated':len(forbidden&stated),'detected_false_assertions':false,
            'unresolved_clauses':unresolved,'unsupported_assertions':None if unresolved or not assertions else false,
            'fully_factual_within_checked_grammar':None if unresolved or not assertions else false==0,
            'accepted_controlled_answer':accepted,'human_review':'pending','release':'not_approved',
            'assertions':assertions,'plan_check_sha256':stable(checked),
            'limitation':'Only the registered claim grammar and signatures are checked; unknown prose is held, not certified factual'}


def batch(store,bench_root,responses_path):
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    ps=plans.load(store);responses=read(responses_path)
    if set(responses)!={'schema','store_manifest_sha256','responses'} or responses['schema']!='comics_qa.benchmark1000.sentence_responses.1' or responses['store_manifest_sha256']!=digest(Path(store)/'manifest.json') or not isinstance(responses['responses'],list):raise ValueError('Invalid or stale sentence responses')
    rows={}
    for row in responses['responses']:
        if set(row)!={'plan_id','plan_sha256','answer','short_answer'} or row['plan_id'] in rows:raise ValueError('Invalid/duplicate sentence response')
        rows[row['plan_id']]=row
    if set(rows)-{p['plan_id'] for p in ps}:raise ValueError('Unknown response plan')
    root=Path(bench_root);roots=[root/x for x in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')];worlds={};results=[]
    for p in ps:
        cid=p['chapter_id']
        if cid not in worlds:
            g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins);worlds[cid]=(g,v,r)
        row=rows.get(p['plan_id'])
        if row and row['plan_sha256']!=stable(p):raise ValueError('Response targets a different plan version')
        result=score(p,row['answer'] if row else '',row['short_answer'] if row else None,*worlds[cid]);result['missing_response']=row is None;results.append(result)
    n=len(results)
    return {'schema':'comics_qa.benchmark1000.sentence_scores.1','store_manifest_sha256':digest(Path(store)/'manifest.json'),'responses_sha256':digest(responses_path),
            'plans':n,'missing':sum(x['missing_response'] for x in results),'accepted_controlled_answers':sum(x['accepted_controlled_answer'] for x in results),
            'short_answer_accuracy':sum(x['short_answer_correct'] for x in results)/n if n else None,
            'mean_required_recall':sum(x['required_claim_recall'] for x in results)/n if n else None,
            'items':results,'human_review':'pending','release':'not_approved'}
