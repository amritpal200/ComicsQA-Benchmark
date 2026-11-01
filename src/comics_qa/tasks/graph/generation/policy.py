"""Versioned generation policy; quotas never relax because a chapter is small."""
import hashlib
import json

VERSION = 'gen1.1'
DEFAULT = {
    'version': VERSION, 'seed': 42, 'max_candidates_per_chapter': 600,
    'max_items_per_chapter': 80, 'max_per_family': 24, 'max_per_answer_support': 1,
    'max_constraint_candidates_per_target': 32, 'max_clauses': 3,
    'count_targets': list(range(2, 13)), 'frequent_top_k': 2,
    'frequent_metric': 'trusted_distinct_page_presence', 'frequent_ties': 'include_cutoff_ties',
    'max_frequent_name_share': 0.30, 'max_two_option_share': 0.05,
    'boolean_true_share': [0.45, 0.55], 'allow_closed_assumed': True,
    'max_steps': 50000, 'max_worlds': 64,
}


def stable(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def configure(overrides=None):
    if overrides is not None and not isinstance(overrides,dict): raise ValueError('Generation policy must be a JSON object')
    p = {**DEFAULT, **(overrides or {})}
    if set(p) != set(DEFAULT): raise ValueError('Unknown generation policy fields')
    for k in ('max_candidates_per_chapter','max_items_per_chapter','max_per_family','max_per_answer_support',
              'max_constraint_candidates_per_target','frequent_top_k','max_steps','max_worlds'):
        if type(p[k]) is not int or p[k] < 1: raise ValueError('Policy needs positive integer: '+k)
    if type(p['seed']) is not int or type(p['allow_closed_assumed']) is not bool: raise ValueError('Invalid seed/coverage policy')
    if p['version'] != VERSION or type(p['max_clauses']) is not int or p['max_clauses'] not in (2,3): raise ValueError('Unsupported version/clause depth')
    if p['frequent_metric'] != DEFAULT['frequent_metric'] or p['frequent_ties'] != DEFAULT['frequent_ties']:
        raise ValueError('Unsupported frequent-character definition')
    if not isinstance(p['count_targets'],list) or not p['count_targets'] or any(type(x) is not int or x<1 for x in p['count_targets']):
        raise ValueError('count_targets must contain positive integers')
    if len(set(p['count_targets']))!=len(p['count_targets']): raise ValueError('count_targets must be distinct')
    for k, cap in [('max_frequent_name_share',.30),('max_two_option_share',.05)]:
        if type(p[k]) not in (int,float) or not 0 <= p[k] <= cap: raise ValueError('Quota exceeds agreed cap: '+k)
    if p['boolean_true_share'] != [.45,.55]: raise ValueError('Boolean balance must remain 45-55%')
    return p
