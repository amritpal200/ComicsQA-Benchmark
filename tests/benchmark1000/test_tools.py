import copy
import tempfile
from pathlib import Path
import unittest

from comics_qa.benchmark1000.claims import validate_claims, score
from comics_qa.benchmark1000.review import zero_error_bound, sample, validate_decision, release_eligible
from comics_qa.benchmark1000.io import stable, digest
from comics_qa.benchmark1000.evaluation import exact, pair_accuracy, evidence_score
from comics_qa.benchmark1000.assets import render, masked_overlay


class ClaimsReviewScoringTests(unittest.TestCase):
    def claims(self):
        return {'required': [{'id': 'r', 'text': 'A speaks.', 'evidence': ['fact'], 'verification': 'supported'}],
                'optional': [], 'forbidden': [{'id': 'f', 'text': 'B speaks.', 'evidence': ['contradiction'], 'verification': 'contradicted'}]}

    def test_unknown_cannot_be_forbidden(self):
        c = self.claims(); c['forbidden'][0]['verification'] = 'unknown'
        with self.assertRaises(ValueError): validate_claims(c)

    def test_no_forbidden_claim_does_not_prove_no_hallucination(self):
        result = score(self.claims(), {'r': True, 'f': False})
        self.assertEqual(result['required_claim_recall'], 1)
        self.assertIsNone(result['fully_factual'])
        self.assertFalse(score(self.claims(), {'r': True, 'f': False}, 1)['fully_factual'])

    def test_missing_judgment_rejected(self):
        with self.assertRaises(ValueError): score(self.claims(), {'r': True})

    def test_sample_bound_and_reproducibility(self):
        self.assertAlmostEqual(zero_error_bound(60), .0487, places=3)
        items = [{'item_id': str(i)} for i in range(100)]
        self.assertEqual(sample(items, 20, 42), sample(items[::-1], 20, 42))
        self.assertEqual(len(sample(items, 20, 42)['selected_ids']), 20)

    def test_ai_review_never_approves_release(self):
        item = {'item_id': 'x', 'evidence_class': 'executed', 'verification': {'proof': 'verified', 'wording': 'verified'}}
        decision = {'item_id': 'x', 'item_sha256': stable(item), 'reviewer': 'test',
                    'reviewer_type': 'ai', 'decision': 'accept', 'reason': 'checked', 'review_version': '1'}
        self.assertFalse(release_eligible(item, [decision]))
        decision['reviewer_type'] = 'human'
        self.assertTrue(release_eligible(item, [decision]))
        item['verification']['wording'] = 'pending'
        self.assertFalse(release_eligible(item, [decision]))

    def test_stale_review_rejected(self):
        item = {'item_id': 'x'}
        with self.assertRaises(ValueError):
            validate_decision(item, {'item_id': 'x', 'item_sha256': 'old', 'reviewer': 'h',
                                    'reviewer_type': 'human', 'decision': 'accept', 'reason': 'ok', 'review_version': '1'})

    def test_typed_scoring_and_alternative_evidence(self):
        self.assertFalse(exact('count', True, 1))
        self.assertTrue(exact('count', ' 12 ', 12))
        self.assertFalse(exact('page', 'page 12', 12))
        self.assertTrue(exact('set', ['B', 'A'], ['A', 'B']))
        self.assertFalse(exact('sequence', ['B', 'A'], ['A', 'B']))
        self.assertEqual(evidence_score([3], [[1, 2], [3]])['f1'], 1)
        self.assertEqual(pair_accuracy({'a': True, 'b': False}, {'p': ['a', 'b']}), 0)


class ImageTests(unittest.TestCase):
    def setUp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed in this Python; use isolated uv environment')
        self.Image = Image
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.source = self.root / 'source.png'
        Image.new('RGB', (10, 10), (255, 255, 255)).save(self.source)
        self.sha = digest(self.source)

    def test_mask_pixels_and_original_unchanged(self):
        out = self.root / 'mask.png'
        manifest = render(self.source, self.sha, [[2, 2, 5, 5]], out, 'mask')
        with self.Image.open(out) as image:
            self.assertEqual(image.getpixel((2, 2)), (0, 0, 0))
            self.assertEqual(image.getpixel((4, 4)), (0, 0, 0))
            self.assertEqual(image.getpixel((5, 5)), (255, 255, 255))
        self.assertEqual(digest(self.source), self.sha)
        self.assertEqual(render(self.source, self.sha, [[2, 2, 5, 5]], out, 'mask'), manifest)

    def test_crop_rejects_wrong_hash_and_outside_box(self):
        for sha, box in [('wrong', [0, 0, 2, 2]), (self.sha, [-1, 0, 2, 2])]:
            with self.assertRaises(ValueError): render(self.source, sha, [box], self.root / 'crop.png', 'crop')

    def test_mask_invalidates_derivatives_but_does_not_assert_absence(self):
        g = {'nodes': [{'id': 'p', 'type': 'Page', 'width': 10, 'height': 10},
                       {'id': 'a', 'page_id': 'p', 'box': [1, 1, 3, 3]}],
             'facts': [{'fact_id': 'f1', 'args': ['a', 'p'], 'page_ids': ['p'], 'origin': 'H', 'premises': []},
                       {'fact_id': 'f2', 'args': ['c', 'p'], 'page_ids': ['p'], 'origin': 'H', 'premises': ['f1']}],
             'coverage': [{'coverage_id': 'c', 'page_id': 'p', 'family': 'char_boxes', 'status': 'closed_assumed'}]}
        before = copy.deepcopy(g)
        overlay = masked_overlay(g, 'p', [[0, 0, 4, 4]])
        self.assertEqual(overlay['invalidated_fact_ids'], ['f1', 'f2'])
        self.assertEqual(overlay['coverage_overrides'][0]['status'], 'open')
        self.assertIsNone(overlay['determinability_certificate'])
        self.assertEqual(g, before)

class CalibrationTests(unittest.TestCase):
    def test_degenerate_marginals_are_not_division_by_zero(self):
        from comics_qa.benchmark1000.calibration import agreement
        result = agreement([{'id': 'x', 'human': True, 'judge': True}])
        self.assertEqual(result['agreement'], 1)
        self.assertIsNone(result['cohens_kappa'])

    def test_balanced_disagreement_and_confusion(self):
        from comics_qa.benchmark1000.calibration import agreement
        result = agreement([{'id': 'x', 'human': True, 'judge': False},
                            {'id': 'y', 'human': False, 'judge': True}])
        self.assertEqual(result['cohens_kappa'], -1)
        self.assertEqual(result['false_negative'], 1)
        self.assertEqual(result['false_positive'], 1)
