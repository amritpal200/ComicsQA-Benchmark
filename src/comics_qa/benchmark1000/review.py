"""Snapshot-bound review records and predeclared zero-error sampling calculations."""
import math
import random
from .io import stable


def zero_error_bound(n, confidence=.95):
    if type(n) is not int or n < 1 or not 0 < confidence < 1:
        raise ValueError('Invalid sampling parameters')
    return -math.expm1(math.log1p(-confidence) / n)


def sample(items, size, seed):
    if type(size) is not int or not 0 <= size <= len(items):
        raise ValueError('Sample larger than stratum')
    ids = sorted(i['item_id'] for i in items)
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate stratum members')
    from .contrast import units, MEMBER
    if any(i.get('schema') == MEMBER for i in items):
        pairs = units(items)
        groups = [[x['item_id'] for x in rows] for rows in pairs.values()] + [[i['item_id']] for i in items if i.get('schema') != MEMBER]
        groups.sort(); random.Random(seed).shuffle(groups); selected = []
        for group in groups:
            if len(selected) + len(group) <= size: selected.extend(group)
        return {'population_ids_sha256': stable(ids), 'population_size': len(ids),
                'selected_ids': sorted(selected), 'seed': seed, 'selection_size': len(selected), 'requested_size': size,
                'design': 'atomic_contrast_units_shuffled_with_item_budget', 'zero_error_binomial_95_upper': None,
                'limitation': 'Clustered unequal-unit sampling; no individual-item binomial bound claimed'}
    selected = sorted(random.Random(seed).sample(ids, size))
    return {'population_ids_sha256': stable(ids), 'population_size': len(ids),
            'selected_ids': selected, 'seed': seed, 'selection_size': size,
            'design': 'simple_random_without_replacement',
            'zero_error_binomial_95_upper': zero_error_bound(size) if size else None,
            'limitation': 'Per-stratum binomial bound; no benchmark-wide multiplicity claim'}


def validate_decision(item, decision):
    fields = {'item_id', 'item_sha256', 'reviewer', 'reviewer_type', 'decision', 'reason', 'review_version'}
    if set(decision) != fields or decision['reviewer_type'] not in ('human', 'ai'):
        raise ValueError('Invalid reviewer record')
    if decision['decision'] not in ('accept', 'reject', 'flag'):
        raise ValueError('Unknown decision')
    if decision['item_id'] != item['item_id'] or decision['item_sha256'] != stable(item):
        raise ValueError('Stale or misbound review')
    if not all(isinstance(decision[k], str) and decision[k].strip() for k in ('reviewer', 'reason', 'review_version')):
        raise ValueError('Missing reviewer/justification/version')
    return decision


def release_eligible(item, decisions):
    if item.get('schema') == 'comics_qa.benchmark1000.contrast_member.1':
        return False  # Pair-wide adjudication/release view is intentionally pending.
    if item.get('admission') == 'proposal':
        return False
    verified = item['verification']
    if item['evidence_class'] == 'interpretive' or verified.get('proof') != 'verified':
        return False
    if verified.get('wording') not in ('verified', 'human_verified'):
        return False
    if item['evidence_class'] == 'claim_verified' and verified.get('claims') != 'verified':
        return False
    reviewed = [validate_decision(item, d) for d in decisions]
    human = [d for d in reviewed if d['reviewer_type'] == 'human']
    # Until stratum-acceptance tooling is complete, require individual human acceptance.
    return bool(human) and all(d['decision'] == 'accept' for d in human)
