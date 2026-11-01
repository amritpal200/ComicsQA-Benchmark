"""Immutable admitted views and per-proposal receipts over a saved semantic run."""
import copy
import fcntl
from collections import Counter
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from comics_qa.tasks.graph.gen2.aliases import validate_reviews
from .io import stable, digest, read, publish, separate, verify_manifest, member, verify_snapshot
from .native import validate as validate_proposal
from .native_store import load as load_proposals
from .admission import VERSION, World, assess, deduplicate, resolved_path, same_answer
from .native_wording import parse_question, bound

SCHEMA = 'comics_qa.benchmark1000.admitted_native.1'
STORE = 'comics_qa.benchmark1000.admission_store.1'


def admitted(proposal, receipt):
    if not receipt['passed'] or receipt['proposal_sha256'] != stable(proposal):
        raise ValueError('Cannot admit a held or misbound proposal')
    item = copy.deepcopy(proposal)
    item.pop('schema'); item.pop('item_id')
    item['proposal'] = copy.deepcopy(proposal)
    item['admission_receipt'] = copy.deepcopy(receipt)
    item['source_item_id'] = proposal['item_id']
    item['admission'] = 'candidate'
    item['verification'].update(gates='verified', wording='verified')
    item['reasoning_tags'] = ['native_admitted', receipt['kind']]
    # Admission is distinct from primary-group/meaningful-hop certification.
    item['primary_group'] = 'unassigned'
    item['complexity'].update(meaningful_hops=None, necessary_pages=receipt['checks']['necessary_pages'], necessity_status='measured',
                              branch_count=len(receipt['checks']['clause_removals']) if receipt['kind'] in ('two_quote_joint', 'three_page_clue') else 0)
    if 'complexity_certificate' in receipt:
        cert = receipt['complexity_certificate']
        item['complexity'].update({k: cert[k] for k in ('meaningful_hops', 'branch_count', 'necessary_pages', 'page_span')})
        item['complexity']['certificate'] = copy.deepcopy(cert)
        item['primary_group'] = cert['primary_group']
    if receipt.get('complexity_certificate', {}).get('long_relational', {}).get('eligible') is True:
        item['reasoning_tags'].append('long_relational')
        item['long_relational_certificate'] = copy.deepcopy(receipt['complexity_certificate']['long_relational'])
    item['features']['semantic_target'] = receipt['resolved_path_sha256']
    if item['answer_format'] == 'page':
        program = proposal['program']
        if 'complexity_certificate' in receipt:
            anchor = parse_question(proposal['question'])['recipe']['start'] - 1
        elif proposal['proof_engine'] == 'relay':
            # Offset relative to the resolved last presence-search anchor, not page A.
            anchor = proposal['execution']['stages'][0]['execution']['result']['display']
        else:
            anchor = program['after']
        basis = 'expanded_question_latest_reference_page' if 'complexity_certificate' in receipt else 'independently_checked_native_scan_anchor'
        if 'complexity_certificate' in receipt and parse_question(proposal['question'])['recipe'].get('profile') == 'coverage_windows.1':
            basis = 'expanded_search_range_predecessor'
            reference = max(x['page'] for x in parse_question(proposal['question'])['recipe']['references'])
            item['features'].update(latest_reference_page_index=reference, reference_page_distance=item['answer']['value'] - reference)
        item['features'].update(page_offset=item['answer']['value'] - anchor, offset_basis=basis, anchor_page_index=anchor)
    item = {'schema': SCHEMA, 'item_id': 'b1000a:' + stable(item), **item}
    return validate(item)


