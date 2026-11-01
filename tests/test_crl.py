"""CRL semantics on synthetic CKG-1/2 artifacts, including open-world failures."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest

import test_ckg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from comics_qa.tasks.graph.crl import Interpreter, LanguageError, canonical, infer, parse, program_hash
from comics_qa.tasks.graph.crl.run_crl import load_world, main, write_new
from name_visibility import summarize


class LanguageTest(unittest.TestCase):
    def test_three_syntaxes_agree(self):
        surface = 'let c=char("Hero Man") in count(pages_with(c, span=ctx()))'
        node = parse(surface)
        self.assertEqual(infer(node), 'Int')
        for other in (parse(canonical(node), 'sexpr'), parse(json.dumps(node), 'json')):
            self.assertEqual(program_hash(node), program_hash(other))

    def test_commutative_hash(self):
        self.assertEqual(program_hash(parse('and(true,false)')), program_hash(parse('and(false,true)')))
        self.assertEqual(program_hash(parse('char("Ｈｅｒｏ")')), program_hash({'op':'char','args':['Hero']}))

    def test_lambda_and_shadowing(self):
        self.assertEqual(infer(parse(r'let p=page(1) in map(ctx(), \p.page_of(p))')), 'Seq[Page]')
        self.assertEqual(infer(parse(r'map(ctx(), λp.count(texts(p)))')), 'Seq[Int]')

    def test_reject_bad_programs(self):
        for p in ['count(page(1))', 'page(true)', 'present(page(1),page(2))',
                  'eq(1,true)', 'mystery()', 'count(x)', 'forall(ctx())',
                  r'filter(ctx(), \p.1)', 'page(i=1,i=2)', 'page(1,i=2)',
                  'let x=1,x=2 in x', '__import__("os")', '1 + 2']:
            with self.subTest(p=p), self.assertRaises(LanguageError):
                infer(parse(p))

    def test_bad_ast_and_depth_limit(self):
        for p in [{'op': 'ctx', 'extra': 1}, {'op': 'page', 'args': [None]}, 'not(' * 80 + 'true' + ')' * 80]:
            with self.assertRaises(LanguageError): parse(p)


class ExecutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = test_ckg2.BuildTest(methodName='test_deterministic_outputs_and_completed_resume')
        cls.fixture.setUp()
        cls.addClassCleanup(cls.fixture.doCleanups)
        cls.fixture.run_build()
        cls.root = cls.fixture.root
        cls.graph, cls.visibility, cls.sources = load_world(cls.root/'graph', cls.root/'visibility', 'hero__c001')

    def setUp(self):
        self.g = copy.deepcopy(self.graph)
        self.v = copy.deepcopy(self.visibility)

    def execute(self, program, **kw):
        return Interpreter(self.g, self.v, **kw).execute(program)

    def result(self, program, status='OK', value=...):
        out = self.execute(program)
        self.assertEqual(out['result']['status'], status, out['result'])
        if value is not ...: self.assertEqual(out['result']['value'], value)
        return out

    def close_synthetic_world(self):
        # Deliberately synthetic: page 2 now means a reviewed blank page.
        for c in self.g['coverage']:
            if c['family'] in ('char_boxes','names','text_boxes','speaker_links'):
                c['status'] = 'closed_verified'

    def test_page_index_and_spread(self):
        self.assertEqual(self.result('page(2)')['result']['display'], 2)
        self.result('count(ctx())', value=3)
        self.result('page(0)', 'ERROR')
        self.result('pages(3,2)', 'ERROR')

    def test_visible_anchor_and_trust(self):
        out = self.result('char("Hero Man")', value='hero__hero-man')
        self.assertEqual(out['result']['display'], 'Hero Man')
        self.assertEqual(out['proof']['trust_min'], 'V')
        self.assertTrue(out['proof']['visibility_evidence'])
        self.assertTrue(out['proof']['facts'])

    def test_unseen_name_and_unseen_canonical_with_seen_alias(self):
        self.result('char("Nobody")', 'UNKNOWN')
        for e in self.v['evidence']:
            if e['form'] == 'Hero Man': e.update(status='rejected', origin='M')
        self.v['visibility'] = summarize(self.g, self.v['evidence'])
        self.result('char("Hero Man")', 'UNKNOWN')
        out = self.result('char("Hero")')
        self.assertIn(out['result']['display'], ('Hero','Man'))
        self.assertNotEqual(out['result']['display'], 'Hero Man')

    def test_open_scope_is_not_zero(self):
        self.result('count(chars(page(2)))', 'UNKNOWN')
        self.result('none(chars(page(2)))', 'UNKNOWN')
        self.result('present(char("Hero Man"),page(2))', 'UNKNOWN')

    def test_positive_lower_bound_and_final_gate(self):
        out = self.result('pages_with(char("Hero Man"))')
        self.assertFalse(out['result']['exact'])
        self.assertFalse(out['eligible_for_generation'])
        out = self.result('at_least(pages_with(char("Hero Man")),1)', value=True)
        self.assertTrue(out['eligible_for_generation'])
        self.assertFalse(out['result']['exact'])
        self.result('at_least(pages_with(char("Hero Man")),3)', 'UNKNOWN')

    def test_empty_ambiguous_unknown_distinct(self):
        self.result('the(chars(page(1)))', 'AMBIGUOUS')
        self.result('the(chars(page(2)))', 'UNKNOWN')
        self.close_synthetic_world()
        self.result('the(chars(page(2)))', 'EMPTY')
        self.result('count(chars(page(2)))', value=0)

    def test_no_order_from_ids(self):
        self.result('first(apps(page(1)))', 'UNKNOWN')
        self.result('nth(texts(page(1)),1)', 'UNKNOWN')
        self.result('first_app(char("Hero Man"),span=page(1))')

    def test_next_app_crosses_unannotated_page(self):
        self.result('next_app(char("Hero Man"),after=page(1))', 'UNKNOWN')
        self.close_synthetic_world()
        out = self.result('page_of(next_app(char("Hero Man"),after=page(1)))')
        self.assertEqual(out['result']['display'], 3)

    def test_next_app_checks_prefix_not_later_pages(self):
        # Search starts after page 2; missing earlier coverage must not poison page 3.
        out = self.result('page_of(next_app(char("Hero Man"),after=page(2)))')
        self.assertEqual(out['result']['display'], 3)

    def test_kleene_logic(self):
        for p, expected in [('or(true,unknown)',True), ('and(false,unknown)',False),
                            ('and(true,true)',True), ('or(false,false)',False)]:
            self.result(p, value=expected)
        self.result('and(true,unknown)', 'UNKNOWN')
        self.result('or(false,unknown)', 'UNKNOWN')
        self.close_synthetic_world()
        self.result('or(true,is_named(the(chars(page(2)))))', 'EMPTY')

    def test_negation_difference_closed_only(self):
        self.result('not(exists(pages_with(char("Hero Man"))))', 'UNKNOWN')
        self.result('diff(ctx(),pages_with(char("Hero Man")))', 'UNKNOWN')
        self.close_synthetic_world()
        self.result('count(diff(ctx(),pages_with(char("Hero Man"))))', value=1)

    def test_let_and_lambda_capture(self):
        self.close_synthetic_world()
        self.result(r'let c=char("Hero Man") in count(filter(ctx(), \p.present(c,p)))', value=2)
        self.result(r'sum(map(ctx(), \p.count(texts(p))))', value=4)
        self.result(r'forall(ctx(), \p.eq(page_of(p),p))', value=True)
        self.result(r'exists(ctx(), \p.present(char("Hero Man"),p))', value=True)

    def test_unknown_filter_does_not_become_exact(self):
        out = self.result(r'filter(ctx(), \p.present(char("Hero Man"),p))')
        self.assertFalse(out['result']['exact'])
        self.result(r'count(filter(ctx(), \p.present(char("Hero Man"),p)))', 'UNKNOWN')

    def test_set_algebra(self):
        self.result('count(union(pages(1,2),pages(2,3)))', value=3)
        self.result('count(intersect(pages(1,2),pages(2,3)))', value=1)
        self.result('in(page(1),pages(2,3))', value=False)

    def test_order_and_arithmetic(self):
        self.result('gap(page(1),page(3))', value=1)
        self.result('count(between(page(1),page(3)))', value=1)
        self.result('precedes(page(1),page(3))', value=True)
        self.result('count(span_after(page(1)))', value=2)
        self.result('rank(page(2),ctx())', value=2)
        self.result('compare(3,1)', value='more')
        self.result('minus(3,1)', value=2)
        self.result('next(page(3),ctx())', 'EMPTY')

    def test_speaker_and_proof_premise_closure(self):
        out = self.result('speaker_char(first(lines(page(1))))')
        facts = {f['fact_id']: f for f in self.g['facts']}
        for fid in out['proof']['facts']:
            self.assertTrue(set(facts[fid]['premises']) <= set(out['proof']['facts']))
        self.assertTrue(out['proof']['certificates'])
        self.assertEqual(out['proof_check'], 'pending_CRL-2')
        self.assertTrue(out['eligible_for_generation'])
        generic = self.result(r'the(filter(chars(page(1)), \c.not(is_named(c))))')
        self.assertFalse(generic['eligible_for_generation'])

    def test_gated_evidence(self):
        for p in ['quote("Hello",on=page(1))','panels(page(1))','mentions_of(char("Hero Man"))']:
            self.result(p, 'UNKNOWN')

    def test_absorbed_unknown_name_cannot_enter_a_question(self):
        out = self.result('or(true,present(char("Unread Name"),page(1)))', value=True)
        self.assertFalse(out['eligible_for_generation'])

    def test_discourse_and_streak(self):
        self.result('turns(ctx())', 'UNKNOWN')
        self.close_synthetic_world()
        self.result('longest_streak(char("Hero Man"))', value=1)
        self.result('line_count(char("Hero Man"))', value=2)
        out = self.result('page_of(next_line(first(lines(page(1)))))')
        self.assertEqual(out['result']['display'], 3)
        self.result('next_other_speaker(first(lines(page(1))))', 'EMPTY')
        self.assertEqual(len(self.result('turns(ctx())')['result']['value']), 1)

    def test_explicit_sort_grouping_and_mapped_multiplicity(self):
        self.close_synthetic_world()
        out = self.result(r'first(sort_by(ctx(), \p.minus(0,rank(p,ctx()))))')
        self.assertEqual(out['result']['display'], 3)
        self.result(r'group_count(ctx(), \p.count(texts(p)))', value=[[0,1],[2,2]])
        self.result(r'count(map(ctx(), \p.1))', value=3)
        self.result(r'count(distinct(map(ctx(), \p.1)))', value=1)

    def test_aggregate_ties_and_margin(self):
        self.close_synthetic_world()
        self.result(r'argmax(ctx(), \p.count(texts(p)))', 'AMBIGUOUS')
        self.result(r'sort_by(ctx(), \p.count(texts(p)))', 'AMBIGUOUS')
        out = self.result(r'argmin(ctx(), \p.count(texts(p)))')
        self.assertEqual(out['result']['display'], 2)
        self.result(r'top_k(ctx(), \p.count(texts(p)),2)', 'AMBIGUOUS')
        self.result(r'mode(map(ctx(), \p.count(texts(p))))', value=2)

    def test_execution_budget_and_strict_coverage(self):
        out = self.execute('count(texts(ctx()))', max_steps=1)
        self.assertEqual(out['result']['status'], 'ERROR')
        out = self.execute('count(ctx())', allow_closed_assumed=False)
        self.assertEqual(out['result']['status'], 'UNKNOWN')

    def test_determinism_and_input_immutability(self):
        before = json.dumps([self.g,self.v],sort_keys=True)
        runner = Interpreter(self.g,self.v)
        node = parse('page_of(first_app(char("Hero Man"),span=page(1)))')
        self.assertEqual(runner.execute(node),runner.execute(canonical(node),'sexpr'))
        self.assertEqual(before,json.dumps([self.g,self.v],sort_keys=True))

    def test_loader_detects_corrupt_shard(self):
        path = self.root/'graph/chapters/hero__c001.json';raw = path.read_bytes()
        try:
            path.write_bytes(raw+b'\n')
            with self.assertRaisesRegex(ValueError,'checksum'):
                load_world(self.root/'graph',self.root/'visibility','hero__c001')
        finally: path.write_bytes(raw)

    def test_cli_and_no_overwrite(self):
        path = self.root/'query.json'
        argv = ['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),
                '--chapter','hero__c001','--program','count(ctx())','--out',str(path)]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(argv),0)
            self.assertEqual(main(argv),2)
        self.assertEqual(json.loads(path.read_text())['result']['value'],3)
        self.assertEqual(json.loads(path.read_text())['inputs_sha256'],self.sources)
        with self.assertRaises(FileExistsError): write_new(path,'bad')


if __name__ == '__main__': unittest.main()
