"""Immutable mixed inventory: deduplication never promotes proof/review status."""
import fcntl
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from fractions import Fraction
from math import ceil
from .io import read, publish, stable, digest, member, separate, verify_manifest, verify_snapshot
from .contract import validate
from .adapters import records as legacy_records
from .store import load as load_store
from .selection import policy, metrics, violations

SCHEMA = 'comics_qa.benchmark1000.pool.1'
LEGACY = 'comics_qa.benchmark1000.candidate.1'
ADMITTED = 'comics_qa.benchmark1000.admitted_native.1'
PAIRED = 'comics_qa.benchmark1000.contrast_member.1'
RAW = {'comics_qa.gen1.build.v1', 'comics_qa.gen2.build.v1'}
STORES = {'comics_qa.benchmark1000.store.1', 'comics_qa.benchmark1000.native_store.1',
          'comics_qa.benchmark1000.admission_store.1', 'comics_qa.benchmark1000.contrast_store.1'}


def key(item):
    if item['schema'] == PAIRED:
        return ['contrast_member', item['pair_id'], item['pair_role'], item['source']['snapshots'], item['features']['semantic_target']]
    if item['schema'] == ADMITTED:
        return ['native_path', item['chapter_id'], item['source']['snapshots'],
                item['admission_receipt']['resolved_path_sha256']]
    original = item['legacy']; execution = original['execution']
    pins = execution.get('inputs_sha256')
    if not pins:
        # No proof-world binding: identical raw records can still be collapsed.
        return ['legacy_identical_record', item['chapter_id'], stable(original)]
    roles = sorted([str(p).split('/evidence/', 1)[-1], h] for p, h in pins.items())
    return ['legacy_program', item['chapter_id'], roles, execution.get('rich_evidence_sha256'), original['program']]


def certified(item):
    cert = item.get('complexity', {}).get('certificate', {})
    return item['schema'] in (ADMITTED, PAIRED) and cert.get('certified') is True


def make_index(records, occurrences):
    groups = defaultdict(list); splits = {}; ids = {}
    for sha, item in sorted(records.items()):
        validate(item)
        if item['schema'] not in (LEGACY, ADMITTED, PAIRED) or item.get('admission') == 'proposal':
            raise ValueError('Pool accepts only archived legacy candidates or admitted native candidates')
        if item['schema'] == LEGACY:
            check = item['legacy'].get('proof_check', {})
            if check.get('proof_valid') is not True or check.get('accepted_for_generation') is not True:
                raise ValueError('Legacy pool record lacks accepted saved proof check')
        if stable(item) != sha: raise ValueError('Pool record content mismatch')
        cid = item['chapter_id']
        if cid in splits and splits[cid] != item['split']: raise ValueError('Conflicting chapter split')
        splits[cid] = item['split']; k = stable(key(item))
        if item['item_id'] in ids and ids[item['item_id']] != k: raise ValueError('Candidate ID has conflicting proof worlds')
        ids[item['item_id']] = k; groups[k].append(sha)
    from .contrast import units
    units(list(records.values()))
    result = []
    for k, members in sorted(groups.items()):
        answers = {stable([records[s]['answer_format'], records[s]['answer']['value'], records[s]['answer'].get('identity_id')]) for s in members}
        if len(answers) != 1: raise ValueError('Duplicate proof path/program has conflicting answers')
        chosen = min(members, key=lambda s: (not certified(records[s]), records[s]['schema'] != ADMITTED, s))
        result.append({'pool_id': 'pool:' + k, 'representative_sha256': chosen, 'record_sha256s': sorted(members),
                       'deduplication_kind': key(records[chosen])[0]})
    if any(o['record_sha256'] not in records or type(o['source_index']) is not int or o['source_index'] < 0 for o in occurrences):
        raise ValueError('Invalid occurrence binding')
    if set(records) != {o['record_sha256'] for o in occurrences}: raise ValueError('Unreferenced pool record')
    return {'schema': 'comics_qa.benchmark1000.pool_index.1', 'groups': result,
            'occurrences': sorted(occurrences, key=lambda o: (o['source_index'], o['record_sha256'])),
            'deduplication': 'Within pinned proof worlds only; no cross-schema or paraphrase semantic-equivalence claim'}


