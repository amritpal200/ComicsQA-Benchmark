"""Atomic claim contracts. Entailment judgments are inputs, never guessed here."""
from .io import stable


def validate_claims(claims):
    allowed = {'required', 'optional', 'forbidden'}
    if set(claims) != allowed or not claims['required']:
        raise ValueError('Claims require nonempty required and explicit optional/forbidden lists')
    seen = set()
    for kind in sorted(allowed):
        for claim in claims[kind]:
            if set(claim) != {'id', 'text', 'evidence', 'verification'}:
                raise ValueError('Malformed atomic claim')
            if not isinstance(claim['text'], str) or not claim['text'].strip() or not claim['evidence']:
                raise ValueError('Claim lacks text/evidence')
            if claim['id'] in seen:
                raise ValueError('Duplicate claim ID')
            seen.add(claim['id'])
            expected = 'contradicted' if kind == 'forbidden' else 'supported'
            if claim['verification'] != expected:
                raise ValueError('Claim is unverified/unknown: ' + claim['id'])
    return claims


def score(claims, judgments, unsupported_assertions=None):
    """Caller supplies calibrated claim-entailment judgments on the submitted answer."""
    validate_claims(claims)
    ids = {c['id'] for values in claims.values() for c in values}
    if set(judgments) != ids or any(type(v) is not bool for v in judgments.values()):
        raise ValueError('Missing/unknown/non-Boolean entailment judgment')
    required = sum(judgments[c['id']] for c in claims['required'])
    forbidden = sum(judgments[c['id']] for c in claims['forbidden'])
    if unsupported_assertions is not None and (type(unsupported_assertions) is not int or unsupported_assertions < 0):
        raise ValueError('Invalid unsupported-assertion count')
    return {'required_claim_recall': required / len(claims['required']),
            'forbidden_claims_stated': forbidden,
            'unsupported_assertions': unsupported_assertions,
            'all_required_correct': required == len(claims['required']),
            'fully_factual': None if unsupported_assertions is None else forbidden == 0 and unsupported_assertions == 0,
            'claims_sha256': stable(claims)}
