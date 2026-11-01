"""New reviewed companions above immutable CKG-1/2/3; no in-place evidence edits."""
from .io import stable


def build_review_overlay(graph, visibility, sources, decisions):
    from comics_qa.evidence.graph.rich.model import build
    if not isinstance(decisions, list):
        raise ValueError('Decisions must be an explicit list')
    for decision in decisions:
        if decision.get('reviewer_type') not in ('human', 'ai'):
            raise ValueError('Explicit human/AI reviewer type required')
    # Existing source-specific review rules are reused as a pure builder.
    companion = build(graph, visibility, sources, decisions)
    return {'schema': 'comics_qa.benchmark1000.review_overlay.1',
            'base_graph_sha256': stable(graph), 'base_visibility_sha256': stable(visibility),
            'decision_sha256': stable(decisions), 'companion': companion,
            'human_decisions': sum(d['reviewer_type'] == 'human' for d in decisions),
            'ai_decisions': sum(d['reviewer_type'] == 'ai' for d in decisions),
            'release_status': 'pending_item_validation_and_review'}


def positive_fact(companion, relation, arguments):
    """A positive witness only. Missing facts never become false/count/uniqueness claims."""
    found = sorted((f for f in companion['facts'] if f['rel'] == relation and f['args'] == arguments
                    and f['origin'] in ('H', 'V') and f['answer_eligible']), key=lambda f: f['id'])
    return {'relation': relation, 'arguments': arguments, 'status': 'OK' if found else 'UNKNOWN',
            'value': True if found else None, 'fact_ids': [f['id'] for f in found],
            'companion_sha256': stable(companion), 'semantics': 'positive_witness_only'}


def check_positive_fact(companion, proof):
    # Checker does not invoke positive_fact; reconstruct the eligible witness set.
    if proof.get('companion_sha256') != stable(companion) or proof.get('semantics') != 'positive_witness_only':
        return False
    matches = {f['id'] for f in companion['facts'] if f['rel'] == proof.get('relation')
               and f['args'] == proof.get('arguments') and f['answer_eligible'] and f['origin'] in ('H', 'V')}
    if sorted(matches) != proof.get('fact_ids'):
        return False
    return (proof.get('status'), proof.get('value')) == (('OK', True) if matches else ('UNKNOWN', None))
