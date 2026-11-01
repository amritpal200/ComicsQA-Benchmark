"""OCR alignment and lexical visibility: conservative verification and pinned builds."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_ckg1
from test_core import build_core
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/comics_qa/evidence/graph'))
import build_ckg2 as builder
import name_visibility as vis


def catalog(form='Hero Man',identity='hero',allowed=True):
    return [{'identity_id':identity,'form':form,'normalized_form':vis.normalized(form),
             'canonical':True,'ambiguous':not allowed,'in_chapter':True,'allowed':allowed}]


def observation(left='HERO MAN!',right='Hero Man.'):
    return {'page_id':'p','image_sha256':'a'*64,'text_id':'t','region_id':'r','alignment_id':'a',
            'paddle_text':left,'magi_text':right,'paddle_ok':True,'magi_ok':True,'status':'aligned',
            'full_transcript_agreement':vis.tokens(left)==vis.tokens(right),
            'paddle_box':[0,0,20,20],'magi_box':[0,0,20,20]}


class MatchingTest(unittest.TestCase):
    def evidence(self,left='HERO MAN!',right='Hero Man.',cat=None,**changes):
        obs=observation(left,right);obs.update(changes)
        return vis.name_evidence('c',obs,cat or catalog(),[{'file':'source','sha256':'a'*64,'pointer':'/ocr'}],vis.DEFAULT_POLICY)

    def test_normalization_and_whole_token_boundaries(self):
        self.assertEqual(vis.tokens('ＨＥＲＯ\nMan!'),['hero','man'])
        self.assertEqual(vis.normalized('O’Neil'),vis.normalized("O'Neil"))
        self.assertEqual(vis.find_matches('superhero manpower',catalog()),[])
        self.assertEqual(vis.find_matches('Man Hero',catalog()),[])

    def test_geometric_alignment_uses_boxes_not_array_position(self):
        a=[0,0,20,20];b=[100,0,120,20]
        rows=vis.align_boxes([a,b],[b,a],vis.DEFAULT_POLICY)
        self.assertEqual([r['magi_index'] for r in rows],[1,0])
        self.assertTrue(all(r['status']=='aligned' for r in rows))

    def test_split_merge_and_duplicate_boxes_are_ambiguous(self):
        for left,right in [([[0,0,100,100]],[[0,0,50,100],[50,0,100,100]]),
                           ([[0,0,50,100],[50,0,100,100]],[[0,0,100,100]]),
                           ([[0,0,100,100]],[[0,0,100,100],[0,0,100,100]])]:
            self.assertTrue(all(r['status']=='ambiguous' and r['magi_index'] is None for r in vis.align_boxes(left,right,vis.DEFAULT_POLICY)))

    def test_no_overlap_invalid_and_low_overlap_are_not_aligned(self):
        states=[vis.align_boxes([a],[b],vis.DEFAULT_POLICY)[0]['status'] for a,b in
                [([0,0,10,10],[20,20,30,30]),([0,0,0,10],[0,0,10,10]),([0,0,10,10],[5,5,15,15])]]
        self.assertEqual(states,['no_overlap','invalid_box','low_overlap'])

    def test_exact_name_span_can_agree_when_other_words_differ(self):
        e=self.evidence('Hero Man has arrived','Hero Man as arrived')[0]
        self.assertEqual(e['status'],'verified')
        self.assertFalse(e['full_transcript_agreement'])
        self.assertEqual(e['agreement_scope'],'name_span_only')

    def test_short_ambiguous_disagreeing_and_truncated_stay_candidates(self):
        cases=[self.evidence('L','L',catalog('L')),
               self.evidence(cat=catalog(allowed=False)),
               self.evidence(right='Hero Nan'),
               self.evidence(paddle_ok=False),self.evidence(magi_ok=False),self.evidence(status='ambiguous')]
        self.assertTrue(all(rows[0]['status']=='candidate' for rows in cases))

    def test_other_identity_long_name_shadows_short_name(self):
        cat=catalog('Light','light')+catalog('Light Turner','turner')
        rows=self.evidence('Light Turner','Light Turner',cat)
        self.assertEqual(next(e for e in rows if e['identity_id']=='turner')['status'],'verified')
        e=next(e for e in rows if e['identity_id']=='light')
        self.assertEqual(e['status'],'candidate')
        self.assertIn('inside_other_identity_name',e['reasons'])

    def test_alias_visibility_does_not_promote_full_canonical(self):
        cat=catalog('Hero');cat[0]['canonical']=False
        rows=self.evidence('Hero','Hero',cat)
        graph={'chapter_id':'c','nodes':[{'id':'hero','type':'Character','generic':False,'canonical_name':'Hero Man'}]}
        chapter={'visibility':vis.summarize(graph,rows)}
        self.assertTrue(vis.form_is_visible(chapter,'hero','HERO'))
        self.assertFalse(vis.form_is_visible(chapter,'hero','Hero Man'))
        self.assertFalse(chapter['visibility'][0]['canonical_visible'])

    def test_explicit_visual_review_and_rejection(self):
        rows=self.evidence('L','L',catalog('L'))
        e=rows[0]
        decision={'evidence_id':e['evidence_id'],'chapter_id':'c','image_sha256':'a'*64,
                  'status':'verified','reviewer':'reviewer','note':'Checked original image','transcription':'I am L'}
        vis.apply_decisions(rows,[decision],{'file':'decisions'})
        self.assertEqual(e['status'],'verified');self.assertEqual(e['verification_method'],'individual_visual_review')
        rows=self.evidence();decision.update(evidence_id=rows[0]['evidence_id'],status='rejected')
        vis.apply_decisions(rows,[decision],{'file':'decisions'})
        self.assertEqual(rows[0]['status'],'rejected')

    def test_stale_or_ambiguous_visual_decision_rejected(self):
        rows=self.evidence(cat=catalog(allowed=False));e=rows[0]
        d={'evidence_id':e['evidence_id'],'chapter_id':'c','image_sha256':'a'*64,
           'status':'verified','reviewer':'r','note':'review','transcription':'Hero Man'}
        with self.assertRaisesRegex(ValueError,'ambiguous'):vis.apply_decisions(copy.deepcopy(rows),[d],{})
        d['image_sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'hash'):vis.apply_decisions(copy.deepcopy(rows),[d],{})
        d['evidence_id']='stale'
        with self.assertRaisesRegex(ValueError,'stale'):vis.apply_decisions(copy.deepcopy(rows),[d],{})

    def test_normalized_alias_collision_across_series_identities(self):
        g={'nodes':[{'id':'c','type':'Chapter','series':'S'},
                    {'id':'a','type':'Character','generic':False,'canonical_name':'A-B','aliases':[]}]}
        ids={k:{'identity_id':k,'series':'S','kind':'named','name':name,'aliases':[]} for k,name in [('a','A-B'),('b','A B')]}
        row=next(r for r in vis.alias_catalog(g,ids) if r['identity_id']=='a')
        self.assertFalse(row['allowed'])

    def test_ocr_quality_flags_come_from_actual_source_metadata(self):
        box=[0,0,10,10]
        page={'id':'p','annotated':True,'image_sha256':'a'*64}
        text={'id':'t','box':box}
        paddle={'ocr':{'boxes_source':'human','_meta':{'status':'complete'},
                      'texts':[{'index':0,'box':box,'text':'Hero Man','status':'ok','truncated':True}]}}
        magi={'magi3':{'_meta':{'status':'complete'},'generation':{'ocr':{'possibly_truncated':True}},
                      'ocr':{'bboxes':[box],'ocr_texts':['Hero Man']}}}
        rows=vis.page_observations(page,[text],paddle,magi,vis.DEFAULT_POLICY)
        self.assertFalse(rows[0]['paddle_ok']);self.assertFalse(rows[0]['magi_ok'])
        paddle['ocr']['texts'][0]['truncated']=False;magi['magi3']['generation']['ocr']['possibly_truncated']=False
        rows=vis.page_observations(page,[text],paddle,magi,vis.DEFAULT_POLICY)
        self.assertTrue(rows[0]['paddle_ok']);self.assertTrue(rows[0]['magi_ok'])

    def test_malformed_magi_arrays_fail_instead_of_truncating_zip(self):
        page={'id':'p','annotated':False,'image_sha256':'a'*64}
        magi={'magi3':{'ocr':{'bboxes':[[0,0,10,10]],'ocr_texts':[]}}}
        with self.assertRaisesRegex(ValueError,'Malformed MAGI OCR'):
            vis.page_observations(page,[],None,magi,vis.DEFAULT_POLICY)


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.fixture=test_ckg1.GraphTest(methodName='test_full_context_and_positive_facts_with_absent_page')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        world=self.fixture.world.world
        for image in sorted(world.images.rglob('*.jpg')):
            rel=image.relative_to(world.images).as_posix();hp=world.human/(rel+'.json')
            mp=world.magi/(rel+'.json');op=world.ocr/(rel+'.json')
            magi=json.loads(mp.read_text());paddle=json.loads(op.read_text())
            boxes=[e['box'] for e in paddle['ocr']['texts']]
            values=['HELLO HERO MAN' if i==0 else 'Hello' for i in range(len(boxes))]
            magi['magi3']['ocr']={'bboxes':boxes,'ocr_texts':values}
            magi['magi3']['generation']={'ocr':{'possibly_truncated':False}}
            mp.write_text(json.dumps(magi))
            for e,value in zip(paddle['ocr']['texts'],values):e.update(text=value,text_normalized=value)
            op.write_text(json.dumps(paddle))
        (self.root/'core').rename(self.root/'original_core')
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            build_core.main(['--images',str(world.images),'--human',str(world.human),'--magi3',str(world.magi),'--out',str(self.root/'core')])
            paths=self.fixture.prepare();self.fixture.run_build()
        self.argv=sum(([f'--{k}',str(v)] for k,v in {**paths,'graphs':self.root/'graph','out':self.root/'visibility'}.items()),[])

    def run_build(self,*extra):
        with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
            return builder.main(self.argv+list(extra))

    def output(self):return json.loads((self.root/'visibility/chapters/hero__c001.json').read_text())

    def test_build_provenance_no_gt_visibility_and_input_immutability(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.run_build(),0)
        out=self.output()
        self.assertTrue(vis.form_is_visible(out,'hero__hero-man','Hero Man'))
        self.assertTrue(any(e['status']=='verified' and e['text_id'] is None for e in out['evidence']))
        self.assertTrue(all(e['sources'] and e['identity_source']['sha256'] for e in out['evidence']))
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        self.assertTrue(any(v['status']=='generic_excluded' for v in out['visibility']))

    def test_deterministic_outputs_and_completed_resume(self):
        self.run_build();first=(self.root/'visibility/chapters/hero__c001.json').read_bytes()
        self.run_build('--out',str(self.root/'visibility2'))
        self.assertEqual(first,(self.root/'visibility2/chapters/hero__c001.json').read_bytes())
        with patch.object(builder,'build_chapter',side_effect=AssertionError('must reuse')):self.run_build('--resume')

    def test_interrupted_build_reuses_checkpoint(self):
        write=builder.audit.write_json
        def fail(path,value):
            if path.name=='report.json':raise OSError('interrupted')
            return write(path,value)
        with patch.object(builder.audit,'write_json',side_effect=fail):
            with self.assertRaisesRegex(OSError,'interrupted'):self.run_build()
        with patch.object(builder,'build_chapter',side_effect=AssertionError('must reuse')):self.run_build('--resume')

    def test_source_mutation_and_graph_corruption_block_build(self):
        path=next((self.root/'ocr').rglob('*.json'));raw=path.read_bytes();path.write_bytes(raw+b'\n')
        with self.assertRaisesRegex(ValueError,'Source changed'):self.run_build()
        path.write_bytes(raw)
        graph=self.root/'graph/chapters/hero__c001.json';graph.write_text('{}')
        with self.assertRaisesRegex(ValueError,'chapter checksum'):self.run_build('--resume')

    def test_output_safety_and_changed_threshold_resume(self):
        with self.assertRaisesRegex(ValueError,'overlaps'):self.run_build('--out',str(self.root/'graph/visibility'))
        self.run_build()
        with self.assertRaisesRegex(ValueError,'configuration/dependencies changed'):self.run_build('--resume','--min-iou','0.75')

    def test_recorded_rejections_remove_exact_form_eligibility(self):
        self.run_build();out=self.output()
        decisions=[{'evidence_id':e['evidence_id'],'chapter_id':e['chapter_id'],'image_sha256':e['image_sha256'],
                    'status':'rejected','reviewer':'test reviewer','note':'Synthetic rejection'}
                   for e in out['evidence'] if e['form']=='Hero Man']
        path=self.root/'decisions.jsonl';path.write_text(''.join(json.dumps(d)+'\n' for d in decisions))
        self.run_build('--decisions',str(path),'--out',str(self.root/'reviewed_visibility'))
        result=json.loads((self.root/'reviewed_visibility/chapters/hero__c001.json').read_text())
        self.assertFalse(vis.form_is_visible(result,'hero__hero-man','Hero Man'))
        self.assertTrue(vis.form_is_visible(result,'hero__hero-man','Hero'))
        self.assertTrue(all(e['review']['source']['sha256'] for e in result['evidence'] if e['status']=='rejected'))


if __name__=='__main__':unittest.main()
