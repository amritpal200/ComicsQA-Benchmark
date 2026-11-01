import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_expanded
from comics_qa.evidence.graph.rich.model import build
from comics_qa.benchmark1000.visual_options import appearances, sheet_bytes
from comics_qa.benchmark1000.visual_choice import produce, check, exact_label, parse_question
from comics_qa.benchmark1000.visual_jobs import chapter_preflight, preflight, pilot, verify_pilot
from comics_qa.benchmark1000.io import stable, digest, publish, read


class VisualPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): test_expanded.ExpandedTests.setUpClass.__func__(cls)

    def setUp(self):
        from PIL import Image
        test_expanded.ExpandedTests.setUp(self)
        test_expanded.ExpandedTests.two_actor_world(self)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)
        hero=next(n for n in self.g['nodes'] if n['type']=='Character' and n.get('canonical_name')=='Hero Man')
        self.target=hero['id']; self.refs=[]
        # Explicit synthetic H identity labels for two otherwise generic test appearances.
        for number,page in enumerate((self.g['page_ids'][5],self.g['page_ids'][6]),1):
            app=next(n for n in self.g['nodes'] if n['type']=='Appearance' and n['page_id']==page and n['generic_name'])
            old=app['identity_id'];cid='hero__synthetic-person-'+str(number)
            node=copy.deepcopy(hero);node.update(id=cid,canonical_name='Synthetic Person '+str(number),aliases=[]);self.g['nodes'].append(node)
            for f in self.g['facts']:
                if f['page_ids']==[page]: f['args']=[cid if a==old else a for a in f['args']]
            app['identity_id']=cid; app['generic_name']=False
        from comics_qa.evidence.graph.ckg_schema import REGISTRY
        for f in self.g['facts']:
            if REGISTRY[f['rel']].get('symmetric'): f['args'][:2]=sorted(f['args'][:2])
        for n in self.g['nodes']:
            if n['type']=='Page':
                p=self.path/(stable(n['id'])+'.png');Image.new('RGB',(n['width'],n['height']),(20+20*n['index_in_chapter'],70,110)).save(p)
                n['image_path']=str(p);n['image_sha256']=digest(p)
        nodes={n['id']:n for n in self.g['nodes']}
        # Keep option crop geometry clear of known text in this synthetic world.
        from PIL import ImageDraw
        for index,n in enumerate(x for x in self.g['nodes'] if x['type']=='Appearance'):
            page=nodes[n['page_id']]
            if n['page_id']!=self.g['page_ids'][0]:
                left=2+25*(index%3);n['box']=[left,page['height']-30,left+20,page['height']-10]
            with Image.open(page['image_path']) as image:
                image=image.convert('RGB');ImageDraw.Draw(image).rectangle(n['box'],fill=((index*41)%250,(index*67)%250,(index*89)%250));image.save(page['image_path'])
            page['image_sha256']=digest(page['image_path'])
        for a in self.v['alignments']:
            if a.get('page_id') in nodes:a['image_sha256']=nodes[a['page_id']]['image_sha256']
        for e in self.v['evidence']:
            if e.get('page_id') in nodes:e['image_sha256']=nodes[e['page_id']]['image_sha256']
        from name_visibility import summarize
        self.v['visibility']=summarize(self.g,self.v['evidence'])
        self.r=build(self.g,self.v,self.r['sources'])
        available,_=appearances(self.g,1)
        self.aids=[next(a for a in aids if nodes[a]['page_id']!=self.g['page_ids'][0]) for cid,aids in sorted(available.items()) if any(nodes[a]['page_id']!=self.g['page_ids'][0] for a in aids)][:4]
        self.assertEqual(len(self.aids),4)

    def item(self): return produce(self.g,self.v,self.r,'please come back now',1,self.aids,self.path/'pilot',1)
    def rehash(self,item):item['item_id']='b1000v:'+stable({k:v for k,v in item.items() if k!='item_id'});return item

    def test_complete_visual_question_and_checker_independence(self):
        before=stable([self.g,self.v,self.r]);item=self.item()
        with patch('comics_qa.benchmark1000.visual_choice.produce',side_effect=AssertionError('producer called')),patch('comics_qa.benchmark1000.visual_choice.Interpreter.execute',side_effect=AssertionError('interpreter called')):
            result=check(self.g,self.v,self.r,item)
        self.assertTrue(result['proof_valid'],result);self.assertFalse(result['release_eligible'])
        self.assertEqual(stable([self.g,self.v,self.r]),before)
        self.assertEqual(len(item['public']['pages']),1)
        self.assertEqual(item['public']['reference_images'][0]['labels'],list('ABCD'))
        self.assertNotIn('identity_id',json.dumps(item['public']))
        self.assertEqual(parse_question(item['public']['question'])[2],item['program'])

    def test_wrong_answer_and_public_identity_leak_rejected_even_rehashed(self):
        item=self.item();bad=copy.deepcopy(item);bad['answer']['value']=next(x for x in 'ABCD' if x!=bad['answer']['value'])
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(bad))['proof_valid'])
        bad=copy.deepcopy(item);bad['public']['gold_identity']=self.target
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(bad))['proof_valid'])

    def test_sheet_pixel_mutation_and_order_rejected(self):
        item=self.item();path=Path(item['option_sheet']['path']);data=sheet_bytes([o['reference'] for o in reversed(item['options'])]);path.write_bytes(data)
        item['option_sheet']['sha256']=digest(path);item['public']['reference_images'][0]['sha256']=digest(path)
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(item))['proof_valid'])

    def test_ablations_and_graph_source_are_bound(self):
        item=self.item();bad=copy.deepcopy(item);bad['controls']['ocr_only']=copy.deepcopy(bad['execution'])
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(bad))['proof_valid'])
        changed=copy.deepcopy(self.g);changed['metadata']['test_change']=True
        self.assertFalse(check(changed,self.v,self.r,item)['proof_valid'])

    def test_unknown_fairness_cannot_self_promote_and_duplicate_options_fail(self):
        item=self.item();bad=copy.deepcopy(item);bad['verification']['human']='verified'
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(bad))['proof_valid'])
        bad=copy.deepcopy(item);bad['options'][1]['reference']=copy.deepcopy(bad['options'][0]['reference'])
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(bad))['proof_valid'])

    def test_inventory_uses_linked_non_generic_identities_and_budget(self):
        report=chapter_preflight(self.g,self.v,self.r,1,1)
        self.assertEqual(report['counts']['considered_quote_anchors'],1)
        self.assertEqual(len(report['available_references']),4)
        self.assertTrue(report['anchor_budget_exhausted'])
        self.assertEqual(report['image_validation'],'metadata/existence only; hashes/pixels verified during pilot')

    def test_label_scoring_is_exact_and_names_are_not_labels(self):
        self.assertTrue(exact_label(' c ','C'));self.assertFalse(exact_label('Hero Man','C'))
        self.assertFalse(exact_label('Option C','C'));self.assertFalse(exact_label(True,'A'))

    def test_jobs_resume_and_model_input_scoring_bindings(self):
        root=self.path/'bench';pre=self.path/'pre';out=self.path/'out'
        for rel in ('evidence/ckg/v1','evidence/name_visibility/v1','evidence/ckg3/v1'):
            publish(root/rel/'manifest.json',{'config':{'chapters':[self.g['chapter_id']]},'outputs_sha256':{}})
        with patch('comics_qa.benchmark1000.visual_jobs.world',return_value=(self.g,self.v,self.r)):
            preflight(root,pre,min_edge=1,quote_budget=20)
            first=pilot(root,pre,out,per_chapter=2,max_attempts=10)
            self.assertGreater(first['items'],0,first)
            result=verify_pilot(root,out);self.assertEqual(result['verified'],first['items']);self.assertEqual(result['rejected'],0)
            with patch('comics_qa.benchmark1000.visual_jobs.produce',side_effect=AssertionError('checkpoint reran')):
                self.assertEqual(pilot(root,pre,out,per_chapter=2,max_attempts=10),first)
            with self.assertRaises(ValueError):pilot(root,pre,out,per_chapter=2,max_attempts=11)
        self.assertTrue((out/'review.html').exists());self.assertTrue((out/'review_requests.json').exists())

    def test_crop_filter_rejects_multi_character_contamination(self):
        original,_=appearances(self.g,1);aid=self.aids[0];node=next(n for n in self.g['nodes'] if n['id']==aid)
        other=copy.deepcopy(node);other['id']=aid+'__overlap';self.g['nodes'].append(other)
        filtered,reasons=appearances(self.g,1)
        self.assertNotIn(aid,{x for aids in filtered.values() for x in aids})
        self.assertGreater(reasons['other_character_overlap'],0)

    def test_graph_option_comparison_is_not_a_free_label_claim(self):
        item=self.item();bad=copy.deepcopy(item);bad['choice_proof'][0]['value']=not bad['choice_proof'][0]['value']
        self.assertFalse(check(self.g,self.v,self.r,self.rehash(bad))['proof_valid'])

    def test_raster_labels_have_the_declared_letter_shapes(self):
        from PIL import Image
        item=self.item();image=Image.open(item['option_sheet']['path']).convert('RGB')
        expected=['01110','10001','10001','11111','10001','10001','10001']
        actual=[''.join('1' if image.getpixel((12+4*c,8+4*r))==(0,0,0) else '0' for c in range(5)) for r in range(7)]
        self.assertEqual(actual,expected)
