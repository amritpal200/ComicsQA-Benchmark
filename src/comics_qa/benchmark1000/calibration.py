"""Human-labelled entailment calibration; no model-family independence assumed."""
from collections import Counter


def agreement(rows):
    if not rows:
        raise ValueError('Empty calibration set')
    seen = set(); pairs = []
    for row in rows:
        if set(row) != {'id', 'human', 'judge'} or row['id'] in seen or type(row['human']) is not bool or type(row['judge']) is not bool:
            raise ValueError('Malformed/duplicate calibration row')
        seen.add(row['id']); pairs.append((row['human'], row['judge']))
    n = len(pairs); observed = sum(a == b for a, b in pairs) / n
    human = Counter(a for a, b in pairs); judge = Counter(b for a, b in pairs)
    chance = sum(human[v] * judge[v] for v in (True, False)) / (n * n)
    return {'count': n, 'agreement': observed,
            'cohens_kappa': (observed - chance) / (1 - chance) if chance < 1 else None,
            'human_positive_share': human[True] / n, 'judge_positive_share': judge[True] / n,
            'false_positive': sum(not a and b for a, b in pairs),
            'false_negative': sum(a and not b for a, b in pairs),
            'limitation': 'Calibration labels and independence must be audited externally; kappa undefined for degenerate marginals.'}
