import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_expanded
from comics_qa.evidence.graph.rich.model import build
from comics_qa.benchmark1000.switch_search import Dependencies, DependencyBudget
from comics_qa.benchmark1000.coverage_windows import discover, chapter
from comics_qa.benchmark1000.expanded_families import compile_recipe, render
from comics_qa.benchmark1000.native import make
from comics_qa.benchmark1000.admission import World, assess
from comics_qa.benchmark1000.admission_store import admitted, validate
from comics_qa.benchmark1000.io import stable, read


class SwitchSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_expanded.ExpandedTests.setUpClass.__func__(cls)

    def setUp(self):
        test_expanded.ExpandedTests.setUp(self)
        test_expanded.ExpandedTests.two_actor_world(self)
        test_expanded.extend_synthetic(self.g, 9)
        from name_visibility import summarize
        self.v['page_ids'] = list(self.g['page_ids']); self.v['visibility'] = summarize(self.g, self.v['evidence'])
        self.r = build(self.g, self.v, self.r['sources'])
        self.walk = {'kind': 'speaker_walk', 'references': [{'quote': 'please come back now', 'page': 1}],
                     'start': 2, 'end': 8, 'steps': 2, 'profile': 'coverage_windows.1'}

    def test_necessary_walk_passes_unchanged_admission_and_keeps_sources(self):
        before = stable([self.g, self.v, self.r]); search = Dependencies(self.g, self.v, self.r, 20)
        result = search.assess(self.walk)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['main']['result']['display'], 7)
        self.assertEqual({i['label'] for i in result['interventions']}, {'switch:0', 'navigate:0', 'navigate:1'})
        self.assertTrue(all(i['proof_valid'] and i['outcome'] == 'necessary' for i in result['interventions']))
        from comics_qa.benchmark1000.semantic import execute
        doc, _, _ = execute('coverage_recipe', compile_recipe(self.walk), self.g, self.v, self.r)
        item = make(self.g, self.v, self.r, {}, question=render(self.walk), answer={'type': 'page', 'value': 7, 'identity_id': None},
                    answer_format='page', structure='chain', engine='coverage_recipe', program=compile_recipe(self.walk), execution=doc)
        receipt = assess(item, World(self.g, self.v, self.r), max_ablation_pages=16)
        self.assertTrue(receipt['passed'], receipt['reasons'])
        candidate = admitted(item, receipt); validate(candidate)
        self.assertEqual(candidate['complexity']['meaningful_hops'], 3)
        self.assertEqual(stable([self.g, self.v, self.r]), before)
        used = search.used; search.assess(self.walk)
        self.assertEqual(search.used, used)
        self.assertGreater(search.cache_hits, 0)

    def fake(self, result, supported=True, valid=True):
        return {'result': result}, {'proof_valid': valid}, supported

    def test_redundant_switch_stops_before_navigation_work(self):
        value = {'type': 'Page', 'status': 'OK', 'value': 'p7', 'display': 7, 'exact': True}
        with patch('comics_qa.benchmark1000.switch_search.execute', return_value=self.fake(value)):
            d = Dependencies(self.g, self.v, self.r); result = d.assess(self.walk)
        self.assertFalse(result['passed']); self.assertEqual(result['reason'], 'redundant_switch')
        self.assertEqual(result['unchecked_interventions'], 2); self.assertEqual(d.used, 2)

    def test_unknown_is_not_emptiness_or_necessity(self):
        main = {'type': 'Page', 'status': 'OK', 'value': 'p7', 'display': 7, 'exact': True}
        unknown = {'type': 'Page', 'status': 'UNKNOWN', 'value': None, 'display': None, 'exact': False}
        with patch('comics_qa.benchmark1000.switch_search.execute', side_effect=[self.fake(main), self.fake(unknown, False)]):
            result = Dependencies(self.g, self.v, self.r).assess(self.walk)
        self.assertEqual(result['reason'], 'unproved_switch'); self.assertFalse(result['passed'])
        empty = {**unknown, 'status': 'EMPTY'}
        with patch('comics_qa.benchmark1000.switch_search.execute', side_effect=[self.fake(main)] + [self.fake(empty, False)] * 3):
            result = Dependencies(self.g, self.v, self.r).assess(self.walk)
        self.assertTrue(result['passed'])

    def test_budget_exhaustion_is_explicit_and_not_a_redundant_result(self):
        d = Dependencies(self.g, self.v, self.r, 1)
        with self.assertRaises(DependencyBudget): d.assess(self.walk)
        report = d.report(); self.assertTrue(report['budget_exhausted']); self.assertEqual(d.used, 1)
        self.assertEqual(report['outcomes'], {'dependency_budget_exhausted': 1})
        self.assertFalse(report['records'][0]['passed'])

    def test_checker_disagreement_fails_closed(self):
        value = {'type': 'Page', 'status': 'OK', 'value': 'p7', 'display': 7, 'exact': True}
        with patch('comics_qa.benchmark1000.switch_search.execute', return_value=self.fake(value, valid=False)):
            with self.assertRaisesRegex(ValueError, 'disagreement'): Dependencies(self.g, self.v, self.r).assess(self.walk)

    def test_discovery_caps_retain_only_walks_that_pass_every_dependency(self):
        pools, stats, diagnostics = discover(self.g, self.v, self.r, search_budget=100, window=8, max_shift=0,
                                              max_windows=1, dependency_budget=80)
        self.assertTrue(pools['speaker_walk'], stats)
        self.assertFalse(any(v for k, v in pools.items() if k != 'speaker_walk'))
        for task in pools['speaker_walk']:
            self.assertTrue(task['dependency_discovery']['passed'])
        self.assertIn('dependency_search', diagnostics)
        self.assertEqual(len(stats['search_budget_hit']), 8)
        # Rejected windows do not count toward the one eligible window per anchor.
        self.assertTrue(all(t['recipe']['end'] >= 8 for t in pools['speaker_walk']))

    def test_runner_invalid_budgets_fail_before_source_access(self):
        from comics_qa.benchmark1000.family_pilot import run
        for budget in (0, -1, True, '10'):
            with self.assertRaises(ValueError): run('/missing', '/tmp/unused-switch-test', coverage_aware=True, dependency_budget=budget)
        with self.assertRaises(ValueError): run('/missing', '/tmp/unused-switch-test', dependency_budget=10)

    def test_runner_resume_and_changed_dependency_budget_refusal(self):
        from comics_qa.benchmark1000.family_pilot import run
        from comics_qa.benchmark1000.io import publish
        with tempfile.TemporaryDirectory() as temp:
            bench = Path(temp) / 'bench'; out = Path(temp) / 'pilot'
            for rel in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'):
                publish(bench / rel / 'manifest.json', {'config': {'chapters': [self.g['chapter_id']]}})
            kw = dict(per_family=1, max_executions=1, search_budget=100, window=8, max_shift=0,
                      coverage_aware=True, dependency_budget=80)
            with patch('comics_qa.benchmark1000.family_pilot.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.family_pilot.load_optional', return_value=self.r):
                first = run(bench, out, **kw)
                self.assertGreater(first['counts']['proposals'], 0)
                self.assertEqual(set(first['families']), {'speaker_walk'})
                self.assertGreater(first['dependency_search']['outcomes']['passed'], 0)
                self.assertEqual(read(out / 'config.json')['version'], 'necessary_switches.1')
                with patch('comics_qa.benchmark1000.coverage_windows.chapter', side_effect=AssertionError('Checkpoint reran')):
                    self.assertEqual(run(bench, out, **kw), first)
                with self.assertRaises(ValueError): run(bench, out, **{**kw, 'dependency_budget': 81})

    def test_three_navigation_walk_checks_both_switches_and_all_navigation_bypasses(self):
        main = {'type': 'Page', 'status': 'OK', 'value': 'p7', 'display': 7, 'exact': True}
        other = {**main, 'value': 'p6', 'display': 6}
        with patch('comics_qa.benchmark1000.switch_search.execute', side_effect=[self.fake(main)] + [self.fake(other)] * 5):
            result = Dependencies(self.g, self.v, self.r).assess({**self.walk, 'steps': 3})
        self.assertTrue(result['passed'])
        self.assertEqual({x['label'] for x in result['interventions']}, {'switch:0', 'switch:1', 'navigate:0', 'navigate:1', 'navigate:2'})
