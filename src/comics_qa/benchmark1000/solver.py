"""Optional CP-SAT backend with constraints matching the reference policy checker."""
from collections import Counter, defaultdict
from fractions import Fraction
import math
from .selection import policy, metrics, violations
from .io import stable


def select_cp(items, raw_policy, pilot=False, seconds=20):
    from ortools.sat.python import cp_model
    p = policy(raw_policy)
    if type(seconds) not in (float, int) or not math.isfinite(seconds) or not 0 < seconds <= 300:
        raise ValueError('Solver seconds must be in (0,300]')
    seen, unique = set(), []
    excluded = {}
    for item in sorted(items, key=lambda i: i['item_id']):
        key = (item['chapter_id'], item['features']['semantic_target'], item.get('pair_id'), item['item_id'] if item.get('pair_id') else None)
        if key in seen:
            excluded[item['item_id']] = 'policy:duplicate_semantic_target'
        else:
            seen.add(key); unique.append(item)
    items = unique
    model = cp_model.CpModel()
    xs = [model.NewBoolVar('i' + str(n)) for n in range(len(items))]
    def indices(test):
        return [n for n, item in enumerate(items) if test(item)]
    def total(scope):
        return sum(xs[n] for n in scope)
    def cap(scope, denom, share, active=None):
        ratio = Fraction(str(share))
        constraint = model.Add(ratio.denominator * total(scope) <= ratio.numerator * total(denom))
        if active is not None:
            constraint.OnlyEnforceIf(active)
    def large(scope, label):
        flag = model.NewBoolVar(label)
        model.Add(total(scope) >= p['minimum_denominator']).OnlyEnforceIf(flag)
        model.Add(total(scope) < p['minimum_denominator']).OnlyEnforceIf(flag.Not())
        return flag
    chapters = {}
    for chapter in sorted({i['chapter_id'] for i in items}):
        scope = indices(lambda i: i['chapter_id'] == chapter)
        model.Add(total(scope) <= p['maximum_per_chapter'])
        flag = model.NewBoolVar('chapter:' + chapter)
        model.Add(total(scope) >= 1).OnlyEnforceIf(flag)
        model.Add(total(scope) == 0).OnlyEnforceIf(flag.Not())
        chapters[chapter] = flag
    all_ids = list(range(len(items)))
    cap(indices(lambda i: i['features']['two_option']), all_ids, p['two_option_share'])
    for n, i in enumerate(items):
        if i.get('admission') == 'proposal' or i['evidence_class'] == 'interpretive' or (not pilot and i['verification']['proof'] != 'verified'):
            model.Add(xs[n] == 0)
    for split in ('seen', 'unseen'):
        chars = indices(lambda i: i['split'] == split and bool(i['features'].get('identity_id')))
        counts = indices(lambda i: i['split'] == split and i['answer_format'] == 'count')
        pages = indices(lambda i: i['split'] == split and i['answer_format'] == 'page' and i['features'].get('page_offset') is not None)
        c_large = large(chars, split + ':chars_large')
        for identity in sorted({items[n]['features']['identity_id'] for n in chars}):
            scope = [n for n in chars if items[n]['features']['identity_id'] == identity]
            cap(scope, chars, p['identity_share'], c_large)
            for cid in chapters:
                model.Add(total([n for n in scope if items[n]['chapter_id'] == cid]) <= p['small_pool_absolute_cap']).OnlyEnforceIf(c_large.Not())
        missing = [n for n in chars if type(items[n]['features'].get('is_top1_identity')) is not bool]
        model.Add(total(missing) == 0).OnlyEnforceIf(c_large)
        cap([n for n in chars if items[n]['features'].get('is_top1_identity') is True], chars, p['top1_share'], c_large)
        model.Add(total([n for n in chars if type(items[n]['features'].get('is_top2_identity')) is not bool]) == 0).OnlyEnforceIf(c_large)
        cap([n for n in chars if items[n]['features'].get('is_top2_identity') is True], chars, p['top2_share'], c_large)
        n_large = large(counts, split + ':counts_large')
        for value in {stable(items[n]['answer']['value']) for n in counts}:
            scope = [n for n in counts if stable(items[n]['answer']['value']) == value]
            cap(scope, counts, p['modal_count_share'], n_large)
            for cid in chapters:
                model.Add(total([n for n in scope if items[n]['chapter_id'] == cid]) <= p['small_pool_absolute_cap']).OnlyEnforceIf(n_large.Not())
        p_large = large(pages, split + ':pages_large')
        ones = [n for n in pages if items[n]['features']['page_offset'] == 1]
        cap(ones, pages, p['page_plus_one_share'], p_large)
        for cid in chapters:
            model.Add(total([n for n in ones if items[n]['chapter_id'] == cid]) <= p['small_pool_absolute_cap']).OnlyEnforceIf(p_large.Not())
    pairs = defaultdict(list)
    for n, i in enumerate(items):
        if i.get('pair_id'):
            pairs[i['pair_id']].append(n)
    for scope in pairs.values():
        if len(scope) != 2 or len({items[n]['split'] for n in scope}) != 1:
            for n in scope:
                model.Add(xs[n] == 0)
        else:
            model.Add(xs[scope[0]] == xs[scope[1]])
    from .contrast import conflict_groups
    for scope in conflict_groups(items):
        model.Add(total(scope) <= 1)
    if not pilot:
        for n, item in enumerate(items):
            group = item['primary_group']; c = item.get('complexity', {})
            invalid = group == 'chain' and (type(c.get('meaningful_hops')) is not int or c['meaningful_hops'] < 3)
            invalid |= group == 'branch_combine' and (type(c.get('branch_count')) is not int or c['branch_count'] < 2 or len(set(c.get('necessary_pages', []))) < 2)
            invalid |= group == 'sentence' and (item['evidence_class'] != 'claim_verified' or item['verification'].get('claims') != 'verified')
            invalid |= group == 'paired' and (not item.get('pair_id') or item.get('edit_verification') != 'verified')
            if 'long_relational' in item.get('reasoning_tags', []):
                cert = item.get('long_relational_certificate', {})
                invalid |= cert.get('eligible') is not True or cert.get('necessary_clauses', 0) < 3 or len(set(cert.get('necessary_pages', []))) < 3 or cert.get('page_span', 0) < 5
            if invalid:
                model.Add(xs[n] == 0)
        model.Add(total(all_ids) == p['target_items'])
        model.Add(sum(chapters.values()) >= p['minimum_chapters'])
        for name, count in p['primary_groups'].items():
            model.Add(total(indices(lambda i: i['primary_group'] == name)) == count)
        model.Add(total(indices(lambda i: i['primary_group'] not in p['primary_groups'])) == 0)
        if p['split_counts'] is None:
            model.Add(0 == 1)
        else:
            for split, count in p['split_counts'].items():
                model.Add(total(indices(lambda i: i['split'] == split)) == count)
        ids = {}
        for identity in {i['features']['identity_id'] for i in items if i['features'].get('identity_id')}:
            flag = model.NewBoolVar('identity:' + identity)
            scope = indices(lambda i: i['features'].get('identity_id') == identity)
            model.Add(total(scope) >= 1).OnlyEnforceIf(flag)
            model.Add(total(scope) == 0).OnlyEnforceIf(flag.Not())
            ids[identity] = flag
        model.Add(sum(ids.values()) >= p['minimum_identities'])
        model.Add(total(indices(lambda i: 'long_relational' in i.get('reasoning_tags', []))) >= p['minimum_long_relational'])
        chars = indices(lambda i: bool(i['features'].get('identity_id')))
        ratio = Fraction(str(p['minimum_visual_character_share']))
        model.Add(ratio.denominator * total([n for n in chars if items[n]['answer_format'] == 'visual_choice']) >= ratio.numerator * total(chars))
    # Maximise yield, then chapter coverage. No claim of optimising every diversity dimension.
    model.Maximize(total(all_ids) * (len(chapters) + 1) + sum(chapters.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.Solve(model)
    status_name = {cp_model.OPTIMAL: 'optimal', cp_model.FEASIBLE: 'feasible',
                   cp_model.INFEASIBLE: 'infeasible', cp_model.UNKNOWN: 'unknown_budget_exhausted'}.get(status, 'invalid_model')
    chosen = [i for n, i in enumerate(items) if solver.Value(xs[n])] if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else []
    if chosen and violations(chosen, p, final=not pilot):
        raise RuntimeError('Solver/reference policy mismatch: ' + str(violations(chosen, p, final=not pilot)))
    return chosen, {'backend': 'cp_sat', 'status': status_name, 'mode': 'pilot' if pilot else 'final',
                    'policy_sha256': stable(p), 'selected_ids': [i['item_id'] for i in chosen],
                    'before': metrics(items), 'after': metrics(chosen), 'excluded': excluded,
                    'objective': 'maximise_count_then_chapter_coverage',
                    'best_bound': solver.BestObjectiveBound(), 'release_status': 'not_approved',
                    'policy': p, 'seconds_budget': seconds}
