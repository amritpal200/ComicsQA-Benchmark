"""Review decisions must preserve evidence and never close unresolved coverage."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

import test_ckg0

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/comics_qa/evidence/graph'))
import audit_ckg0
import review_ckg0


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.world = test_ckg0.AuditTest(methodName='test_sample_never_claims_full_chapter')
        with contextlib.redirect_stderr(io.StringIO()):
            self.world.setUp()
        self.addCleanup(self.world.doCleanups)
        self.root = self.world.root

    def snapshot(self, generic=False, tail_flag=False):
        core = self.root / 'core/v1'
        if generic:
            path = core / 'pages.jsonl'
            pages = review_ckg0.read_rows(path)
            p = pages[0]
            char = p['characters'][0]
            char.update(name='Unnamed woman', identity_id='hero__unnamed-woman')
            human_path = self.world.human / (p['relative_path'] + '.json')
            human = review_ckg0.read_json(human_path)
            human['human']['characters'][0]['name'] = 'Unnamed woman'
            if tail_flag:
                human['human']['text_character'] = []
                p['texts'][1]['speaker_char_ids'] = []
            human_path.write_text(json.dumps(human))
            p['sources']['human']['sha256'] = audit_ckg0.sha256(human_path.read_bytes())
            audit_ckg0.write_jsonl(path, pages)
            m = review_ckg0.read_json(core / 'manifest.json')
            m['input_files_sha256'][p['relative_path']] = p['sources']
            audit_ckg0.write_json(core / 'manifest.json', m)
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            audit_ckg0.main(self.world.argv)
        return core, self.root / 'report'

    def review(self, generic=False, tail_flag=False):
        core, report = self.snapshot(generic, tail_flag)
        _, _, pages, audit_pages, chapters, issues = review_ckg0.load_snapshot(report, core)
        return review_ckg0.make_review(pages, audit_pages, chapters, issues)

    def test_generic_resolution_is_explicit_and_preserves_source_id(self):
        summary, rows = self.review(generic=True)
        self.assertEqual(summary['resolved_errors'], 1)
        self.assertEqual(summary['unresolved_errors'], 0)
        override = rows['identity_overrides'][0]
        self.assertEqual(override['source_identity_id'], 'hero__unnamed-woman')
        self.assertEqual(override['identity_id'], 'hero__c001__p000__unnamed0')
        self.assertEqual(override['aliases'], [])
        self.assertFalse(override['named'])
        p = rows['coverage'][0]
        self.assertEqual(p['candidate_coverage']['names'], 'closed_assumed')
        self.assertEqual(p['previous_candidate_coverage']['names'], 'open')

    def test_resolved_identity_does_not_close_other_flags(self):
        summary, rows = self.review(generic=True, tail_flag=True)
        self.assertEqual(summary['unresolved_errors'], 0)
        self.assertEqual(rows['coverage'][0]['candidate_coverage']['speaker_links'], 'open')
        self.assertTrue(rows['coverage'][0]['unresolved_issue_lines'])

    def test_absent_and_model_coverage_stay_unchanged(self):
        _, rows = self.review()
        self.assertEqual(rows['identity_overrides'], [])
        self.assertEqual(rows['coverage'][1]['candidate_coverage']['names'], 'absent')
        self.assertFalse(rows['coverage'][1]['allow_positive_facts'])
        self.assertTrue(all(p['candidate_coverage']['panels'] == 'open' for p in rows['coverage']))
        self.assertFalse(rows['chapters'][0]['full_chapter_candidate_closed']['names'])

    def test_unknown_errors_remain_blocking(self):
        core, report = self.snapshot()
        _, _, pages, ap, chapters, issues = review_ckg0.load_snapshot(report, core)
        issues.append({'code': 'unrecognized_error', 'severity': 'error', 'page_id': None,
                       'chapter_id': None, 'families': [], 'pointer': '', 'file': None})
        summary, rows = review_ckg0.make_review(pages, ap, chapters, issues)
        self.assertFalse(summary['ready_for_ckg1_with_restrictions'])
        self.assertEqual(summary['unresolved_errors'], 1)

    def test_modified_report_rejected(self):
        core, report = self.snapshot()
        (report / 'issues.jsonl').write_text('')
        # Ensure bytes actually differ even when the clean fixture has no issues.
        (report / 'issues.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'Audit checksum mismatch'):
            review_ckg0.load_snapshot(report, core)

    def test_modified_core_rejected(self):
        core, report = self.snapshot()
        with (core / 'pages.jsonl').open('a') as handle:
            handle.write('\n')
        with self.assertRaisesRegex(ValueError, 'Core differs'):
            review_ckg0.load_snapshot(report, core)

    def test_outputs_checksums_and_no_input_mutation(self):
        core, report = self.snapshot(generic=True)
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        out = self.root / 'review'
        argv = ['--core', str(core), '--audit', str(report), '--out', str(out)]
        self.assertEqual(review_ckg0.main(argv), 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        m = review_ckg0.read_json(out / 'manifest.json')
        for name, digest in m['outputs_sha256'].items():
            self.assertEqual(audit_ckg0.sha256((out / name).read_bytes()), digest)
        with self.assertRaisesRegex(ValueError, 'exists'):
            review_ckg0.main(argv)

    def test_output_overlap_rejected(self):
        core, report = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'separate'):
            review_ckg0.main(['--core', str(core), '--audit', str(report), '--out', str(report / 'review')])

    def test_named_cluster_conflict_not_silently_merged(self):
        core, report = self.snapshot(generic=True)
        _, _, pages, ap, chapters, issues = review_ckg0.load_snapshot(report, core)
        char = pages['hero__c001__p000']['characters'][1]
        char.update(name='Teacher', page_cluster=0)
        summary, rows = review_ckg0.make_review(pages, ap, chapters, issues)
        self.assertEqual(rows['identity_overrides'], [])
        self.assertEqual(summary['unresolved_errors'], 1)

    def test_geometry_flag_ranked_without_clipping_or_closing(self):
        core, report = self.snapshot()
        _, _, pages, ap, chapters, issues = review_ckg0.load_snapshot(report, core)
        pid = 'hero__c001__p000'
        pages[pid]['characters'][0]['box'] = [-20, 10, 90, 90]
        ap[pid]['candidate_coverage']['char_boxes'] = 'open'
        issues.append({'code': 'box_outside_image', 'severity': 'warning', 'page_id': pid,
                       'chapter_id': 'hero__c001', 'families': ['char_boxes'],
                       'pointer': '/human/characters/0/box', 'file': 'human.json'})
        _, rows = review_ckg0.make_review(pages, ap, chapters, issues)
        self.assertEqual(rows['geometry_review'][0]['max_overflow_px'], 20)
        self.assertEqual(rows['geometry_review'][0]['box'][0], -20)
        self.assertEqual(rows['coverage'][0]['candidate_coverage']['char_boxes'], 'open')


if __name__ == '__main__':
    unittest.main()
