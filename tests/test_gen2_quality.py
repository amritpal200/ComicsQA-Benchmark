"""Name eligibility, resolved-target deduplication and simultaneous shortcut caps."""
import copy
import unittest
from comics_qa.tasks.graph.gen2.quality import configure, usable_name, select, target
from test_gen1 import pool_item,frequency_world


def world():
    return {**frequency_world(),'chapter_id':'chapter','page_ids':['p'+str(i) for i in range(200)]}


def item(i,typ='int',value=2,cid='d',anchor=None,offset=1,family=None):
    anchor=i if anchor is None else anchor
    a=pool_item(i,typ,value,identity=cid if typ=='char' else None)
    a['chapter_id']='chapter'
    a['family']=family or {'int':'quote_speaker_depictions','char':'quote_speaker','page':'quote_speaker_next_page'}[typ]
    steps=[{'nid':0,'op':'quote','type':'Text','value':'text'+str(i),'children':[]},
           {'nid':1,'op':'speaker_char','type':'Char','value':cid,'children':[0]},
           {'nid':2,'op':'page','type':'Page','value':'p'+str(anchor),'children':[]}]
    if typ=='int':steps.append({'nid':3,'op':'apps_of','type':'Seq[App]','value':[],'children':[1,2]})
    if typ=='page':
        steps.append({'nid':3,'op':'next_app','type':'App','value':'app','children':[1,2]})
        a['answer']['value']=anchor+1+offset
    a['execution']['proof']['steps']=steps
    return a


class QualityTest(unittest.TestCase):
    def test_fragments_rejected_even_when_visible(self):
        g={'nodes':[{'id':'x','type':'Character','canonical_name':'The student council president','generic':False},
                    {'id':'d','type':'Character','canonical_name':'DEBT COLLECTOR','generic':False}]}
        v={'visibility':[{'identity_id':'x','generic':False,'verified_normalized_forms':['the','the student council president']},
                         {'identity_id':'d','generic':False,'verified_normalized_forms':['debt','debt collector']}]}
        self.assertFalse(usable_name(g,v,'x','The'));self.assertFalse(usable_name(g,v,'d','DEBT'))
        self.assertTrue(usable_name(g,v,'d','debt collector'))
        v['visibility'][1]['verified_normalized_forms']=['debt']
        self.assertFalse(usable_name(g,v,'d','DEBT COLLECTOR'))

    def test_policy_invalid_values_rejected(self):
        for extra in [{'max_count_share':0},{'max_count_share':True},{'max_count_share':float('nan')},
                      {'max_page_offset_share':1.1},{'unexpected':1},{'name_forms':'all_aliases'}]:
            with self.subTest(extra=extra),self.assertRaises(ValueError):configure({'quality':extra})
        self.assertEqual(configure(configure()),configure())

    def test_cross_anchor_family_semantic_duplicate(self):
        p=configure({'quality':{'max_count_share':1,'max_count_value_share':1}})
        pool=[item(1,anchor=0),item(2,anchor=0,family='name_speaker_depictions'),item(3,anchor=1)]
        selected,rejected,r=select(pool,world(),p)
        self.assertEqual(len(selected),2);self.assertEqual(r['quality']['after']['semantic_targets'],2)
        self.assertEqual(rejected[0]['reason'],'duplicate_semantic_target')

    def test_same_answer_different_resolved_targets_not_duplicates(self):
        self.assertNotEqual(target(item(1,anchor=0),world()),target(item(2,anchor=1),world()))
        self.assertNotEqual(target(item(1,cid='c',anchor=0),world()),target(item(2,cid='d',anchor=0),world()))

    def test_single_page_offset_bucket_held_out(self):
        selected,rejected,r=select([item(i,'page',offset=1) for i in range(5)],world(),configure())
        self.assertEqual(selected,[]);self.assertTrue(all(x['reason']=='page_offset_shortcut' for x in rejected))
        self.assertEqual(r['quality']['before']['always_next_page_accuracy'],1)

    def test_balanced_offsets_retained(self):
        selected,_,r=select([item(1,'page',offset=1),item(2,'page',offset=2)],world(),configure())
        self.assertEqual(len(selected),2);self.assertEqual(r['quality']['after']['max_page_offset_share'],.5)

    def test_simultaneous_count_value_and_type_caps(self):
        pool=[item(i,value=2+i%3) for i in range(12)]+[item(i,'char',value='D') for i in range(20,24)]
        selected,rejected,r=select(pool,world(),configure())
        self.assertGreater(r['quality']['after']['count_answers'],0)
        self.assertLessEqual(r['quality']['after']['count_share'],.7)
        self.assertLessEqual(r['quality']['after']['max_count_value_share'],.35)
        self.assertEqual(len(selected)+len(rejected),len(pool));self.assertFalse(r['limits_relaxed'])

    def test_single_count_value_no_silent_relaxation(self):
        selected,_,r=select([item(i) for i in range(4)],world(),configure())
        self.assertEqual(selected,[]);self.assertIsNone(r['quality']['after']['count_share'])

    def test_shuffle_invariant_and_old_name_quota_survives(self):
        pool=[item(i,'char','D') for i in range(7)]+[item(i,'char','A',cid='a') for i in range(10,20)]
        p=configure();a=select(copy.deepcopy(pool),world(),p);b=select(copy.deepcopy(pool[::-1]),world(),p)
        self.assertEqual(a[0],b[0]);self.assertLessEqual(a[2]['selected']['frequent_name_share'],.3)
        self.assertEqual(len(a[0])+len(a[1]),len(pool))

    def test_unrecognized_shape_fails_closed(self):
        a=item(1);a['execution']['proof']['steps']=[]
        with self.assertRaises(ValueError):select([a],world(),configure())
