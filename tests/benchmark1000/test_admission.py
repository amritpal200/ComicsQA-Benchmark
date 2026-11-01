import copy
import unittest
from unittest.mock import patch
import test_semantic
from comics_qa.benchmark1000.io import stable
from comics_qa.benchmark1000.semantic import patterns, execute
from comics_qa.benchmark1000.native import make
from comics_qa.benchmark1000.native_wording import parse_question, bound
from comics_qa.benchmark1000.admission import World, assess, deduplicate, name_eligibility, resolved_path
from comics_qa.benchmark1000.admission_store import admitted, validate
from comics_qa.benchmark1000.review import release_eligible


class AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_semantic.SemanticTests.setUpClass.__func__(cls)

    def setUp(self):
        test_semantic.SemanticTests.setUp(self)
        from comics_qa.evidence.graph.rich.model import build
        for c in self.g['coverage']:
            if c['family'] in ('char_boxes', 'names', 'text_boxes', 'speaker_links'):
                c['status'] = 'closed_verified'
        self.r = build(self.g, self.v, self.r['sources'])
        tasks, _ = patterns(self.g, self.r, 4, 1)
        task = next(t for t in tasks if t['pattern'] == 'quote_next_speaks' and t['program']['after'] == 1)
        doc, _, known = execute(task['engine'], task['program'], self.g, self.v, self.r)
        self.assertTrue(known)
        self.item = make(self.g, self.v, self.r, {}, question=task['question'], answer={'type': 'page', 'value': doc['result']['display'], 'identity_id': None},
                         answer_format='page', structure='chain', engine=task['engine'], program=task['program'], execution=doc)
        self.world = World(self.g, self.v, self.r)

    def rehash(self, item):
        item['item_id'] = 'b1000n:' + stable({k: v for k, v in item.items() if k not in ('schema', 'item_id')})
        return item

    def test_positive_admission_preserves_original_and_holds_release(self):
        before = copy.deepcopy(self.item)
        receipt = assess(self.item, self.world)
        self.assertTrue(receipt['passed'], receipt['reasons'])
        self.assertGreaterEqual(len(receipt['checks']['necessary_visual_pages']), 2)
        item = admitted(self.item, receipt)
        self.assertEqual(before, self.item)
        self.assertEqual(item['verification']['human'], 'pending')
        self.assertFalse(release_eligible(item, []))
        self.assertIsNone(item['complexity']['meaningful_hops'])
        self.assertEqual(validate(item), item)

    def test_changed_wording_or_page_cannot_reuse_answer_proof(self):
        item = copy.deepcopy(self.item)
        item['question'] = item['question'].replace('next speak?', 'not speak?')
        self.assertEqual(assess(self.rehash(item), self.world)['reasons'], ['wording_unrecognized'])
        item = copy.deepcopy(self.item)
        item['question'] = item['question'].replace('After page 1,', 'After page 2,')
        self.assertEqual(assess(self.rehash(item), self.world)['reasons'], ['wording_program_mismatch'])

    def test_page_budget_holds_rather_than_assumes_necessity(self):
        row = assess(self.item, self.world, max_ablation_pages=1)
        self.assertFalse(row['passed'])
        self.assertIn('page_ablation_budget_exceeded', row['reasons'])
        self.assertEqual(row['checks']['page_removals'], [])

    def test_ocr_only_keeps_transcripts_but_removes_speaker_links(self):
        g, v, r = self.world.changed(self.g['page_ids'], True)
        self.assertEqual(v['alignments'], self.v['alignments'])
        self.assertTrue(any(f['rel'] == 'transcript' for f in r['facts']))
        self.assertFalse(any(f['rel'] in ('present', 'spoken_by', 'speaks_on') for f in g['facts']))
        row = assess(self.item, self.world)
        self.assertNotEqual(row['checks']['text_only']['result']['status'], 'OK')

    def test_visibility_alone_does_not_approve_alias(self):
        from comics_qa.tasks.graph.gen2.quality import normalized, form_is_visible
        aliases = [(n['id'], f) for n in self.g['nodes'] if n['type'] == 'Character' and not n['generic'] for f in n['aliases']
                   if normalized(f) != normalized(n['canonical_name']) and form_is_visible(self.v, n['id'], f)]
        self.assertTrue(aliases)
        cid, form = aliases[0]
        self.assertEqual(name_eligibility(self.g, self.v, cid, form), 'name_alias_unapproved')
        self.assertIsNone(name_eligibility(self.g, self.v, cid, form, [{'identity_id': cid, 'form': form}]))

    def test_dedup_never_uses_held_proposal_as_representative(self):
        row = assess(self.item, self.world)
        other = copy.deepcopy(self.item); other['complexity']['pattern_depth'] = 999
        self.rehash(other)
        receipts = {self.item['item_id']: row, other['item_id']: {**row, 'passed': False, 'reasons': ['name_alias_unapproved']}}
        ds = deduplicate([other, self.item], receipts)
        self.assertEqual(ds[self.item['item_id']]['status'], 'admitted')
        self.assertEqual(ds[other['item_id']]['status'], 'held')
        receipts[other['item_id']] = {**row, 'proposal_id': other['item_id'], 'proposal_sha256': stable(other)}
        ds = deduplicate([other, self.item], receipts)
        self.assertEqual(sorted(d['status'] for d in ds.values()), ['admitted', 'duplicate'])

    def test_resolved_paths_merge_quote_variants_but_keep_distinct_conditions(self):
        parsed = parse_question(self.item['question'])
        other = copy.deepcopy(parsed); other['program']['characters'][0] = {'call': 'ignored_test_anchor'}
        with patch.object(self.world, 'run', return_value={'answer_supported': True, 'result': {'status': 'OK', 'value': 'same_character'}}):
            self.assertEqual(resolved_path(self.item, parsed, self.world), resolved_path(self.item, other, self.world))
        a = {'kind': 'three_page_clue', 'program': {}, 'clue_keys': [['present', 1], ['present', 3], ['speaks_on', 9]]}
        b = {**a, 'clue_keys': [['present', 2], ['present', 3], ['speaks_on', 9]]}
        self.assertNotEqual(resolved_path(self.item, a, self.world), resolved_path(self.item, b, self.world))

    def test_receipt_tampering_and_automatic_human_approval_rejected(self):
        row = assess(self.item, self.world); item = admitted(self.item, row)
        item['verification']['human'] = 'verified'
        item['item_id'] = 'b1000a:' + stable({k: v for k, v in item.items() if k not in ('schema', 'item_id')})
        with self.assertRaises(ValueError): validate(item)
        item = admitted(self.item, row); item['admission_receipt']['proposal_sha256'] = 'wrong'
        item['item_id'] = 'b1000a:' + stable({k: v for k, v in item.items() if k not in ('schema', 'item_id')})
        with self.assertRaises(ValueError): validate(item)

    def test_clue_grammar_rejects_negation_and_preserves_conjunction(self):
        from comics_qa.benchmark1000.native_wording import INTRO, TAIL
        text = INTRO + '(1) On page 1, this character is drawn in at least one character depiction. (2) At least one dialogue text region on page 7 has this character as its speaker. (3) On page 9, this character is drawn in at least one character depiction.' + TAIL
        parsed = parse_question(text)
        self.assertEqual(len(parsed['relaxations']), 3)
        self.assertEqual(parsed['clue_keys'], [['present', 1], ['speaks_on', 7], ['present', 9]])
        self.assertTrue(bound(parsed, {'proof_engine': 'crl', 'program': parsed['program']}))
        with self.assertRaises(ValueError): parse_question(text.replace('is drawn', 'is not drawn', 1))

    def test_joint_necessity_is_recomputed_despite_claimed_saved_success(self):
        import json
        q = json.dumps('please come back now')
        question = f'Identify the speakers of {q} on page 1 and {q} on page 1. After page 1, on which page are both characters next drawn?'
        parsed = parse_question(question)
        doc, _, known = execute('scan', parsed['program'], self.g, self.v, self.r)
        self.assertTrue(known)
        item = make(self.g, self.v, self.r, {}, question=question, answer={'type': 'page', 'value': doc['result']['display'], 'identity_id': None},
                    answer_format='page', structure='branch_combine', engine='scan', program=parsed['program'], execution=doc,
                    complexity={'clause_necessity': [True, True], 'branch_count': 99, 'necessary_pages': self.g['page_ids']})
        row = assess(item, self.world)
        self.assertIn('redundant_clause', row['reasons'])
        self.assertEqual([c['necessary'] for c in row['checks']['clause_removals']], [False, False])

    def test_counterfactual_proof_tampering_is_rejected_even_after_rehash(self):
        row = assess(self.item, self.world); item = admitted(self.item, row)
        item['admission_receipt']['checks']['text_only']['execution']['result']['status'] = 'OK'
        item['item_id'] = 'b1000a:' + stable({k: v for k, v in item.items() if k not in ('schema', 'item_id')})
        with self.assertRaises(ValueError): validate(item)

    def test_store_resumes_without_rerunning_gates_and_detects_tampering(self):
        import tempfile
        from pathlib import Path
        from comics_qa.benchmark1000.io import publish, digest
        from comics_qa.benchmark1000.native_store import write
        from comics_qa.benchmark1000.admission_store import run
        from comics_qa.benchmark1000.store import load
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'semantic'; bench = root / 'bench'; out = root / 'admitted'
            config = {'chapters': [self.g['chapter_id']]}
            write([self.item], source / 'native_store', {'test': 1})
            publish(source / 'config.json', config)
            publish(source / 'manifest.json', {'schema': 'comics_qa.benchmark1000.semantic_artifacts.1', 'config': config, 'config_sha256': stable(config),
                    'outputs_sha256': {'native_store/manifest.json': digest(source / 'native_store/manifest.json')}})
            for rel, obj in [('evidence/ckg/v1', self.g), ('evidence/name_visibility/v1', self.v)]:
                publish(bench / rel / 'chapters' / (self.g['chapter_id'] + '.json'), obj)
            with patch('comics_qa.benchmark1000.admission_store.load_world', return_value=(self.g, self.v, {})), patch('comics_qa.benchmark1000.admission_store.load_optional', return_value=self.r):
                first = run(source, bench, out)
                self.assertEqual(first['counts'], {'proposals': 1, 'admitted': 1, 'held': 0, 'duplicate': 0})
                self.assertEqual(len(load(out)), 1)
                with patch('comics_qa.benchmark1000.admission_store.assess', side_effect=AssertionError('Gates reran')):
                    self.assertEqual(run(source, bench, out), first)
                with self.assertRaises(ValueError): run(source, bench, out, max_ablation_pages=1)
            path = next((out / 'checks').glob('*.json')); path.write_text('{}')
            with self.assertRaises(ValueError): load(out)

    def test_relay_identity_switch_is_not_certified_by_intermediate_ambiguity(self):
        # Exercise the native relay-profile gate without inventing an annotated scene.
        from comics_qa.benchmark1000 import admission
        item = copy.deepcopy(self.item)
        item['proof_engine'] = 'relay'
        item['execution'] = {'result': self.item['execution']['result'], 'stages': [{'execution': {'result': {'display': 2, 'value': self.g['page_ids'][1]}}}]}
        item['evidence']['fact_ids'] = []
        parsed = {'kind': 'speaker_relay', 'engine': 'relay', 'program': {'quote': 'please come back now', 'page': 1}, 'relaxations': [], 'min_pages': 0}
        same = {'result': self.item['execution']['result'], 'proof_valid': True, 'answer_supported': True}
        def run(engine, program, world=None):
            if world is not None:
                return {'result': {'status': 'UNKNOWN', 'value': None}, 'proof_valid': True, 'answer_supported': False}
            return same
        with patch.object(admission, 'check_answer', return_value={'answer_supported': True}), patch.object(admission, 'parse_question', return_value=parsed), patch.object(admission, 'bound', return_value=True), patch.object(admission, 'support', return_value={'pages': []}), patch.object(admission, 'resolved_path', return_value=['fixture']), patch.object(self.world, 'run', side_effect=run):
            row = assess(item, self.world)
        self.assertIn('relay_identity_switch_redundant', row['reasons'])

    def test_preflight_does_not_treat_unknown_legacy_frequency_as_nonfrequent(self):
        from comics_qa.benchmark1000.preflight import pool_report
        from comics_qa.tasks.graph.crl import Interpreter
        from comics_qa.tasks.graph.crl.language import call
        doc = Interpreter(self.g, self.v, rich=self.r).execute(call('char', 'Hero Man'))
        item = make(self.g, self.v, self.r, {}, question='Identify the character.',
                    answer={'type': 'char', 'value': doc['result']['display'], 'identity_id': doc['result']['value']},
                    answer_format='character', structure='direct', engine='crl', program=doc['program'], execution=doc)
        report = pool_report([item])
        self.assertEqual(report['nonfrequent_identities'], {})
        self.assertEqual(report['legacy_frequency_unknown'], {item['split']: 1})
