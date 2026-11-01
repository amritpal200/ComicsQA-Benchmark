"""Bind raw model responses to packs; independently recover question semantics and claims."""
import json
from pathlib import Path
from comics_qa.tasks.graph.crl.language import parse,program_hash
from . import qwen_language as language,qwen_packs as packs,qwen_jobs as jobs
from .sentence_scoring import score as sentence_score
from .io import read,publish,stable,digest,separate


def content(raw,expected_model,prompt_tokens):
    """Keep all raw reasoning outside the answer; never repair incomplete JSON."""
    d=json.loads(raw)
    if d.get('model')!=expected_model:raise ValueError('response_model_mismatch')
    if not isinstance(d.get('choices'),list) or len(d['choices'])!=1:raise ValueError('expected_one_response_choice')
    c=d['choices'][0]
    if c.get('finish_reason')!='stop':raise ValueError('truncated_or_unfinished_response')
    m=c['message']
    if m.get('refusal'):raise ValueError('model_refusal')
    if d.get('usage',{}).get('prompt_tokens')!=prompt_tokens:raise ValueError('server_processor_token_count_mismatch')
    text=m.get('content')
    if not isinstance(text,str):raise ValueError('missing_text_response')
    text=text.strip()
    if text.startswith('<think>'):
        if '</think>' not in text:raise ValueError('unfinished_reasoning_block')
        text=text.split('</think>',1)[1].strip()
    def invalid(x):raise ValueError('nonfinite_response_json')
    obj=json.loads(text,parse_constant=invalid)
    if not isinstance(obj,dict):raise ValueError('response_must_be_object')
    return obj



def rendered_names(program,g,v):
    from comics_qa.tasks.graph.gen2.quality import normalized,form_is_visible
    forms=[]
    def visit(x):
        if isinstance(x,dict):
            if x.get('op')=='char' and isinstance(x.get('args'),list) and len(x['args'])==1 and isinstance(x['args'][0],str):forms.append(x['args'][0])
            for y in x.values():visit(y)
        elif isinstance(x,list):
            for y in x:visit(y)
    visit(program);rows=[]
    for form in sorted(set(forms)):
        owners=[n for n in g['nodes'] if n['type']=='Character' and not n['generic'] and normalized(form) in {normalized(s) for s in [n['canonical_name'],*n['aliases']]}]
        if len(owners)!=1 or not form_is_visible(v,owners[0]['id'],form):raise ValueError('generated_name_not_uniquely_readable')
        rows.append({'form':form,'identity_id':owners[0]['id'],'readable':True})
    return rows


def validate(pack,raw,model,prompt_tokens,g,v,r):
    row={'schema':'comics_qa.benchmark1000.qwen_response_check.2','pack_id':pack['pack_id'],'pack_sha256':stable(pack),
         'raw_response_sha256':stable(raw),'generation_mode':pack['mode'],'response_class':'claim_backed_sentence' if pack['mode']=='synthesis' else 'executed_paraphrase','parser_version':language.PARSER_VERSION,'status':'held','human_review':'pending','release':'not_approved'}
    packs.check(pack,g,v,r)
    try:
        obj=content(raw,model,prompt_tokens);synthesis=pack['mode']=='synthesis'
        if set(obj)!=({'question','short_answer','answer'} if synthesis else {'question'}):raise ValueError('unexpected_response_fields')
        if not isinstance(obj['question'],str):raise ValueError('question_must_be_text')
        question=obj['question'].strip();parsed=language.parse_question(question)
        seed=packs.seed(pack['source_record'],pack['mode']);t=packs.task(seed)
        if parsed['requires_roles']!=synthesis:raise ValueError('question_added_or_removed_role_answer_requirement')
        if parsed['engine']!=t['engine']:raise ValueError('question_engine_changed')
        if t['engine'] in ('crl','recipe','coverage_recipe'):
            equivalent=program_hash(parse(parsed['program']))==program_hash(parse(t['program']))
        else:
            from .native_wording import bound
            equivalent=bound(parsed,{'proof_engine':t['engine'],'program':t['program']})
        if not equivalent:raise ValueError('question_semantics_changed_even_if_answer_coincides')
        row['name_checks']=rendered_names(parsed['program'],g,v)
        row.update(question=question,question_program_sha256=stable(parsed['program']),question_alignment='verified_controlled_profile')
        if synthesis:
            result=sentence_score(pack['source_record'],obj['answer'],obj['short_answer'],g,v,r);row['claim_check']=result
            if not result['accepted_controlled_answer']:raise ValueError('sentence_claims_missing_false_or_unresolved')
            row.update(answer=obj['answer'],short_answer=obj['short_answer'])
        row['status']='verified_pending_human';row['reason']='controlled_semantics_and_facts_verified'
    except (ValueError,KeyError,TypeError) as error:row['reason']=str(error)
    return row


def ingest(request_root,response_root,bench_root,out):
    config,m,requests=jobs.run_config(response_root,request_root);pack_root=m['config']['packs_root'];ps={p['pack_id']:p for p in packs.load(pack_root)}
    if digest(Path(pack_root)/'manifest.json')!=m['config']['packs_manifest_sha256']:raise ValueError('Request pack source changed')
    root=Path(bench_root);roots=[root/p for p in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1')]
    out=separate(out,[request_root,response_root,pack_root,*roots,root/'core']);out.mkdir(parents=True,exist_ok=True)
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    worlds={};rows=[];outputs={}
    for request in requests:
        if request['request_id'] not in config['request_ids']:continue
        raw=jobs.response(response_root,request)
        if raw is None:
            row={'request_id':request['request_id'],'status':'pending','reason':'no_completed_raw_response'}
        elif raw['status']!='succeeded':
            row={'request_id':request['request_id'],'status':'held','reason':'transport_failed','transport_sha256':stable(raw)}
        else:
            pack=ps[request['pack_id']]
            if stable(pack)!=request['pack_sha256']:raise ValueError('Response pack binding changed')
            cid=pack['chapter_id']
            if cid not in worlds:
                g,v,pins=load_world(*roots[:2],cid);r=load_optional(*roots,cid,pins);worlds[cid]=(g,v,r)
            row=validate(pack,raw['raw_response'],request['payload']['model'],request['budget']['prompt_tokens'],*worlds[cid]);row['request_id']=request['request_id'];row['transport_sha256']=stable(raw)
        # A validation snapshot is immutable. To ingest newly completed requests,
        # choose a new output version; raw records and earlier snapshots stay intact.
        path='checks/'+stable(request['request_id'])+'.json';publish(out/path,row);outputs[path]=digest(out/path);rows.append(row)
    from collections import Counter
    report={'schema':'comics_qa.benchmark1000.qwen_validation_report.2','requests_manifest_sha256':digest(Path(request_root)/'manifest.json'),
            'response_config_sha256':stable(config),'counts':dict(Counter(r['status'] for r in rows)),
            'candidate_admission':'not_promoted','human_review':'pending','release':'not_approved'}
    publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
    publish(out/'manifest.json',{'schema':'comics_qa.benchmark1000.qwen_validation_store.2','outputs_sha256':outputs,'report_sha256':stable(report)})
    return report
