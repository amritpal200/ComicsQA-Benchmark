import copy
from pathlib import Path
import unittest
from comics_qa.benchmark1000.io import read
from comics_qa.benchmark1000.selection import select, violations, policy

CONFIG = Path(__file__).resolve().parents[2] / 'configs/benchmark1000/v1.json'


def candidate(index, value=2, fmt='count', identity=None, chapter='c', split='seen'):
    return {'item_id': str(index), 'chapter_id': chapter, 'split': split,
            'evidence_class': 'executed', 'answer_format': fmt,
            'primary_group': 'short', 'reasoning_tags': [],
            'answer': {'value': value}, 'verification': {'proof': 'verified'},
            'features': {'semantic_target': str(index), 'identity_id': identity,
                         'two_option': False, 'is_top2_identity': False, 'page_offset': None}}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.p = read(CONFIG)

    def test_final_reports_insufficient_pool_not_invalid_proofs(self):
        _, report = select([candidate(1)], self.p)
        self.assertEqual(report['status'], 'infeasible')
        self.assertEqual(report['reason'], 'too_few_distinct_candidates')

    def test_small_pool_uses_absolute_cap_and_preserves_inputs(self):
        items = [candidate(i, identity='hero', fmt='character') for i in range(5)]
        saved = copy.deepcopy(items)
        selected, report = select(items, self.p, pilot=True)
        self.assertEqual(len(selected), 3)
        self.assertEqual(report['status'], 'optimal')
        self.assertEqual(items, saved)

    def test_ratio_can_be_repaired_by_later_candidates(self):
        self.p['minimum_denominator'] = 2
        self.p['modal_count_share'] = .5
        selected, _ = select([candidate(1, 2), candidate(2, 2), candidate(3, 3), candidate(4, 3)], self.p, pilot=True)
        self.assertEqual(len(selected), 4)

    def test_budget_does_not_claim_infeasibility(self):
        _, r = select([candidate(i) for i in range(20)], self.p, pilot=True, max_nodes=1)
        self.assertEqual(r['status'], 'unknown_budget_exhausted')

    def test_split_cannot_subsidise_modal_answer(self):
        self.p['minimum_denominator'] = 2
        self.p['modal_count_share'] = .5
        errors = violations([candidate(1, 2), candidate(2, 2), candidate(3, 3, split='unseen'), candidate(4, 4, split='unseen')], self.p)
        self.assertIn('seen:modal_count', errors)

    def test_missing_top1_not_treated_as_false(self):
        self.p['minimum_denominator'] = 2
        errors = violations([candidate(1, fmt='character', identity='a'), candidate(2, fmt='character', identity='b')], self.p)
        self.assertIn('seen:unknown_top1_features', errors)

    def test_pair_cannot_be_selected_alone(self):
        i = candidate(1); i['pair_id'] = 'pair'
        self.assertIn('pair_closure', violations([i], self.p))
        j = candidate(2); j['pair_id'] = 'pair'
        self.assertNotIn('pair_closure', violations([i, j], self.p))

    def test_bad_policy_rejected(self):
        self.p['two_option_share'] = float('nan')
        with self.assertRaises(ValueError):
            policy(self.p)

    def test_binary_budget_applies_even_in_pilot(self):
        i = candidate(1, fmt='boolean'); i['features']['two_option'] = True
        selected, _ = select([i], self.p, pilot=True)
        self.assertFalse(selected)

    def test_intentional_mask_pair_with_same_target_is_not_deduplicated(self):
        a, b = candidate(1, 2), candidate(2, 3)
        a['pair_id'] = b['pair_id'] = 'mask-pair'
        a['features']['semantic_target'] = b['features']['semantic_target'] = 'same-target'
        chosen, report = select([a, b], self.p, pilot=True)
        self.assertEqual(len(chosen), 2)
        self.assertFalse(report['excluded'])

    def test_split_freeze_requires_full_scope_and_preserves_source_ratios(self):
        from comics_qa.benchmark1000.freeze import freeze
        report = {'scope': 'selected_chapters', 'chapters': [{'chapter_id': 'a', 'split': 'seen'}], 'manifest_sha256': 'm'}
        with self.assertRaises(ValueError): freeze(self.p, report)
        report['scope'] = 'full_collection'
        report['chapters'] += [{'chapter_id': 'b', 'split': 'seen'}, {'chapter_id': 'c', 'split': 'unseen'}]
        frozen, lineage = freeze(self.p, report)
        self.assertEqual(frozen['split_counts'], {'seen': 667, 'unseen': 333})
        self.assertIsNone(self.p['split_counts'])
        self.assertEqual(lineage['feasibility'], 'not_established_by_structural_inventory')

    def test_final_labels_do_not_certify_complexity_or_sentence_claims(self):
        item = candidate(1); item['primary_group'] = 'chain'
        self.assertIn('chain_complexity_uncertified', violations([item], self.p, final=True))
        item['primary_group'] = 'sentence'
        self.assertIn('sentence_claims_unverified', violations([item], self.p, final=True))
        item['primary_group'] = 'paired'
        self.assertIn('paired_edit_unverified', violations([item], self.p, final=True))

    def test_direct_proposal_input_never_enters_pilot_selection(self):
        i = candidate(1); i['admission'] = 'proposal'
        selected, _ = select([i], self.p, pilot=True)
        self.assertEqual(selected, [])
