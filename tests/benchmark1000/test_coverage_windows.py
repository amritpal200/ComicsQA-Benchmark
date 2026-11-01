import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_expanded
from comics_qa.evidence.graph.rich.model import build
from comics_qa.benchmark1000.coverage_windows import Probes, ProbeBudget, discover, VERSION
from comics_qa.benchmark1000.expanded_families import compile_recipe, parse_question, render
from comics_qa.benchmark1000.native_wording import speaker
from comics_qa.benchmark1000.recipe_engine import RecipeEngine
from comics_qa.benchmark1000.native import make
from comics_qa.benchmark1000.admission import World, assess
from comics_qa.benchmark1000.admission_store import admitted, validate
from comics_qa.benchmark1000.io import stable, publish


class CoverageWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_expanded.ExpandedTests.setUpClass.__func__(cls)

    def setUp(self):
        test_expanded.ExpandedTests.setUp(self)

    def open_page(self, page):
        for c in self.g['coverage']:
            if c['page_id'] == self.g['page_ids'][page - 1] and c['family'] in ('char_boxes', 'names', 'text_boxes', 'speaker_links'):
                c['status'] = 'open'
        self.r = build(self.g, self.v, self.r['sources'])

    def test_new_shifted_wording_round_trip_does_not_change_legacy_grammar(self):
        old = {**self.recipe, 'start': 3}
        with self.assertRaises(ValueError): compile_recipe(old)
        recipe = {**old, 'profile': VERSION}
        parsed = parse_question(render(recipe))
        self.assertEqual(parsed['recipe'], recipe)
        self.assertEqual(parsed['profile_version'], VERSION)
        legacy = parse_question(render(self.recipe))
        self.assertEqual(legacy['profile_version'], 'expanded_families.1')
        self.assertNotIn('profile', legacy['recipe'])
        with self.assertRaises(ValueError): parse_question(render(recipe).replace('inclusive range', 'exclusive range'))

    def test_known_positive_is_usable_with_open_coverage_without_mutation(self):
        self.open_page(3); before = stable([self.g, self.v, self.r])
        probes = Probes(self.g, self.v, self.r, 8, 8)
        actor = probes.actor(speaker('please come back now', 1), '_anchors')
        value = probes.predicate('present', [actor], 3, 'shared_presence_pages')
        self.assertIs(value['value'], True)
        from comics_qa.benchmark1000.membership import known_truth
        self.assertTrue(known_truth(value))
        self.assertEqual(stable([self.g, self.v, self.r]), before)
        self.assertTrue(any(c['status'] == 'open' for c in self.g['coverage'] if c['page_id'] == self.g['page_ids'][2]))

    def test_unknown_absence_has_operator_identity_page_and_coverage_diagnostics(self):
        self.open_page(2); probes = Probes(self.g, self.v, self.r, 8, 8)
        actor = probes.actor(speaker('please come back now', 1), '_anchors')
        value = probes.predicate('present', [actor], 2, 'shared_presence_pages')
        self.assertEqual(value['status'], 'UNKNOWN')
        report = probes.report(); details = [d for r in report['uncertainty_records'] for d in r['uncertainty']['details'] if d['operator'] == 'present']
        self.assertTrue(details)
        detail = details[0]
        self.assertEqual(detail['page_ids'], [self.g['page_ids'][1]])
        self.assertIn(actor['id'], detail['known_identity_ids'])
        self.assertEqual({c['family'] for c in detail['open_requirements']}, {'char_boxes', 'names'})
        self.assertEqual(detail['category'], 'open_coverage')
        self.assertTrue(detail['reason'])

    def test_budget_exhaustion_is_not_an_absence_or_a_coverage_decision(self):
        probes = Probes(self.g, self.v, self.r, 1, 8)
        actor = probes.actor(speaker('please come back now', 1), '_anchors')
        probes.predicate('present', [actor], 3, 'shared_presence_pages')
        with self.assertRaises(ProbeBudget): probes.predicate('present', [actor], 4, 'shared_presence_pages')
        report = probes.report()
        self.assertEqual(report['new_queries']['shared_presence_pages'], 1)
        self.assertEqual(report['budget_exhaustion'][0]['category'], 'probe_budget_exhausted')
        self.assertEqual(report['authority'], 'discovery_only; not admission or coverage review')

    def test_shifted_range_recovers_chain_after_an_unknown_earlier_page(self):
        self.open_page(2)
        pools, stats, _ = discover(self.g, self.v, self.r, search_budget=80, window=6, min_window=4, max_shift=2, probe_budget=32, max_windows=4)
        task = next(t for t in pools['successive_speech'] if t['recipe']['references'][0]['page'] == 1 and t['recipe']['start'] == 3 and t['recipe']['steps'] == 3)
        recipe = task['recipe']; program = compile_recipe(recipe)
        doc = RecipeEngine(self.g, self.v, self.r, membership_refinement=True).execute(program)
        self.assertEqual(doc['result']['display'], 5)
        item = make(self.g, self.v, self.r, {}, question=render(recipe), answer={'type': 'page', 'value': 5, 'identity_id': None},
                    answer_format='page', structure='chain', engine='coverage_recipe', program=program, execution=doc)
        row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertTrue(row['passed'], row['reasons'])
        candidate = admitted(item, row)
        self.assertEqual(candidate['complexity']['meaningful_hops'], 3)
        self.assertEqual(candidate['complexity']['certificate']['version'], VERSION)
        self.assertEqual(candidate['features']['anchor_page_index'], 2)
        self.assertEqual(candidate['features']['page_offset'], 3)
        self.assertEqual(candidate['features']['reference_page_distance'], 4)
        self.assertEqual(candidate['features']['offset_basis'], 'expanded_search_range_predecessor')
        self.assertEqual(validate(json.loads(json.dumps(candidate))), candidate)
        self.assertFalse(stats['exhaustive'])

    def test_shorter_range_recovers_exact_shared_set_before_unknown_tail(self):
        test_expanded.ExpandedTests.two_actor_world(self)
        test_expanded.extend_synthetic(self.g, 10)
        from name_visibility import summarize
        self.v['page_ids'] = list(self.g['page_ids']); self.v['visibility'] = summarize(self.g, self.v['evidence'])
        self.open_page(8)
        before = stable([self.g, self.v, self.r])
        pools, _, _ = discover(self.g, self.v, self.r, search_budget=100, window=7, min_window=4, max_shift=2, probe_budget=40, max_windows=4)
        task = next(t for t in pools['shared_presence_pages'] if t['recipe']['start'] == 4 and t['recipe']['end'] == 7)
        recipe = task['recipe']; program = compile_recipe(recipe)
        doc = RecipeEngine(self.g, self.v, self.r, membership_refinement=True).execute(program)
        self.assertEqual(doc['result']['display'], [4, 5]); self.assertTrue(doc['result']['exact'])
        item = make(self.g, self.v, self.r, {}, question=render(recipe), answer={'type': 'set', 'value': [4, 5], 'identity_id': None},
                    answer_format='set', structure='branch_combine', engine='coverage_recipe', program=program, execution=doc)
        row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertTrue(row['passed'], row['reasons'])
        candidate = admitted(item, row)
        self.assertEqual(candidate['primary_group'], 'branch_combine')
        self.assertEqual(candidate['complexity']['branch_count'], 2)
        self.assertEqual(stable([self.g, self.v, self.r]), before)

    def test_coverage_checkpoint_resume_and_changed_budget_refusal(self):
        from comics_qa.benchmark1000.family_pilot import run
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); bench = root / 'bench'; out = root / 'pilot'
            for rel in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'):
                publish(bench / rel / 'manifest.json', {'config': {'chapters': [self.g['chapter_id']]}})
            with patch('comics_qa.benchmark1000.family_pilot.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.family_pilot.load_optional', return_value=self.r):
                kwargs = dict(per_family=1, max_executions=1, search_budget=20, window=6, coverage_aware=True, max_shift=1, probe_budget=16, max_windows=2)
                report = run(bench, out, **kwargs)
                self.assertTrue((out / 'diagnostics.json').exists())
                with patch('comics_qa.benchmark1000.coverage_windows.chapter', side_effect=AssertionError('reran')):
                    self.assertEqual(run(bench, out, **kwargs), report)
                with self.assertRaises(ValueError): run(bench, out, **{**kwargs, 'probe_budget': 17})

    def test_new_membership_checker_uses_positive_witnesses_without_closing_coverage(self):
        from comics_qa.benchmark1000.membership import MembershipEngine, MembershipChecker
        from comics_qa.benchmark1000.recipe_engine import RecipeChecker
        test_expanded.ExpandedTests.two_actor_world(self)
        self.open_page(4)
        recipe = {'kind': 'shared_presence_pages', 'references': [{'quote': 'please come back now', 'page': 1}, {'quote': 'please come back now', 'page': 3}],
                  'start': 4, 'end': 7, 'steps': 1, 'profile': VERSION}
        program = compile_recipe(recipe); old = RecipeEngine(self.g, self.v, self.r).execute(program)
        self.assertFalse(old['result']['exact'])
        doc = RecipeEngine(self.g, self.v, self.r, membership_refinement=True).execute(program)
        checker = RecipeChecker(self.g, self.v, self.r, membership_refinement=True)
        with patch.object(MembershipEngine, 'execute', side_effect=AssertionError('Producer invoked')):
            self.assertTrue(checker.check(doc, program)['answer_supported'])
        self.assertTrue(doc['result']['exact']); self.assertEqual(doc['result']['display'], [4, 5])
        self.assertFalse(RecipeChecker(self.g, self.v, self.r).check(doc, program)['proof_valid'])
        member = doc['stages'][-1]['execution']
        bad = copy.deepcopy(member); bad['probes'].pop(0)
        self.assertFalse(MembershipChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        bad = copy.deepcopy(member); bad['result']['value'] = []
        self.assertFalse(MembershipChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        self.open_page(6)
        partial = RecipeEngine(self.g, self.v, self.r, membership_refinement=True).execute(program)
        self.assertFalse(partial['result']['exact'])
        self.assertFalse(RecipeChecker(self.g, self.v, self.r, membership_refinement=True).check(partial)['answer_supported'])
        forged = copy.deepcopy(partial); forged['result']['exact'] = True
        self.assertFalse(RecipeChecker(self.g, self.v, self.r, membership_refinement=True).check(forged)['proof_valid'])

    def test_negative_page_ablation_breaks_complete_set_even_if_known_members_stay(self):
        from comics_qa.benchmark1000.admission import same_answer
        self.assertFalse(same_answer({'status': 'OK', 'value': ['p1'], 'exact': False}, {'value': ['p1']}))
        self.assertTrue(same_answer({'status': 'OK', 'value': ['p1'], 'exact': True}, {'value': ['p1']}))

    def test_membership_refinement_is_used_by_public_proof_and_private_probes(self):
        from comics_qa.benchmark1000.probes import recipe_probes
        test_expanded.ExpandedTests.two_actor_world(self); self.open_page(4)
        recipe = {'kind': 'shared_presence_pages', 'references': [{'quote': 'please come back now', 'page': 1}, {'quote': 'please come back now', 'page': 3}],
                  'start': 4, 'end': 7, 'steps': 1, 'profile': VERSION}
        program = compile_recipe(recipe); doc = RecipeEngine(self.g, self.v, self.r, membership_refinement=True).execute(program)
        item = make(self.g, self.v, self.r, {}, question=render(recipe), answer={'type': 'set', 'value': [4, 5], 'identity_id': None},
                    answer_format='set', structure='branch_combine', engine='coverage_recipe', program=program, execution=doc)
        row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertTrue(row['passed'], row['reasons'])
        self.assertIn(self.g['page_ids'][5], row['checks']['necessary_pages'])
        candidate = admitted(item, row)
        self.assertEqual(validate(json.loads(json.dumps(candidate))), candidate)
        probes = recipe_probes(candidate, self.g, self.v, self.r)
        self.assertTrue(any(p['engine'] == 'membership' and p['proof_check']['proof_valid'] for p in probes))

    def test_last_witness_ignores_only_earlier_unknown_not_later_unknown(self):
        from comics_qa.benchmark1000.membership import MembershipEngine, MembershipChecker
        from comics_qa.tasks.graph.crl.language import call
        expression = call('last', call('pages_with', speaker('please come back now', 1), call('pages', 2, 7)))
        self.open_page(2)
        doc = MembershipEngine(self.g, self.v, self.r).execute(expression)
        self.assertEqual(doc['result']['display'], 7)
        self.assertEqual(len(doc['probes']), 1)
        self.assertTrue(MembershipChecker(self.g, self.v, self.r).check(doc)['answer_supported'])
        # Remove the last positive while leaving its coverage open: no absence claim.
        from comics_qa.tasks.graph.generation.gates import without_pages
        graph, visibility = without_pages(self.g, self.v, [self.g['page_ids'][-1]])
        for c in graph['coverage']:
            if c['page_id'] == graph['page_ids'][-1] and c['family'] in ('char_boxes', 'names'): c['status'] = 'open'
        rich = build(graph, visibility, self.r['sources'])
        unknown = MembershipEngine(graph, visibility, rich).execute(expression)
        self.assertEqual(unknown['result']['status'], 'UNKNOWN')
        self.assertFalse(MembershipChecker(graph, visibility, rich).check(unknown)['answer_supported'])

    def test_window_enumeration_clamps_huge_requests_to_actual_chapter(self):
        from comics_qa.benchmark1000.coverage_windows import window_options
        values = list(window_options([{'quote': 'known source quote', 'page': 1}], 7, 4, 10**9, 10**9, 'successive_speech'))
        self.assertLess(len(values), 40)
        self.assertTrue(all(2 <= r['start'] <= r['end'] <= 7 for r in values))

    def test_diagnosis_rejects_unknown_family_without_executing(self):
        from comics_qa.benchmark1000.diagnose_families import run
        with self.assertRaises(ValueError): run('/tmp/no-source', '/tmp/no-bench', '/tmp/no-output', families=['unsupported_family'])
