import copy
import unittest
import test_crl
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.tasks.graph.crl.language import call, SPECS
from comics_qa.tasks.graph.generation.gates import PROFILE_OPS
from comics_qa.benchmark1000.reasoning import next_speaking_page, next_joint_page, last_presence, page_gap, typed


class CompositionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass.__func__(cls)

    def setUp(self):
        test_crl.ExecutionTest.setUp(self)
        test_crl.ExecutionTest.close_synthetic_world(self)

    def test_compositions_typed_and_independently_checked(self):
        char = call('char', 'Hero Man'); page = call('page', 1)
        programs = [next_speaking_page(char, page), next_joint_page(char, char, page),
                    last_presence(char), page_gap(call('page', 1), call('page', 3))]
        specs, profile = copy.deepcopy(SPECS), copy.deepcopy(PROFILE_OPS)
        for program in programs:
            typed(program)
            doc = Interpreter(self.g, self.v).execute(program)
            checked = ProofChecker(self.g, self.v).check(doc, program)
            self.assertTrue(checked['proof_valid'], checked)
            if doc['result']['status'] == 'OK':
                bad = copy.deepcopy(doc); bad['result']['value'] = 'wrong'
                self.assertFalse(ProofChecker(self.g, self.v).check(bad, program)['proof_valid'])
        self.assertEqual(SPECS, specs)
        self.assertEqual(PROFILE_OPS, profile)

    def test_open_coverage_does_not_become_exact(self):
        for c in self.g['coverage']:
            if c['family'] == 'speaker_links': c['status'] = 'open'
        doc = Interpreter(self.g, self.v).execute(next_speaking_page(call('char', 'Hero Man'), call('page', 1)))
        self.assertFalse(doc['eligible_for_generation'])
