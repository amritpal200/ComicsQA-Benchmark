import copy
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import test_branch_relations as fixture
from comics_qa.benchmark1000 import claim_programs as cp,sentence_plans as sp,sentence_scoring as ss
from comics_qa.benchmark1000.admission import World,assess
from comics_qa.benchmark1000.admission_store import admitted
from comics_qa.benchmark1000.io import stable,read,publish,digest


class SentencePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.BranchRelationsTests.setUpClass();x=fixture.BranchRelationsTests();x.setUp()
        cls.g,cls.v,cls.r=x.g,x.v,x.r
        native=x.native({**x.recipe,'steps':[3,2]});cls.seed=admitted(native,assess(native,World(x.g,x.v,x.r),max_ablation_pages=20))
        cls.plan=sp.make(cls.seed,cls.g,cls.v,cls.r)

    def scored(self,text=None,short=None):return ss.score(self.plan,self.plan['reference_answer'] if text is None else text,self.seed['answer']['value'] if short is None else short,self.g,self.v,self.r)

    def test_real_typed_claims_and_reference_answer_are_verified(self):
        checked=sp.check(self.plan,self.g,self.v,self.r);self.assertTrue(checked['verified'])
        self.assertEqual(checked['claims'],{'supported':7,'contradicted':5});self.assertEqual(self.plan['unique_query_count'],7)
        self.assertTrue(self.scored()['accepted_controlled_answer'])
        self.assertEqual(self.plan['verification']['sentence_admission'],'pending')
        self.assertEqual(self.plan['verification']['inference'],'not_run')

    def test_independent_checker_does_not_call_claim_or_recipe_producer(self):
        from comics_qa.benchmark1000.recipe_engine import RecipeEngine
        with patch('comics_qa.benchmark1000.semantic.execute',side_effect=AssertionError('producer used')),patch.object(RecipeEngine,'execute',side_effect=AssertionError('recipe producer used')),patch.object(cp,'record',side_effect=AssertionError('claim producer used')):
            self.assertTrue(sp.check(self.plan,self.g,self.v,self.r)['verified'])

    def test_supported_paraphrases_recover_specs_without_expected_answer(self):
        text='For the first speaker, the final speaking page is page 6. The final speaking page for the second speaker is page 8. Chronologically, the final pages are 6 and 8.'
        self.assertTrue(self.scored(text)['accepted_controlled_answer'])
        self.assertEqual(ss.extract('The first speaker’s final speaking page is not page 6.')['relation'],'neq')

    def test_swapped_speakers_fail_even_with_correct_short_answer(self):
        text="The first speaker's final speaking page is page 8. The second speaker's final speaking page is page 6. The final pages in chronological order are pages 6 and 8."
        result=self.scored(text);self.assertTrue(result['short_answer_correct']);self.assertFalse(result['accepted_controlled_answer'])
        self.assertEqual(result['detected_false_assertions'],2);self.assertEqual(result['forbidden_claims_stated'],2)

    def test_negation_and_wrong_page_are_proved_false_not_missing(self):
        result=self.scored(self.plan['reference_answer']+" The first speaker's final speaking page is not page 6.")
        self.assertEqual(result['forbidden_claims_stated'],1);self.assertEqual(result['detected_false_assertions'],1)
        result=self.scored(self.plan['reference_answer']+" The first speaker's final speaking page is page 7.")
        self.assertEqual(result['forbidden_claims_stated'],0);self.assertEqual(result['detected_false_assertions'],1);self.assertFalse(result['accepted_controlled_answer'])

    def test_omissions_repetition_and_short_answer_do_not_bypass_claim_coverage(self):
        text=self.plan['claims']['required'][0]['text']+' '+self.plan['claims']['required'][0]['text']
        result=self.scored(text);self.assertEqual(result['required_claim_recall'],1/3);self.assertFalse(result['all_required_correct'])
        self.assertFalse(self.scored(short=[8,6])['accepted_controlled_answer'])
        self.assertFalse(self.scored('')['accepted_controlled_answer'])

    def test_extra_unknown_factual_clause_is_held_without_zero_hallucination_claim(self):
        result=self.scored(self.plan['reference_answer']+' The first speaker is angry.')
        self.assertEqual(result['required_claim_recall'],1);self.assertFalse(result['accepted_controlled_answer'])
        self.assertIsNone(result['unsupported_assertions']);self.assertIsNone(result['fully_factual_within_checked_grammar'])
        self.assertEqual(len(result['unresolved_clauses']),1)

    def test_optional_steps_and_extra_true_negation_are_checked(self):
        result=self.scored(self.plan['reference_answer']+' '+self.plan['claims']['optional'][0]['text'])
        self.assertTrue(result['accepted_controlled_answer']);self.assertEqual(result['optional_claims_covered'],1)
        result=self.scored(self.plan['reference_answer']+" The first speaker's final speaking page is not page 7.")
        self.assertTrue(result['accepted_controlled_answer'])

    def test_out_of_scope_step_and_page_are_unresolved_not_false(self):
        for clause in ('For the first speaker, speaking-search step 9 finds page 4.',"The first speaker's final speaking page is page 999."):
            result=self.scored(self.plan['reference_answer']+' '+clause)
            self.assertEqual(result['detected_false_assertions'],0);self.assertTrue(result['unresolved_clauses']);self.assertFalse(result['accepted_controlled_answer'])

    def test_missing_annotations_do_not_verify_forbidden_claim(self):
        g=copy.deepcopy(self.g)
        for c in g['coverage']:
            if c['page_id']==g['page_ids'][3] and c['family']=='speaker_links':c['status']='open'
        from comics_qa.evidence.graph.rich.model import build
        r=build(g,self.v,self.r['sources']);s=cp.expected(self.seed)['forbidden'][1]
        record=cp.record(self.seed,s,g,self.v,r,{})
        self.assertEqual(record['verification'],'unresolved')
        with self.assertRaises(ValueError):sp.check(self.plan,g,self.v,r)

    def test_claim_truth_and_program_tampering_are_rejected(self):
        c=copy.deepcopy(self.plan['claims']['required'][0]);c['verification']='contradicted'
        with self.assertRaises(ValueError):cp.Checker(self.seed,self.g,self.v,self.r).check(c)
        c=copy.deepcopy(self.plan['claims']['required'][0]);c['program']['in']={'var':'p1_1'}
        with self.assertRaises(ValueError):cp.Checker(self.seed,self.g,self.v,self.r).check(c)
        c=copy.deepcopy(self.plan['claims']['required'][0]);c['execution']['result']['display']=99;c['execution_sha256']=stable(c['execution'])
        with self.assertRaises(ValueError):cp.Checker(self.seed,self.g,self.v,self.r).check(c)

    def test_dropped_claims_changed_question_and_review_claims_are_rejected(self):
        for mutate in (lambda p:p['claims']['required'].pop(),lambda p:p.update(question=p['question']+' Why is he sad?'),lambda p:p['verification'].update(human='verified')):
            p=copy.deepcopy(self.plan);mutate(p);p['plan_id']='b1000sentenceplan:'+stable({k:v for k,v in p.items() if k not in ('schema','plan_id')})
            with self.assertRaises(ValueError):sp.validate(p)

    def test_final_step_alias_and_count_answer_plans(self):
        text=self.plan['reference_answer'].replace("The first speaker's final speaking page is page 6.",'For the first speaker, speaking-search step 3 finds page 6.')
        self.assertTrue(self.scored(text)['accepted_controlled_answer'])
        x=fixture.BranchRelationsTests();x.g,x.v,x.r=self.g,self.v,self.r
        x.recipe=cp.parse_question(self.seed['question'])['recipe']
        native=x.native({**x.recipe,'steps':[2,2],'kind':'branch_chain_gap'})
        seed=admitted(native,assess(native,World(self.g,self.v,self.r),max_ablation_pages=20))
        p=sp.make(seed,self.g,self.v,self.r)
        self.assertEqual(p['short_answer']['value'],2)
        self.assertTrue(ss.score(p,p['reference_answer'],2,self.g,self.v,self.r)['accepted_controlled_answer'])
        self.assertFalse(ss.score(p,p['reference_answer'],[5,8],self.g,self.v,self.r)['accepted_controlled_answer'])

    def test_store_resume_and_response_binding_cli(self):
        from comics_qa.benchmark1000.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'bench';source=Path(tmp)/'source';out=Path(tmp)/'plans';cid=self.g['chapter_id']
            parent={'config':{'chapters':[cid]},'outputs_sha256':{}}
            publish(source/'manifest.json',parent)
            for rel in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1'):publish(root/rel/'manifest.json',parent)
            for rel,doc in (('evidence/ckg/v1',self.g),('evidence/name_visibility/v1',self.v)):publish(root/rel/'chapters'/(cid+'.json'),doc)
            with ExitStack() as stack:
                stack.enter_context(patch('comics_qa.benchmark1000.sentence_plans.load_admitted',return_value=[self.seed]))
                for name,value in (('comics_qa.benchmark1000.sentence_plans.load_world',(self.g,self.v,{})),('comics_qa.benchmark1000.sentence_plans.load_optional',self.r),('comics_qa.tasks.graph.crl.artifacts.load_world',(self.g,self.v,{})),('comics_qa.tasks.graph.crl.rich_contract.load_optional',self.r)):
                    stack.enter_context(patch(name,return_value=value))
                first=sp.run(source,root,out);self.assertEqual(first['counts']['plans'],1)
                self.assertEqual(len(sp.load(out)),1);self.assertEqual(sp.verify(out,root)['verified'],1)
                with patch.object(sp,'make',side_effect=AssertionError('checkpoint recomputed')):self.assertEqual(sp.run(source,root,out),first)
                response={'schema':'comics_qa.benchmark1000.sentence_responses.1','store_manifest_sha256':digest(out/'manifest.json'),
                          'responses':[{'plan_id':self.plan['plan_id'],'plan_sha256':stable(self.plan),'answer':self.plan['reference_answer'],'short_answer':self.seed['answer']['value']}]}
                response_path=Path(tmp)/'responses.json';publish(response_path,response)
                scores=Path(tmp)/'scores.json'
                self.assertEqual(main(['score-sentences','--store',str(out),'--bench-root',str(root),'--responses',str(response_path),'--out',str(scores)]),0)
                self.assertEqual(read(scores)['accepted_controlled_answers'],1)
                response['responses'][0]['plan_sha256']='stale';response_path.write_text(json.dumps(response))
                with self.assertRaises(ValueError):ss.batch(out,root,response_path)
                from comics_qa.benchmark1000.store import load
                with self.assertRaises(ValueError):load(out) # Plans are not candidate supply.
            manifest=read(out/'manifest.json');name=next(k for k in manifest['outputs_sha256'] if k.startswith('plans/'));del manifest['outputs_sha256'][name];(out/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):sp.load(out)
