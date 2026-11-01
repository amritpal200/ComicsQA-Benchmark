"""Supported rich families, honest shortcut worlds and immutable GEN-2 builds."""
import contextlib
import copy
import io
import json
import unittest
from unittest.mock import patch
import test_crl
import test_ckg3
from comics_qa.evidence.graph.rich.model import build
from comics_qa.tasks.graph.gen2 import build as builder
from comics_qa.tasks.graph.gen2.families import propose
from comics_qa.tasks.graph.gen2.gates import RichGates
from comics_qa.tasks.graph.generation.policy import configure
from comics_qa.tasks.graph.generation.proposals import Proposal
from comics_qa.tasks.graph.crl.language import call,canonical
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker


class FamiliesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):test_crl.ExecutionTest.setUpClass.__func__(cls)
    def setUp(self):
        test_crl.ExecutionTest.setUp(self)
        for c in self.g['coverage']:
            if c['family']=='speaker_links':c['status']='closed_verified'
        for a in self.v['alignments']:
            if a.get('text_id','') and a['text_id'].endswith('htext01'):
                a['paddle_text']=a['magi_text']='come back now'
        self.r=build(self.g,self.v,{'graph_sha256':self.v['graph_source']['sha256'],'visibility_sha256':'fixture'})
        self.p=configure();self.gates=RichGates(self.g,self.v,self.r,self.p,{})

    def query(self):return call('speaker_char',call('quote','come back now',on=call('page',1)))

    def test_all_six_families_deterministic_and_bounded(self):
        qs=list(propose(self.g,self.v,self.r,self.p))
        self.assertEqual(len({q.family for q in qs}),6)
        self.assertEqual([canonical(q.ast) for q in qs],[canonical(q.ast) for q in propose(self.g,self.v,self.r,self.p)])
        self.assertEqual(len(list(propose(self.g,self.v,self.r,configure({'max_candidates_per_chapter':4})))),4)

    def test_quoted_speaker_passes_gates_and_checker(self):
        q=Proposal('quote_speaker','ocr_anchor',self.query(),'Who says “come back now” on page 1?',anchors=[1])
        item,rejection=self.gates.assess(q)
        self.assertIsNone(rejection,rejection)
        self.assertEqual(item['question_type'],'graph_verified')
        self.assertTrue(ProofChecker(self.g,self.v,rich=self.r).check(item['execution'])['proof_valid'])
        self.assertTrue(item['gates']['G9']['W4']['transcripts'])
        self.assertEqual(item['gates']['G8']['text_only']['status'],'UNKNOWN')

    def test_question_alias_fragment_rejected(self):
        cid=next(n['id'] for n in self.g['nodes'] if n['type']=='Character' and n.get('canonical_name')=='Hero Man')
        q=Proposal('name_speaker','ocr_anchor',self.query(),'Who speaks?',names=[(cid,'Hero')])
        item,rejection=self.gates.assess(q)
        self.assertIsNone(item);self.assertEqual(rejection['reason'],'ineligible_question_name_form')

    def test_answer_accepted_forms_exclude_fragments(self):
        q=Proposal('quote_speaker','ocr_anchor',self.query(),'Who says “come back now” on page 1?',anchors=[1])
        item,rejection=self.gates.assess(q)
        self.assertIsNone(rejection)
        self.assertEqual(item['answer']['accepted_forms'],['Hero Man'])

    def test_text_only_retains_ocr_and_names_but_not_speaker(self):
        world=self.gates.world(self.g['page_ids'],True)
        for program in ['quote("come back now",on=page(1))','count(name_texts("Hero Man",on=page(1)))']:
            d,c=self.gates.run(program,world);self.assertEqual(d['result']['status'],'OK');self.assertTrue(c['proof_valid'])
        self.assertEqual(self.gates.run(self.query(),world)[0]['result']['status'],'UNKNOWN')

    def test_page_ablation_removes_ocr_evidence(self):
        world=self.gates.world([self.g['page_ids'][0]])
        d,_=self.gates.run('quote("come back now",on=page(1))',world)
        self.assertEqual(d['result']['status'],'UNKNOWN')

    def test_lexical_only_candidate_rejected(self):
        q=Proposal('test','ocr_anchor',call('count',call('name_texts','Hero Man',on=call('page',1))),
                   'How many text regions contain Hero Man on the first page?')
        item,rejection=self.gates.assess(q);self.assertIsNone(item);self.assertIsNotNone(rejection)

    def test_no_closed_ocr_pages_no_proposals(self):
        r=copy.deepcopy(self.r)
        for c in r['coverage']:
            if c['family']=='ocr':c['status']='open'
        self.assertEqual(list(propose(self.g,self.v,r,self.p)),[])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_ckg3.BuildTests('test_build_resume_and_loader');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.assertEqual(self.fixture.run_cli(),0)
        self.root=self.fixture.root;self.out=self.root/'gen2'

    def cli(self,*extra):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return builder.main(['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),
                '--rich',str(self.root/'rich'),'--out',str(self.out),'--max-candidates-per-chapter','12',*extra])

    def test_completed_resume_and_rich_pins(self):
        self.assertEqual(self.cli(),0);self.assertEqual(self.cli('--resume'),0);self.assertEqual(self.cli(),2)
        payload=builder.read(self.out/'chapters/hero__c001.json')['payload']
        self.assertEqual(len(payload['inputs_sha256']),6)
        self.assertFalse(payload['balance']['limits_relaxed'])

    def test_interrupted_resume_and_output_tamper(self):
        original=builder.write
        def interrupt(path,payload):
            if path.name=='report.json':raise KeyboardInterrupt
            return original(path,payload)
        with patch.object(builder,'write',interrupt):self.assertEqual(self.cli(),130)
        self.assertEqual(self.cli('--resume'),0)
        (self.out/'report.json').write_text('{}')
        self.assertEqual(self.cli('--resume'),2)

    def test_changed_rich_input_and_code_rejected(self):
        self.assertEqual(self.cli(),0)
        with patch.object(builder,'code_hashes',return_value={'changed':'hash'}):self.assertEqual(self.cli('--resume'),2)
        (self.root/'rich/chapters/hero__c001.json').write_text('{}')
        self.assertEqual(self.cli('--resume'),2)

    def test_rich_overlap_and_missing_chapter_rejected(self):
        self.assertEqual(self.cli('--out',str(self.root/'rich/nested')),2)
        self.assertEqual(self.cli('--chapter','missing'),2)

    def test_quality_policy_change_invalidates_resume(self):
        config=self.root/'quality.json'
        config.write_text(json.dumps({'quality':{'max_count_share':0.7}}))
        self.assertEqual(self.cli('--config',str(config)),0)
        config.write_text(json.dumps({'quality':{'max_count_share':0.6}}))
        self.assertEqual(self.cli('--config',str(config),'--resume'),2)