def validate(item):
    if item.get('schema') != SCHEMA or item.get('item_id') != 'b1000a:' + stable({k: v for k, v in item.items() if k not in ('schema', 'item_id')}):
        raise ValueError('Invalid admitted native identity/schema')
    proposal = validate_proposal(item['proposal']); row = item['admission_receipt']
    if (row.get('version') != VERSION or not row.get('passed') or row.get('reasons') != [] or row.get('proposal_id') != proposal['item_id']
            or row.get('proposal_sha256') != stable(proposal) or row.get('snapshots') != proposal['source']['snapshots']
            or row.get('resolved_path_sha256') != stable(row['resolved_path'])):
        raise ValueError('Admission receipt binding mismatch')
    for key in ('chapter_id', 'split', 'question', 'answer', 'answer_format', 'evidence_class', 'generation_mode', 'reasoning_structure',
                'proof_engine', 'program', 'execution', 'context', 'source', 'evidence', 'claims', 'options', 'answer_check'):
        if item.get(key) != proposal.get(key):
            raise ValueError('Admitted view changed its original ' + key)
    expected = copy.deepcopy(proposal['verification']); expected.update(gates='verified', wording='verified')
    if item['verification'] != expected or item['admission'] != 'candidate' or item['source_item_id'] != proposal['item_id']:
        raise ValueError('Admission cannot approve human review/release')
    if not bound(parse_question(item['question']), item) or item['features']['semantic_target'] != row['resolved_path_sha256']:
        raise ValueError('Admitted wording/path mismatch')
    parsed = parse_question(item['question'])
    if row['kind'] != parsed['kind'] or row['checks']['wording']['kind'] != parsed['kind']:
        raise ValueError('Admission family/wording mismatch')
    operands = iter(row['resolved_characters'])
    class OperandProofs:
        def run(self, engine, program):
            from comics_qa.tasks.graph.crl.language import parse, program_hash
            try:
                operand = next(operands)
            except StopIteration:
                raise ValueError('Missing resolved-character proof') from None
            if (engine != 'crl' or not operand['proof_valid'] or operand['execution_sha256'] != stable(operand['execution'])
                    or operand['result'] != operand['execution']['result']
                    or program_hash(parse(program)) != program_hash(parse(operand['execution']['program']))):
                raise ValueError('Resolved-character proof binding mismatch')
            return operand
    if resolved_path(proposal, parsed, OperandProofs()) != row['resolved_path'] or next(operands, None) is not None:
        raise ValueError('Incorrect resolved path or surplus operand proofs')
    checks = row['checks']
    if (not checks['answer']['answer_supported'] or not checks['wording']['pass'] or not checks['answer_leakage']['pass']
            or not checks['transcript_agreement']['pass'] or any(n['reason'] for n in checks['names'])
            or any(not c['necessary'] for c in checks['clause_removals'])
            or len(checks['necessary_visual_pages']) < parse_question(item['question'])['min_pages']):
        raise ValueError('Admission certificate contains a failed gate')
    if checks['text_only']['result']['status'] == 'OK' and checks['text_only']['result']['value'] == proposal['execution']['result']['value']:
        raise ValueError('Text-only solved admitted question')
    unrestricted = checks['wording'].get('unrestricted_domain')
    target = proposal['execution']['result']['value']
    if unrestricted and (not unrestricted['answer_supported'] or unrestricted['result']['status'] != 'OK' or unrestricted['result']['value'] != target):
        raise ValueError('Unstated named-domain restriction changes the answer')
    measured = checks['page_removals']
    if (len({p['removed_page'] for p in measured}) != len(measured)
            or checks['necessary_pages'] != [p['removed_page'] for p in measured if p['necessary']]
            or not set(checks['necessary_visual_pages']).issubset(checks['necessary_pages'])):
        raise ValueError('Page necessity certificate mismatch')
    for p in measured:
        if p['necessary'] != (not same_answer(p['result'], {'value': target})):
            raise ValueError('Incorrect page necessity verdict')
    for p in checks['clause_removals']:
        if p['necessary'] != (p['result']['status'] in ('OK', 'AMBIGUOUS', 'EMPTY') and (not same_answer(p['result'], {'value': target}))):
            raise ValueError('Incorrect clause necessity verdict')
    alternative = checks.get('relay_identity_alternative')
    if row['kind'] == 'speaker_relay' and (not alternative or alternative['result']['status'] not in ('OK', 'EMPTY') or alternative['result']['status'] == 'OK' and alternative['result']['value'] == target):
        raise ValueError('Relay identity switch does not demonstrably affect the final answer')
    for p in [*[trial for c in checks['clause_removals'] for trial in c.get('sensitivity_trials', [])], *measured, *checks['clause_removals'], checks['text_only'], *([unrestricted] if unrestricted else []), *([alternative] if alternative else [])]:
        if not p['proof_valid'] or p['execution_sha256'] != stable(p['execution']) or p['result'] != p['execution']['result']:
            raise ValueError('Counterfactual proof/result binding mismatch')
    if 'profile_version' in parsed:
        from .complexity import certify, bindings
        for at, removal in enumerate(checks['clause_removals']):
            options = [parsed['relaxations'][at]]
            if parsed.get('alternative_relaxations'):
                options.append(parsed['alternative_relaxations'][at])
            if not any(bound({'engine': e, 'program': p}, {'proof_engine': removal['engine'], 'program': removal['program']}) for e, p in options):
                raise ValueError('Bypass does not match its stated semantic step')
            if not bound({'engine': removal['engine'], 'program': removal['program']}, {'proof_engine': removal['engine'], 'program': removal['execution']['program']}):
                raise ValueError('Bypass execution/program mismatch')
        cert = certify(proposal, parsed, checks)
        if (not cert['certified'] or row.get('complexity_certificate') != cert or item['complexity'].get('certificate') != cert
                or item['primary_group'] != cert['primary_group'] or checks['resolved_bindings'] != bindings(proposal)
                or any(item['complexity'].get(k) != cert[k] for k in ('meaningful_hops', 'branch_count', 'necessary_pages', 'page_span'))):
            raise ValueError('Invalid measured complexity/group certificate')
    if parsed.get('profile_version') == 'branch_relations.1':
        long = row['complexity_certificate']['long_relational']
        tags = ['native_admitted', row['kind']] + (['long_relational'] if long['eligible'] else [])
        if item['reasoning_tags'] != tags or item.get('long_relational_certificate') != (long if long['eligible'] else None):
            raise ValueError('Forged long-relational classification')
    elif 'long_relational' in item['reasoning_tags'] or item.get('long_relational_certificate') is not None:
        raise ValueError('Long-relational claims need a supported measured certificate')
    if 'profile_version' in parsed and item['answer_format'] == 'page':
        anchor = parsed['recipe']['start'] - 1
        basis = 'expanded_search_range_predecessor' if parsed['recipe'].get('profile') == 'coverage_windows.1' else 'expanded_question_latest_reference_page'
        if (item['features'].get('page_offset') != item['answer']['value'] - anchor or item['features'].get('anchor_page_index') != anchor
                or item['features'].get('offset_basis') != basis):
            raise ValueError('Expanded page-offset feature mismatch')
        if parsed['recipe'].get('profile') == 'coverage_windows.1':
            reference = max(x['page'] for x in parsed['recipe']['references'])
            if item['features'].get('latest_reference_page_index') != reference or item['features'].get('reference_page_distance') != item['answer']['value'] - reference:
                raise ValueError('Reference distance feature mismatch')
    return item


