"""Split selection, retained pools and snapshot-bound alias reviews."""
import copy
import contextlib
import io
import json
import unittest
from unittest.mock import patch
import test_gen2
from test_gen2_quality import item,world
from comics_qa.tasks.graph.gen2.quality import configure,target,usable_name
from comics_qa.tasks.graph.gen2.collection import select
from comics_qa.tasks.graph.gen2.aliases import validate_reviews
from comics_qa.tasks.graph.gen2 import build_v3 as b
from comics_qa.tasks.graph.gen2 import review_aliases


def pool(cid,items,split='seen',frequent=()):
    g=world();g['chapter_id']=cid
    for i in items:
        i['chapter_id']=cid;i['split']=split;i['quality']={**target(i,g),'policy_version':'gen2.3'}
    return {'chapter_id':cid,'split':split,'frequent_ids':list(frequent),'candidates':items}


class SelectionTests(unittest.TestCase):
    def diverse(self):
        return [pool('a',[item(1,value=2),item(10,'char','D',cid='d')]),
                pool('b',[item(2,value=3),item(11,'char','E',cid='e')]),pool('c',[item(3,value=4)])]

    def test_sparse_chapters_balance_at_split_level(self):
        items,rejected,report=select(self.diverse(),configure())
        self.assertEqual(len(items),5);self.assertFalse(rejected)
        self.assertEqual(report['splits']['seen']['after']['chapters'],3)
        self.assertAlmostEqual(report['splits']['seen']['after']['max_count_value_share'],1/3)

    def test_splits_cannot_subsidize_each_other(self):
        pools=self.diverse();pools[-1]['split']='unseen'
        for i in pools[-1]['candidates']:i['split']='unseen'
        items,_,r=select(pools,configure())
        self.assertEqual(len(items),2);self.assertTrue(all(i['answer']['type']=='char' for i in items))
        self.assertEqual(r['splits']['unseen']['after']['items'],0)

    def test_repeated_actual_name_answer_held_out(self):
        items,rejected,r=select([pool('a',[item(1,'char','D'),item(2,'char','D')])],configure())
        self.assertEqual(items,[]);self.assertEqual(set(rejected.values()),{'split_name_identity'})

    def test_legacy_frequent_quota_remains_per_chapter(self):
        p=pool('a',[item(1,'char','A',cid='a'),item(2,'char','D',cid='d'),item(3,'char','E',cid='e')],frequent=['a'])
        items,rejected,_=select([p],configure())
        self.assertEqual(len(items),2);self.assertIn('chapter_frequent_name_quota',rejected.values())

    def test_same_display_name_different_identities_is_checked(self):
        ps=[pool('a',[item(1,'char','Boss',cid='d'),item(2,'char','Boss',cid='e')])]
        items,rejected,_=select(ps,configure())
        self.assertEqual(items,[]);self.assertIn('split_name_form',rejected.values())

    def test_page_offset_shortcut_checked_per_split(self):
        ps=[pool('a',[item(1,'page',offset=1)]),pool('b',[item(2,'page',offset=1)])]
        items,rejected,_=select(ps,configure())
        self.assertEqual(items,[]);self.assertEqual(set(rejected.values()),{'split_page_offset'})

    def test_semantic_dedup_cross_anchor_families(self):
        p=pool('a',[item(1,anchor=0),item(2,anchor=0,family='name_speaker_depictions')])
        config=configure({'quality':{'max_count_share':1,'max_count_value_share':1}})
        items,rejected,_=select([p],config)
        self.assertEqual(len(items),1);self.assertEqual(list(rejected.values()),['duplicate_semantic_target_or_program'])

    def test_trimming_prefers_preserving_sparse_chapter(self):
        ps=[pool('a',[item(1,value=2),item(2,value=2),item(3,value=2),item(4,value=3),item(5,value=4)]),pool('b',[item(6,value=2)])]
        config=configure({'quality':{'max_count_share':1,'max_count_value_share':.5}})
        items,_,_=select(ps,config);self.assertTrue(any(i['chapter_id']=='b' for i in items))

    def test_order_invariance_and_input_immutability(self):
        ps=self.diverse();saved=copy.deepcopy(ps);a=select(ps,configure());z=copy.deepcopy(ps[::-1])
        for p in z:p['candidates'].reverse()
        self.assertEqual(a[0],select(z,configure())[0]);self.assertEqual(ps,saved)


