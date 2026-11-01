import copy
import unittest
from comics_qa.benchmark1000.views import page_offset, feature_audit, apply
from comics_qa.benchmark1000.io import stable


def item():
    return {'item_id': 'i', 'answer_format': 'page', 'answer': {'value': 8},
            'verification': {'proof': 'archived_check'}, 'features': {'page_offset': None},
            'legacy': {'program_sha256': 'program', 'context': {'pages': [{'page_id': 'anchor', 'index': 3}]},
                       'execution': {'proof': {'steps': [
                           {'nid': 1, 'op': 'the', 'type': 'Page', 'value': 'anchor', 'status': 'OK', 'children': []},
                           {'nid': 2, 'op': 'char', 'type': 'Char', 'value': 'hero', 'status': 'OK', 'children': []},
                           {'nid': 3, 'op': 'next_app', 'type': 'App', 'children': [2, 1]}]}}}}


class ViewTests(unittest.TestCase):
    def test_offset_is_from_trace_not_question_numbers(self):
        self.assertEqual(page_offset(item()), {'page_offset': 5, 'offset_basis': 'checked_next_app_page_child', 'anchor_page_index': 3})

    def test_unanchored_page_answer_is_not_a_plus_one_opportunity(self):
        i = item(); i['legacy']['execution']['proof']['steps'] = []
        self.assertEqual(page_offset(i)['offset_basis'], 'not_next_appearance')
        self.assertIsNone(page_offset(i)['page_offset'])

    def test_reports_apply_without_modifying_original(self):
        i = item(); saved = copy.deepcopy(i)
        f = feature_audit([i], 'store')
        p = {'schema': 'comics_qa.benchmark1000.proof_validation.1', 'store_manifest_sha256': 'store',
             'items': [{'item_id': 'i', 'item_sha256': stable(i), 'proof': 'verified',
                        'check': {'proof_valid': True, 'accepted_for_generation': True, 'program_sha256': 'program'}}]}
        view = apply([i], 'store', p, f)[0]
        self.assertEqual(view['features']['page_offset'], 5)
        self.assertEqual(view['verification']['proof'], 'verified')
        self.assertEqual(i, saved)

    def test_stale_forged_and_rejected_reports_fail_closed(self):
        i = item(); f = feature_audit([i], 'store')
        f['items'][0]['features']['page_offset'] = 1
        with self.assertRaises(ValueError): apply([i], 'store', features=f)
        f = feature_audit([i], 'different-store')
        with self.assertRaises(ValueError): apply([i], 'store', features=f)
        f = feature_audit([i], 'store'); i['answer']['value'] = 9
        with self.assertRaises(ValueError): apply([i], 'store', features=f)

    def test_negative_next_offset_rejected(self):
        i = item(); i['answer']['value'] = 2
        with self.assertRaises(ValueError): page_offset(i)