def load(root):
    root = Path(root).resolve(); manifest = verify_manifest(root)
    if manifest.get('schema') != STORE or stable(manifest['config']) != manifest['config_sha256'] or read(root / 'config.json') != manifest['config']:
        raise ValueError('Invalid admission store config/schema')
    items = [validate(read(member(root, p))) for p in sorted(manifest['outputs_sha256']) if p.startswith('candidates/')]
    report = read(root / 'report.json')
    if len({i['item_id'] for i in items}) != len(items) or len(items) != manifest['counts']['admitted'] or report['counts'] != manifest['counts']:
        raise ValueError('Admission store totals mismatch')
    decisions = report['decisions']
    expected_counts = {'proposals': len(decisions), **{s: sum(d['status'] == s for d in decisions.values()) for s in ('admitted', 'held', 'duplicate')}}
    if manifest['counts'] != expected_counts or report['config_sha256'] != manifest['config_sha256']:
        raise ValueError('Admission report/config counts mismatch')
    receipts = {}
    for pid, decision in decisions.items():
        name = 'checks/' + stable(pid) + '.json'
        if name not in manifest['outputs_sha256'] or decision['status'] not in ('admitted', 'held', 'duplicate'):
            raise ValueError('Missing proposal decision/checkpoint')
        row = read(member(root, name)); receipts[pid] = row
        if row['proposal_id'] != pid or row['run_config_sha256'] != manifest['config_sha256'] or row['passed'] != (decision['status'] != 'held'):
            raise ValueError('Misbound proposal admission decision')
        if decision['status'] == 'held' and decision['reasons'] != row['reasons']:
            raise ValueError('Held proposal reasons mismatch')
    for pid, decision in decisions.items():
        if decision['status'] == 'duplicate':
            target = decision['duplicate_of']
            if target not in decisions or decisions[target]['status'] != 'admitted' or receipts[target]['resolved_path_sha256'] != receipts[pid]['resolved_path_sha256']:
                raise ValueError('Duplicate lacks a passing identical resolved-path representative')
    for item in items:
        pid = item['proposal']['item_id']; name = 'checks/' + stable(pid) + '.json'
        if name not in manifest['outputs_sha256'] or read(member(root, name)) != item['admission_receipt'] or decisions[pid]['status'] != 'admitted' or decisions[pid]['candidate_id'] != item['item_id']:
            raise ValueError('Candidate lacks its bound passing admission decision')
    if len({i['features']['semantic_target'] for i in items}) != len(items):
        raise ValueError('Duplicate admitted resolved path')
    return items


