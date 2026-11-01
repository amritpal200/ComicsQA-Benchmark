"""Resolve source-proportional split counts only from an explicitly full inventory."""
from collections import Counter
from fractions import Fraction
from .selection import policy


def freeze(raw_policy, preflight):
    p = dict(policy(raw_policy))
    graph_report = preflight.get('graphs', preflight)
    if graph_report.get('scope') != 'full_collection':
        raise ValueError('Split freeze requires a full source graph inventory, not a selected chapter pilot')
    rows = graph_report['chapters']
    if not rows or len({r['chapter_id'] for r in rows}) != len(rows):
        raise ValueError('Empty or duplicate source chapter inventory')
    counts = Counter(r['split'] for r in rows)
    if set(counts) != {'seen', 'unseen'}:
        raise ValueError('Need both original source splits')
    quotas = {s: Fraction(p['target_items'] * n, len(rows)) for s, n in counts.items()}
    splits = {s: q.numerator // q.denominator for s, q in quotas.items()}
    remainder = p['target_items'] - sum(splits.values())
    ranked = sorted(quotas, key=lambda s: (-(quotas[s] - splits[s]), s))
    for s in ranked[:remainder]:
        splits[s] += 1
    p['split_counts'] = dict(sorted(splits.items()))
    return policy(p), {'definition': 'proportional to source chapter counts; largest remainder, lexicographic tie-break',
                       'source_chapters': dict(counts), 'source_manifest_sha256': graph_report['manifest_sha256'],
                       'feasibility': 'not_established_by_structural_inventory'}
