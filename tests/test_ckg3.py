"""CKG-3 trust gates, geometry, full OCR agreement and immutable build tests."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from comics_qa.evidence.graph.rich import model as m
from comics_qa.evidence.graph.rich import build as builder
from comics_qa.evidence.graph.rich.loader import load_rich
import test_ckg2


def fixture():
    def node(i, typ, box):
        return {'id': i, 'type': typ, 'origin': 'M' if typ == 'Panel' else 'H', 'page_id': 'p',
                'box': box, 'sources': [], 'estimated_reading_rank': 0}
    nodes = [{'id': 'p', 'type': 'Page', 'width': 100, 'height': 100, 'image_sha256': 'image',
              'annotated': True, 'index_in_chapter': 0, 'image_path': '/tmp/p.jpg'},
             {'id': 'hero', 'type': 'Character', 'generic': False},
             node('panel', 'Panel', [0,0,100,100]), node('a', 'Appearance', [10,10,30,40]),
             node('b', 'Appearance', [60,60,70,70]), node('t', 'Text', [10,75,50,90])]
    coverage = [{'page_id': 'p', 'family': f, 'status': 'closed_assumed', 'coverage_id': 'cov:'+f}
                for f in ('char_boxes', 'text_boxes', 'panels', 'reading_order', 'ocr')]
    g = {'chapter_id': 'c', 'split': 'seen', 'page_ids': ['p'], 'nodes': nodes, 'coverage': coverage,
         'facts': [{'fact_id': 'speaker', 'rel': 'spoken_by', 'args': ['t','a'], 'origin': 'H', 'answer_eligible': True},
                   {'fact_id': 'identity', 'rel': 'is_char', 'args': ['a','hero'], 'origin': 'H', 'answer_eligible': True}]}
    a = {'alignment_id': 'align', 'page_id': 'p', 'image_sha256': 'image', 'text_id': 't', 'status': 'aligned',
         'paddle_ok': True, 'magi_ok': True, 'paddle_text': 'Hello HERO!', 'magi_text': 'Hello Hero!', 'sources': []}
    e = {'evidence_id': 'name', 'page_id': 'p', 'text_id': 't', 'alignment_id': 'align', 'identity_id': 'hero',
         'form': 'Hero', 'status': 'verified', 'sources': []}
    v = {'chapter_id': 'c', 'page_ids': ['p'], 'alignments': [a], 'evidence': [e]}
    return g, v, {'graph_sha256': 'g', 'visibility_sha256': 'v'}


def decision(kind, target='p', **kw):
    return {'kind': kind, 'target_id': target, 'chapter_id': 'c', 'page_id': 'p', 'graph_sha256': 'g',
            'visibility_sha256': 'v', 'image_sha256': 'image', 'status': 'verified', 'reviewer': 'human',
            'note': 'Checked the original image', **kw}


def panels():
    return decision('panels', complete_inventory=True, panel_ids=['panel'])


class EvidenceTests(unittest.TestCase):
    def setUp(self): self.g, self.v, self.s = fixture()
    def build(self, decisions=()): return m.build(self.g, self.v, self.s, decisions)

    def test_default_model_panels_never_eligible(self):
        r = self.build()
        self.assertEqual(m.eligible_facts(r, 'in_panel'), [])
        self.assertEqual(m.eligible_facts(r, 'left_of'), [])
        self.assertTrue(any(f['rel']=='left_of' for f in r['facts']))
        self.assertEqual(r['counts']['verified_panel_pages'], 0)

    def test_review_unlocks_geometry_and_presence(self):
        r = self.build([panels()])
        self.assertEqual(m.eligible_facts(r, 'left_of')[0]['args'], ['a','b'])
        self.assertEqual(m.eligible_facts(r, 'above')[0]['args'], ['a','b'])
        self.assertEqual(m.eligible_facts(r, 'larger_than')[0]['args'], ['a','b'])
        self.assertEqual(m.eligible_facts(r, 'present_panel')[0]['args'], ['hero','panel'])

    def test_geometry_tie_is_unknown_not_direction(self):
        self.g['nodes'][4]['box'] = [15,60,35,70]  # exactly 5px center margin
        r = self.build([panels()])
        self.assertEqual(m.eligible_facts(r, 'left_of'), [])

    def test_cross_panel_geometry_excluded_offpanel_link_retained(self):
        self.g['nodes'][2]['box'] = [0,0,50,100]
        self.g['nodes'].append({'id': 'panel2', 'type': 'Panel', 'origin': 'M', 'page_id': 'p', 'box': [50,0,100,100], 'estimated_reading_rank': 1})
        self.g['nodes'][5]['box'] = [60,75,90,90]
        r = self.build([decision('panels', complete_inventory=True, panel_ids=['panel','panel2'])])
        self.assertEqual(m.eligible_facts(r, 'left_of'), [])
        self.assertEqual(m.eligible_facts(r, 'offpanel_line')[0]['args'], ['t','a'])

    def test_ambiguous_membership_is_not_resolved_by_best_score(self):
        self.g['nodes'].append({'id': 'panel2','type':'Panel','origin':'M','page_id':'p','box':[0,0,80,100],'estimated_reading_rank':1})
        r = self.build([decision('panels', complete_inventory=True, panel_ids=['panel','panel2'])])
        self.assertTrue(all(x['status']=='ambiguous' for x in r['memberships']))
        self.assertEqual(m.eligible_facts(r,'in_panel'), [])

    def test_invalid_geometry_and_truncated_size(self):
        self.g['nodes'][3]['box'] = [-1,10,30,40]
        self.assertFalse(next(x for x in self.build([panels()])['memberships'] if x['region_id']=='a')['answer_eligible'])
        self.g['nodes'][3]['box'] = [0,10,30,40]
        self.assertEqual(m.eligible_facts(self.build([panels()]), 'larger_than'), [])

    def test_ocr_full_agreement_retains_punctuation(self):
        self.assertEqual(len(m.eligible_facts(self.build(), 'transcript')), 1)
        self.v['alignments'][0]['magi_text'] = 'Hello Hero?'
        self.assertEqual(m.eligible_facts(self.build(), 'transcript'), [])
        self.v['alignments'][0]['magi_text'] = 'Different Hero!'
        self.assertEqual(m.eligible_facts(self.build(), 'transcript'), [])

    def test_truncation_alignment_and_empty_ocr_never_verify(self):
        for changes in ({'paddle_ok': False}, {'magi_ok': False}, {'status':'ambiguous'}, {'paddle_text':'','magi_text':''}):
            g,v,s = fixture(); v['alignments'][0].update(changes)
            self.assertEqual(m.eligible_facts(m.build(g,v,s),'transcript'), [])

    def test_transcript_review_can_override_disagreement(self):
        self.v['alignments'][0]['magi_text'] = 'wrong'
        r = self.build([decision('transcript','align',transcription='Hello Hero!')])
        self.assertEqual(m.eligible_facts(r,'transcript')[0]['args'], ['t','hello hero!'])
        r = self.build([decision('transcript','align',status='rejected')])
        self.assertEqual(m.eligible_facts(r,'transcript'), [])

    def test_name_occurrence_is_not_semantic_mention(self):
        r = self.build()
        self.assertEqual(len(m.eligible_facts(r,'name_occurs')),1)
        self.assertEqual(m.eligible_facts(r,'mentions'), [])
        r = self.build([decision('mention','name',identity_id='hero')])
        self.assertEqual(len(m.eligible_facts(r,'mentions')),1)
        self.assertEqual(next(c for c in r['coverage'] if c['family']=='semantic_mentions')['status'],'open')

    def test_semantic_review_needs_readable_full_transcript_and_identity(self):
        for changes in ({'identity_id':'other'},):
            with self.assertRaises(ValueError): self.build([decision('mention','name',**changes)])
        self.v['alignments'][0]['magi_ok'] = False
        with self.assertRaises(ValueError): self.build([decision('mention','name',identity_id='hero')])

    def test_no_gt_ocr_does_not_create_human_text_fact(self):
        self.v['alignments'][0]['text_id'] = None; self.v['evidence'][0]['text_id'] = None
        r = self.build()
        self.assertEqual(r['counts']['verified_transcripts'],1)
        self.assertEqual(m.eligible_facts(r,'transcript'),[])
        self.assertEqual(m.eligible_facts(r,'name_occurs'),[])

    def test_order_requires_complete_permutation_and_closed_texts(self):
        d = decision('text_order',ordered_ids=['t'])
        r = self.build([d]);self.assertEqual(len(m.eligible_facts(r,'text_order_rank')),1)
        for order in ([], ['t','t'], ['missing']):
            with self.assertRaises(ValueError): self.build([decision('text_order',ordered_ids=order)])
        next(c for c in self.g['coverage'] if c['family']=='text_boxes')['status']='open'
        with self.assertRaises(ValueError): self.build([d])

    def test_reading_position_requires_both_reviewed_orders(self):
        ds=[panels(), decision('panel_order',ordered_ids=['panel']), decision('text_order',ordered_ids=['t'])]
        self.assertEqual(m.eligible_facts(self.build(ds),'reading_pos')[0]['args'],['t',0,0,0])
        self.assertEqual(m.eligible_facts(self.build(ds[:2]),'reading_pos'),[])

    def test_partial_mapping_blocks_exact_reading_positions(self):
        self.g['nodes'].append({'id':'u','type':'Text','origin':'H','page_id':'p','box':[-5,2,10,10]})
        ds=[panels(), decision('panel_order',ordered_ids=['panel']), decision('text_order',ordered_ids=['u','t'])]
        r=self.build(ds)
        self.assertEqual(m.eligible_facts(r,'reading_pos'),[])
        self.assertEqual(m.eligible_facts(r,'next_text')[0]['args'],['u','t'])

    def test_conflicting_panel_and_text_orders_rejected(self):
        self.g['nodes'][2]['box']=[0,0,50,100]
        self.g['nodes'].append({'id':'panel2','type':'Panel','origin':'M','page_id':'p','box':[50,0,100,100],'estimated_reading_rank':1})
        self.g['nodes'].append({'id':'u','type':'Text','origin':'H','page_id':'p','box':[60,75,90,90]})
        ds=[decision('panels',complete_inventory=True,panel_ids=['panel','panel2']),
            decision('panel_order',ordered_ids=['panel','panel2']),decision('text_order',ordered_ids=['u','t'])]
        with self.assertRaises(ValueError): self.build(ds)

    def test_rejected_panels_cannot_support_order(self):
        with self.assertRaises(ValueError):self.build([decision('panels',status='rejected'),decision('panel_order',ordered_ids=['panel'])])

    def test_overlap_iou_and_multiple_speakers(self):
        self.g['nodes'][4]['box']=[20,20,40,50]
        self.assertEqual(len(m.eligible_facts(self.build([panels()]),'overlaps')),1)
        self.g['facts'].append({'fact_id':'speaker2','rel':'spoken_by','args':['t','b'],'origin':'H','answer_eligible':True})
        self.assertEqual(m.eligible_facts(self.build([panels()]),'offpanel_line'),[])

    def test_assumed_coverage_not_promoted(self):
        r = self.build([panels(),decision('text_order',ordered_ids=['t'])])
        for fam in ('ocr','text_order','panel_memberships'):
            self.assertEqual(next(c for c in r['coverage'] if c['family']==fam)['status'],'closed_assumed')
        self.assertEqual(next(c for c in r['coverage'] if c['family']=='panels')['status'],'closed_verified')

    def test_open_text_coverage_keeps_ocr_scope_open(self):
        next(c for c in self.g['coverage'] if c['family']=='text_boxes')['status']='open'
        self.assertEqual(next(c for c in self.build()['coverage'] if c['family']=='ocr')['status'],'open')

    def test_stale_unknown_duplicate_or_unattributed_reviews_rejected(self):
        for change in ({'graph_sha256':'old'},{'visibility_sha256':'old'},{'image_sha256':'old'},{'target_id':'missing'},
                       {'reviewer':''},{'status':'pending'},{'panel_ids':[]},{'complete_inventory':False}):
            d=panels();d.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError): self.build([d])
        with self.assertRaises(ValueError): self.build([panels(),panels()])

    def test_deterministic_and_inputs_immutable(self):
        before=copy.deepcopy((self.g,self.v));self.assertEqual(self.build(),self.build())
        self.assertEqual((self.g,self.v),before)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_ckg2.BuildTest(methodName='test_deterministic_outputs_and_completed_resume')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups);self.fixture.run_build()
        self.root=self.fixture.root;self.out=self.root/'rich'

    def run_cli(self,*extra):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return builder.main(['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),'--out',str(self.out),*extra])

    def test_build_resume_and_loader(self):
        self.assertEqual(self.run_cli(),0);self.assertEqual(self.run_cli('--resume'),0)
        rich=load_rich(self.root/'graph',self.root/'visibility',self.out,'hero__c001')
        self.assertEqual(rich['counts']['pages'],3)
        self.assertEqual(rich['counts']['verified_panel_pages'],0)
        self.assertEqual(self.run_cli(),2)

    def test_changed_output_and_source_fail(self):
        self.assertEqual(self.run_cli(),0)
        path=self.out/'chapters/hero__c001.json';path.write_text('{}')
        self.assertEqual(self.run_cli('--resume'),2)
        with self.assertRaises(ValueError):load_rich(self.root/'graph',self.root/'visibility',self.out,'hero__c001')

    def test_raw_source_changes_fail(self):
        self.assertEqual(self.run_cli(),0)
        saved=builder.read(self.out/'chapters/hero__c001.json')
        path=next(Path(p) for p in saved['raw_sources_sha256'] if '/human/' in p)
        path.write_text('{}')
        self.assertEqual(self.run_cli('--resume'),2)

    def test_partial_resume(self):
        original=builder.write
        def interrupt(path,payload):
            if Path(path).name=='report.json':raise KeyboardInterrupt
            return original(path,payload)
        with patch.object(builder,'write',interrupt):self.assertEqual(self.run_cli(),130)
        self.assertEqual(self.run_cli('--resume'),0)

    def test_changed_code_and_unknown_chapter(self):
        self.assertEqual(self.run_cli('--chapter','missing'),2)
        self.assertEqual(self.run_cli(),0)
        with patch.object(builder,'code_hashes',return_value={'changed':'hash'}):self.assertEqual(self.run_cli('--resume'),2)

    def test_overlap_rejected(self):
        self.assertEqual(self.run_cli('--out',str(self.root/'graph/nested')),2)

    def test_source_directory_overlap_rejected(self):
        graph_manifest=builder.read(self.root/'graph/manifest.json')
        human=graph_manifest['config']['arguments']['human']
        self.assertEqual(self.run_cli('--out',str(Path(human)/'bad')),2)

    def test_review_file_rejects_pending_and_wrong_scope(self):
        path=self.root/'decisions.jsonl'
        path.write_text(json.dumps({'chapter_id':'missing','kind':'panels','target_id':'p'})+'\n')
        self.assertEqual(self.run_cli('--decisions',str(path)),2)

    def test_loader_rejects_semantic_tamper_even_with_rehashed_output(self):
        self.assertEqual(self.run_cli(),0)
        path=self.out/'chapters/hero__c001.json';wrapper=builder.read(path)
        wrapper['payload']['counts']['verified_panel_pages']=999
        wrapper['payload_sha256']=builder.stable(wrapper['payload']);builder.write(path,wrapper)
        manifest=builder.read(self.out/'manifest.json')
        manifest['outputs_sha256']['chapters/hero__c001.json']=builder.digest(path.read_bytes())
        builder.write(self.out/'manifest.json',manifest)
        with self.assertRaises(ValueError):load_rich(self.root/'graph',self.root/'visibility',self.out,'hero__c001')

    def test_html_escapes_model_text(self):
        g,v,s=fixture();v['alignments'][0]['magi_text']='<script>alert(1)</script>'
        html=builder.review_html(g,m.build(g,v,s))
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)


if __name__=='__main__':unittest.main()
