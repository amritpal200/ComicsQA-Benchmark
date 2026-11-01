import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import urllib.error
import test_branch_relations as fixture
from comics_qa.benchmark1000 import qwen_packs as qp,qwen_runtime as rt,qwen_jobs as jobs,qwen_language as ql,qwen_validation as qv,sentence_plans as sp
from comics_qa.benchmark1000.admission import World,assess
from comics_qa.benchmark1000.admission_store import admitted
from comics_qa.benchmark1000.io import publish,read,stable,digest


class Processor:
    def apply_chat_template(self,*a,**kw):return 'test-only formatted prompt'
    def __call__(self,**kw):
        assert kw['truncation'] is False
        return {'input_ids':SimpleNamespace(shape=(1,37))}


class QwenPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.BranchRelationsTests.setUpClass();x=fixture.BranchRelationsTests();x.setUp();cls.tmp=tempfile.TemporaryDirectory();base=Path(cls.tmp.name)
        from PIL import Image
        for n,p in enumerate(x.g['nodes']):
            if p['type']=='Page':
                path=base/(p['id']+'.png');Image.new('RGB',(p['width'],p['height']),(n%255,70,160)).save(path)
                p['image_path']=str(path);p['image_sha256']=digest(path)
        page_hashes={p['id']:p['image_sha256'] for p in x.g['nodes'] if p['type']=='Page'}
        for row in x.v['alignments']:
            row['image_sha256']=page_hashes[row['page_id']]
        for row in x.v['evidence']:
            if row.get('page_id') in page_hashes and 'image_sha256' in row:row['image_sha256']=page_hashes[row['page_id']]
        from comics_qa.evidence.graph.rich.model import build
        x.r=build(x.g,x.v,x.r['sources']);n=x.native({**x.recipe,'steps':[3,2]});cls.seed=admitted(n,assess(n,World(x.g,x.v,x.r),max_ablation_pages=20))
        cls.g,cls.v,cls.r=x.g,x.v,x.r;cls.plan=sp.make(cls.seed,x.g,x.v,x.r)
        cls.para=qp.make(cls.seed,'paraphrase',x.g,x.v,x.r,base/'para');cls.synth=qp.make(cls.plan,'synthesis',x.g,x.v,x.r,base/'synth')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def raw(self,obj,finish='stop',tokens=37):
        return json.dumps({'model':'test-model','choices':[{'finish_reason':finish,'message':{'role':'assistant','content':json.dumps(obj)}}],'usage':{'prompt_tokens':tokens}})

    def test_compact_question_backparse_is_blind_and_program_identical(self):
        q=self.para['controlled_question_example'][0];p=ql.parse_question(q)
        self.assertEqual(p['program'],self.seed['program']);self.assertFalse(p['requires_roles'])
        self.assertTrue(ql.parse_question(q+ql.ROLE_SUFFIX)['requires_roles'])
        with self.assertRaises(ValueError):ql.parse_question(q+' Why is he angry?')

    def test_hydration_and_synthesis_pixels_are_checked(self):
        self.assertTrue(qp.check(self.para,self.g,self.v,self.r)['verified']);self.assertTrue(qp.check(self.synth,self.g,self.v,self.r)['verified'])
        self.assertFalse(self.para['evidence_crops']);self.assertTrue(self.synth['evidence_crops'])
        self.assertTrue(all(f['origin'] in ('H','V') and f['answer_eligible'] for f in self.synth['evidence']['facts']))
        self.assertTrue(all('canonical_name' not in n and 'aliases' not in n for n in self.synth['evidence']['nodes']))
        body=qp.model_context(self.synth);self.assertNotIn('source_record',body)
        self.assertTrue(all('execution' not in c for rows in body['target']['claims'].values() for c in rows))

    def test_full_page_crops_preserve_pending_geometry_without_clipping(self):
        g=copy.deepcopy(self.g);n=next(n for n in g['nodes'] if n['type']=='Text' and n['id'] in {n['id'] for n in self.synth['evidence']['nodes']})
        n['geometry_review_required']=True;n['outside_image']=True;n['box'][0]=-10
        with self.assertRaises(ValueError):qp.crop_specs(self.synth['evidence'],g,'proof-union')
        specs=qp.crop_specs(self.synth['evidence'],g,'full-page')
        ns={n['id']:n for n in g['nodes']}
        self.assertTrue(all(s['box']==[0,0,ns[s['page_id']]['width'],ns[s['page_id']]['height']] for s in specs))
        self.assertEqual(n['box'][0],-10);self.assertTrue(n['geometry_review_required'])

    def test_legacy_alias_parser_and_unreadable_names(self):
        from comics_qa.tasks.graph.crl.language import call
        self.assertEqual(ql.parse_question('On page 2, how many text regions are there?')['program'],call('count',call('texts',call('page',2))))
        with self.assertRaises(ValueError):qv.rendered_names(call('char','not a verified identity'),self.g,self.v)

    def test_older_question_aliases_preserve_direction_and_scope(self):
        from comics_qa.tasks.graph.crl.language import program_hash,parse
        texts=['How many text regions are shown on page 2?','How many text regions on page 9 have Hero as their speaker?',
               'After Hero appears on page 5, on which later page is this character next drawn?','Is Hero drawn on page 2?',
               'Compared with page 5, does page 3 contain more text regions, fewer, or the same number?',
               'Which named character is drawn on page 9 and is drawn on page 3?',
               'Who is the speaker of the text region reading "hello there" on page 2?']
        for original in texts:
            for alias in ql.alternatives(original):
                self.assertEqual(program_hash(parse(ql.parse_question(original)['program'])),program_hash(parse(ql.parse_question(alias)['program'])))

    def test_pack_publication_resume_and_checker(self):
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);root=b/'bench';source=b/'source';out=b/'prepared';cid=self.g['chapter_id'];parent={'config':{'chapters':[cid]},'outputs_sha256':{}}
            publish(source/'manifest.json',parent)
            for rel in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1'):publish(root/rel/'manifest.json',parent)
            for rel,doc in (('evidence/ckg/v1',self.g),('evidence/name_visibility/v1',self.v)):publish(root/rel/'chapters'/(cid+'.json'),doc)
            with ExitStack() as stack:
                stack.enter_context(patch.object(qp,'sources',return_value=[self.seed]))
                stack.enter_context(patch('comics_qa.tasks.graph.crl.artifacts.load_world',return_value=(self.g,self.v,{})))
                stack.enter_context(patch('comics_qa.tasks.graph.crl.rich_contract.load_optional',return_value=self.r))
                first=qp.run(source,root,out);self.assertEqual(first['counts'],{'prepared':1})
                self.assertEqual(len(qp.load(out)),1);self.assertEqual(qp.verify(out,root)['verified'],1)
                with patch.object(qp,'make',side_effect=AssertionError('checkpoint recomputed')):self.assertEqual(qp.run(source,root,out),first)
                with self.assertRaises(ValueError):qp.run(source,root,out,max_images=10)

    def test_missing_crop_or_changed_dag_is_rejected(self):
        for mutate in (lambda p:p['evidence_crops'].pop(),lambda p:p['dependency_order'].reverse()):
            p=copy.deepcopy(self.synth);mutate(p);p['pack_id']='b1000qwenpack:'+stable({k:v for k,v in p.items() if k not in ('schema','pack_id')})
            with self.assertRaises(ValueError):qp.check(p,self.g,self.v,self.r)

    def test_budget_never_truncates(self):
        with self.assertRaises(ValueError):qp.make(self.seed,'paraphrase',self.g,self.v,self.r,'/tmp/unused-qwen',max_bytes=10)
        with self.assertRaises(ValueError):qp.make(self.plan,'synthesis',self.g,self.v,self.r,Path(self.tmp.name)/'synth',max_images=1)
        p={'max_image_pixels':10000,'max_new_tokens':64,'max_context_tokens':80,'chat_template_kwargs':{}}
        with self.assertRaises(ValueError):rt.measure({'messages':[{'role':'user','content':'x'}]},p,Processor())

    def test_paraphrase_semantics_and_synthesis_claims_are_verified(self):
        q=self.para['controlled_question_example'][0]
        self.assertEqual(qv.validate(self.para,self.raw({'question':q}),'test-model',37,self.g,self.v,self.r)['status'],'verified_pending_human')
        obj={'question':self.synth['controlled_question_example'][0],'short_answer':self.plan['short_answer']['value'],'answer':self.plan['reference_answer']}
        self.assertEqual(qv.validate(self.synth,self.raw(obj),'test-model',37,self.g,self.v,self.r)['status'],'verified_pending_human')
        obj['answer']+=' The first speaker is angry.'
        self.assertEqual(qv.validate(self.synth,self.raw(obj),'test-model',37,self.g,self.v,self.r)['status'],'held')

    def test_coincident_answer_extra_fields_and_unverified_wording_stay_held(self):
        q=self.para['controlled_question_example'][0]
        changed=q.replace('pages 4 to 10','pages 4 to 9') # same endpoints, changed condition
        self.assertIn('semantics_changed',qv.validate(self.para,self.raw({'question':changed}),'test-model',37,self.g,self.v,self.r)['reason'])
        self.assertEqual(qv.validate(self.para,self.raw({'question':q,'back_parsed_program':self.seed['program']}),'test-model',37,self.g,self.v,self.r)['status'],'held')
        self.assertEqual(qv.validate(self.para,self.raw({'question':q+' because he is sad.'}),'test-model',37,self.g,self.v,self.r)['status'],'held')

    def test_truncated_model_and_processor_mismatches_are_held(self):
        obj={'question':self.para['template_question']}
        for raw,model,tokens in ((self.raw(obj,finish='length'),'test-model',37),(self.raw(obj),'other-model',37),(self.raw(obj),'test-model',38)):
            self.assertEqual(qv.validate(self.para,raw,model,tokens,self.g,self.v,self.r)['status'],'held')
        raw=json.loads(self.raw(obj));raw['choices'][0]['message']['content']='<think>private reasoning</think>'+json.dumps(obj)
        self.assertEqual(qv.validate(self.para,json.dumps(raw),'test-model',37,self.g,self.v,self.r)['status'],'verified_pending_human')

    def setup_requests(self,base):
        pack_root=base/'packs';cfg={'mode':'paraphrase','record_hashes':{self.seed['item_id']:stable(self.seed)}}
        path='packs/'+stable(self.para['pack_id'])+'.json';check_path='checks/'+stable(self.seed['item_id'])+'.json'
        publish(pack_root/'config.json',cfg);publish(pack_root/path,self.para)
        publish(pack_root/check_path,{'status':'prepared','pack_path':path,'pack_id':self.para['pack_id'],'source_id':self.seed['item_id'],'source_sha256':stable(self.seed),'config_sha256':stable(cfg)})
        publish(pack_root/'report.json',{'counts':{'prepared':1},'records':1})
        publish(pack_root/'manifest.json',{'schema':qp.STORE,'config':cfg,'config_sha256':stable(cfg),'outputs_sha256':{p:digest(pack_root/p) for p in (path,check_path,'report.json')}})
        model=base/'model'
        for name,value in [('config.json',{'model_type':'qwen3_vl','architectures':['test-only'],'text_config':{'max_position_embeddings':4096}}),('preprocessor_config.json',{}),('tokenizer_config.json',{'chat_template':'test-only'}),('tokenizer.json',{})]:publish(model/name,value)
        profile={'schema':rt.SCHEMA,'model_path':str(model),'served_model':'test-model','endpoint':'http://localhost:9999/v1/chat/completions','max_context_tokens':4096,'max_new_tokens':256,'max_images':16,'max_image_pixels':1000000,'max_request_bytes':1000000,'timeout_seconds':5,'max_attempts':2,'chat_template_kwargs':{}}
        profile_path=base/'runtime.json';publish(profile_path,profile);requests=base/'requests'
        with patch.object(rt,'processor',return_value=Processor()),patch('importlib.metadata.version',return_value='test-only'):
            jobs.prepare(pack_root,profile_path,requests)
        return requests,profile

    def fake_http(self,req,timeout):
        if req.data is None:return io.BytesIO(json.dumps({'data':[{'id':'test-model','max_model_len':4096}]}).encode())
        return io.BytesIO(self.raw({'question':self.para['controlled_question_example'][0]}).encode())

    def test_placeholder_runtime_is_not_dispatchable(self):
        with self.assertRaises(ValueError):rt.profile('configs/benchmark1000/qwen_runtime.example.json')

    def test_request_preflight_http_resume_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);requests,p=self.setup_requests(b);m,rows=jobs.load(requests)
            self.assertEqual(rows[0]['budget']['prompt_tokens'],37)
            with patch('urllib.request.urlopen',side_effect=AssertionError('HTTP used')):self.assertEqual(jobs.run(requests,b/'dry',dry_run=True)['status'],'dry_run_no_http')
            with patch('urllib.request.urlopen',side_effect=self.fake_http) as network:
                report=jobs.run(requests,b/'run');self.assertEqual(report['counts'],{'succeeded':1});self.assertEqual(network.call_count,2)
            with patch('urllib.request.urlopen',side_effect=AssertionError('duplicate inference')):self.assertEqual(jobs.run(requests,b/'run')['counts'],{'succeeded':1})
            with patch.dict(os.environ,{'BENCHMARK1000_API_KEY':'do-not-persist'}):self.assertIn('Authorization',jobs.headers())
            self.assertNotIn('do-not-persist',json.dumps([read(p) for p in (b/'run').rglob('*.json')]))

    def test_interrupted_or_timed_out_requests_are_not_resent_automatically(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);requests,p=self.setup_requests(b);_,rows=jobs.load(requests);out=b/'run';row=rows[0]
            with patch('urllib.request.urlopen',side_effect=lambda req,timeout:self.fake_http(req,timeout) if req.data is None else (_ for _ in ()).throw(TimeoutError())):
                self.assertEqual(jobs.run(requests,out)['counts'],{'ambiguous':1})
            with patch('urllib.request.urlopen',side_effect=self.fake_http) as network:
                self.assertEqual(jobs.run(requests,out)['counts'],{'ambiguous':1});self.assertEqual(network.call_count,1) # models GET only
                self.assertEqual(jobs.run(requests,out,retry_ambiguous=True)['counts'],{'succeeded':1})

    def test_raw_success_before_completion_checkpoint_recovers_without_post(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);requests,p=self.setup_requests(b);_,rows=jobs.load(requests);row=rows[0];out=b/'run';d=out/'responses'/stable(row['request_id'])
            publish(d/'attempt-001.start.json',{'request_id':row['request_id']})
            publish(d/'attempt-001.result.json',{'request_id':row['request_id'],'payload_sha256':row['payload_sha256'],'status':'succeeded','raw_response':self.raw({'question':self.para['template_question']})})
            with patch('urllib.request.urlopen',side_effect=AssertionError('duplicate POST')):self.assertEqual(jobs.send(row,p,out),'succeeded')
            self.assertEqual(jobs.response(out,row)['status'],'succeeded')

    def test_retry_http_failure_is_bounded_and_raw_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);requests,p=self.setup_requests(b);_,rows=jobs.load(requests);calls=[]
            def failing(req,timeout):
                calls.append(req);raise urllib.error.HTTPError(req.full_url,503,'busy',{},io.BytesIO(b'server-busy'))
            with patch('urllib.request.urlopen',side_effect=failing),patch('time.sleep'):
                self.assertEqual(jobs.send(rows[0],p,b/'run'),'failed')
            self.assertEqual(len(calls),2)
            self.assertTrue(any(read(f).get('raw_response')=='server-busy' for f in (b/'run').rglob('*.result.json')))

    def test_ingestion_uses_source_world_and_keeps_human_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            b=Path(tmp);requests,p=self.setup_requests(b)
            with patch('urllib.request.urlopen',side_effect=self.fake_http):jobs.run(requests,b/'run')
            with patch('comics_qa.tasks.graph.crl.artifacts.load_world',return_value=(self.g,self.v,{})),patch('comics_qa.tasks.graph.crl.rich_contract.load_optional',return_value=self.r):
                report=qv.ingest(requests,b/'run',b/'bench',b/'validated')
            self.assertEqual(report['counts'],{'verified_pending_human':1});self.assertEqual(report['candidate_admission'],'not_promoted')
