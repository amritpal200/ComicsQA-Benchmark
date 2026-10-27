"""CKG-0 safety, provenance and coverage regression tests; stdlib only."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

from test_core import make_world, build_core

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/comics_qa/evidence/graph'))
import audit_ckg0 as audit


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.images, self.human, self.magi = make_world(self.root)
        self.ocr = self.root / 'ocr'
        for image in sorted(self.images.rglob('*.jpg')):
            rel = image.relative_to(self.images).as_posix()
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            for kind, folder in [('human', self.human), ('magi3', self.magi)]:
                path = folder / (rel + '.json')
                if not path.exists():
                    continue
                doc = json.loads(path.read_text())
                doc['schema'] = f'comics_qa.{kind}.v1'
                doc['page'].update(relative_path=rel, image_sha256=digest)
                if kind == 'human':
                    doc['human']['panels_proxy'] = []
                else:
                    doc['magi3']['_meta']['status'] = 'complete'
                path.write_text(json.dumps(doc))
            hp = self.human / (rel + '.json')
            gt = hp.exists()
            boxes = ([t['box'] for t in json.loads(hp.read_text())['human']['texts']] if gt else
                     json.loads((self.magi / (rel + '.json')).read_text())['magi3']['texts'])
            op = self.ocr / (rel + '.json')
            op.parent.mkdir(parents=True, exist_ok=True)
            op.write_text(json.dumps({'schema': 'comics_qa.ocr.v1',
                'page': {'relative_path': rel, 'image_sha256': digest},
                'ocr': {'boxes_source': 'human' if gt else 'model:magi3', '_meta': {'status': 'complete'},
                        'texts': [{'index': i, 'box': b, 'status': 'ok', 'truncated': False,
                                   'text_normalized': 'Hello'} for i, b in enumerate(boxes)]}}))
        build_core.main(['--images', str(self.images), '--human', str(self.human),
                         '--magi3', str(self.magi), '--out', str(self.root / 'core')])
        self.argv = sum(([f'--{k}', str(v)] for k, v in {
            'images': self.images, 'human': self.human, 'magi3': self.magi,
            'ocr': self.ocr, 'core': self.root / 'core/v1', 'out': self.root / 'report'}.items()), [])

    def run_audit(self, *extra):
        return audit.audit(audit.parse_args(self.argv + list(extra)))

    def mutate(self, folder, change):
        path = sorted(folder.rglob('*.json'))[0]
        doc = json.loads(path.read_text())
        change(doc)
        path.write_text(json.dumps(doc))

    def test_clean_provenance_absent_gt_and_unverified_classes(self):
        a, report, pages, chapters, names, classes = self.run_audit('--verify-images')
        self.assertTrue(report['integrity_ok'], a.issues)
        self.assertEqual(report['pages_without_ground_truth'], 1)
        self.assertEqual(pages[1]['candidate_coverage']['char_boxes'], 'absent')
        self.assertEqual(pages[0]['candidate_coverage']['char_boxes'], 'closed_assumed')
        self.assertEqual(pages[0]['candidate_coverage']['panels'], 'open')
        self.assertFalse(chapters[0]['full_chapter_candidate_closed']['char_boxes'])
        self.assertEqual(classes[0]['semantics'], 'unverified')

    def test_output_manifest_and_sources_unchanged(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(audit.main(self.argv), 0)
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        out = self.root / 'report'
        manifest = json.loads((out / 'manifest.json').read_text())
        for name, digest in manifest['outputs_sha256'].items():
            self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
        with self.assertRaises(SystemExit):
            audit.parse_args(self.argv)

    def test_sample_never_claims_full_chapter(self):
        _, report, pages, chapters, _, _ = self.run_audit('--limit-pages', '1')
        self.assertEqual(report['scope'], 'sample')
        self.assertEqual(len(pages), 1)
        self.assertFalse(any(chapters[0]['full_chapter_candidate_closed'].values()))

    def test_stale_source_and_invalid_link(self):
        self.mutate(self.human, lambda d: d['human']['text_character'].append([0, 999]))
        _, report, pages, _, _, _ = self.run_audit()
        self.assertIn('invalid_human_link', report['issues_by_code'])
        self.assertIn('stale_core_source', report['issues_by_code'])
        self.assertEqual(pages[0]['candidate_coverage']['speaker_links'], 'open')

    def test_complete_ocr_can_be_truncated(self):
        self.mutate(self.ocr, lambda d: d['ocr']['texts'][0].update(status='truncated', truncated=True))
        _, report, _, _, _, _ = self.run_audit()
        self.assertEqual(report['ocr_statuses']['truncated'], 1)
        self.assertIn('ocr_text_review', report['issues_by_code'])

    def test_tail_without_speaker(self):
        self.mutate(self.human, lambda d: d['human'].update(text_character=[]))
        self.assertIn('tail_without_speaker', self.run_audit()[1]['issues_by_code'])

    def test_generic_name_policy(self):
        self.mutate(self.human, lambda d: d['human']['characters'][0].update(name='Unnamed person'))
        codes = self.run_audit()[1]['issues_by_code']
        self.assertIn('generic_policy_mismatch', codes)
        self.assertIn('identity_reference', codes)
        self.assertEqual(audit.name_kind('Teacher'), 'named')

    def test_invalid_json_stays_in_denominator(self):
        sorted(self.human.rglob('*.json'))[0].write_text('{broken')
        _, report, pages, _, _, _ = self.run_audit()
        self.assertEqual(report['pages_audited'], 3)
        self.assertIn('invalid_json', report['issues_by_code'])
        self.assertEqual(pages[0]['candidate_coverage']['char_boxes'], 'open')

    def test_duplicate_core_id_blocks_closure(self):
        path = self.root / 'core/v1/pages.jsonl'
        path.write_text(path.read_text() + path.read_text().splitlines()[0] + '\n')
        _, report, _, chapters, _, _ = self.run_audit()
        self.assertFalse(report['integrity_ok'])
        self.assertIn('duplicate_id', report['issues_by_code'])
        self.assertFalse(any(chapters[0]['full_chapter_candidate_closed'].values()))

    def test_extra_image_and_hash_change(self):
        image = sorted(self.images.rglob('*.jpg'))[0]
        image.write_bytes(b'changed')
        image.with_name('extra.jpg').write_bytes(b'extra')
        codes = self.run_audit('--verify-images')[1]['issues_by_code']
        self.assertIn('image_checksum', codes)
        self.assertIn('image_inventory', codes)

    def test_output_cannot_overlap_source_even_through_symlink(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.human, target_is_directory=True)
        with self.assertRaises(SystemExit):
            audit.parse_args(self.argv + ['--out', str(alias / 'report')])
        with self.assertRaises(ValueError):
            audit.safe_path(self.human, '../escape')


if __name__ == '__main__':
    unittest.main()
