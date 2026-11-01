import copy
import json
from pathlib import Path
import tempfile
import unittest

from comics_qa.benchmark1000.adapters import records
from comics_qa.benchmark1000.io import stable, publish, digest, member, legacy_snapshot, verify_snapshot
from comics_qa.benchmark1000.store import ingest, load


def fixture(root):
    item = {'item_id': 'old:1', 'chapter_id': 'c', 'split': 'seen', 'question': 'How many?',
            'answer': {'type': 'int', 'value': 3, 'identity_id': None}, 'program': {'op': 'count'},
            'program_sha256': 'p', 'execution': {'program': {'op': 'count'}},
            'proof_check': {'accepted_for_generation': True, 'proof_valid': True},
            'dimensions': {'necessary_pages': ['c__p1']}}
    payload = {'chapter_id': 'c', 'split': 'seen', 'candidates': [item], 'frequent_ids': []}
    wrapper = {'payload': payload, 'payload_sha256': stable(payload)}
    publish(root / 'candidate_pools/c.json', wrapper)
    publish(root / 'manifest.json', {'config': {'chapters': ['c']}, 'outputs_sha256': {
        'candidate_pools/c.json': digest(root / 'candidate_pools/c.json')}})


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'old'
        fixture(self.source)

    def test_import_resume_and_legacy_unchanged(self):
        before = {str(p): digest(p) for p in self.source.rglob('*.json')}
        a = ingest([self.source], self.root / 'new')
        self.assertEqual(a, ingest([self.source], self.root / 'new'))
        items = load(self.root / 'new')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['verification']['proof'], 'archived_check')
        self.assertEqual(items[0]['verification']['release'], 'pending')
        self.assertEqual(before, {str(p): digest(p) for p in self.source.rglob('*.json')})

    def test_changed_input_rejected_without_overwriting_store(self):
        ingest([self.source], self.root / 'new')
        p = self.source / 'manifest.json'
        d = json.loads(p.read_text()); d['changed'] = True; p.write_text(json.dumps(d))
        with self.assertRaises(ValueError):
            ingest([self.source], self.root / 'new')
        self.assertEqual(len(load(self.root / 'new')), 1)

    def test_output_inside_or_above_source_rejected(self):
        for dest in (self.source / 'sub', self.source, self.root):
            with self.assertRaises(ValueError):
                ingest([self.source], dest)

    def test_manifest_cannot_escape_root(self):
        for name in ('../secret', '/etc/passwd', '.'):
            with self.assertRaises(ValueError):
                member(self.source, name)

    def test_symlink_escape_rejected(self):
        (self.source / 'escape').symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            member(self.source, 'escape/file')

    def test_tampered_source_shard_rejected(self):
        p = self.source / 'candidate_pools/c.json'
        p.write_text('{}')
        with self.assertRaises(ValueError):
            list(records(self.source))

    def test_unknown_chapter_rejected(self):
        with self.assertRaises(ValueError):
            list(records(self.source, ['other']))

    def test_duplicate_sources_rejected(self):
        with self.assertRaises(ValueError):
            ingest([self.source, self.source], self.root / 'new')

    def test_publish_never_replaces(self):
        p = self.root / 'answer.json'
        publish(p, {'answer': 1})
        with self.assertRaises(ValueError):
            publish(p, {'answer': 2})
        self.assertEqual(json.loads(p.read_text()), {'answer': 1})

    def test_snapshot_detects_legacy_addition_and_ignores_new_layer(self):
        repo = self.root / 'repo'; (repo / 'src').mkdir(parents=True)
        (repo / 'src/old.py').write_text('old')
        snap = legacy_snapshot(repo)
        (repo / 'src/benchmark1000').mkdir()
        (repo / 'src/benchmark1000/new.py').write_text('new')
        verify_snapshot(repo, snap)
        (repo / 'src/old.py').write_text('changed')
        with self.assertRaises(ValueError):
            verify_snapshot(repo, snap)

class NamespaceGuardTests(unittest.TestCase):
    def test_outputs_cannot_enter_other_legacy_dataset_roots(self):
        from comics_qa.benchmark1000.io import separate
        with tempfile.TemporaryDirectory() as temp:
            bench = Path(temp)
            source = bench / 'items/gen2/v3'
            with self.assertRaises(ValueError):
                separate(bench / 'items/gen1/new', [source])
            with self.assertRaises(ValueError):
                separate(bench / 'annotations/new', [source])
            self.assertEqual(separate(bench / 'items/benchmark1000/new', [source]), bench / 'items/benchmark1000/new')

    def test_new_launcher_is_not_misclassified_as_legacy(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp); (repo / 'scripts').mkdir()
            (repo / 'scripts/benchmark1000.sh').write_text('new')
            (repo / 'scripts/legacy.sh').write_text('old')
            self.assertEqual(set(legacy_snapshot(repo)), {'scripts/legacy.sh'})