def inventory(items):
    native = [i for i in items if i['schema'] in (ADMITTED, PAIRED)]
    measured = [i for i in native if certified(i)]
    def count(field): return dict(Counter(str(i.get(field, 'unknown')) for i in items))
    return {'items': len(items), 'native_admitted': len(native), 'archived_legacy': len(items) - len(native),
            'splits': count('split'), 'chapters': len({i['chapter_id'] for i in items}),
            'chapter_items': dict(Counter(i['chapter_id'] for i in items)), 'answer_formats': count('answer_format'),
            'families': dict(Counter(i['admission_receipt']['kind'] if i['schema'] in (ADMITTED, PAIRED) else i['legacy'].get('family', 'legacy_unspecified') for i in items)),
            'generation_modes': count('generation_mode'), 'evidence_classes': count('evidence_class'),
            'split_groups': {s: dict(Counter(i['primary_group'] for i in items if i['split'] == s)) for s in ('seen', 'unseen')},
            'feature_unknowns': {'top1_identity': sum(type(i['features'].get('is_top1_identity')) is not bool for i in items if i['features'].get('identity_id')),
                                 'top2_identity': sum(type(i['features'].get('is_top2_identity')) is not bool for i in items if i['features'].get('identity_id')),
                                 'page_offset': sum(i['features'].get('page_offset') is None for i in items if i['answer_format'] == 'page')},
            'declared_groups': count('primary_group'), 'certified_native_groups': dict(Counter(i['primary_group'] for i in measured)),
            'certified_native_hops': dict(Counter(str(i['complexity'].get('meaningful_hops')) for i in measured)),
            'uncertified_hop_items': sum(i['complexity'].get('meaningful_hops') is None for i in items),
            'proof_status': dict(Counter(i['verification'].get('proof', 'unknown') for i in items)),
            'wording_status': dict(Counter(i['verification'].get('wording', 'unknown') for i in items)),
            'human_status': dict(Counter(i['verification'].get('human', 'unknown') for i in items)),
            'release_status_counts': dict(Counter(i['verification'].get('release', 'unknown') for i in items)),
            'visual_page_support': {'native_measured': dict(Counter(str(len(i['admission_receipt']['checks']['necessary_visual_pages'])) for i in native)),
                                    'legacy': 'archived dimensions only; not new native admission'},
            'target_identities': len({i['features']['identity_id'] for i in items if i['features'].get('identity_id')}),
            'sentence_items': sum(i['answer_format'] == 'sentence' for i in items),
            'certified_long_relational': sum('long_relational' in i.get('reasoning_tags', []) and i.get('long_relational_certificate', {}).get('eligible') is True
                and i['long_relational_certificate'].get('necessary_clauses', 0) >= 3 and len(set(i['long_relational_certificate'].get('necessary_pages', []))) >= 3
                and i['long_relational_certificate'].get('page_span', 0) >= 5 for i in items),
            'unselected_pool_metrics': metrics(items)}


