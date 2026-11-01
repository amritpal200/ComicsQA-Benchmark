"""Preflighted request manifests and append-only, bounded OpenAI-compatible jobs."""
import fcntl
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from . import qwen_packs as packs,qwen_runtime as runtime
from .io import stable,read,publish,digest,encoded,separate,verify_manifest,member

REQUESTS='comics_qa.benchmark1000.qwen_requests.2'


def prepare(pack_root,profile_path,out,limit=2):
    if type(limit) is not int or limit<0:raise ValueError('Request limit must be nonnegative; zero explicitly selects all')
    pack_root=Path(pack_root).resolve();p,meta=runtime.profile(profile_path);ps=packs.load(pack_root);ps=sorted(ps,key=lambda p:p['pack_id'])
    if limit:ps=ps[:limit]
    out=separate(out,[pack_root,profile_path,p['model_path']]);out.mkdir(parents=True,exist_ok=True)
    config={'version':'qwen_requests.2','packs_root':str(pack_root),'packs_manifest_sha256':digest(pack_root/'manifest.json'),
            'profile':p,'model_metadata':meta,'selected_packs':{x['pack_id']:stable(x) for x in ps}}
    import importlib.metadata
    with (out/'.request-writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config);outputs={};proc=None
        for pack in ps:
            payload=runtime.payload(pack,p);request_id='b1000request:'+stable([pack['pack_id'],payload,config]);path=out/'requests'/(stable(request_id)+'.json')
            if path.exists():
                row=read(path)
                if row['request_id']!=request_id or row['payload']!=payload or row['pack_sha256']!=stable(pack):raise ValueError('Stale request checkpoint')
            else:
                if proc is None:proc=runtime.processor(p['model_path'])
                budget=runtime.measure(payload,p,proc)
                row={'request_id':request_id,'pack_id':pack['pack_id'],'pack_sha256':stable(pack),'payload':payload,'payload_sha256':stable(payload),
                     'runtime_config_sha256':stable(config),'budget':budget,'processor_version':importlib.metadata.version('transformers'),
                     'status':'preflighted_not_inferred'}
                publish(path,row)
            outputs[str(path.relative_to(out))]=digest(path)
        report={'requests':len(ps),'status':'preflighted_not_inferred','no_silent_truncation':True}
        publish(out/'report.json',report);outputs['report.json']=digest(out/'report.json')
        publish(out/'manifest.json',{'schema':REQUESTS,'config':config,'config_sha256':stable(config),'outputs_sha256':outputs})
    return report


def load(root):
    root=Path(root).resolve();m=verify_manifest(root);cfg=m['config']
    if m.get('schema')!=REQUESTS or read(root/'config.json')!=cfg or stable(cfg)!=m['config_sha256']:raise ValueError('Invalid Qwen requests')
    rows=[read(member(root,n)) for n in sorted(m['outputs_sha256']) if n.startswith('requests/')]
    if {r['pack_id']:r['pack_sha256'] for r in rows}!=cfg['selected_packs'] or len(rows)!=len(cfg['selected_packs']):raise ValueError('Incomplete request/pack binding')
    pack_root=cfg['packs_root']
    if digest(Path(pack_root)/'manifest.json')!=cfg['packs_manifest_sha256']:raise ValueError('Request pack source changed')
    ps={p['pack_id']:p for p in packs.load(pack_root)}
    for r in rows:
        if stable(ps[r['pack_id']])!=r['pack_sha256'] or runtime.payload(ps[r['pack_id']],cfg['profile'])!=r['payload']:raise ValueError('Request does not match its bound task/prompt')
        if r['payload_sha256']!=stable(r['payload']) or r['runtime_config_sha256']!=m['config_sha256'] or r['status']!='preflighted_not_inferred':raise ValueError('Request fingerprint mismatch')
        if r['request_id']!='b1000request:'+stable([r['pack_id'],r['payload'],cfg]):raise ValueError('Request identity mismatch')
        b=r['budget'];p=cfg['profile']
        if b['method']!='actual_local_processor_expanded_tokens.1' or type(b['prompt_tokens']) is not int or b['prompt_tokens']<1 or b['prompt_tokens']+p['max_new_tokens']>p['max_context_tokens']:raise ValueError('Invalid exact token budget')
    return m,rows


def headers():
    result={'Content-Type':'application/json'};key=os.environ.get('BENCHMARK1000_API_KEY')
    if key:result['Authorization']='Bearer '+key
    return result


def server(profile):
    url=profile['endpoint'].rsplit('/chat/completions',1)[0]+'/models'
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers()),timeout=profile['timeout_seconds']) as response:raw=response.read().decode()
    data=json.loads(raw);matches=[x for x in data['data'] if x['id']==profile['served_model']]
    if len(matches)!=1:raise ValueError('Configured served model not listed by endpoint')
    actual=matches[0].get('max_model_len')
    if type(actual) is not int or actual<profile['max_context_tokens']:raise ValueError('Server must report a sufficient actual max_model_len')
    return {'endpoint':url,'served_model':profile['served_model'],'max_model_len':actual,'raw_response':raw}


