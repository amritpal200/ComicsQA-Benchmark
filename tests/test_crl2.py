"""Independent proof verification and adversarial mutations."""
import copy
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_crl
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.tasks.graph.crl.interpreter import Interpreter
from comics_qa.tasks.graph.crl.check_crl import main, strict_json, verify_input_pins
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.language import SPECS, parse


class IndependentRulesTest(test_crl.ExecutionTest):
    """Every checked result in the CRL-1 semantic corpus must agree independently."""
    def result(self, program, status='OK', value=...):
        document = super().result(program, status, value)
        report = ProofChecker(self.g, self.v).check(document)
        if status == 'ERROR':
            self.assertFalse(report['proof_valid'])
        else:
            self.assertTrue(report['proof_valid'], (program, report))
            self.assertEqual(report['accepted_for_generation'], document['eligible_for_generation'])
        return document


class TamperingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_crl.ExecutionTest.setUpClass()
        cls.addClassCleanup(test_crl.ExecutionTest.doClassCleanups)
        cls.graph = test_crl.ExecutionTest.graph
        cls.visibility = test_crl.ExecutionTest.visibility
        cls.root = test_crl.ExecutionTest.root

    def setUp(self):
        self.g, self.v = copy.deepcopy(self.graph), copy.deepcopy(self.visibility)
        self.doc = Interpreter(self.g, self.v).execute('count(texts(page(1)))')

    def assertRejected(self, doc=None):
        report = ProofChecker(self.g, self.v).check(self.doc if doc is None else doc)
        self.assertFalse(report['proof_valid'], report)
        self.assertFalse(report['accepted_for_generation'])
        self.assertTrue(report['errors'])
        return report

    def test_wrong_answer_and_display(self):
        for field, value in [('value',99), ('display',99), ('type','Bool3'), ('value',True), ('exact',False)]:
            doc = copy.deepcopy(self.doc);doc['result'][field] = value
            self.assertRejected(doc)

    def test_coherent_forgery_changes_intermediate_and_final_count(self):
        self.doc['proof']['steps'][-2]['value'].pop()
        self.doc['proof']['steps'][-1]['value'] = 1
        self.doc['result'].update(value=1, display=1)
        self.assertRejected()

    def test_bad_topology_and_extra_steps(self):
        for mutate in [lambda d: d['proof']['steps'][1].update(children=[1]),
                       lambda d: d['proof']['steps'][1].update(nid=10),
                       lambda d: d['proof'].update(root=0),
                       lambda d: d['proof']['steps'].append(copy.deepcopy(d['proof']['steps'][-1])),
                       lambda d: d['proof']['steps'].pop(0)]:
            doc = copy.deepcopy(self.doc);mutate(doc);self.assertRejected(doc)

    def test_fact_coverage_and_scope_tampering(self):
        for field in ['facts','certificates','range_pages','node_refs']:
            doc = copy.deepcopy(self.doc)
            step = next(s for s in doc['proof']['steps'] if s[field])
            step[field].pop()
            self.assertRejected(doc)
        for field in ['facts','certificates','range_pages','key_support_pages','node_refs']:
            doc = copy.deepcopy(self.doc);doc['proof'][field] = [];self.assertRejected(doc)

    def test_fabricated_and_cross_page_refs(self):
        for ref in ['invented', self.g['facts'][-1]['fact_id']]:
            doc = copy.deepcopy(self.doc);doc['proof']['facts'].append(ref);self.assertRejected(doc)

    def test_trust_promotion(self):
        doc = Interpreter(self.g,self.v).execute('char("Hero Man")')
        doc['proof']['trust_min'] = 'H';self.assertRejected(doc)
        doc = Interpreter(self.g,self.v).execute('char("Hero Man")')
        doc['proof']['steps'][-1]['trust_min'] = 'H';self.assertRejected(doc)

    def test_name_visibility_and_rendered_form(self):
        original = Interpreter(self.g,self.v).execute('char("Hero Man")')
        for field in ['visibility_evidence','answer_visibility_evidence']:
            doc = copy.deepcopy(original);doc['proof'][field] = [];self.assertRejected(doc)
        doc = copy.deepcopy(original);doc['result']['display'] = 'Unseen';self.assertRejected(doc)

    def test_open_coverage_not_upgraded(self):
        doc = Interpreter(self.g,self.v).execute('count(chars(page(2)))')
        doc['result'].update(status='OK',exact=True,value=0,display=0)
        doc['proof']['steps'][-1].update(status='OK',exact=True,value=0)
        doc['eligible_for_generation'] = True
        self.assertRejected(doc)

    def test_order_not_upgraded(self):
        doc = Interpreter(self.g,self.v).execute('first(apps(page(1)))')
        self.assertEqual(doc['result']['status'],'UNKNOWN')
        step = next(s for s in doc['proof']['steps'] if s['op']=='apps')
        step['ordered'] = True
        self.assertRejected(doc)

    def test_policy_version_chapter_program_binding(self):
        for key, value in [('chapter_id','elsewhere'),('crl_version','fake'),('canonical','(ctx)'),('program_sha256','f'*64)]:
            doc=copy.deepcopy(self.doc);doc[key]=value;self.assertRejected(doc)
        self.doc['policy']['closed_statuses'].append('open');self.assertRejected()
        report=ProofChecker(self.g,self.v).check(Interpreter(self.g,self.v).execute('count(ctx())'),expected_program='count(texts(ctx()))')
        self.assertFalse(report['proof_valid'])

    def test_lambda_substitution_is_checked(self):
        doc=Interpreter(self.g,self.v).execute(r'sum(map(ctx(), \p.rank(p,ctx())))')
        self.assertTrue(ProofChecker(self.g,self.v).check(doc)['proof_valid'])
        step=next(s for s in doc['proof']['steps'] if s['op']=='var')
        step['value']=self.g['page_ids'][-1]
        self.assertRejected(doc)

    def test_checker_never_calls_producer(self):
        with patch.object(Interpreter,'execute',side_effect=AssertionError('Producer called')), \
             patch.object(Interpreter,'eval',side_effect=AssertionError('Producer called')), \
             patch.object(Interpreter,'operation',side_effect=AssertionError('Producer called')):
            self.assertTrue(ProofChecker(self.g,self.v).check(self.doc)['proof_valid'])

    def test_reject_a_deliberately_broken_producer(self):
        from comics_qa.tasks.graph.crl.interpreter import Result
        original=Interpreter.operation
        def wrong(runner,op,args):
            return Result(value=42) if op=='count' else original(runner,op,args)
        with patch.object(Interpreter,'operation',wrong):
            doc=Interpreter(self.g,self.v).execute('count(texts(page(1)))')
        self.assertEqual(doc['result']['value'],42)
        self.assertRejected(doc)

    def test_unknown_is_valid_but_not_accepted(self):
        doc=Interpreter(self.g,self.v).execute('count(chars(page(2)))')
        report=ProofChecker(self.g,self.v).check(doc)
        self.assertTrue(report['proof_valid']);self.assertFalse(report['accepted_for_generation'])
        doc['eligible_for_generation']=True;self.assertRejected(doc)

    def test_unsupported_error_and_malformed_documents_fail_closed(self):
        for doc in [None,{},[],{'schema':[]},Interpreter(self.g,self.v).execute('bad()'),
                    Interpreter(self.g,self.v,max_steps=1).execute('count(ctx())')]:
            self.assertRejected(doc if doc is not None else {})

    def test_strict_coverage_and_resource_policy(self):
        doc=Interpreter(self.g,self.v,allow_closed_assumed=False).execute('count(ctx())')
        self.assertTrue(ProofChecker(self.g,self.v,allow_closed_assumed=False).check(doc)['proof_valid'])
        self.assertRejected(doc)
        self.assertFalse(ProofChecker(self.g,self.v,max_steps=2).check(self.doc)['proof_valid'])

    def test_premises_must_prove_relation(self):
        f=next(f for f in self.g['facts'] if f['rel']=='present' and f['args'][1]==self.g['page_ids'][0])
        wrong=next(x for x in self.g['facts'] if x['rel']=='page_in')
        f['premises']=[wrong['fact_id']]
        doc=Interpreter(self.g,self.v).execute('chars(page(1))')
        self.assertRejected(doc)

    def test_determinism_and_immutability(self):
        before=json.dumps([self.g,self.v,self.doc],sort_keys=True)
        checker=ProofChecker(self.g,self.v)
        self.assertEqual(checker.check(self.doc),checker.check(self.doc))
        self.assertEqual(before,json.dumps([self.g,self.v,self.doc],sort_keys=True))

    def test_every_registered_operation_has_independent_semantics(self):
        for c in self.g['coverage']:
            if c['family'] in ('char_boxes','names','text_boxes','speaker_links'): c['status']='closed_verified'
        c='char("Hero Man")'; a=f'first_app({c},span=page(1))'; t=f'first_line({c},span=page(1))'
        programs=['ctx()', 'unknown', 'page(1)', 'pages(1,3)', c]
        programs += [f'{op}(page(1))' for op in ('chars','apps','texts','lines','turns','chars_on','panels')]
        programs += [f'{op}({c},span=page(1))' for op in ('apps_of','lines_of','pages_with','pages_speaking','first_app','last_app','first_line','line_count','longest_streak','mentions_of','first_mention')]
        programs += [f'char_of({a})',f'page_of({a})',f'panel_of({a})',f'co_present({c})',f'is_named({c})']
        programs += [f'{op}({t})' for op in ('speaker','speaker_char','next_line','prev_line','next_other_speaker','mentioned_in','offpanel_line')]
        programs += [f'{op}({c},page(1))' for op in ('present','speaks_on','silent_on')]
        programs += [f'together({c},{c},unit=page(1))',f'exchanges({c},{c})',f'next_app({c},after=page(1))',f'nth_line({c},1,span=page(1))']
        programs += [f'{op}(1,2)' for op in ('eq','neq','compare','minus')]
        programs += [f'{op}(page(1),page(3))' for op in ('precedes','between','gap')]
        programs += [f'{op}(page(2))' for op in ('span_before','span_after')]
        programs += [f'{op}(ctx())' for op in ('first','last','distinct','count','exists','none')]
        programs += [f'{op}(page(2),ctx())' for op in ('next','prev','rank','in')]
        programs += ['the(pages(1,1))','nth(ctx(),2)','not(false)','and(true,false)','or(true,unknown)','at_least(ctx(),2)','quote("hello")','name_texts("Hero Man")']
        programs += [f'{op}(pages(1,2),pages(2,3))' for op in ('union','intersect','diff')]
        programs += [rf'{op}(map(ctx(), \p.rank(p,ctx())))' for op in ('min','max','sum','mode')]
        programs += [rf'{op}(ctx(), \p.rank(p,ctx()))' for op in ('map','sort_by','argmax','argmin','group_count')]
        programs += [r'top_k(ctx(), \p.rank(p,ctx()),1)',r'filter(ctx(), \p.eq(p,page(1)))',r'forall(ctx(), \p.eq(p,page(1)))']
        self.assertEqual({parse(p)['op'] for p in programs},set(SPECS))
        runner=Interpreter(self.g,self.v);checker=ProofChecker(self.g,self.v)
        for p in programs:
            with self.subTest(program=p):
                doc=runner.execute(p);report=checker.check(doc)
                self.assertTrue(report['proof_valid'],report)

    def test_streak_scope_with_duplicate_interior_pages(self):
        # Synthetic three-page world: two appearances per page, all Hero-readable.
        for cert in self.g['coverage']:
            if cert['family'] in ('char_boxes','names','text_boxes','speaker_links'): cert['status']='closed_verified'
        pid=self.g['page_ids'][1]
        template=next(n for n in self.g['nodes'] if n['type']=='Appearance' and n['identity_id']=='hero__hero-man')
        for i in range(2):
            aid=f'fixture-middle-{i}';node=copy.deepcopy(template);node.update(id=aid,page_id=pid);self.g['nodes'].append(node)
            for rel,args,premises in [('on_page',[aid,pid],[]),('is_char',[aid,'hero__hero-man'],[f'fixture-on_page-{i}']),
                                     ('present',['hero__hero-man',pid],[f'fixture-on_page-{i}',f'fixture-is_char-{i}'])]:
                if rel=='present' and i: continue
                fact=copy.deepcopy(next(f for f in self.g['facts'] if f['rel']==rel and f['origin']=='H'))
                families={'char_boxes'} if rel=='on_page' else {'char_boxes','names'}
                fact.update(fact_id=f'fixture-{rel}-{i}',args=args,premises=premises,page_ids=[pid],
                            coverage_refs=sorted(c['coverage_id'] for c in self.g['coverage'] if c['page_id']==pid and c['family'] in families))
                self.g['facts'].append(fact)
        doc=Interpreter(self.g,self.v).execute(r'longest_streak(char("Hero Man"),span=map(apps(ctx()), \a.page_of(a)))')
        report=ProofChecker(self.g,self.v).check(doc)
        self.assertTrue(report['proof_valid'],report)
        self.assertEqual(doc['result']['value'],3)

    def test_cli_artifact_pins_output_safety_and_exit_codes(self):
        _,_,sources=load_world(self.root/'graph',self.root/'visibility','hero__c001')
        self.doc['inputs_sha256']=sources
        path=self.root/'check-input.json';path.write_text(json.dumps(self.doc))
        out=self.root/'check-output.json'
        args=['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),'--result',str(path)]
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(args+['--out',str(out)]),0)
            self.assertEqual(main(args+['--out',str(out)]),2)
            self.assertEqual(main(args+['--out',str(path)]),2)
            self.assertEqual(main(args+['--out',str(self.root/'graph/new.json')]),2)
            self.doc['result']['value']=99;path.write_text(json.dumps(self.doc))
            self.assertEqual(main(args),1)
            self.doc['inputs_sha256']={};path.write_text(json.dumps(self.doc))
            self.assertEqual(main(args),2)
        report=json.loads(out.read_text())
        self.assertTrue(report['proof_valid'])
        self.assertTrue(report['checker_code_sha256'])
        self.assertEqual(report['inputs_sha256'],sources)

    def test_moved_paths_are_content_pinned_and_json_is_strict(self):
        _,_,sources=load_world(self.root/'graph',self.root/'visibility','hero__c001')
        doc={'inputs_sha256':{f'/moved/{i}':sha for i,sha in enumerate(sources.values())}}
        verify_input_pins(doc,sources)
        doc['inputs_sha256']['/moved/0']='f'*64
        with self.assertRaises(ValueError): verify_input_pins(doc,sources)
        for raw in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}']:
            with self.assertRaises(ValueError): strict_json(raw)


if __name__=='__main__': unittest.main()