def gaps(items, raw_policy):
    p = policy(raw_policy); observed = inventory(items)
    def bound(required, available):
        return {'required': required, 'available': available, 'shortfall': max(0, required - available)}
    cap = p['maximum_per_chapter']; chapter_capacity = sum(min(n, cap) for n in observed['chapter_items'].values())
    splits = {}
    if p['split_counts'] is not None:
        for split, required in p['split_counts'].items():
            subset = [i for i in items if i['split'] == split]
            capacity = sum(min(n, cap) for n in Counter(i['chapter_id'] for i in subset).values())
            splits[split] = {**bound(required, len(subset)), 'chapter_capped_capacity': capacity,
                            'chapter_capped_shortfall': max(0, required - capacity)}
    chars = [i for i in items if i['features'].get('identity_id')]
    visual = sum(i['answer_format'] == 'visual_choice' for i in chars)
    visual_minimum = ceil(Fraction(str(p['minimum_visual_character_share'])) * p['minimum_identities'])
    return {'status': 'not_established; necessary inventory bounds only; no selection solver run',
            'total': bound(p['target_items'], len(items)), 'chapter_capped_total': bound(p['target_items'], chapter_capacity),
            'chapters': bound(p['minimum_chapters'], observed['chapters']), 'target_identities': bound(p['minimum_identities'], observed['target_identities']),
            'long_relational': bound(p['minimum_long_relational'], observed['certified_long_relational']),
            'visual_character': {'opportunities': len(chars), 'visual_choice_items': visual, 'observed_share': visual / len(chars) if chars else None,
                'minimum_share': p['minimum_visual_character_share'], 'necessary_minimum_from_identity_floor': visual_minimum,
                'shortfall_against_identity_floor': max(0, visual_minimum - visual), 'definition': 'At least minimum_identities identity-target items are needed; joint final opportunity count remains unknown'},
            'primary_groups': {g: {'declared': bound(n, observed['declared_groups'].get(g, 0)),
                                   'certified_native': bound(n, observed['certified_native_groups'].get(g, 0))} for g, n in p['primary_groups'].items()},
            'splits': splits, 'split_configuration': 'configured' if p['split_counts'] is not None else 'pending; no split counts invented',
            'unselected_pool_violations': violations(items, p, final=False),
            'limitations': ['Whole-pool ratios are not selection infeasibility proofs', 'Group availability is distinct from verified eligibility',
                            'Pair closure, baseline ratios, assets and joint group/split constraints need actual selection',
                            'No archived item is revalidated or reviewed by this inventory', 'No current-external-source freshness or full semantic equivalence claimed'],
            'release': 'not_approved; no review decisions or release-view integration applied'}


def run(sources, out, raw_policy, chapters=None):
    sources = [Path(p).resolve() for p in sources]
    if not sources or len(set(sources)) != len(sources): raise ValueError('Nonempty distinct pool sources required')
    sources.sort(); policy(raw_policy)
    out = separate(out, sources)
    repo = Path(__file__).resolve().parents[3]; baseline = repo / 'configs/benchmark1000/legacy_baseline_v1.json'
    verify_snapshot(repo, read(baseline)['files'])
    parents = [verify_manifest(p) for p in sources]
    allowed = RAW | STORES
    if any(m.get('schema') not in allowed for m in parents): raise ValueError('Unsupported pool source schema')
    prepared = {n: load_store(p, include_proposals=True) for n, (p, m) in enumerate(zip(sources, parents))
                if m['schema'] in STORES and m.get('config', {}).get('chapters') is None}
    declared = set().union(*(set(m.get('config', {}).get('chapters') or []) for m in parents),
                               *({i['chapter_id'] for i in items} for items in prepared.values()))
    if chapters is not None and (not chapters or not set(chapters) <= declared): raise ValueError('Unknown/empty pool chapter scope')
    config = {'version': 'unified_pool.1', 'sources': [{'root': str(p), 'manifest_sha256': digest(p / 'manifest.json')} for p in sources],
              'chapters': sorted(set(chapters)) if chapters is not None else None, 'policy': raw_policy, 'policy_sha256': stable(raw_policy),
              'legacy_baseline_sha256': digest(baseline),
              'code_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')}}
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.pool-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        variants = {}; occurrences = []; source_reports = []; outputs = {}
        for index, (source, manifest) in enumerate(zip(sources, parents)):
            if manifest['schema'] in RAW:
                chosen = sorted(set(chapters) & set(manifest['config']['chapters'])) if chapters is not None else None
                items = [] if chosen == [] else legacy_records(source, chosen)
            else:
                items = prepared[index] if index in prepared else load_store(source, include_proposals=True)
            retained = 0; excluded = Counter()
            for item in items:
                if chapters is not None and item['chapter_id'] not in chapters: continue
                if item.get('admission') == 'proposal': excluded['unadmitted_proposal'] += 1; continue
                sha = stable(item); variants[sha] = item
                name = 'records/' + sha + '.json'; publish(out / name, item); outputs[name] = digest(out / name)
                occurrences.append({'record_sha256': sha, 'source_index': index, 'item_id': item['item_id']}); retained += 1
            parent_report = read(source / 'report.json') if 'report.json' in manifest['outputs_sha256'] else None
            ledger = {'source': config['sources'][index], 'manifest': manifest, 'manifest_utf8': (source / 'manifest.json').read_bytes().decode('utf-8'),
                      'pinned_parent_report': parent_report, 'report_utf8': (source / 'report.json').read_bytes().decode('utf-8') if parent_report is not None else None,
                      'retained_occurrences': retained, 'excluded': dict(excluded)}
            name = f'sources/{index:03d}.json'; publish(out / name, ledger); outputs[name] = digest(out / name)
            source_reports.append({'source_index': index, 'retained_occurrences': retained, 'excluded': dict(excluded)})
        idx = make_index(variants, occurrences)
        reps = [variants[g['representative_sha256']] for g in idx['groups']]
        report = {'schema': 'comics_qa.benchmark1000.pool_report.1', 'counts': {'occurrences': len(occurrences), 'record_variants': len(variants),
                  'representatives': len(reps), 'duplicate_occurrences': len(occurrences) - len(reps)}, 'sources': source_reports,
                  'all_candidates': inventory(reps), 'native_admitted_only': inventory([i for i in reps if i['schema'] in (ADMITTED, PAIRED)]),
                  'feasibility': gaps(reps, raw_policy), 'release_status': 'not_approved', 'proof_replay': 'not_run; saved checks validated only'}
        for name, body in [('index.json', idx), ('report.json', report)]:
            publish(out / name, body); outputs[name] = digest(out / name)
        manifest = {'schema': SCHEMA, 'config': config, 'config_sha256': stable(config), 'outputs_sha256': outputs,
                    'counts': report['counts'], 'release_status': 'not_approved'}
        publish(out / 'manifest.json', manifest)
    return report