def response(root,row):
    directory=Path(root)/'responses'/stable(row['request_id']);done=directory/'completed.json'
    if not done.exists():return None
    completed=read(done)
    if completed['request_id']!=row['request_id'] or completed['payload_sha256']!=row['payload_sha256']:raise ValueError('Misbound completed response')
    result_path=member(root,completed['attempt_path'])
    if digest(result_path)!=completed['attempt_sha256']:raise ValueError('Raw response artifact changed')
    result=read(result_path)
    if result['request_id']!=row['request_id'] or result['payload_sha256']!=row['payload_sha256'] or result['status']!=completed['status']:raise ValueError('Misbound raw response')
    return result


def send(row,profile,out,retry_ambiguous=False):
    directory=Path(out)/'responses'/stable(row['request_id']);directory.mkdir(parents=True,exist_ok=True)
    existing=response(out,row)
    if existing:return existing['status']
    starts=sorted(directory.glob('attempt-*.start.json'))
    for path in starts:
        end=path.with_name(path.name.replace('.start.json','.result.json'))
        if not end.exists():
            if not retry_ambiguous:return 'ambiguous'
            publish(end,{'request_id':row['request_id'],'payload_sha256':row['payload_sha256'],'status':'ambiguous','error':'interrupted_after_request_started','raw_response':None})
    results=[read(p) for p in sorted(directory.glob('attempt-*.result.json'))]
    if results and results[-1]['status']=='ambiguous' and not retry_ambiguous:return 'ambiguous'
    if results and results[-1]['status'] in ('succeeded','failed'):
        last_path=sorted(directory.glob('attempt-*.result.json'))[-1]
        publish(directory/'completed.json',{'request_id':row['request_id'],'payload_sha256':row['payload_sha256'],'status':results[-1]['status'],
                'attempt_path':str(last_path.relative_to(out)),'attempt_sha256':digest(last_path)})
        return results[-1]['status']

    for attempt in range(len(starts)+1,profile['max_attempts']+1):
        begin=directory/f'attempt-{attempt:03d}.start.json';end=directory/f'attempt-{attempt:03d}.result.json'
        publish(begin,{'request_id':row['request_id'],'payload_sha256':row['payload_sha256'],'attempt':attempt,'started_unix_utc':time.time()})
        started=time.monotonic()
        h=headers();h['Idempotency-Key']=row['request_id']
        req=urllib.request.Request(profile['endpoint'],data=encoded(row['payload']).encode(),headers=h)
        try:
            with urllib.request.urlopen(req,timeout=profile['timeout_seconds']) as http:raw=http.read().decode()
            result={'status':'succeeded','raw_response':raw}
        except urllib.error.HTTPError as e:
            raw_error=e.read().decode(errors='replace');e.close()
            result={'status':'retryable' if e.code in (408,429) or e.code>=500 else 'failed','http_status':e.code,'raw_response':raw_error}
        except (urllib.error.URLError,TimeoutError,OSError) as e:
            result={'status':'ambiguous','error':type(e).__name__,'raw_response':None}
        result.update(request_id=row['request_id'],payload_sha256=row['payload_sha256'],elapsed_seconds=time.monotonic()-started);publish(end,result);results.append(result)
        if result['status']=='succeeded' or result['status']=='failed':break
        if result['status']=='ambiguous' and not retry_ambiguous:return 'ambiguous'
        if attempt<profile['max_attempts']:time.sleep(min(2**(attempt-1),5))
    # If the last attempt is ambiguous, require explicit retry authorization or
    # report terminal failure after the configured attempt cap, never certainty.
    if not results:return 'pending'
    last=results[-1];last_path=sorted(directory.glob('attempt-*.result.json'))[-1]
    if last['status'] not in ('succeeded','failed'):
        terminal=directory/'terminal.json';publish(terminal,{**last,'status':'failed','error':'attempt_budget_exhausted','last_outcome':last['status']});last_path=terminal;last=read(terminal)
    publish(directory/'completed.json',{'request_id':row['request_id'],'payload_sha256':row['payload_sha256'],'status':last['status'],
            'attempt_path':str(last_path.relative_to(out)),'attempt_sha256':digest(last_path)})
    return last['status']


