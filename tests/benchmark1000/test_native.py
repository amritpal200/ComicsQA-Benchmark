import copy
from pathlib import Path
import tempfile
import unittest
import test_crl
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.benchmark1000.native import make, validate, check_answer
from comics_qa.benchmark1000.native_store import write
from comics_qa.benchmark1000.store import load
from comics_qa.benchmark1000.io import stable


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass.__func__(cls)

    def setUp(self):
        test_crl.ExecutionTest.setUp(self)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make(self, **kwargs):
        args = {'question': 'On which page is the first supplied image?', 'answer': {'type': 'page', 'value': 1},
                'answer_format': 'page', 'structure': 'direct'}
        args.update(kwargs)
        return make(self.g, self.v, None, {}, **args)

    def test_native_crl_proof_without_legacy_wrapper(self):
        doc = Interpreter(self.g, self.v).execute('page(1)')
        i = self.make(engine='crl', program=doc['program'], execution=doc)
        self.assertNotIn('legacy', i)
        self.assertEqual(i['verification']['proof'], 'verified')
        self.assertEqual(i['admission'], 'proposal')
        self.assertTrue(check_answer(i, self.g, self.v, None)['answer_supported'])

    def test_pending_sentence_and_visual_records_are_not_certified(self):
        sentence = self.make(answer={'type': 'sentence', 'value': 'A speaks.'}, answer_format='sentence',
                             claims={'required': [{'text': 'A speaks.', 'evidence': ['to_verify']}]})
        visual = self.make(answer={'type': 'visual_choice', 'value': 'A'}, answer_format='visual_choice',
                           options=[{'label': c, 'identity_id': c} for c in 'ABCD'])
        for i in (sentence, visual):
            self.assertEqual(i['verification']['proof'], 'pending')
            self.assertFalse(check_answer(i, self.g, self.v, None)['answer_supported'])

    def test_native_store_resumes_but_default_selection_hides_proposals(self):
        i = self.make()
        a = write([i], self.root / 'native', {'version': 1})
        self.assertEqual(a, write([i], self.root / 'native', {'version': 1}))
        self.assertEqual(load(self.root / 'native'), [])
        self.assertEqual(load(self.root / 'native', include_proposals=True), [i])
        self.assertEqual(a['counts'], {'records': 1, 'proposals': 1, 'candidates': 0})

    def test_tampering_and_self_approval_rejected(self):
        i = self.make(); i['answer']['value'] = 2
        with self.assertRaises(ValueError): validate(i)
        i = self.make(); i['verification']['gates'] = 'verified'
        body = {k: v for k, v in i.items() if k not in ('schema', 'item_id')}
        i['item_id'] = 'b1000n:' + stable(body)
        with self.assertRaises(ValueError): validate(i)

    def test_wrong_program_proof_and_snapshot_fail(self):
        doc = Interpreter(self.g, self.v).execute('page(1)')
        i = self.make(engine='crl', program=doc['program'], execution=doc,
                      answer={'type': 'page', 'value': 2})
        self.assertEqual(i['verification']['proof'], 'pending')
        gg = copy.deepcopy(self.g); gg['builder_version'] += '-changed'
        with self.assertRaises(ValueError): check_answer(i, gg, self.v, None)

    def test_mixed_store_preserves_legacy_and_hides_new_proposals(self):
        from test_foundation import fixture
        from comics_qa.benchmark1000.store import ingest
        fixture(self.root / 'old')
        ingest([self.root / 'old'], self.root / 'base')
        legacy = load(self.root / 'base')
        write(legacy + [self.make()], self.root / 'mixed', {'base': 'fixture'})
        self.assertEqual(load(self.root / 'mixed'), legacy)
        self.assertEqual(len(load(self.root / 'mixed', include_proposals=True)), 2)

    def test_context_image_tampering_rejected_even_after_rehash(self):
        i = self.make()
        i['context']['pages'][0]['image_sha256'] = 'wrong-image'
        body = {k: v for k, v in i.items() if k not in ('schema', 'item_id')}
        i['item_id'] = 'b1000n:' + stable(body)
        with self.assertRaises(ValueError): check_answer(i, self.g, self.v, None)

    def test_proof_receipt_cannot_be_rebound_to_a_different_answer(self):
        doc = Interpreter(self.g, self.v).execute('page(1)')
        i = self.make(engine='crl', program=doc['program'], execution=doc)
        i['answer']['value'] = 2
        body = {k: v for k, v in i.items() if k not in ('schema', 'item_id')}
        i['item_id'] = 'b1000n:' + stable(body)
        with self.assertRaises(ValueError): validate(i)

    def test_scalar_type_coincidence_is_not_an_answer_proof(self):
        doc = Interpreter(self.g, self.v).execute('page(1)')
        i = self.make(engine='crl', program=doc['program'], execution=doc,
                      answer_format='count', answer={'type': 'count', 'value': 1})
        self.assertEqual(i['verification']['proof'], 'pending')

    def test_proposal_cannot_be_released_by_a_human_decision_alone(self):
        from comics_qa.benchmark1000.review import release_eligible
        i = self.make()
        i['verification'].update(proof='verified', wording='verified')
        decision = {'item_id': i['item_id'], 'item_sha256': stable(i), 'reviewer_type': 'human',
                    'reviewer': 'synthetic reviewer', 'decision': 'accept', 'reason': 'checked', 'review_version': '1'}
        self.assertFalse(release_eligible(i, [decision]))

    def test_canonical_commutative_program_binding(self):
        from comics_qa.tasks.graph.crl.language import call
        program = call('and', True, False)
        doc = Interpreter(self.g, self.v).execute(program)
        self.assertNotEqual(program, doc['program'])
        item = self.make(engine='crl', program=program, execution=doc,
                         answer_format='boolean', answer={'type': 'boolean', 'value': False})
        self.assertEqual(item['verification']['proof'], 'verified')
        self.assertTrue(check_answer(item, self.g, self.v, None)['answer_supported'])

    def test_same_answer_from_a_different_program_is_not_a_binding(self):
        from comics_qa.tasks.graph.crl.language import call
        doc = Interpreter(self.g, self.v).execute(call('and', True, False))
        with self.assertRaisesRegex(ValueError, 'program/execution binding'):
            self.make(engine='crl', program=call('eq', 1, 2), execution=doc,
                      answer_format='boolean', answer={'type': 'boolean', 'value': False})
