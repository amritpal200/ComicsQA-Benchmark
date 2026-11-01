"""Snapshot-bound derived views. Never rewrite an imported candidate store."""
import copy
from .io import stable


def page_offset(item):
    """Recover a next-appearance anchor from independently recorded trace values.

    A Page result without a next_app operation is not a page+1 opportunity.
    Numeric constants elsewhere in the question are never guessed as anchors.
    """
    if item['answer_format'] != 'page':
        return {'page_offset': None, 'offset_basis': 'not_a_page_answer'}
    if item.get('schema') == 'comics_qa.benchmark1000.admitted_native.1':
        from .admission_store import validate
        validate(item)
        return {k: item['features'][k] for k in ('page_offset', 'offset_basis', 'anchor_page_index')}
    old = item['legacy']; steps = old['execution']['proof']['steps']
    next_steps = [s for s in steps if s['op'] == 'next_app']
    if not next_steps:
        return {'page_offset': None, 'offset_basis': 'not_next_appearance'}
    if len(next_steps) != 1:
        return {'page_offset': None, 'offset_basis': 'multiple_next_appearance_steps'}
    byid = {s['nid']: s for s in steps}
    children = [byid[n] for n in next_steps[0]['children']]
    anchors = [s for s in children if s['type'] == 'Page' and s['status'] == 'OK']
    if len(anchors) != 1:
        return {'page_offset': None, 'offset_basis': 'anchor_not_unique_page'}
    pages = {p['page_id']: p['index'] for p in old['context']['pages']}
    anchor = pages.get(anchors[0]['value'])
    answer = item['answer']['value']
    if type(anchor) is not int or type(answer) is not int or answer <= anchor:
        raise ValueError('Next-appearance trace/display binding invalid')
    return {'page_offset': answer - anchor, 'offset_basis': 'checked_next_app_page_child',
            'anchor_page_index': anchor}


def feature_audit(items, manifest_sha256):
    from collections import Counter
    rows = []
    for item in items:
        features = page_offset(item)
        rows.append({'item_id': item['item_id'], 'item_sha256': stable(item), 'features': features})
    pages = [r for i, r in zip(items, rows) if i['answer_format'] == 'page']
    return {'schema': 'comics_qa.benchmark1000.feature_audit.1',
            'store_manifest_sha256': manifest_sha256, 'items': rows,
            'counts': {'candidates': len(items), 'page_answers': len(pages),
                       'next_appearance_offsets': sum(r['features']['page_offset'] is not None for r in pages)},
            'offset_distribution': dict(Counter(str(r['features']['page_offset']) for r in pages if r['features']['page_offset'] is not None)),
            'offset_basis': dict(Counter(r['features']['offset_basis'] for r in pages)),
            'release_status': 'not_approved'}


def apply(items, manifest_sha256, proofs=None, features=None):
    original = {i['item_id']: i for i in items}
    if len(original) != len(items):
        raise ValueError('Duplicate view input IDs')
    original_sha = {key: stable(value) for key, value in original.items()}
    result = copy.deepcopy(items)
    byid = {i['item_id']: i for i in result}
    for report, schema, kind in ((proofs, 'comics_qa.benchmark1000.proof_validation.1', 'proofs'),
                                  (features, 'comics_qa.benchmark1000.feature_audit.1', 'features')):
        if report is None:
            continue
        if report.get('schema') != schema or report.get('store_manifest_sha256') != manifest_sha256:
            raise ValueError('View report schema/store binding mismatch')
        report_sha = stable(report)
        rows = report['items']
        if len(rows) != len(original) or {r['item_id'] for r in rows} != set(original):
            raise ValueError('View report ID set differs from store')
        for row in rows:
            item_id = row['item_id']
            if row['item_sha256'] != original_sha[item_id]:
                raise ValueError('Stale view report candidate hash')
            target = byid[item_id]
            if kind == 'proofs':
                checked = row['check']
                if row['proof'] != 'verified' or checked.get('proof_valid') is not True or checked.get('accepted_for_generation') is not True:
                    raise ValueError('Rejected/ineligible proof cannot enter a validated view')
                if checked.get('program_sha256') != original[item_id]['legacy']['program_sha256']:
                    raise ValueError('Proof report program mismatch')
                target['verification']['proof'] = 'verified'
            else:
                if row['features'] != page_offset(original[item_id]):
                    raise ValueError('Offset report does not follow original execution trace')
                target['features'].update(row['features'])
            target.setdefault('view_sources', {})[kind] = report_sha
            target['base_candidate_sha256'] = original_sha[item_id]
    return result
