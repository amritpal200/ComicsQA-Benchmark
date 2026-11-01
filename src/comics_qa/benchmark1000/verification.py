"""Read-only composition with the unchanged legacy independent checker."""
from pathlib import Path
from .io import digest, stable


def revalidate(items, bench_root):
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
    root = Path(bench_root).resolve()
    worlds, results = {}, []
    for i in items:
        if i.get('schema') == 'comics_qa.benchmark1000.contrast_member.1':
            from .contrast import validate_member
            validate_member(i)
            base = i['pair_certificate']['members'][i['pair_role']]
            checked = revalidate([base], bench_root)['items'][0]
            results.append({**checked, 'item_id': i['item_id'], 'item_sha256': stable(i),
                            'check': {**checked['check'], 'contrast_condition_verified': True}})
            continue
        if i.get('schema') == 'comics_qa.benchmark1000.admitted_native.1':
            from .admission_store import validate
            from .admission import World, assess
            from comics_qa.tasks.graph.gen2.aliases import validate_reviews
            validate(i); cid = i['chapter_id']; key = ('native', cid)
            if key not in worlds:
                gr, vr, rr = (root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'))
                g, v, pins = load_world(gr, vr, cid)
                r = load_optional(gr, vr, rr, cid, pins)
                worlds[key] = (World(g, v, r), gr, vr)
            world, gr, vr = worlds[key]
            rows = [{k: v for k, v in row.items() if k != 'review_sha256'} for row in i['admission_receipt']['checks']['alias_reviews']]
            approvals = validate_reviews(rows, world.g, world.v, digest(gr / 'chapters' / (cid + '.json')), digest(vr / 'chapters' / (cid + '.json')))
            saved = {k: v for k, v in i['admission_receipt'].items() if k != 'run_config_sha256'}
            budget = max(8, len(saved['checks']['page_removals']))
            fresh = assess(i['proposal'], world, approvals, budget)
            accepted = fresh == saved and fresh['passed']
            results.append({'item_id': i['item_id'], 'item_sha256': stable(i), 'proof': 'verified' if accepted else 'rejected',
                            'check': {'proof_valid': fresh['checks']['answer']['proof_valid'], 'native_admission_reproduced': accepted}})
            continue
        old = i['legacy']; cid = i['chapter_id']
        needs_rich = old['execution'].get('rich_evidence_sha256') is not None
        key = (cid, needs_rich)
        if key not in worlds:
            g, v, pins = load_world(root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1', cid)
            r = load_optional(root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1', root / 'evidence/ckg3/v1', cid, pins) if needs_rich else None
            worlds[key] = (g, v, r, pins, ProofChecker(g, v, rich=r))
        g, v, r, pins, checker = worlds[key]
        # Original paths can differ between hosts: compare role-relative content pins.
        recorded = old['execution']['inputs_sha256']
        def roles(mapping):
            return {str(Path(p)).split('/evidence/', 1)[1]: sha for p, sha in mapping.items() if '/evidence/' in str(p)}
        if roles(recorded) != roles(pins):
            raise ValueError('Legacy proof inputs differ from current snapshots')
        checked = checker.check(old['execution'], old['program'])
        result = old['execution']['result']
        accepted = checked['accepted_for_generation'] and checked['proof_valid']
        accepted = accepted and stable(old['answer']['value']) == stable(result['display'])
        if old['answer'].get('identity_id'):
            accepted = accepted and old['answer']['identity_id'] == result['value']
        results.append({'item_id': i['item_id'], 'item_sha256': stable(i),
                        'proof': 'verified' if accepted else 'rejected', 'check': checked})
    return {'schema': 'comics_qa.benchmark1000.proof_validation.1', 'items': results,
            'verified': sum(i['proof'] == 'verified' for i in results),
            'rejected': sum(i['proof'] != 'verified' for i in results)}
