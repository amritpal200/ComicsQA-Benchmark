import copy
import unittest
import test_gen2
from comics_qa.benchmark1000.relay import RelayEngine, RelayChecker
from comics_qa.benchmark1000.semantic import patterns, chapter_inventory


class SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_gen2.FamiliesTest.setUpClass.__func__(cls)

    def setUp(self):
        test_gen2.FamiliesTest.setUp(self)
        from comics_qa.evidence.graph.rich.model import build
        for alignment in self.v['alignments']:
            if (alignment.get('text_id') or '').endswith('htext01'):
                alignment['paddle_text'] = alignment['magi_text'] = 'please come back now'
        self.r = build(self.g, self.v, self.r['sources'])
    def test_relay_stops_honestly_and_wrong_result_is_rejected(self):
        program = {'op': 'speaker_relay', 'quote': 'please come back now', 'page': 1}
        doc = RelayEngine(self.g, self.v, self.r).execute(program)
        self.assertTrue(RelayChecker(self.g, self.v, self.r).check(doc)['proof_valid'])
        bad = copy.deepcopy(doc); bad['result']['value'] = 'wrong'
        self.assertFalse(RelayChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        bad = copy.deepcopy(doc); bad['stages'][0]['execution']['program']['after'] = 2
        self.assertFalse(RelayChecker(self.g, self.v, self.r).check(bad)['proof_valid'])

    def test_inventory_measures_executions_and_reports_bounds(self):
        qs, stats = patterns(self.g, self.r, per_pattern=1, clue_search=1)
        self.assertGreaterEqual(len(qs), 2)
        self.assertLessEqual(len(qs), 4)
        self.assertTrue(all(q['engine'] in ('crl', 'scan', 'relay') for q in qs))
        result = chapter_inventory(self.g, self.v, self.r, {}, 1, 0, 1)
        self.assertEqual(result['counts']['executed'], len(result['queries']))
        self.assertTrue(all(q['check']['proof_valid'] for q in result['queries']))
        self.assertTrue(all(q['meaningful_hops'] is None for q in result['queries']))
        self.assertTrue(all(i['admission'] == 'proposal' for i in result['proposals']))

    def test_page_dependencies_are_measured_on_a_closed_synthetic_world(self):
        from comics_qa.evidence.graph.rich.model import build
        for c in self.g['coverage']:
            if c['family'] in ('char_boxes', 'names', 'text_boxes', 'speaker_links'):
                c['status'] = 'closed_verified'
        self.r = build(self.g, self.v, self.r['sources'])
        result = chapter_inventory(self.g, self.v, self.r, {}, 2, 8, 1)
        known = [q for q in result['queries'] if q['answer_supported']]
        self.assertTrue(known)
        self.assertTrue(all(q['ablation_status'] == 'measured' for q in known))
        self.assertTrue(any(len(q['required_pages']) >= 2 for q in known))

    def test_budget_reporting_is_not_an_exhaustive_depth_claim(self):
        _, stats = patterns(self.g, self.r, per_pattern=1, clue_search=1)
        clues = stats['three_page_clue']
        self.assertLessEqual(clues['combinations_tested'], 1)
        self.assertIn('search_exhausted', clues)
        self.assertIn('search_budget_hit', clues)

    def test_checkpoint_resume_skips_execution_and_rejects_new_budget(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from comics_qa.benchmark1000.io import publish
        from comics_qa.benchmark1000.semantic import run
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'bench'; cid = self.g['chapter_id']
            for name in ('ckg', 'name_visibility', 'ckg3'):
                publish(root / 'evidence' / name / 'v1/manifest.json', {'config': {'chapters': [cid]}})
            kwargs = {'chapters': [cid], 'per_pattern': 1, 'max_ablation_pages': 0, 'clue_search': 1}
            with patch('comics_qa.benchmark1000.semantic.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.semantic.load_optional', return_value=self.r):
                first = run(root, Path(temp) / 'out', **kwargs)
                with patch('comics_qa.benchmark1000.semantic.chapter_inventory', side_effect=AssertionError('must reuse checkpoint')):
                    self.assertEqual(first, run(root, Path(temp) / 'out', **kwargs))
                with self.assertRaises(ValueError):
                    run(root, Path(temp) / 'out', **{**kwargs, 'per_pattern': 2})

    def test_removed_pages_cannot_keep_ocr_alignments(self):
        from unittest.mock import patch
        from comics_qa.evidence.graph.rich.model import build
        for c in self.g['coverage']:
            if c['family'] in ('char_boxes', 'names', 'text_boxes', 'speaker_links'):
                c['status'] = 'closed_verified'
        self.r = build(self.g, self.v, self.r['sources'])
        with patch('comics_qa.benchmark1000.semantic.rebuild_rich', wraps=build) as rebuild:
            chapter_inventory(self.g, self.v, self.r, {}, 2, 8, 1)
        self.assertTrue(rebuild.call_args_list)
        for call_args in rebuild.call_args_list:
            g2, v2 = call_args.args[:2]
            hidden = {c['page_id'] for c in g2['coverage'] if c['family'] == 'text_boxes' and c['status'] == 'absent'}
            self.assertFalse(hidden & {a['page_id'] for a in v2['alignments']})

    def test_invalid_budgets_publish_nothing(self):
        import tempfile
        from pathlib import Path
        from comics_qa.benchmark1000.semantic import run
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out'
            with self.assertRaises(ValueError):
                run(Path(temp) / 'bench', out, per_pattern=0)
            self.assertFalse(out.exists())

    def test_recovery_reexecutes_and_preserves_original_checkpoints(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from comics_qa.benchmark1000.io import publish, read, digest, encoded, stable
        from comics_qa.benchmark1000.semantic import run
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'bench'; cid = self.g['chapter_id']
            for name in ('ckg', 'name_visibility', 'ckg3'):
                publish(root / 'evidence' / name / 'v1/manifest.json', {'config': {'chapters': [cid]}})
            args = {'chapters': [cid], 'per_pattern': 1, 'max_ablation_pages': 0, 'clue_search': 1}
            old, new = Path(temp) / 'old', Path(temp) / 'new'
            with patch('comics_qa.benchmark1000.semantic.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.semantic.load_optional', return_value=self.r):
                run(root, old, **args)
                # Model a partial run produced by an earlier native-code version.
                config = read(old / 'config.json'); config['code_sha256']['native.py'] = 'previous-code'
                (old / 'config.json').write_text(encoded(config) + '\n')
                checkpoint = old / 'chapters' / (cid + '.json')
                wrapper = read(checkpoint); wrapper['config_sha256'] = stable(config)
                checkpoint.write_text(encoded(wrapper) + '\n'); (old / 'manifest.json').unlink()
                before = digest(checkpoint)
                from comics_qa.benchmark1000.semantic import chapter_inventory as actual
                with patch('comics_qa.benchmark1000.semantic.chapter_inventory', wraps=actual) as recheck:
                    result = run(root, new, reuse_from=old, **args)
                    self.assertEqual(recheck.call_count, 1)
                self.assertEqual(digest(checkpoint), before)
                recovered = read(new / 'chapters' / (cid + '.json'))
                self.assertEqual(recovered['reused_checkpoint']['sha256'], before)
                self.assertEqual(recovered['payload'], wrapper['payload'])
                self.assertEqual(result, run(root, new, reuse_from=old, **args))
                with self.assertRaises(ValueError): run(root, Path(temp) / 'bad', reuse_from=old, **{**args, 'per_pattern': 2})