class AliasTests(unittest.TestCase):
    def setUp(self):
        self.g={'chapter_id':'c','nodes':[{'id':'hero','type':'Character','canonical_name':'Hero Man','aliases':['Hero'],'generic':False}]}
        self.v={'visibility':[{'identity_id':'hero','generic':False,'verified_normalized_forms':['hero']}],
                'evidence':[{'evidence_id':'e','identity_id':'hero','status':'verified','form':'Hero'}]}
        self.row={'chapter_id':'c','identity_id':'hero','form':'Hero','graph_sha256':'g','visibility_sha256':'v',
                  'decision':'approved','name_use':'character_name','reviewer':'synthetic fixture reviewer','note':'Synthetic test only','evidence_ids':['e']}

    def test_approved_exact_visible_registered_alias(self):
        reviews=validate_reviews([self.row],self.g,self.v,'g','v')
        self.assertTrue(usable_name(self.g,self.v,'hero','Hero',reviews));self.assertFalse(usable_name(self.g,self.v,'hero','Hero'))
        self.assertFalse(usable_name(self.g,self.v,'hero','Hero Man',reviews))

    def test_pending_never_promoted(self):
        self.row['decision']='pending';self.assertEqual(validate_reviews([self.row],self.g,self.v,'g','v'),[])

    def test_stale_missing_and_wrong_evidence_fail(self):
        for field,value in [('graph_sha256','bad'),('visibility_sha256','bad'),('reviewer',''),('note',''),('evidence_ids',['bad']),('form','Invented'),('name_use','word_fragment')]:
            row={**self.row,field:value}
            with self.subTest(field=field),self.assertRaises(ValueError):validate_reviews([row],self.g,self.v,'g','v')
        with self.assertRaises(ValueError):validate_reviews([self.row,self.row],self.g,self.v,'g','v')


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_gen2.BuildTest('test_completed_resume_and_rich_pins');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root;self.out=self.root/'v3'
    def cli(self,*extra):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return b.main(['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),'--rich',str(self.root/'rich'),
                           '--out',str(self.out),'--max-candidates-per-chapter','12',*extra])
    def test_pool_retention_and_completed_resume(self):
        self.assertEqual(self.cli(),0);self.assertEqual(self.cli('--resume'),0);self.assertEqual(self.cli(),2)
        m=b.verify(self.out);self.assertIn('candidate_pools/hero__c001.json',m['outputs_sha256'])
        p=b.read(self.out/'candidate_pools/hero__c001.json')['payload'];self.assertEqual(len(p['candidates']),p['counts']['gates_passed'])
    def test_reselection_uses_retained_pools(self):
        self.assertEqual(self.cli(),0);cfg=self.root/'changed.json';cfg.write_text(json.dumps({'quality':{'max_count_share':.6}}))
        with patch.object(b,'collect',side_effect=AssertionError('must reuse pools')):
            self.assertEqual(self.cli('--pool-source',str(self.out),'--out',str(self.root/'reselected'),'--config',str(cfg)),0)
    def test_interruption_resume_and_tamper(self):
        original=b.write
        def interrupt(path,payload):
            if path.name=='report.json':raise KeyboardInterrupt
            return original(path,payload)
        with patch.object(b,'write',interrupt):self.assertEqual(self.cli(),130)
        self.assertEqual(self.cli('--resume'),0)
        (self.out/'candidate_pools/hero__c001.json').write_text('{}');self.assertEqual(self.cli('--resume'),2)
    def test_pool_dependency_and_overlap_rejected(self):
        self.assertEqual(self.cli(),0)
        self.assertEqual(self.cli('--pool-source',str(self.out),'--out',str(self.out/'nested')),2)
        self.assertEqual(self.cli('--pool-source',str(self.out),'--out',str(self.root/'changed'),'--seed','3'),2)
    def test_review_template_has_no_automatic_approvals(self):
        out=self.root/'reviews.json'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(review_aliases.main(['--graphs',str(self.root/'graph'),'--visibility',str(self.root/'visibility'),'--out',str(out)]),0)
        rows=b.read(out);self.assertTrue(rows);self.assertTrue(all(r['decision']=='pending' and not r['reviewer'] for r in rows))
