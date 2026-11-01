import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_expanded
from comics_qa.evidence.graph.rich.model import build
from comics_qa.benchmark1000.branch_relations import VERSION,KINDS,compile_recipe,render,parse_question,resolved,certificate
from comics_qa.benchmark1000.semantic import execute
from comics_qa.benchmark1000.native import make
from comics_qa.benchmark1000.admission import assess,World
from comics_qa.benchmark1000.admission_store import admitted,validate
from comics_qa.benchmark1000.io import stable,read,publish


class BranchRelationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):test_expanded.ExpandedTests.setUpClass.__func__(cls)

    def setUp(self):
        test_expanded.ExpandedTests.setUp(self);test_expanded.ExpandedTests.two_actor_world(self)
        test_expanded.extend_synthetic(self.g,10)
        from name_visibility import summarize
        self.v['page_ids']=list(self.g['page_ids']);self.v['visibility']=summarize(self.g,self.v['evidence']);self.r=build(self.g,self.v,self.r['sources'])
        self.recipe={'kind':'branch_chain_pages','references':[{'quote':'please come back now','page':1},{'quote':'please come back now','page':3}],
                     'start':4,'end':10,'steps':[2,2],'profile':VERSION}

    def native(self,r=None):
        r=r or self.recipe;p=compile_recipe(r);doc,_,known=execute('coverage_recipe',p,self.g,self.v,self.r)
        self.assertTrue(known,doc['result']);fmt='sequence' if r['kind']=='branch_chain_pages' else 'count'
        return make(self.g,self.v,self.r,{},question=render(r),answer={'type':fmt,'value':doc['result']['display'],'identity_id':None},answer_format=fmt,
                    structure='branch_combine',engine='coverage_recipe',program=p,execution=doc)

    def test_grammar_roundtrip_all_depths_and_wrong_condition_rejected(self):
        for kind in KINDS:
            for steps in ([2,2],[2,3],[3,2],[3,3]):
                r={**self.recipe,'kind':kind,'steps':steps};parsed=parse_question(render(r))
                self.assertEqual(parsed['recipe'],r);self.assertEqual(parsed['program'],compile_recipe(r))
                self.assertEqual(len(parsed['relaxations']),sum(steps)+2)
        with self.assertRaises(ValueError):parse_question(render(self.recipe).replace('strictly after','on or after',1))

    def test_exact_sequence_and_count_pass_full_gates_with_long_certificate(self):
        before=stable([self.g,self.v,self.r])
        for kind,answer in [('branch_chain_pages',[5,8]),('branch_chain_gap',2)]:
            item=self.native({**self.recipe,'kind':kind});self.assertEqual(item['answer']['value'],answer)
            receipt=assess(item,World(self.g,self.v,self.r),max_ablation_pages=20)
            self.assertTrue(receipt['passed'],receipt['reasons']);result=admitted(item,receipt);validate(result)
            self.assertEqual(result['primary_group'],'branch_combine')
            self.assertEqual(result['complexity']['meaningful_hops'],2) # parallel depths are not summed
            self.assertEqual(result['complexity']['branch_count'],2)
            self.assertIn('long_relational',result['reasoning_tags'])
            self.assertEqual(result['long_relational_certificate']['necessary_clauses'],4)
            self.assertGreaterEqual(result['long_relational_certificate']['page_span'],5)
            self.assertTrue(all(x['necessary'] for x in receipt['checks']['clause_removals']))
            self.assertEqual(result['verification']['human'],'pending')
        self.assertEqual(stable([self.g,self.v,self.r]),before)

    def test_original_recipe_checker_stays_independent(self):
        from comics_qa.benchmark1000.recipe_engine import RecipeEngine,RecipeChecker
        item=self.native()
        with patch.object(RecipeEngine,'execute',side_effect=AssertionError('producer called')):
            self.assertTrue(RecipeChecker(self.g,self.v,self.r,True).check(item['execution'],item['program'])['proof_valid'])
        bad=copy.deepcopy(item['execution']);bad['result']['value']=list(reversed(bad['result']['value']))
        self.assertFalse(RecipeChecker(self.g,self.v,self.r,True).check(bad,item['program'])['proof_valid'])

    def test_long_tag_is_not_word_count_or_user_metadata(self):
        item=self.native();receipt=assess(item,World(self.g,self.v,self.r),max_ablation_pages=20);candidate=admitted(item,receipt)
        bad=copy.deepcopy(candidate);bad['long_relational_certificate']['necessary_clauses']=99
        bad['item_id']='b1000a:'+stable({k:v for k,v in bad.items() if k not in ('schema','item_id')})
        with self.assertRaises(ValueError):validate(bad)
        controls=copy.deepcopy(receipt['checks']);controls['clause_removals'][0]['necessary']=False
        self.assertFalse(certificate(item,parse_question(item['question']),controls)['long_relational']['eligible'])

    def test_open_coverage_blocks_a_required_branch(self):
        for c in self.g['coverage']:
            if c['page_id']==self.g['page_ids'][3] and c['family']=='speaker_links':c['status']='open'
        self.r=build(self.g,self.v,self.r['sources']);doc,checked,known=execute('coverage_recipe',compile_recipe(self.recipe),self.g,self.v,self.r)
        self.assertTrue(checked['proof_valid']);self.assertFalse(known)

    def test_same_person_in_two_branches_is_held(self):
        r={**self.recipe,'references':[self.recipe['references'][0],self.recipe['references'][0]],'steps':[2,3]}
        item=self.native(r);row=assess(item,World(self.g,self.v,self.r),max_ablation_pages=20)
        self.assertFalse(row['passed']);self.assertIn('branches_resolve_same_identity',row['reasons'])

    def test_commutative_reference_swap_deduplicates_by_resolved_paths(self):
        a=self.native();swapped={**self.recipe,'references':list(reversed(self.recipe['references']))};b=self.native(swapped)
        self.assertEqual(resolved(a,parse_question(a['question'])),resolved(b,parse_question(b['question'])))

    def test_source_and_private_probe_schema_remain_bound(self):
        from comics_qa.benchmark1000.probes import recipe_probes
        item=self.native();candidate=admitted(item,assess(item,World(self.g,self.v,self.r),max_ablation_pages=20))
        probes=recipe_probes(candidate,self.g,self.v,self.r)
        self.assertTrue(probes);self.assertTrue(all(p['standalone_program_verified'] and not p['main_item'] for p in probes))
        wrong=copy.deepcopy(candidate);wrong['program']=compile_recipe({**self.recipe,'steps':[3,2]})
        wrong['item_id']='b1000a:'+stable({k:v for k,v in wrong.items() if k not in ('schema','item_id')})
        with self.assertRaises(ValueError):validate(wrong)

    def test_checkpoint_resume_and_budget_binding(self):
        from comics_qa.benchmark1000.branch_pilot import run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'bench';out=Path(tmp)/'out'
            for rel in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1'):
                publish(root/rel/'manifest.json',{'config':{'chapters':[self.g['chapter_id']]},'outputs_sha256':{}})
            with patch('comics_qa.benchmark1000.branch_pilot.load_world',return_value=(self.g,self.v,{})),patch('comics_qa.benchmark1000.branch_pilot.load_optional',return_value=self.r):
                first=run(root,out,per_family=1,search_budget=100,dependency_budget=64)
                self.assertEqual(first['counts']['proposals'],2)
                with patch('comics_qa.benchmark1000.branch_pilot.chapter',side_effect=AssertionError('checkpoint reran')):
                    self.assertEqual(run(root,out,per_family=1,search_budget=100,dependency_budget=64),first)
                with self.assertRaises(ValueError):run(root,out,per_family=1,search_budget=100,dependency_budget=65)

    def test_three_step_branches_measure_max_depth_and_all_six_navigations(self):
        item=self.native({**self.recipe,'steps':[3,3]});self.assertEqual(item['answer']['value'],[6,9])
        receipt=assess(item,World(self.g,self.v,self.r),max_ablation_pages=20);self.assertTrue(receipt['passed'],receipt['reasons'])
        candidate=admitted(item,receipt)
        self.assertEqual(candidate['complexity']['meaningful_hops'],3)
        self.assertEqual(candidate['long_relational_certificate']['necessary_clauses'],6)
        self.assertEqual(len(receipt['checks']['clause_removals']),8)

    def test_dependency_budget_is_cached_and_never_creates_false_necessity(self):
        from comics_qa.benchmark1000.branch_pilot import CheckedQueries,DependencyBudget
        queries=CheckedQueries(self.g,self.v,self.r,1);program=compile_recipe(self.recipe)
        _,main=queries.query(program);queries.query(program)
        self.assertEqual(queries.used,1);self.assertEqual(queries.hits,1)
        with self.assertRaises(DependencyBudget):queries.dependencies(self.recipe,main)
        self.assertFalse(queries.records[0]['passed']);self.assertEqual(queries.records[0]['unchecked_interventions'],6)
        self.assertTrue(queries.exhausted)

    def test_words_alone_cannot_certify_a_long_question(self):
        item=self.native();checks=assess(item,World(self.g,self.v,self.r),max_ablation_pages=20)['checks']
        checks=copy.deepcopy(checks);checks['necessary_pages']=self.g['page_ids'][3:6];checks['necessary_visual_pages']=checks['necessary_pages']
        cert=certificate(item,parse_question(item['question']),checks)
        self.assertGreater(cert['word_count'],81);self.assertTrue(cert['certified']);self.assertFalse(cert['long_relational']['eligible'])

    def test_invalid_budgets_fail_before_data_access(self):
        from comics_qa.benchmark1000.branch_pilot import run
        for kw in ({'dependency_budget':0},{'probe_budget':True},{'min_window':3},{'max_steps':4},{'max_shift':-1}):
            with self.assertRaises(ValueError):run('/missing','/tmp/unused-branch-test',**kw)
