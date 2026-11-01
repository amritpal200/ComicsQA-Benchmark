import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_branch_relations as branch_fixture
from comics_qa.benchmark1000 import contrast
from comics_qa.benchmark1000.admission import World,assess
from comics_qa.benchmark1000.admission_store import admitted
from comics_qa.benchmark1000.io import read,publish,stable


class ContrastTests(unittest.TestCase):
    native=branch_fixture.BranchRelationsTests.native
    @classmethod
    def setUpClass(cls):
        branch_fixture.BranchRelationsTests.setUpClass.__func__(cls)
        obj=cls();branch_fixture.BranchRelationsTests.setUp(obj)
        world=World(obj.g,obj.v,obj.r)
        cls.a=admitted(obj.native({**obj.recipe,'steps':[3,2]}),assess(obj.native({**obj.recipe,'steps':[3,2]}),world,max_ablation_pages=20))
        n=obj.native();cls.b=admitted(n,assess(n,world,max_ablation_pages=20))
        cls.g,cls.v,cls.r,cls.recipe=obj.g,obj.v,obj.r,obj.recipe
        cls.pair=contrast.build(cls.a,cls.b);cls.items=[contrast.member(cls.pair,n) for n in (0,1)]

    def test_exact_single_parameter_delta_and_views(self):
        self.assertEqual(self.pair['delta']['path'],['steps',0]);self.assertEqual(self.a['answer']['value'],[6,8]);self.assertEqual(self.b['answer']['value'],[5,8])
        for i in self.items:
            self.assertEqual(contrast.validate_member(i),i);self.assertEqual(i['primary_group'],'paired');self.assertEqual(i['verification']['human'],'pending')
        self.assertEqual(len(contrast.units(self.items)),1)

    def test_unchanged_answers_and_zero_changes_rejected(self):
        with self.assertRaises(ValueError):contrast.build(self.a,self.a)
        with self.assertRaises(ValueError):contrast.build(self.b,self.b)

    def test_more_than_one_parameter_change_rejected(self):
        bad=copy.deepcopy(self.b);bad['question']=bad['question'].replace('from page 4','from page 5')
        with self.assertRaises(ValueError):contrast.delta(self.a,bad)

    def test_view_tampering_cannot_override_human_or_answer(self):
        for field,value in [('answer',{'type':'sequence','value':[99,100],'identity_id':None}),('verification',{'proof':'verified','human':'verified'}),('pair_role',True),('edit_verification','pending')]:
            bad=copy.deepcopy(self.items[0]);bad[field]=value
            bad['item_id']='b1000contrast:'+stable({k:v for k,v in bad.items() if k not in ('schema','item_id')})
            with self.assertRaises(ValueError):contrast.validate_member(bad)

    def test_missing_member_and_mixed_pair_fail_closed(self):
        with self.assertRaises(ValueError):contrast.units(self.items[:1])
        with self.assertRaises(ValueError):contrast.units([self.items[0],self.items[0]])

    def test_public_input_has_one_question_and_no_private_pair_data(self):
        for i in self.items:
            public=contrast.public_input(i)
            self.assertEqual(set(public),{'item_id','question','answer_format','images'})
            self.assertNotIn('pair_id',json.dumps(public));self.assertNotIn('execution',json.dumps(public));self.assertNotIn('answer_check',json.dumps(public))
            self.assertEqual(len(public['images']),10)

    def test_scoring_requires_both_correct_and_counts_missing(self):
        predictions={x['item_id']:x['answer']['value'] for x in self.items}
        self.assertEqual(contrast.score(self.items,predictions)['both_correct_pair_accuracy'],1)
        predictions[self.items[1]['item_id']]=self.items[0]['answer']['value']
        result=contrast.score(self.items,predictions);self.assertEqual(result['member_accuracy'],.5);self.assertEqual(result['both_correct_pair_accuracy'],0)
        self.assertEqual(contrast.score(self.items,{})['missing'],2)
        with self.assertRaises(ValueError):contrast.score(self.items,{'unknown':[]})

    def test_reference_and_cp_selection_keep_closure_without_standalone_repeat(self):
        from comics_qa.benchmark1000.selection import select,violations
        from comics_qa.benchmark1000.solver import select_cp
        p=read(Path('configs/benchmark1000/v1.json'));p['maximum_per_chapter']=10
        pool=[self.a,*self.items];chosen,r=select(pool,p,pilot=True)
        self.assertEqual(len(chosen),2);self.assertEqual({i['pair_id'] for i in chosen},{self.pair['pair_id']})
        cp,r=select_cp(pool,p,pilot=True,seconds=3);self.assertEqual(len(cp),2)
        self.assertIn('repeated_contrast_task',violations(pool,p))
        self.assertIn('pair_closure',violations(self.items[:1],p))

    def test_review_sampling_preserves_pairs_and_does_not_claim_item_binomial_bound(self):
        from comics_qa.benchmark1000.review import sample,release_eligible
        self.assertEqual(sample(self.items,1,42)['selection_size'],0)
        result=sample(self.items,2,42);self.assertEqual(len(result['selected_ids']),2);self.assertIsNone(result['zero_error_binomial_95_upper'])
        self.assertFalse(release_eligible(self.items[0],[]))

    def test_generator_proves_both_members_and_respects_budget(self):
        from comics_qa.benchmark1000.contrast_pilot import generate
        result=generate([self.a],World(self.g,self.v,self.r),{}, {self.a['item_id']:[]},1,1,20)
        self.assertEqual(result['counts'],{'pairs':1,'members':2,'attempted':1})
        self.assertEqual(result['pairs'][0],self.pair)

    def test_unknown_variant_is_held_without_using_unknown_as_contrast(self):
        from comics_qa.benchmark1000.contrast_pilot import generate
        with patch('comics_qa.benchmark1000.contrast_pilot.execute',return_value=({'result':{'status':'UNKNOWN','value':None}}, {'proof_valid':True},False)):
            result=generate([self.a],World(self.g,self.v,self.r),{}, {self.a['item_id']:[]},1,1,20)
        self.assertEqual(result['pairs'],[]);self.assertEqual(result['trials'][0]['status'],'answer_unproved');self.assertTrue(result['budget_hit'])

    def test_store_checkpoint_resume_and_pair_publication(self):
        from comics_qa.benchmark1000.contrast_pilot import run,load
        from comics_qa.benchmark1000.pool import inventory,make_index
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'bench';source=Path(tmp)/'source';out=Path(tmp)/'out'
            parent={'config':{'chapters':[self.g['chapter_id']]},'outputs_sha256':{}}
            publish(source/'manifest.json',parent)
            for name in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1'):publish(root/name/'manifest.json',parent)
            with patch('comics_qa.benchmark1000.contrast_pilot.load_admitted',return_value=[self.a]),patch('comics_qa.benchmark1000.contrast_pilot.load_world',return_value=(self.g,self.v,{})),patch('comics_qa.benchmark1000.contrast_pilot.load_optional',return_value=self.r),patch('comics_qa.benchmark1000.contrast_pilot.approvals',return_value=[]):
                first=run(source,root,out,max_pairs=1,max_variants=1,max_ablation_pages=20)
                self.assertEqual(first['counts']['pairs'],1);xs=load(out);self.assertEqual(len(xs),2)
                self.assertEqual(inventory(xs)['certified_native_groups'],{'paired':2})
                from comics_qa.benchmark1000.cli import main
                predictions=Path(tmp)/'predictions.json';scores=Path(tmp)/'scores.json'
                publish(predictions,{x['item_id']:x['answer']['value'] for x in xs})
                self.assertEqual(main(['score-contrast','--store',str(out),'--predictions',str(predictions),'--out',str(scores)]),0)
                self.assertEqual(read(scores)['both_correct_pair_accuracy'],1)
                with patch('comics_qa.benchmark1000.contrast_pilot.generate',side_effect=AssertionError('checkpoint recomputed')):
                    self.assertEqual(run(source,root,out,max_pairs=1,max_variants=1,max_ablation_pages=20),first)
                with self.assertRaises(ValueError):run(source,root,out,max_pairs=1,max_variants=2,max_ablation_pages=20)
                records={stable(x):x for x in xs};occurrences=[{'record_sha256':k,'source_index':0,'item_id':v['item_id']} for k,v in records.items()]
                self.assertEqual(len(make_index(records,occurrences)['groups']),2)
                with self.assertRaises(ValueError):make_index({stable(xs[0]):xs[0]},occurrences[:1])
            manifest=read(out/'manifest.json');name=next(n for n in manifest['outputs_sha256'] if n.startswith('candidates/'))
            del manifest['outputs_sha256'][name];(out/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):load(out)

    def test_range_only_variant_passes_full_admission(self):
        proposal=self.native({**self.recipe,'start':5})
        receipt=assess(proposal,World(self.g,self.v,self.r),max_ablation_pages=20)
        self.assertTrue(receipt['passed'],receipt['reasons'])
        variant=admitted(proposal,receipt);pair=contrast.build(self.b,variant)
        self.assertEqual(pair['delta']['path'],['start']);self.assertEqual(variant['answer']['value'],[6,8])
        self.assertNotEqual(self.b['answer']['value'],variant['answer']['value'])

    def test_standalone_proof_replay_reproduces_both_member_admissions(self):
        from comics_qa.benchmark1000.verification import revalidate
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,doc in (('evidence/ckg/v1',self.g),('evidence/name_visibility/v1',self.v)):
                publish(root/name/'chapters'/(self.g['chapter_id']+'.json'),doc)
            with patch('comics_qa.tasks.graph.crl.artifacts.load_world',return_value=(self.g,self.v,{})),patch('comics_qa.tasks.graph.crl.rich_contract.load_optional',return_value=self.r):
                report=revalidate(self.items,root)
            self.assertEqual(report['verified'],2);self.assertEqual(report['rejected'],0)
            self.assertTrue(all(x['check']['native_admission_reproduced'] and x['check']['contrast_condition_verified'] for x in report['items']))

    def test_range_start_is_an_independent_single_condition(self):
        from comics_qa.benchmark1000.branch_relations import render
        a={'question':render(self.recipe)};b={'question':render({**self.recipe,'start':5})}
        d=contrast.delta(a,b);self.assertEqual(d['path'],['start']);self.assertEqual((d['before'],d['after']),(4,5))
        c={'question':render({**self.recipe,'start':5,'steps':[3,2]})}
        with self.assertRaises(ValueError):contrast.delta(a,c)

    def test_invalid_run_budget_fails_before_source_access(self):
        from comics_qa.benchmark1000.contrast_pilot import run
        for kw in ({'max_pairs':0},{'max_variants':True},{'max_ablation_pages':-1}):
            with self.assertRaises(ValueError):run('/missing','/missing','/tmp/unused',**kw)