def load(root):
    root = Path(root).resolve(); m = verify_manifest(root)
    if m.get('schema') != SCHEMA or read(root / 'config.json') != m['config'] or stable(m['config']) != m['config_sha256']:
        raise ValueError('Invalid unified pool manifest/config')
    required = {'index.json', 'report.json'} | {f'sources/{n:03d}.json' for n in range(len(m['config']['sources']))}
    if not required <= set(m['outputs_sha256']) or stable(m['config']['policy']) != m['config']['policy_sha256']:
        raise ValueError('Missing pool index/report/ledger or changed policy')
    for n, source in enumerate(m['config']['sources']):
        ledger = read(root / f'sources/{n:03d}.json')
        if (ledger['source'] != source or hashlib.sha256(ledger['manifest_utf8'].encode('utf-8')).hexdigest() != source['manifest_sha256']
                or json.loads(ledger['manifest_utf8']) != ledger['manifest']): raise ValueError('Pool source ledger mismatch')
        if ledger['report_utf8'] is not None:
            if (hashlib.sha256(ledger['report_utf8'].encode('utf-8')).hexdigest() != ledger['manifest']['outputs_sha256'].get('report.json')
                    or json.loads(ledger['report_utf8']) != ledger['pinned_parent_report']): raise ValueError('Changed parent report ledger')
    idx = read(root / 'index.json'); records = {}
    for name in m['outputs_sha256']:
        if name.startswith('records/'):
            item = validate(read(member(root, name))); sha = stable(item)
            if name != 'records/' + sha + '.json': raise ValueError('Misnamed pool record')
            records[sha] = item
    if any(o['source_index'] >= len(m['config']['sources']) or o['item_id'] != records[o['record_sha256']]['item_id'] for o in idx['occurrences']):
        raise ValueError('Invalid pool provenance')
    if idx != make_index(records, idx['occurrences']): raise ValueError('Pool index/deduplication mismatch')
    items = [records[g['representative_sha256']] for g in idx['groups']]
    expected = {'occurrences': len(idx['occurrences']), 'record_variants': len(records), 'representatives': len(items),
                'duplicate_occurrences': len(idx['occurrences']) - len(items)}
    report = read(root / 'report.json')
    if expected != m['counts'] or report['counts'] != expected: raise ValueError('Pool count mismatch')
    if (report['all_candidates'] != inventory(items) or report['native_admitted_only'] != inventory([i for i in items if i['schema'] in (ADMITTED, PAIRED)])
            or report['feasibility'] != gaps(items, m['config']['policy'])): raise ValueError('Pool inventory/feasibility mismatch')
    counts = Counter(o['source_index'] for o in idx['occurrences'])
    for n in range(len(m['config']['sources'])):
        if read(root / f'sources/{n:03d}.json')['retained_occurrences'] != counts[n]: raise ValueError('Pool occurrence ledger mismatch')
    return items
