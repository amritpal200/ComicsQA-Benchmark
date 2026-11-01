"""GEN-1 proof gates, quota edge cases, deterministic and resumable builds."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

import test_crl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from comics_qa.tasks.graph.generation import build_gen1 as builder
from comics_qa.tasks.graph.generation.policy import configure,stable
from comics_qa.tasks.graph.generation.proposals import propose,Proposal,named,conjunction
from comics_qa.tasks.graph.generation.gates import Gates,without_pages
from comics_qa.tasks.graph.generation.balance import select,frequent_characters
from comics_qa.tasks.graph.crl.language import call,canonical,infer
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.tasks.graph.crl.interpreter import Interpreter
from name_visibility import summarize,normalized


def pool_item(i,typ='int',value=3,identity=None,two=False,family='f'):
    return {'item_id':str(i),'program_sha256':str(i),'canonical':str(i),'family':family,'strategy':'test',
            'answer':{'type':typ,'value':value,'identity_id':identity},'two_option':two,'gates':{},
            'execution':{'proof':{'facts':[str(i)],'certificates':[]}}}


def frequency_world():
    return {'nodes':[{'id':c,'generic':False} for c in 'abcd'],
            'facts':[{'rel':'present','args':[c,str(p)],'origin':'H','answer_eligible':True} for c,n in zip('abcd',[5,3,3,1]) for p in range(n)]}


class BalanceTest(unittest.TestCase):
    def policy(self,**kw): return configure({'max_items_per_chapter':200,'max_per_family':200,**kw})

    def test_top_two_cutoff_includes_ties(self):
        frequent,counts=frequent_characters(frequency_world(),self.policy())
        self.assertEqual(frequent,{'a','b','c'});self.assertEqual(counts['d'],1)

    def test_name_cap_applies_to_names_not_all_items(self):
        pool=[pool_item(i,'char','D','d') for i in range(7)]+[pool_item(i+10,'char','A','a') for i in range(20)]
        pool += [pool_item(i+100) for i in range(100)]
        selected,rejected,report=select(pool,frequency_world(),self.policy())
        self.assertEqual(report['selected']['name_answers'],10)
        self.assertEqual(report['selected']['frequent_name_answers'],3)
        self.assertLessEqual(report['selected']['frequent_name_share'],.3)

    def test_small_chapter_never_relaxes_frequent_quota(self):
        selected,_,report=select([pool_item(1,'char','A','a')],frequency_world(),self.policy())
        self.assertEqual(selected,[]);self.assertFalse(report['limits_relaxed'])

    def test_two_option_cap_and_balanced_true_false(self):
        pool=[pool_item(i) for i in range(76)]
        pool += [pool_item(100+i,'bool',bool(i%2),two=True) for i in range(20)]
        selected,_,report=select(pool,frequency_world(),self.policy(max_items_per_chapter=80))
        self.assertEqual(len(selected),80)
        self.assertEqual(report['selected']['two_option_answers'],4)
        self.assertEqual(report['selected']['boolean_true_share'],.5)

    def test_small_and_single_polarity_boolean_pools_are_held_out(self):
        for n,both in [(10,True),(100,False)]:
            pool=[pool_item(i) for i in range(n)]+[pool_item(1000+i,'bool',bool(i%2) if both else True,two=True) for i in range(10)]
            selected,_,report=select(pool,frequency_world(),self.policy())
            self.assertEqual(report['selected']['boolean_answers'],0)

    def test_dedup_program_and_answer_support(self):
        a=pool_item(1);b=copy.deepcopy(a);b['item_id']='other'
        c=copy.deepcopy(a);c.update(item_id='third',program_sha256='third')
        selected,_,_=select([a,b,c],frequency_world(),self.policy())
        self.assertEqual(len(selected),1)

    def test_shuffle_and_seed_determinism(self):
        pool=[pool_item(i,family=str(i%3),value=i%5+2) for i in range(40)]
        a=select(copy.deepcopy(pool),frequency_world(),self.policy(max_items_per_chapter=10))[0]
        b=select(copy.deepcopy(pool[::-1]),frequency_world(),self.policy(max_items_per_chapter=10))[0]
        self.assertEqual(a,b)

    def test_bad_policy_rejected(self):
        for change in [[],{'max_clauses':2.0},{'count_targets':[2,2]},{'max_frequent_name_share':.31},{'max_two_option_share':.06},{'count_targets':[]},{'max_steps':0},{'other':1}]:
            with self.assertRaises(ValueError): configure(change)


class GenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass();cls.addClassCleanup(test_crl.ExecutionTest.doClassCleanups)
        cls.fixture=test_crl.ExecutionTest

    def setUp(self):
        self.g=copy.deepcopy(self.fixture.graph);self.v=copy.deepcopy(self.fixture.visibility)
        self.policy=configure({'max_candidates_per_chapter':40,'max_items_per_chapter':10})
        self.sources=self.fixture.sources

    def gates(self): return Gates(self.g,self.v,self.policy,self.sources)

    def count(self,p=1):
        return Proposal('count_texts','answer_first',call('count',call('texts',call('page',p))),
                        f'How many text regions are shown on page {p}?',anchors=[p],target_answer=2)

    def test_valid_count_has_checked_evidence_and_full_context(self):
        item,reject=self.gates().assess(self.count())
        self.assertIsNone(reject)
        self.assertEqual(item['answer']['value'],2)
        self.assertTrue(item['proof_check']['proof_valid'])
        self.assertEqual(len(item['context']['pages']),3)
        self.assertEqual(item['context']['pages'][1]['index'],2)  # spread remains one image
        self.assertEqual(item['proof_check']['execution_sha256'],stable(item['execution']))
        self.assertEqual(item['review']['status'],'pending')
        self.assertIsNone(item['level'])
        self.assertEqual(item['scope_tier'],'single_page')
        self.assertEqual(item['gates']['G9']['applicable_noise_worlds'],0)
        self.assertIsNone(item['gates']['G9']['noise_invariance_fraction'])

    def test_unannotated_page_not_zero(self):
        item,reject=self.gates().assess(self.count(2))
        self.assertIsNone(item);self.assertEqual(reject['reason'],'UNKNOWN')

    def test_actual_rendered_name_is_checked(self):
        q=self.count();q.names=[('hero__hero-man','Unread Name')]
        item,reject=self.gates().assess(q)
        self.assertIsNone(item);self.assertEqual(reject['gate'],'names')

    def test_redundant_clause_is_rejected(self):
        q=self.count();q.clauses=['unnecessary'];q.relaxations=[q.ast]
        item,reject=self.gates().assess(q)
        self.assertIsNone(item);self.assertEqual(reject['reason'],'redundant_clause')

    def test_single_page_mislabeled_multi_step_is_rejected(self):
        q=self.count();q.level='L2'
        _,reject=self.gates().assess(q)
        self.assertEqual(reject['reason'],'single_page_multi_step_shortcut')

    def test_answer_leakage_and_target_mismatch(self):
        q=self.count();q.question='Are there 2 text regions?'
        _,reject=self.gates().assess(q);self.assertEqual(reject['reason'],'answer_number_in_question')
        q=self.count();q.target_answer=9
        _,reject=self.gates().assess(q);self.assertEqual(reject['reason'],'answer_first_target_mismatch')

    def test_checker_disagreement_blocks_generation(self):
        with patch.object(ProofChecker,'check',return_value={'proof_valid':False,'errors':['synthetic disagreement']}):
            with self.assertRaisesRegex(RuntimeError,'disagreement'): self.gates().assess(self.count())

    def test_profile_rejects_deferred_evidence_and_bad_clause_contract(self):
        q=self.count();q.ast=call('quote','Unverified transcript')
        _,reject=self.gates().assess(q)
        self.assertEqual(reject['gate'],'G1')
        q=self.count();q.clauses=['untracked clause']
        _,reject=self.gates().assess(q)
        self.assertEqual(reject['reason'],'invalid_shape_contract')

    def test_ablation_removes_derived_dependents_and_preserves_inputs(self):
        original=stable([self.g,self.v]);page=self.g['page_ids'][0]
        g,v=without_pages(self.g,self.v,[page]);runner=Interpreter(g,v)
        self.assertEqual(g['page_ids'],self.g['page_ids'])
        self.assertEqual(runner.execute('count(texts(page(1)))')['result']['status'],'UNKNOWN')
        ids={f['fact_id'] for f in g['facts']}
        self.assertTrue(all(set(f['premises'])<=ids for f in g['facts']))
        self.assertEqual(stable([self.g,self.v]),original)

    def test_proposals_are_bounded_typed_and_deterministic(self):
        first=list(propose(self.g,self.v,self.policy));second=list(propose(self.g,self.v,self.policy))
        self.assertEqual(first,second);self.assertLessEqual(len(first),40)
        self.assertEqual(len({canonical(q.ast) for q in first}),len(first))
        for q in first: infer(q.ast)

    def test_chapter_determinism_and_selected_proofs(self):
        before=stable([self.g,self.v]);a=builder.chapter(self.g,self.v,self.policy,self.sources)
        b=builder.chapter(self.g,self.v,self.policy,self.sources)
        self.assertEqual(a,b);self.assertEqual(before,stable([self.g,self.v]))
        self.assertEqual(a['counts']['attempted'],a['counts']['selected']+a['counts']['rejected'])
        for item in a['items']:
            self.assertTrue(ProofChecker(self.g,self.v).check(item['execution'])['proof_valid'])
            self.assertNotIn('hero__',item['question'])

    def named_world(self):
        # Make the page-local generic identities named in this synthetic world:
        # page 1 = Hero + Alpha, page 3 = Hero + Beta, so both clauses are necessary.
        for node in self.g['nodes']:
            if node['type']!='Character' or not node['generic']: continue
            pid=node['appearance_ids'][0].split('__hchar')[0]
            label='Alpha' if pid==self.g['page_ids'][0] else 'Beta'
            node.update(generic=False,canonical_name=label,aliases=[])
            cert=next(c['coverage_id'] for c in self.g['coverage'] if c['page_id']==pid and c['family']=='names')
            fact=copy.deepcopy(next(f for f in self.g['facts'] if f['rel']=='named'))
            fact.update(fact_id='fixture-name-'+label,args=[node['id'],label],page_ids=[pid],coverage_refs=[cert])
            self.g['facts'].append(fact)
            evidence=copy.deepcopy(next(e for e in self.v['evidence'] if e['status']=='verified' and e['page_id']==pid))
            evidence.update(evidence_id='fixture-visible-'+label,identity_id=node['id'],form=label,normalized_form=normalized(label),is_canonical=True)
            self.v['evidence'].append(evidence)
        self.v['visibility']=summarize(self.g,self.v['evidence'])

    def test_constraint_accretion_and_necessity_end_to_end(self):
        self.named_world()
        candidates=[q for q in propose(self.g,self.v,self.policy) if q.strategy=='constraint_accretion']
        self.assertTrue(candidates)
        q=next(q for q in candidates if all('drawn' in label for label in q.clauses))
        item,rejection=self.gates().assess(q)
        self.assertIsNone(rejection,rejection)
        self.assertEqual(item['answer']['value'],'Hero Man')
        self.assertEqual(len(item['gates']['G6']['removals']),2)
        self.assertTrue(all(r['result']['status']=='AMBIGUOUS' for r in item['gates']['G6']['removals']))
        self.assertEqual(len(item['dimensions']['visual_support_pages']),2)
        self.assertTrue(item['gates']['G8']['anchor_only'])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_crl.test_ckg2.BuildTest(methodName='test_deterministic_outputs_and_completed_resume')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.fixture.run_build()
        self.root=self.fixture.root
        self.args=['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),
                   '--out',str(self.root/'gen'),'--max-candidates-per-chapter','12','--max-items-per-chapter','4']

    def run_build(self,*args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return builder.main(self.args+list(args))

    def test_build_resume_checksums_and_source_immutability(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.run_build(),0)
        manifest=builder.read(self.root/'gen/manifest.json')
        for path,sha in manifest['outputs_sha256'].items(): self.assertEqual(builder.digest((self.root/'gen'/path).read_bytes()),sha)
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        with patch.object(builder,'chapter',side_effect=AssertionError('must reuse')):
            self.assertEqual(self.run_build('--resume'),0)
        self.assertEqual(self.run_build(),2)

    def test_interruption_reuses_checkpoint(self):
        original=builder.write
        def interrupted(path,obj):
            if path.name=='report.json': raise OSError('simulated interruption')
            return original(path,obj)
        with patch.object(builder,'write',interrupted): self.assertEqual(self.run_build(),2)
        self.assertTrue((self.root/'gen.partial/chapters/hero__c001.json').exists())
        with patch.object(builder,'chapter',side_effect=AssertionError('must reuse')):
            self.assertEqual(self.run_build('--resume'),0)

    def test_resume_rejects_changed_policy_corruption_and_sources(self):
        self.assertEqual(self.run_build(),0)
        self.assertEqual(self.run_build('--resume','--seed','1'),2)
        path=self.root/'gen/report.md';path.write_text('corrupt')
        self.assertEqual(self.run_build('--resume'),2)

    def test_output_overlap_and_changed_graph(self):
        self.assertEqual(self.run_build('--out',str(self.root/'graph/new')),2)
        path=self.root/'graph/chapters/hero__c001.json';path.write_bytes(path.read_bytes()+b'\n')
        self.assertEqual(self.run_build(),2)

    def test_same_build_different_output_is_deterministic(self):
        self.assertEqual(self.run_build(),0)
        self.assertEqual(self.run_build('--out',str(self.root/'gen2')),0)
        self.assertEqual((self.root/'gen/chapters/hero__c001.json').read_bytes(),(self.root/'gen2/chapters/hero__c001.json').read_bytes())

    def test_separate_process_hash_seed_determinism(self):
        self.assertEqual(self.run_build(),0)
        command=[sys.executable,str(Path(builder.__file__)),*self.args,'--out',str(self.root/'other-process')]
        result=subprocess.run(command,env={**os.environ,'PYTHONHASHSEED':'97'},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual((self.root/'gen/chapters/hero__c001.json').read_bytes(),(self.root/'other-process/chapters/hero__c001.json').read_bytes())

    def test_missing_visibility_chapter_cannot_shrink_collection(self):
        path=self.root/'visibility/manifest.json';data=builder.read(path);data['config']['chapters']=[];builder.write(path,data)
        self.assertEqual(self.run_build(),2)
        self.assertFalse((self.root/'gen').exists())

    def test_completed_resume_rechecks_current_graph_bytes(self):
        self.assertEqual(self.run_build(),0)
        path=self.root/'graph/chapters/hero__c001.json';path.write_bytes(path.read_bytes()+b'\n')
        self.assertEqual(self.run_build('--resume'),2)

    def test_zero_yield_is_reported_without_relaxing_coverage(self):
        config=self.root/'strict.json';builder.write(config,configure({'allow_closed_assumed':False}))
        self.assertEqual(self.run_build('--config',str(config)),0)
        report=builder.read(self.root/'gen/report.json')
        self.assertEqual(report['counts']['selected'],0)
        self.assertEqual(report['counts']['chapters'],1)
        self.assertFalse(report['chapters'][0]['balance']['limits_relaxed'])


if __name__=='__main__': unittest.main()
