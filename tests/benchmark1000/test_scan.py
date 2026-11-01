import copy
import unittest
import test_crl
from comics_qa.tasks.graph.crl.language import call
from comics_qa.benchmark1000.scan import ScanEngine, ScanChecker


class ScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass.__func__(cls)

    def setUp(self):
        test_crl.ExecutionTest.setUp(self)
        test_crl.ExecutionTest.close_synthetic_world(self)

    def program(self, op='next_speaks', after=1):
        return {'op': op, 'characters': [call('char', 'Hero Man')], 'after': after}

    def test_next_scan_verified_and_missing_prefix_rejected(self):
        doc = ScanEngine(self.g, self.v).execute(self.program())
        checked = ScanChecker(self.g, self.v).check(doc)
        self.assertTrue(checked['proof_valid'], checked)
        if len(doc['probes']) > 1:
            bad = copy.deepcopy(doc); bad['probes'].pop(0)
            self.assertFalse(ScanChecker(self.g, self.v).check(bad)['proof_valid'])
        bad = copy.deepcopy(doc); bad['result']['value'] = 'wrong'
        self.assertFalse(ScanChecker(self.g, self.v).check(bad)['proof_valid'])

    def test_unknown_earlier_page_blocks_next(self):
        for c in self.g['coverage']:
            if c['page_id'] == self.g['page_ids'][1] and c['family'] == 'speaker_links':
                c['status'] = 'open'
        doc = ScanEngine(self.g, self.v).execute(self.program())
        self.assertEqual(doc['result']['status'], 'UNKNOWN')
        self.assertTrue(ScanChecker(self.g, self.v).check(doc)['proof_valid'])

    def test_last_presence_backward_scan_and_tampered_source(self):
        doc = ScanEngine(self.g, self.v).execute(self.program('last_presence', 0))
        self.assertTrue(ScanChecker(self.g, self.v).check(doc)['proof_valid'])
        doc['graph_sha256'] = 'wrong'
        self.assertFalse(ScanChecker(self.g, self.v).check(doc)['proof_valid'])

    def test_empty_scan_is_not_known_target(self):
        doc = ScanEngine(self.g, self.v).execute(self.program(after=len(self.g['page_ids'])))
        self.assertEqual(doc['result']['status'], 'EMPTY')
        self.assertFalse(ScanChecker(self.g, self.v).check(doc)['answer_supported'])
