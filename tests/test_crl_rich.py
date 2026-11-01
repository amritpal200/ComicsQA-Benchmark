"""Independent OCR/lexical CRL semantics, open coverage and proof tampering."""
import copy
import unittest
import test_crl
from comics_qa.evidence.graph.rich.model import build
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker


class RichTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass.__func__(cls)
    setUp = test_crl.ExecutionTest.setUp
    # Reuse only the fixture setup, not the inherited original test methods.
    def rich(self,g=None,v=None):
        g=g or self.g;v=v or self.v
        return build(g,v,{'graph_sha256':v['graph_source']['sha256'],'visibility_sha256':'fixture'})

    def pair(self,program,g=None,v=None,rich=None):
        g=g or self.g;v=v or self.v;r=rich or self.rich(g,v)
        doc=Interpreter(g,v,rich=r).execute(program)
        check=ProofChecker(g,v,rich=r).check(doc)
        self.assertTrue(check['proof_valid'],check)
        return doc,check

    def test_rich_quote_unique_and_named_speaker(self):
        for c in self.g['coverage']:
            if c['family']=='speaker_links':c['status']='closed_verified'
        d,_=self.pair('quote("HELLO HERO MAN",on=page(1))')
        self.assertEqual(d['result']['status'],'OK')
        self.assertTrue(d['result']['value'].endswith('htext00'))
        d,_=self.pair('speaker_char(quote("hello",on=page(1)))')
        self.assertEqual(d['result']['status'],'OK')

    def test_rich_quote_open_empty_and_ambiguous(self):
        for query,status in [('quote("absent")','UNKNOWN'),('quote("hello",on=page(1))','OK'),
                             ('quote("absent",on=page(1))','EMPTY'),('quote("hello")','AMBIGUOUS')]:
            with self.subTest(query=query):self.assertEqual(self.pair(query)[0]['result']['status'],status)

    def test_rich_not_fuzzy_or_substring(self):
        self.assertEqual(self.pair('quote("hero man",on=page(1))')[0]['result']['status'],'EMPTY')
        self.assertEqual(self.pair('quote("hello!",on=page(1))')[0]['result']['status'],'EMPTY')

    def test_rich_lexical_exact_and_lower_bound(self):
        d,_=self.pair('count(name_texts("Hero Man",on=page(1)))')
        self.assertEqual(d['result']['value'],1)
        d,c=self.pair('at_least(name_texts("Hero Man"),1)')
        self.assertEqual(d['result']['value'],True);self.assertTrue(c['accepted_for_generation'])
        self.assertEqual(self.pair('count(name_texts("Hero Man"))')[0]['result']['status'],'UNKNOWN')

    def test_rich_missing_companion_stays_unknown(self):
        d=Interpreter(self.g,self.v).execute('quote("hello",on=page(1))')
        self.assertEqual(d['result']['status'],'UNKNOWN')
        self.assertTrue(ProofChecker(self.g,self.v).check(d)['proof_valid'])

    def test_rich_changed_pins_and_evidence_rejected(self):
        d,_=self.pair('count(name_texts("Hero Man",on=page(1)))');r=self.rich()
        tampered=copy.deepcopy(d);tampered['rich_evidence_sha256']='bad'
        self.assertFalse(ProofChecker(self.g,self.v,rich=r).check(tampered)['proof_valid'])
        tampered=copy.deepcopy(d);tampered['result']['value']=2
        self.assertFalse(ProofChecker(self.g,self.v,rich=r).check(tampered)['proof_valid'])
        tampered=copy.deepcopy(d);tampered['proof']['facts']=[]
        self.assertFalse(ProofChecker(self.g,self.v,rich=r).check(tampered)['proof_valid'])
        self.assertFalse(ProofChecker(self.g,self.v).check(d)['proof_valid'])

    def test_rich_rejects_forged_companion(self):
        r=self.rich();r['facts'][0]['answer_eligible']=True
        with self.assertRaises(ValueError):Interpreter(self.g,self.v,rich=r)
        with self.assertRaises(ValueError):ProofChecker(self.g,self.v,rich=r)

    def test_rich_strict_coverage_policy(self):
        r=self.rich();d=Interpreter(self.g,self.v,rich=r,allow_closed_assumed=False).execute('quote("hello",on=page(1))')
        self.assertEqual(d['result']['status'],'UNKNOWN')
        self.assertTrue(ProofChecker(self.g,self.v,rich=r,allow_closed_assumed=False).check(d)['proof_valid'])
