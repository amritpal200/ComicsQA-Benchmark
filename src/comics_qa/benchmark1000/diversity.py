"""Candidate-pool diagnostics; never change validity, quotas or release decisions."""
from collections import Counter
from pathlib import Path
from .io import read, stable
from .selection import policy, violations, metrics


def describe(items):
    declared = policy(read(Path(__file__).resolve().parents[3] / 'configs/benchmark1000/v1.json'))
    return {'items': len(items), 'families': dict(Counter(i['admission_receipt']['kind'] for i in items)),
            'answer_formats': dict(Counter(i['answer_format'] for i in items)),
            'primary_groups': dict(Counter(i['primary_group'] for i in items)),
            'distinct_typed_answers': len({stable([i['answer_format'], i['answer']['value']]) for i in items}),
            'complexity_certified': sum('complexity_certificate' in i['admission_receipt'] for i in items),
            'page_offsets': dict(Counter(str(i['features']['page_offset']) for i in items if i['features'].get('page_offset') is not None)),
            'count_values': dict(Counter(str(i['answer']['value']) for i in items if i['answer_format'] == 'count')),
            'set_cardinalities': dict(Counter(str(len(i['answer']['value'])) for i in items if i['answer_format'] == 'set')),
            'metrics': metrics(items), 'pool_policy_violations': violations(items, declared, final=False),
            'final_target': declared['target_items'], 'policy_applied_as_filter': False,
            'feasibility': 'not_established_by_bounded_pilot', 'release_status': 'not_approved'}
