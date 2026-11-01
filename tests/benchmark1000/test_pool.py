import copy
import json
import tempfile
import unittest
from pathlib import Path
import test_foundation
import test_expanded
from comics_qa.benchmark1000.io import read, publish, digest, stable
from comics_qa.benchmark1000.pool import run, load, make_index, key, inventory, gaps
from comics_qa.benchmark1000.store import load as load_store, ingest


def raw(root, answer=3, bound='world1', question='How many?'):
    test_foundation.fixture(root)
    path = root / 'candidate_pools/c.json'; wrapper = read(path); item = wrapper['payload']['candidates'][0]
    item['question'] = question; item['answer']['value'] = answer
    item['execution']['inputs_sha256'] = {'/relocated/evidence/ckg/v1/chapters/c.json': bound}
    wrapper['payload_sha256'] = stable(wrapper['payload']); path.write_text(json.dumps(wrapper))
    m = read(root / 'manifest.json'); m['schema'] = 'comics_qa.gen2.build.v1'
    m['outputs_sha256']['candidate_pools/c.json'] = digest(path); (root / 'manifest.json').write_text(json.dumps(m))


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root = Path(self.tmp.name)
        self.policy = read(Path(__file__).resolve().parents[2] / 'configs/benchmark1000/v1.json')
        self.a = self.root / 'a'; self.b = self.root / 'b'; raw(self.a); raw(self.b)

    def test_duplicate_legacy_proofs_preserve_variants_status_and_all_sources(self):
        before = {str(p): digest(p) for d in (self.a, self.b) for p in d.rglob('*.json')}
        out = self.root / 'pool'; report = run([self.b, self.a], out, self.policy)
        self.assertEqual(report['counts'], {'occurrences': 2, 'record_variants': 2, 'representatives': 1, 'duplicate_occurrences': 1})
        items = load_store(out); self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['verification']['proof'], 'archived_check')
        self.assertEqual(items[0]['verification']['human'], 'pending')
        self.assertEqual(report['all_candidates']['native_admitted'], 0)
        self.assertEqual(len(read(out / 'index.json')['occurrences']), 2)
        self.assertEqual(report, run([self.a, self.b], out, self.policy))
        self.assertEqual(before, {str(p): digest(p) for d in (self.a, self.b) for p in d.rglob('*.json')})

    def test_same_program_in_different_worlds_stays_separate(self):
        raw_source = self.root / 'different'; raw(raw_source, bound='world2')
        report = run([self.a, raw_source], self.root / 'out', self.policy)
        self.assertEqual(report['counts']['representatives'], 2)

    def test_conflicting_answers_for_same_bound_program_fail(self):
        other = self.root / 'conflict'; raw(other, answer=4)
        with self.assertRaisesRegex(ValueError, 'conflicting answers'): run([self.a, other], self.root / 'out', self.policy)
        self.assertFalse((self.root / 'out/manifest.json').exists())

    def test_policy_change_requires_new_output_and_original_stays_loadable(self):
        out = self.root / 'out'; run([self.a], out, self.policy)
        changed = {**self.policy, 'minimum_chapters': 39}
        with self.assertRaises(ValueError): run([self.a], out, changed)
        self.assertEqual(len(load(out)), 1)

    def test_unknown_schema_proposal_root_and_overlapping_output_fail(self):
        for out in (self.a, self.a / 'sub', self.root):
            with self.assertRaises(ValueError): run([self.a], out, self.policy)
        m = read(self.a / 'manifest.json'); m['schema'] = 'unknown'; (self.a / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError): run([self.a], self.root / 'new', self.policy)

    def test_scope_and_imported_store_without_declared_chapters(self):
        imported = self.root / 'imported'; ingest([self.a], imported)
        r = run([imported], self.root / 'out', self.policy, ['c'])
        self.assertEqual(r['counts']['representatives'], 1)
        with self.assertRaises(ValueError): run([self.a], self.root / 'bad', self.policy, ['missing'])

    def test_index_cannot_select_unbacked_or_unhashed_records(self):
        out = self.root / 'out'; run([self.a], out, self.policy)
        p = out / 'index.json'; idx = read(p); idx['groups'][0]['representative_sha256'] = 'fake'; p.write_text(json.dumps(idx))
        with self.assertRaises(ValueError): load(out)
        # Even a rewritten checksum does not bypass semantic index validation.
        m = read(out / 'manifest.json'); m['outputs_sha256']['index.json'] = digest(p); (out / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaises(ValueError): load(out)

    def test_feasibility_is_necessary_bounds_not_solver_or_release_approval(self):
        report = run([self.a], self.root / 'out', self.policy); f = report['feasibility']
        self.assertEqual(f['total']['shortfall'], 999)
        self.assertEqual(f['primary_groups']['chain']['certified_native']['available'], 0)
        self.assertEqual(f['long_relational']['shortfall'], 200)
        self.assertEqual(f['split_configuration'], 'pending; no split counts invented')
        self.assertIn('no selection solver', f['status'])
        self.assertEqual(report['release_status'], 'not_approved')
        self.assertEqual(f['visual_character']['necessary_minimum_from_identity_floor'], 23)

    def test_split_leakage_is_rejected_even_between_different_worlds(self):
        out = self.root / 'temp'; run([self.a], out, self.policy); item = load(out)[0]
        b = copy.deepcopy(item); b['split'] = b['legacy']['split'] = 'unseen'; b['source']['item_sha256'] = stable(b['legacy'])
        b['item_id'] = 'b1000:' + stable([b['source_item_id'], b['source']['item_sha256']])
        with self.assertRaisesRegex(ValueError, 'chapter split'):
            make_index({stable(item): item, stable(b): b}, [{'record_sha256': stable(i), 'source_index': n} for n, i in enumerate((item,b))])

    def test_native_duplicates_remain_admitted_and_proposals_never_enter_pool(self):
        test_expanded.ExpandedTests.setUpClass(); case = test_expanded.ExpandedTests(); case.setUp()
        from comics_qa.benchmark1000.admission import World, assess
        from comics_qa.benchmark1000.admission_store import admitted
        from comics_qa.benchmark1000.native_store import write
        proposal = case.native(); candidate = admitted(proposal, assess(proposal, World(case.g, case.v, case.r), max_ablation_pages=16))
        a, b = self.root / 'native_a', self.root / 'native_b'
        write([candidate, proposal], a, {'chapters': [case.g['chapter_id']]})
        write([candidate], b, {'chapters': [case.g['chapter_id']]})
        out = self.root / 'out'; r = run([a, b], out, self.policy)
        self.assertEqual(r['counts']['representatives'], 1)
        self.assertEqual(r['counts']['occurrences'], 2)
        self.assertEqual(load(out)[0], candidate)
        self.assertEqual(r['native_admitted_only']['items'], 1)
        self.assertEqual(sum(x['excluded'].get('unadmitted_proposal', 0) for x in r['sources']), 1)
        self.assertEqual(r['all_candidates']['certified_native_hops'], {'3': 1})

    def test_cached_report_cannot_invent_certified_candidates(self):
        out = self.root / 'out'; run([self.a], out, self.policy)
        p = out / 'report.json'; r = read(p); r['all_candidates']['native_admitted'] = 1000; p.write_text(json.dumps(r))
        m = read(out / 'manifest.json'); m['outputs_sha256']['report.json'] = digest(p); (out / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'inventory/feasibility'): load(out)

    def test_source_ledger_cannot_change_parent_manifest(self):
        out = self.root / 'out'; run([self.a], out, self.policy)
        p = out / 'sources/000.json'; r = read(p); r['manifest']['schema'] = 'invented'; p.write_text(json.dumps(r))
        m = read(out / 'manifest.json'); m['outputs_sha256']['sources/000.json'] = digest(p); (out / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'source ledger'): load(out)

    def test_missing_manifest_backed_index_is_rejected(self):
        out = self.root / 'out'; run([self.a], out, self.policy)
        m = read(out / 'manifest.json'); del m['outputs_sha256']['index.json']; (out / 'manifest.json').write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError, 'Missing pool index'): load(out)
