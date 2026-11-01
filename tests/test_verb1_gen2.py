"""GEN-2 closed wording grammar, evidence packing and immutable preparation."""
import argparse
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import test_gen2
from comics_qa.tasks.graph.verbalization import prepare as base, prepare_gen2 as p
from comics_qa.tasks.graph.verbalization.gen2_gloss import parse_gloss
from comics_qa.tasks.graph.crl.language import canonical,call
from comics_qa.tasks.graph.gen2.families import propose
from comics_qa.tasks.graph.generation.proposals import Proposal


class RecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):test_gen2.FamiliesTest.setUpClass.__func__(cls)
    def setUp(self):
        test_gen2.FamiliesTest.setUp(self)
        ast=call('speaker_char',call('quote','come back now',on=call('page',1)))
        q=Proposal('quote_speaker','ocr_anchor',ast,'Who is the speaker of the text region reading "come back now" on page 1?',anchors=[1])
        self.item,rejected=self.gates.assess(q);self.assertIsNone(rejected)
        self.profile=p.Profile(argparse.Namespace(graphs=self.root/'graph',visibility=self.root/'visibility',rich=self.root/'rich',out=self.root/'pack'))
        self.profile.g=self.g;self.profile.v=self.v;self.profile.r=self.r
        self.profile.checker=self.gates.base[1]
        self.profile.facts={f['fact_id']:f for f in self.g['facts']};self.profile.facts.update({f['id']:f for f in self.r['facts']})
        self.profile.certs={c['coverage_id']:c for c in self.g['coverage']};self.profile.certs.update({c['id']:c for c in self.r['coverage']})
        # make_record unit tests use the real graph manifest as a synthetic hash fixture.
        self.profile.roots=[self.root/'graph']*3

    def test_all_six_templates_round_trip(self):
        qs=list(propose(self.g,self.v,self.r,self.p));self.assertEqual(len({q.family for q in qs}),6)
        for q in qs:self.assertEqual(canonical(parse_gloss(q.question)),canonical(q.ast))

    def test_escaped_quotes_and_unicode(self):
        for form in ['say "hello" now','日本語 and \\ paths','literal on page 3?']:
            text='Who is the speaker of the text region reading '+json.dumps(form,ensure_ascii=False)+' on page 1?'
            self.assertEqual(canonical(parse_gloss(text)),canonical(call('speaker_char',call('quote',form,on=call('page',1)))))

    def test_bad_scope_and_extra_claims_rejected(self):
        for text in [self.item['question']+' Explain why.',self.item['question'].replace('page 1','page 0'),
                     'After page 2, on which page is the speaker of the text region reading "hello" on page 1 next drawn?']:
            with self.assertRaises(ValueError):parse_gloss(text)

    def test_private_evidence_and_model_message_separation(self):
        before=copy.deepcopy(self.item);request,record=self.profile.make_record(self.item)
        payload=json.loads(request['messages'][1]['content'])
        self.assertNotIn('answer',payload);self.assertNotIn('facts',payload)
        pack=record['evidence_pack'];self.assertEqual(pack['fixed_answer'],self.item['answer'])
        self.assertTrue(pack['facts']);self.assertTrue(pack['rich_records']);self.assertTrue(pack['alignments'])
        self.assertTrue(record['independent_proof_check']['accepted_for_generation'])
        self.assertEqual(record['evidence_pack_sha256'],base.stable(pack))
        self.assertTrue(all('image_path' not in p for p in pack['context_images']))
        self.assertEqual(before,self.item);self.assertEqual(request,self.profile.make_record(self.item)[0])

    def test_rewrite_checks_without_model_program_echo(self):
        question=self.item['question'].replace('Who is','Which character is',1)
        self.assertEqual(p.validate_rewrite(self.item,{'question':question})['status'],'closed_grammar_match')
        self.assertEqual(p.validate_rewrite(self.item,{'question':question.replace('page 1','page 3')})['status'],'rejected')
        self.assertEqual(p.validate_rewrite(self.item,{'question':question,'program':self.item['program']})['reason'],'response_contract')
        self.assertEqual(p.validate_rewrite(self.item,{'question':'Who said this?'})['status'],'needs_blind_parse_back')

    def test_answer_or_quote_tamper_rejected(self):
        for which in ('answer','question'):
            item=copy.deepcopy(self.item)
            if which=='answer':item['answer']['value']='Another person'
            else:item['question']=item['question'].replace('come back now','come back later')
            with self.assertRaises(ValueError):self.profile.make_record(item)

    def test_context_and_answer_type_mismatch_rejected(self):
        for mode in ('context','type'):
            item=copy.deepcopy(self.item)
            if mode=='context':item['context']['pages']=item['context']['pages'][:-1]
            else:item['answer']['type']='int'
            with self.assertRaises(ValueError):self.profile.make_record(item)

    def test_independent_checker_rejects_rehashed_forgery(self):
        item=copy.deepcopy(self.item);item['execution']['proof']['facts']=[]
        item['proof_check']['execution_sha256']=base.stable(item['execution'])
        with self.assertRaises(ValueError):self.profile.make_record(item)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_gen2.BuildTest('test_completed_resume_and_rich_pins');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.assertEqual(self.fixture.cli(),0)
        self.root=self.fixture.root;self.out=self.root/'requests'

    def cli(self,*extra):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return p.main(['--source',str(self.root/'gen2'),'--out',str(self.out),
                          '--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),
                          '--rich',str(self.root/'rich'),*extra])

    def test_resume_empty_chapter_and_overlap(self):
        self.assertEqual(self.cli(),0);self.assertEqual(self.cli('--resume'),0)
        self.assertEqual(self.cli(),2);self.assertEqual(self.cli('--out',str(self.root/'rich/nested')),2)
        self.assertEqual(base.read(self.out/'report.json')['status'],'prepared_not_inferred')

    def test_interrupted_resume_and_tampered_output(self):
        original=base.write
        def interrupt(path,payload):
            if Path(path).name=='report.json':raise KeyboardInterrupt
            return original(path,payload)
        with patch.object(base,'write',interrupt):self.assertEqual(self.cli(),130)
        self.assertEqual(self.cli('--resume'),0)
        (self.out/'report.json').write_text('{}');self.assertEqual(self.cli('--resume'),2)

    def test_missing_finished_manifest_and_unknown_chapter(self):
        self.assertEqual(self.cli('--source',str(self.root/'gen2.partial')),2)
        self.assertEqual(self.cli('--chapter','unknown'),2)

    def test_evidence_tamper_detected_on_completed_resume(self):
        self.assertEqual(self.cli(),0)
        (self.root/'rich/chapters/hero__c001.json').write_text('{}')
        self.assertEqual(self.cli('--resume'),2)

    def test_dependency_code_change_invalidates_resume(self):
        self.assertEqual(self.cli(),0)
        with patch.object(p.Profile,'code_hashes',return_value={'changed':'hash'}):self.assertEqual(self.cli('--resume'),2)
