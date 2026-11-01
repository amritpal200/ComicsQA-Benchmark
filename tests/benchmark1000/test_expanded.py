import copy
import unittest
from unittest.mock import patch
import test_semantic
from comics_qa.tasks.graph.crl.language import infer
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.evidence.graph.rich.model import build
from comics_qa.benchmark1000.io import stable
from comics_qa.benchmark1000.expanded_families import KINDS, compile_recipe, render, parse_question
from comics_qa.benchmark1000.recipe_engine import RecipeEngine, RecipeChecker
from comics_qa.benchmark1000.native import make, check_answer
from comics_qa.benchmark1000.admission import World, assess
from comics_qa.benchmark1000.admission_store import admitted, validate


def extend_synthetic(g, total=7):
    """Synthetic schema-valid repeats of page 3; never used on real annotations."""
    import ckg_schema
    original = g['page_ids'][-1]
    nodes = [n for n in g['nodes'] if n['id'] == original or n.get('page_id') == original or n['id'].startswith(original + '__')]
    facts = [f for f in g['facts'] if f['page_ids'] == [original]]
    coverage = [c for c in g['coverage'] if c['page_id'] == original]
    edge = next(f for f in g['facts'] if f['rel'] == 'next_page')
    def replace(x, mapping):
        if isinstance(x, str): return mapping.get(x, x)
        if isinstance(x, list): return [replace(v, mapping) for v in x]
        if isinstance(x, dict): return {k: replace(v, mapping) for k, v in x.items()}
        return x
    for number in range(len(g['page_ids']) + 1, total + 1):
        page = 'hero__c001__p' + str(number).zfill(3)
        mapping = {n['id']: n['id'].replace(original, page) for n in nodes}
        mapping.update({f['fact_id']: 'f:' + stable([f['fact_id'], page]) for f in facts})
        mapping.update({c['coverage_id']: 'cov:' + stable([c['coverage_id'], page]) for c in coverage})
        g['nodes'].extend(replace(nodes, mapping)); g['facts'].extend(replace(facts, mapping)); g['coverage'].extend(replace(coverage, mapping))
        previous = g['page_ids'][-1]; g['page_ids'].append(page)
        new_edge = copy.deepcopy(edge); new_edge.update(fact_id='f:' + stable([previous, page]), args=[previous, page], page_ids=[previous, page],
            coverage_refs=[c['coverage_id'] for c in g['coverage'] if c['family'] == 'page_sequence' and c['page_id'] in (previous, page)])
        g['facts'].append(new_edge)
    for c in g['coverage']:
        if c['family'] in ('char_boxes', 'names', 'text_boxes', 'speaker_links'):
            c['status'] = 'closed_verified'
    ckg_schema.validate_graph(g)


class ExpandedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_semantic.SemanticTests.setUpClass.__func__(cls)

    def setUp(self):
        test_semantic.SemanticTests.setUp(self)
        extend_synthetic(self.g)
        self.v['page_ids'] = list(self.g['page_ids'])
        from name_visibility import summarize
        self.v['visibility'] = summarize(self.g, self.v['evidence'])
        self.r = build(self.g, self.v, self.r['sources'])
        self.recipe = {'kind': 'successive_speech', 'references': [{'quote': 'please come back now', 'page': 1}], 'start': 2, 'end': 7, 'steps': 3}

    def native(self, recipe=None):
        recipe = recipe or self.recipe; p = compile_recipe(recipe)
        doc = RecipeEngine(self.g, self.v, self.r).execute(p)
        self.assertEqual(doc['result']['status'], 'OK', doc['result'])
        return make(self.g, self.v, self.r, {}, question=render(recipe), answer={'type': 'page', 'value': doc['result']['display'], 'identity_id': None},
                    answer_format='page', structure='chain', engine='recipe', program=p, execution=doc)

    def test_three_navigation_chain_is_independently_proved_and_certified(self):
        item = self.native()
        self.assertEqual(item['answer']['value'], 5)
        self.assertTrue(check_answer(item, self.g, self.v, self.r)['answer_supported'])
        receipt = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertTrue(receipt['passed'], receipt['reasons'])
        self.assertEqual(receipt['complexity_certificate']['meaningful_hops'], 3)
        candidate = admitted(item, receipt)
        self.assertEqual(candidate['primary_group'], 'chain')
        self.assertEqual(candidate['complexity']['meaningful_hops'], 3)
        self.assertGreaterEqual(len(candidate['complexity']['necessary_pages']), 4)
        import json
        self.assertEqual(validate(json.loads(json.dumps(candidate))), candidate)
        self.assertEqual(candidate['verification']['human'], 'pending')

    def test_recipe_checker_does_not_invoke_producer(self):
        item = self.native()
        with patch.object(RecipeEngine, 'execute', side_effect=AssertionError('Producer called')):
            self.assertTrue(RecipeChecker(self.g, self.v, self.r).check(item['execution'], item['program'])['proof_valid'])

    def test_modified_binding_skipped_probe_final_value_and_sources_fail(self):
        item = self.native(); doc = item['execution']
        bad = copy.deepcopy(doc); bad['stages'][1]['execution']['program']['end'] -= 1
        self.assertFalse(RecipeChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        bad = copy.deepcopy(doc); bad['stages'][1]['execution']['probes'].pop(0)
        self.assertFalse(RecipeChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        bad = copy.deepcopy(doc); bad['stages'][2]['execution']['program']['after'] = 1
        self.assertFalse(RecipeChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        bad = copy.deepcopy(doc); bad['result']['value'] = self.g['page_ids'][-1]
        self.assertFalse(RecipeChecker(self.g, self.v, self.r).check(bad)['proof_valid'])
        bad = copy.deepcopy(doc); bad['rich_sha256'] = 'stale'
        self.assertFalse(RecipeChecker(self.g, self.v, self.r).check(bad)['proof_valid'])

    def test_unknown_after_witness_does_not_break_prefix_but_earlier_unknown_does(self):
        from comics_qa.benchmark1000.scan import ScanEngine, ScanChecker
        from comics_qa.benchmark1000.native_wording import speaker
        for c in self.g['coverage']:
            if c['page_id'] == self.g['page_ids'][5] and c['family'] == 'speaker_links': c['status'] = 'open'
        p = {'op': 'next_speaks', 'characters': [speaker('please come back now', 1)], 'after': 1, 'end': 7}
        d = ScanEngine(self.g, self.v, self.r).execute(p)
        self.assertEqual(d['result']['display'], 3)
        self.assertTrue(ScanChecker(self.g, self.v, self.r).check(d)['proof_valid'])
        for c in self.g['coverage']:
            if c['page_id'] == self.g['page_ids'][1] and c['family'] == 'speaker_links': c['status'] = 'open'
        self.assertEqual(ScanEngine(self.g, self.v, self.r).execute(p)['result']['status'], 'UNKNOWN')

    def test_all_recipe_formats_round_trip_and_negation_is_not_accepted(self):
        expected = {'speaking_gap': 'Int', 'speaking_before': 'Bool3', 'shared_speaking_pages': 'Set[Page]', 'shared_presence_pages': 'Set[Page]', 'next_speech_line_count': 'Int'}
        for kind in KINDS:
            r = {**self.recipe, 'kind': kind, 'steps': 2 if kind in ('successive_speech', 'speaker_walk') else 1}
            if kind in ('speaking_gap', 'speaking_before', 'shared_speaking_pages', 'shared_presence_pages'):
                r['references'] = [r['references'][0], {'quote': 'another verified source quote', 'page': 1}]
            parsed = parse_question(render(r))
            self.assertEqual(parsed['recipe'], r)
            self.assertEqual(infer(compile_recipe(r)), expected.get(kind, 'Page'))
        with self.assertRaises(ValueError): parse_question(render(self.recipe).replace('next speaking', 'previous speaking'))

    def test_complexity_cannot_be_changed_by_relabelling_or_feature_edit(self):
        item = self.native(); candidate = admitted(item, assess(item, World(self.g, self.v, self.r), max_ablation_pages=12))
        for field in ('hops', 'offset'):
            bad = copy.deepcopy(candidate)
            if field == 'hops': bad['complexity']['meaningful_hops'] = 99
            else: bad['features']['page_offset'] = 99
            bad['item_id'] = 'b1000a:' + stable({k: v for k, v in bad.items() if k not in ('schema', 'item_id')})
            with self.assertRaises(ValueError): validate(bad)

    def test_count_navigation_is_held_when_source_and_target_counts_coincide(self):
        r = {**self.recipe, 'kind': 'next_speech_line_count', 'steps': 1}
        p = compile_recipe(r); d = RecipeEngine(self.g, self.v, self.r).execute(p)
        item = make(self.g, self.v, self.r, {}, question=render(r), answer={'type': 'count', 'value': d['result']['display'], 'identity_id': None},
                    answer_format='count', structure='aggregate', engine='recipe', program=p, execution=d)
        receipt = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertFalse(receipt['passed'])
        self.assertIn('redundant_clause', receipt['reasons'])

    def two_actor_world(self):
        import ckg_schema
        from name_visibility import summarize
        hero = next(n['id'] for n in self.g['nodes'] if n['type'] == 'Character' and n.get('canonical_name') == 'Hero Man')
        node = copy.deepcopy(next(n for n in self.g['nodes'] if n['id'] == hero))
        shadow = 'hero__shadow-man'; node.update(id=shadow, canonical_name='Shadow Man', aliases=[])
        self.g['nodes'].append(node)
        pages = self.g['page_ids']
        mapping = {}
        for f in self.g['facts']:
            if f['rel'] == 'is_char':
                aid, cid = f['args']; app = next(n for n in self.g['nodes'] if n['id'] == aid); page = app['page_id']
                if cid == hero and page in (pages[2], pages[6]) or cid != hero and page in (pages[3], pages[4]):
                    mapping[cid, page] = shadow
        for f in self.g['facts']:
            if len(f['page_ids']) == 1:
                page = f['page_ids'][0]
                if f['rel'] in ('present', 'speaks_on'): f['args'][0] = mapping.get((f['args'][0], page), f['args'][0])
                if f['rel'] == 'is_char': f['args'][1] = mapping.get((f['args'][1], page), f['args'][1])
        for n in self.g['nodes']:
            if n['type'] == 'Appearance': n['identity_id'] = mapping.get((n['identity_id'], n['page_id']), n['identity_id'])
        ckg_schema.validate_graph(self.g)
        self.v['visibility'] = summarize(self.g, self.v['evidence'])
        self.r = build(self.g, self.v, self.r['sources'])
        return {'kind': 'speaking_gap', 'references': [{'quote': 'please come back now', 'page': 1}, {'quote': 'please come back now', 'page': 3}], 'start': 4, 'end': 7, 'steps': 1}

    def test_two_independent_branches_prove_gap_and_shared_page_set(self):
        recipe = self.two_actor_world()
        for kind, fmt, expected, group in [('speaking_gap', 'count', 2, 'aggregate_compare'), ('shared_presence_pages', 'set', [4, 5], 'branch_combine')]:
            recipe['kind'] = kind; program = compile_recipe(recipe)
            d = RecipeEngine(self.g, self.v, self.r).execute(program)
            self.assertTrue(RecipeChecker(self.g, self.v, self.r).check(d)['answer_supported'], d['result'])
            self.assertEqual(d['result']['display'], expected)
            item = make(self.g, self.v, self.r, {}, question=render(recipe), answer={'type': fmt, 'value': expected, 'identity_id': None},
                        answer_format=fmt, structure='branch_combine', engine='recipe', program=program, execution=d)
            row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
            self.assertTrue(row['passed'], row['reasons'])
            candidate = admitted(item, row)
            self.assertEqual(candidate['complexity']['branch_count'], 2)
            self.assertEqual(candidate['primary_group'], group)
            if fmt == 'set': self.assertTrue(all(x['known_extra_members'] for x in row['checks']['clause_removals']))

    def test_family_checkpoint_resume_and_changed_budget_refusal(self):
        import tempfile
        from pathlib import Path
        from comics_qa.benchmark1000.io import publish
        from comics_qa.benchmark1000.family_pilot import run
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); bench = root / 'bench'; out = root / 'pilot'
            for rel in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'):
                publish(bench / rel / 'manifest.json', {'config': {'chapters': [self.g['chapter_id']]}})
            with patch('comics_qa.benchmark1000.family_pilot.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.family_pilot.load_optional', return_value=self.r):
                first = run(bench, out, per_family=1, max_executions=1, search_budget=20, window=6)
                self.assertGreater(first['counts']['proposals'], 0)
                with patch('comics_qa.benchmark1000.family_pilot.chapter', side_effect=AssertionError('Checkpoint reran')):
                    self.assertEqual(run(bench, out, per_family=1, max_executions=1, search_budget=20, window=6), first)
                with self.assertRaises(ValueError): run(bench, out, per_family=1, max_executions=1, search_budget=20, window=7)

    def test_private_probes_are_checked_but_never_main_items(self):
        from comics_qa.benchmark1000.probes import recipe_probes
        item = self.native(); row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        candidate = admitted(item, row)
        probes = recipe_probes(candidate, self.g, self.v, self.r)
        self.assertEqual(len(probes), 5)
        self.assertTrue(all(p['proof_check']['proof_valid'] and p['standalone_program_verified'] and not p['main_item'] for p in probes))
        self.assertTrue(all(p['parent_id'] == candidate['item_id'] and p['input_mode'] == 'privileged_subproblem' for p in probes))

    def test_character_switch_walk_has_three_necessary_semantic_steps(self):
        self.two_actor_world()
        extend_synthetic(self.g, 8)
        from name_visibility import summarize
        self.v['page_ids'] = list(self.g['page_ids']); self.v['visibility'] = summarize(self.g, self.v['evidence'])
        self.r = build(self.g, self.v, self.r['sources'])
        recipe = {**self.recipe, 'kind': 'speaker_walk', 'end': 8, 'steps': 2}
        item = self.native(recipe)
        self.assertEqual(item['answer']['value'], 7)
        row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertTrue(row['passed'], row['reasons'])
        candidate = admitted(item, row)
        self.assertEqual(candidate['complexity']['meaningful_hops'], 3)
        self.assertEqual(row['complexity_certificate']['necessary_steps'], ['navigate:0', 'switch:0', 'navigate:1'])

    def test_no_eligible_ocr_is_reported_as_empty_not_feasible(self):
        import tempfile
        from pathlib import Path
        from name_visibility import summarize
        from comics_qa.benchmark1000.io import publish
        from comics_qa.benchmark1000.family_pilot import run
        from comics_qa.benchmark1000.admission_store import run as admit_run
        from comics_qa.benchmark1000.store import load
        self.v['alignments'] = []; self.v['evidence'] = []; self.v['visibility'] = summarize(self.g, [])
        self.r = build(self.g, self.v, self.r['sources'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); bench = root / 'bench'; out = root / 'pilot'
            for rel in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'):
                publish(bench / rel / 'manifest.json', {'config': {'chapters': [self.g['chapter_id']]}})
            with patch('comics_qa.benchmark1000.family_pilot.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.family_pilot.load_optional', return_value=self.r):
                result = run(bench, out, per_family=1, max_executions=1, search_budget=10, window=6)
                self.assertEqual(result['counts']['executed'], 0)
            report = admit_run(out, bench, root / 'admission')
            self.assertEqual(report['counts']['admitted'], 0)
            self.assertEqual(load(root / 'admission'), [])
            self.assertEqual(report['diversity']['feasibility'], 'not_established_by_bounded_pilot')

    def test_boolean_branch_sensitivity_uses_both_valid_range_endpoints(self):
        recipe = self.two_actor_world(); recipe['kind'] = 'speaking_before'
        program = compile_recipe(recipe); doc = RecipeEngine(self.g, self.v, self.r).execute(program)
        self.assertIs(doc['result']['display'], True)
        item = make(self.g, self.v, self.r, {}, question=render(recipe), answer={'type': 'bool', 'value': True, 'identity_id': None},
                    answer_format='boolean', structure='compare', engine='recipe', program=program, execution=doc)
        row = assess(item, World(self.g, self.v, self.r), max_ablation_pages=12)
        self.assertTrue(row['passed'], row['reasons'])
        self.assertTrue(any(c.get('sensitivity_trials') for c in row['checks']['clause_removals']))
        candidate = admitted(item, row)
        self.assertTrue(candidate['features']['two_option'])
        self.assertEqual(candidate['complexity']['branch_count'], 2)