def pending_aliases(items, receipts, worlds, pins):
    requests = {}
    from comics_qa.tasks.graph.gen2.quality import normalized
    for item in items:
        cid = item['chapter_id']; world = worlds[cid]; g, v = world.g, world.v
        nodes = {n['id']: n for n in g['nodes']}
        for row in receipts[item['item_id']]['checks'].get('names', []):
            if row['reason'] != 'name_alias_unapproved':
                continue
            identity, form = row['identity_id'], row['form']
            es = [e for e in v['evidence'] if e['identity_id'] == identity and e['status'] == 'verified' and normalized(e['form']) == normalized(form)]
            requests[cid, identity, normalized(form)] = {'chapter_id': cid, 'identity_id': identity, 'form': form,
                'canonical_name': nodes[identity]['canonical_name'], **pins[cid], 'evidence_ids': sorted(e['evidence_id'] for e in es),
                'evidence': es, 'decision': 'pending', 'reviewer': '', 'note': '', 'name_use': ''}
    return [requests[k] for k in sorted(requests)]


def run(semantic_root, bench_root, out, alias_reviews=None, chapters=None, max_ablation_pages=8):
    if type(max_ablation_pages) is not int or max_ablation_pages < 1:
        raise ValueError('Positive admission page budget required')
    semantic_root, bench_root = Path(semantic_root).resolve(), Path(bench_root).resolve()
    protected = [semantic_root, bench_root / 'evidence', bench_root / 'core'] + ([alias_reviews] if alias_reviews else [])
    out = separate(out, protected)
    parent = verify_manifest(semantic_root)
    if parent.get('schema') not in ('comics_qa.benchmark1000.semantic_artifacts.1', 'comics_qa.benchmark1000.family_artifacts.1') or read(semantic_root / 'config.json') != parent['config'] or stable(parent['config']) != parent['config_sha256']:
        raise ValueError('Expected a complete pinned semantic run')
    items = load_proposals(semantic_root / 'native_store', include_proposals=True)
    for item in items:
        validate_proposal(item)
    requested = sorted(set(chapters or parent['config']['chapters']))
    if not requested or set(requested) - set(parent['config']['chapters']):
        raise ValueError('Invalid or empty admission chapter scope')
    items = [i for i in items if i['chapter_id'] in requested]
    reviews = read(alias_reviews) if alias_reviews else []
    if not isinstance(reviews, list):
        raise ValueError('Alias reviews must be a JSON list')
    repo = Path(__file__).resolve().parents[3]
    baseline = repo / 'configs/benchmark1000/legacy_baseline_v1.json'
    verify_snapshot(repo, read(baseline)['files'])
    code = {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')}
    config = {'version': VERSION, 'legacy_baseline_sha256': digest(baseline), 'semantic_root': str(semantic_root), 'semantic_manifest_sha256': digest(semantic_root / 'manifest.json'),
              'native_manifest_sha256': digest(semantic_root / 'native_store/manifest.json'),
              'alias_reviews_sha256': digest(alias_reviews) if alias_reviews else None, 'chapters': requested,
              'max_ablation_pages': max_ablation_pages, 'code_sha256': code}
    worlds, approvals, name_pins = {}, {}, {}
    for cid in sorted({i['chapter_id'] for i in items}):
        gr, vr, rr = (bench_root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'))
        g, v, pins = load_world(gr, vr, cid)
        r = load_optional(gr, vr, rr, cid, pins)
        worlds[cid] = World(g, v, r)
        name_pins[cid] = {'graph_sha256': digest(gr / 'chapters' / (cid + '.json')), 'visibility_sha256': digest(vr / 'chapters' / (cid + '.json'))}
        approvals[cid] = validate_reviews(reviews, g, v, name_pins[cid]['graph_sha256'], name_pins[cid]['visibility_sha256'])
        # Native answer validation checks all loaded snapshots before any checkpoint reuse.
        for item in (i for i in items if i['chapter_id'] == cid):
            if item['source']['snapshots'] != {'graph': stable(g), 'visibility': stable(v), 'rich': stable(r)}:
                raise ValueError('Admission source snapshot mismatch')
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.admission-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        if (out / 'manifest.json').exists():
            load(out)
        receipts, outputs = {}, {}
        for item in sorted(items, key=lambda i: i['item_id']):
            path = out / 'checks' / (stable(item['item_id']) + '.json')
            if path.exists():
                receipt = read(path)
                if receipt['proposal_sha256'] != stable(item) or receipt.get('run_config_sha256') != stable(config):
                    raise ValueError('Stale admission checkpoint')
            else:
                receipt = assess(item, worlds[item['chapter_id']], approvals[item['chapter_id']], max_ablation_pages)
                receipt['run_config_sha256'] = stable(config)
                publish(path, receipt)
            receipts[item['item_id']] = receipt
            outputs[str(path.relative_to(out))] = digest(path)
            print(f"{item['chapter_id']}: {'checks passed' if receipt['passed'] else ', '.join(receipt['reasons'])}", flush=True)
        decisions = deduplicate(items, receipts)
        counts = {'proposals': len(items), **{s: sum(d['status'] == s for d in decisions.values()) for s in ('admitted', 'held', 'duplicate')}}
        admitted_items = []
        for item in items:
            if decisions[item['item_id']]['status'] == 'admitted':
                candidate = admitted(item, receipts[item['item_id']])
                admitted_items.append(candidate)
                path = out / 'candidates' / (stable(candidate['item_id']) + '.json')
                publish(path, candidate); outputs[str(path.relative_to(out))] = digest(path)
                decisions[item['item_id']]['candidate_id'] = candidate['item_id']
        report = {'schema': 'comics_qa.benchmark1000.admission_report.1', 'config_sha256': stable(config), 'counts': counts, 'decisions': decisions,
                  'reason_counts': dict(Counter(r for d in decisions.values() for r in d['reasons'])),
                  'release_status': 'not_approved', 'primary_group_assignment': 'pending_complexity_certification',
                  'meaningful_hops': 'not_certified', 'selection_policy': 'unchanged; global quotas not applied by admission'}
        from .probes import recipe_probes
        probes = [p for i in admitted_items if i['proof_engine'] in ('recipe', 'coverage_recipe') for p in recipe_probes(i, worlds[i['chapter_id']].g, worlds[i['chapter_id']].v, worlds[i['chapter_id']].r)]
        publish(out / 'probes.json', probes); outputs['probes.json'] = digest(out / 'probes.json')
        report['auxiliary_probe_count'] = len(probes)
        from .diversity import describe
        report['diversity'] = describe(admitted_items)
        report['held_by_family'] = dict(Counter(receipts[pid].get('kind', receipts[pid]['checks'].get('wording', {}).get('kind', 'unrecognized')) for pid, d in decisions.items() if d['status'] == 'held'))
        report['primary_group_assignment'] = 'certified_for_expanded_profiles; older profiles pending'
        report['meaningful_hops'] = 'measured_for_expanded_profiles; older profiles pending'
        for name, obj in [('report.json', report), ('pending_alias_reviews.json', pending_aliases(items, receipts, worlds, name_pins))]:
            publish(out / name, obj); outputs[name] = digest(out / name)
        manifest = {'schema': STORE, 'config': config, 'config_sha256': stable(config), 'outputs_sha256': outputs,
                    'counts': counts, 'release_status': 'not_approved'}
        publish(out / 'manifest.json', manifest)
    load(out)
    return report
