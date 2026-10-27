"""CKG-1 contracts: trust, coverage, provenance, identity and interrupted builds."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import test_ckg0_review

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src/comics_qa/evidence/graph'))
import build_ckg1 as builder
import ckg_schema as schema
import review_ckg0 as review


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.world = test_ckg0_review.ReviewTest(methodName='test_absent_and_model_coverage_stay_unchanged')
        self.world.setUp()
        self.addCleanup(self.world.doCleanups)
        self.root = self.world.root

    def prepare(self, generic=False, tail_flag=False):
        core, report = self.world.snapshot(generic, tail_flag)
        reviewed = self.root / 'review'
        with contextlib.redirect_stdout(io.StringIO()):
            review.main(['--audit',str(report),'--core',str(core),'--out',str(reviewed)])
        paths = {'core': core, 'audit': report, 'review': reviewed,
                 'images': self.world.world.images, 'human': self.world.world.human,
                 'magi3': self.world.world.magi, 'ocr': self.world.world.ocr, 'out': self.root/'graph'}
        self.argv = sum(([f'--{k}',str(v)] for k,v in paths.items()), [])
        return paths

    def run_build(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return builder.main(self.argv + list(extra))

    def graph(self):
        return review.read_json(self.root/'graph/chapters/hero__c001.json')

    def test_full_context_and_positive_facts_with_absent_page(self):
        self.prepare()
        self.run_build()
        graph = self.graph()
        self.assertEqual(len(graph['page_ids']), 3)
        self.assertEqual({tuple(f['args']) for f in graph['facts'] if f['rel']=='next_page'},
                         {('hero__c001__p000','hero__c001__p001-002'), ('hero__c001__p001-002','hero__c001__p003')})
        self.assertFalse(schema.scope_is_closed(graph, graph['page_ids'], ['char_boxes']))
        self.assertTrue(schema.scope_is_closed(graph, ['hero__c001__p000'], ['char_boxes']))
        self.assertFalse(schema.scope_is_closed(graph, ['unknown'], ['char_boxes']))
        self.assertFalse(schema.scope_is_closed(graph, [], ['char_boxes']))
        self.assertTrue(any(f['rel']=='present' for f in graph['facts']))
        self.assertFalse(any(n['type']=='Appearance' and n['page_id']=='hero__c001__p001-002' for n in graph['nodes']))

    def test_model_trust_and_no_ocr_semantic_promotion(self):
        self.prepare()
        self.run_build()
        graph = self.graph()
        nodes = {n['id']:n for n in graph['nodes']}
        panels = [f for f in graph['facts'] if f['rel']=='on_page' and nodes[f['args'][0]]['type']=='Panel']
        self.assertTrue(panels)
        self.assertTrue(all(f['origin']=='M' and not f['answer_eligible'] for f in panels))
        self.assertFalse(any(f['rel'] in ('mentions','in_panel','left_of','reading_pos') for f in graph['facts']))
        self.assertTrue(all(n['visibility_status']=='not_checked' for n in nodes.values() if n['type']=='Character'))

    def test_line_requires_speaker_despite_same_raw_class(self):
        self.prepare()
        self.run_build()
        graph = self.graph()
        lines = {f['args'][0] for f in graph['facts'] if f['rel']=='is_line'}
        self.assertIn('hero__c001__p000__htext01',lines)
        self.assertNotIn('hero__c001__p000__htext00',lines)
        self.assertTrue(any(f['rel']=='speaks_on' for f in graph['facts']))

    def test_generic_overrides_applied_without_named_alias(self):
        self.prepare(generic=True)
        self.run_build()
        graph = self.graph()
        nodes = {n['id']:n for n in graph['nodes']}
        aid='hero__c001__p000__hchar00'
        corrected='hero__c001__p000__unnamed0'
        self.assertEqual(nodes[aid]['source_identity_id'],'hero__unnamed-woman')
        self.assertEqual(nodes[aid]['identity_id'],corrected)
        self.assertEqual(nodes[corrected]['aliases'],[])
        self.assertNotIn('hero__unnamed-woman',nodes)
        self.assertFalse(any(f['rel'] in ('named','alias') and f['args'][0]==corrected for f in graph['facts']))
        fact=next(f for f in graph['facts'] if f['rel']=='is_char' and f['args'][0]==aid)
        self.assertTrue(any(s['file'].endswith('identity_overrides.jsonl') for s in fact['sources']))

    def test_open_speaker_family_survives_resolved_identity(self):
        self.prepare(generic=True,tail_flag=True)
        self.run_build()
        graph=self.graph()
        self.assertFalse(schema.scope_is_closed(graph,['hero__c001__p000'],['speaker_links']))
        self.assertTrue(any(f['rel']=='present' and f['args'][1]=='hero__c001__p000' for f in graph['facts']))

    def test_determinism_provenance_and_source_immutability(self):
        self.prepare()
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.run_build()
        first=(self.root/'graph/chapters/hero__c001.json').read_bytes()
        self.run_build('--out',str(self.root/'graph2'))
        self.assertEqual(first,(self.root/'graph2/chapters/hero__c001.json').read_bytes())
        self.assertEqual(before,{p:p.read_bytes() for p in before})
        graph=self.graph()
        self.assertTrue(all(f['sources'] and f['coverage_refs'] for f in graph['facts']))
        self.assertTrue(all(s.get('sha256') for f in graph['facts'] for s in f['sources']))
        self.assertTrue(all(f['premises'] for f in graph['facts'] if f['derivation']=='R'))

    def test_source_change_blocks_build(self):
        paths=self.prepare()
        source=sorted(paths['human'].rglob('*.json'))[0]
        source.write_text(source.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'Source changed'):
            self.run_build()

    def test_image_change_blocks_build(self):
        paths=self.prepare()
        sorted(paths['images'].rglob('*.jpg'))[0].write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Image bytes changed'):
            self.run_build()

    def test_extra_image_blocks_build(self):
        paths=self.prepare()
        first=sorted(paths['images'].rglob('*.jpg'))[0]
        first.with_name('extra.jpg').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'Image inventory changed'):
            self.run_build()

    def test_review_tampering_rejected(self):
        paths=self.prepare()
        (paths['review']/'coverage.jsonl').write_text('{}\n')
        with self.assertRaisesRegex(ValueError,'Checksum mismatch'):
            self.run_build()

    def test_semantic_review_change_rejected_even_with_updated_hash(self):
        paths=self.prepare()
        path=paths['review']/'coverage.jsonl'
        rows=review.read_rows(path)
        rows[1]['candidate_coverage']['char_boxes']='closed_assumed'
        builder.audit.write_jsonl(path,rows)
        manifest=review.read_json(paths['review']/'manifest.json')
        manifest['outputs_sha256']['coverage.jsonl']=builder.checksum(path)
        builder.audit.write_json(paths['review']/'manifest.json',manifest)
        with self.assertRaisesRegex(ValueError,'Review decisions differ'):
            self.run_build()

    def test_new_human_source_on_absent_page_requires_new_audit(self):
        paths=self.prepare()
        core=review.read_rows(paths['core']/'pages.jsonl')
        absent=next(p for p in core if not p['has_ground_truth'])
        path=paths['human']/(absent['relative_path']+'.json')
        path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'Previously missing input now exists'):
            self.run_build()

    def test_ambiguous_alias_is_not_emitted(self):
        self.prepare()
        inp=builder.Inputs(builder.parse_args(self.argv))
        for alias in inp.identities['hero__hero-man']['aliases']:
            if alias['text']=='Hero':
                alias['ambiguous']=True
        chapter=inp.chapters['hero__c001']
        _,docs=inp.chapter_sources(chapter)
        graph=builder.ChapterGraph(inp,chapter).build(docs)
        aliases={f['args'][1] for f in graph['facts'] if f['rel']=='alias'}
        self.assertNotIn('Hero',aliases)
        self.assertIn('Hero Man',aliases)

    def test_resume_reuses_completed_shard_after_interruption(self):
        self.prepare()
        original=builder.audit.write_json
        def fail_at_registry(path,value):
            if path.name=='relations.json':
                raise OSError('simulated interruption')
            return original(path,value)
        with patch.object(builder.audit,'write_json',side_effect=fail_at_registry):
            with self.assertRaisesRegex(OSError,'simulated'):
                self.run_build()
        partial=self.root/'graph.partial'
        shard=partial/'chapters/hero__c001.json'
        before=shard.read_bytes()
        with patch.object(builder.ChapterGraph,'build',side_effect=AssertionError('must reuse shard')):
            self.run_build('--resume')
            self.run_build('--resume')
        self.assertEqual(before,(self.root/'graph/chapters/hero__c001.json').read_bytes())
        self.assertFalse(partial.exists())

    def test_resume_rejects_corrupt_completed_shard(self):
        self.prepare()
        self.run_build()
        (self.root/'graph/chapters/hero__c001.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Checksum mismatch'):
            self.run_build('--resume')

    def test_output_safety_and_existing_output(self):
        paths=self.prepare()
        with self.assertRaisesRegex(ValueError,'overlaps'):
            self.run_build('--out',str(paths['human']/'graphs'))
        (self.root/'graph.partial').symlink_to(paths['human'],target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'symlink'):
            self.run_build('--resume')
        (self.root/'graph.partial').unlink()
        self.run_build()
        with self.assertRaisesRegex(ValueError,'exists'):
            self.run_build()

    def test_validation_catches_types_premises_trust_and_missing_coverage(self):
        self.prepare()
        self.run_build()
        graph=self.graph()
        wrong=copy.deepcopy(graph)
        next(f for f in wrong['facts'] if f['rel']=='spoken_by')['args'][1]='hero__c001'
        with self.assertRaisesRegex(ValueError,'type/reference'):
            schema.validate_graph(wrong)
        wrong=copy.deepcopy(graph)
        next(f for f in wrong['facts'] if f['rel']=='present')['premises']=['absent']
        with self.assertRaisesRegex(ValueError,'Missing premise'):
            schema.validate_graph(wrong)
        wrong=copy.deepcopy(graph)
        f=next(f for f in wrong['facts'] if f['origin']=='M')
        f.update(origin='H',answer_eligible=True)
        with self.assertRaisesRegex(ValueError,'promotes node trust'):
            schema.validate_graph(wrong)
        wrong=copy.deepcopy(graph)
        wrong['coverage'].pop()
        with self.assertRaisesRegex(ValueError,'Incomplete page/family'):
            schema.validate_graph(wrong)


if __name__=='__main__':
    unittest.main()