def run(request_root,out,max_requests=2,shard=0,shards=1,dry_run=False,retry_ambiguous=False):
    if any(type(n) is not int for n in (max_requests,shard,shards)) or max_requests<0 or shards<1 or not 0<=shard<shards:raise ValueError('Invalid request execution/shard limits')
    request_root=Path(request_root).resolve();m,rows=load(request_root);p=m['config']['profile']
    if runtime.metadata(p['model_path'])!=m['config']['model_metadata']:raise ValueError('Model/processor metadata changed since token preflight')
    rows=[r for r in rows if int(stable(r['request_id']),16)%shards==shard]
    out=separate(out,[request_root,p['model_path']])
    config={'schema':'comics_qa.benchmark1000.qwen_run.2','request_root':str(request_root),'requests_manifest_sha256':digest(request_root/'manifest.json'),
            'runtime_config_sha256':m['config_sha256'],'shard':shard,'shards':shards,'request_ids':sorted(r['request_id'] for r in rows)}
    if dry_run:return {'status':'dry_run_no_http','requests_in_shard':len(rows),'max_new_requests':max_requests,'endpoint':p['endpoint']}
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.qwen-worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);publish(out/'config.json',config)
        todo=[r for r in rows if response(out,r) is None]
        if todo:
            observed=server(p);publish(out/'server_observations'/(stable(observed)+'.json'),observed)
        used=0;outcomes={}
        for row in rows:
            prior=response(out,row)
            if prior:outcomes[row['request_id']]=prior['status'];continue
            if max_requests and used>=max_requests:outcomes[row['request_id']]='pending';continue
            outcomes[row['request_id']]=send(row,p,out,retry_ambiguous);used+=1
        from collections import Counter
        report={'schema':'comics_qa.benchmark1000.qwen_run_report.2','counts':dict(Counter(outcomes.values())),'new_requests_visited':used,
                'requests':outcomes,'all_terminal':all(v in ('succeeded','failed') for v in outcomes.values()),'status':'raw_not_validated','release':'not_approved'}
        publish(out/'summaries'/(stable(report)+'.json'),report)
    return report


def run_config(root,request_root):
    config=read(Path(root)/'config.json');m,rows=load(request_root)
    if config['requests_manifest_sha256']!=digest(Path(request_root)/'manifest.json') or config['runtime_config_sha256']!=m['config_sha256']:raise ValueError('Inference run uses a different request version')
    expected=sorted(r['request_id'] for r in rows if int(stable(r['request_id']),16)%config['shards']==config['shard'])
    if expected!=config['request_ids']:raise ValueError('Inference shard identity changed')
    return config,m,rows
