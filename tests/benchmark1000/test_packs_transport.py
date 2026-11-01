import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from comics_qa.benchmark1000.packs import prepare, hydrate
from comics_qa.benchmark1000.transport import request, infer
from comics_qa.benchmark1000.io import stable
from comics_qa.benchmark1000.probes import composition_metrics
from comics_qa.benchmark1000.overlays import positive_fact, check_positive_fact


class PackTransportTests(unittest.TestCase):
    def fixture(self):
        item = {'item_id': 'i', 'question': 'Who speaks?', 'answer': {'value': 'A'},
                'legacy': {'context': {'pages': [{'index': 1, 'page_id': 'p'}]}, 'program': {'op': 'ctx'},
                           'execution': {'inputs_sha256': {'/x/evidence/ckg/v1/chapters/c.json': 'pin'},
                                         'proof': {'steps': [], 'facts': ['f'], 'certificates': ['cov']}}}}
        graph = {'page_ids': ['p'], 'nodes': [{'id': 'a', 'type': 'Character', 'canonical_name': 'UNREADABLE', 'aliases': []}],
                 'facts': [{'fact_id': 'f', 'args': ['a', 'p'], 'answer_eligible': True, 'origin': 'H'}],
                 'coverage': [{'coverage_id': 'cov', 'status': 'closed_assumed'}]}
        visibility = {'visibility': [{'identity_id': 'a', 'verified_forms': []}]}
        pins = {'/y/evidence/ckg/v1/chapters/c.json': 'pin'}
        return item, graph, visibility, pins

    def test_pack_requires_resolved_bound_facts(self):
        item, g, v, pins = self.fixture(); pack = prepare(item)
        with self.assertRaises(ValueError): request(pack, 'test-model')
        with self.assertRaises(ValueError): hydrate(pack, g)
        hydrated = hydrate(pack, g, visibility=v, verified_pins=pins)
        self.assertNotIn('canonical_name', hydrated['node_bodies'][0])
        self.assertEqual(hydrated['node_bodies'][0]['readable_name_forms'], [])
        payload = request(hydrated, 'test-model')
        self.assertEqual(payload['model'], 'test-model')
        self.assertEqual(len(payload['messages'][1]['content']), 1)

    def test_pack_rejects_stale_source_and_page_order(self):
        item, g, v, pins = self.fixture(); pack = prepare(item)
        with self.assertRaises(ValueError): hydrate(pack, g, visibility=v, verified_pins={'/y/evidence/ckg/v1/chapters/c.json': 'stale'})
        g['page_ids'] = ['other']
        with self.assertRaises(ValueError): hydrate(pack, g, visibility=v, verified_pins=pins)

    def test_paraphrase_cannot_get_crops_or_silent_truncation(self):
        item, *_ = self.fixture()
        with self.assertRaises(ValueError): prepare(item, crops=[{}])
        with self.assertRaises(ValueError): prepare(item, max_characters=1)

    def test_transport_resumes_raw_response_without_repeating_call(self):
        with tempfile.TemporaryDirectory() as temp:
            response = MagicMock(); response.__enter__.return_value.read.return_value = b'{"response":"test"}'
            with patch('urllib.request.urlopen', return_value=response) as network:
                out = Path(temp) / 'response.json'
                first = infer({'model': 'test'}, 'http://localhost/test', out)
                second = infer({'model': 'test'}, 'http://localhost/test', out)
                self.assertEqual(first, second)
                self.assertEqual(network.call_count, 1)
                with self.assertRaises(ValueError): infer({'model': 'changed'}, 'http://localhost/test', out)

    def test_positive_witness_missing_is_unknown_and_wrong_proof_rejected(self):
        companion = {'facts': [{'id': 'f', 'rel': 'left_of', 'args': ['a', 'b'], 'origin': 'V', 'answer_eligible': True}]}
        proof = positive_fact(companion, 'left_of', ['a', 'b'])
        self.assertTrue(check_positive_fact(companion, proof))
        proof['value'] = False
        self.assertFalse(check_positive_fact(companion, proof))
        self.assertEqual(positive_fact(companion, 'left_of', ['b', 'a'])['status'], 'UNKNOWN')

    def test_composition_reports_both_directions(self):
        r = composition_metrics({'a': False, 'b': True}, {'a': [True, True], 'b': [True, False]})
        self.assertEqual(r['all_steps_correct_full_wrong'], .5)
        self.assertEqual(r['full_correct_steps_not_all_correct'], .5)
