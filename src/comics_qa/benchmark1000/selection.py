"""Deterministic bounded exact search. Never calls a heuristic infeasibility proof."""
from collections import Counter, defaultdict
from fractions import Fraction
import math
from .io import stable

FIELDS = {'version', 'target_items', 'minimum_chapters', 'maximum_per_chapter',
          'minimum_identities', 'minimum_long_relational', 'minimum_visual_character_share',
          'two_option_share', 'minimum_denominator', 'small_pool_absolute_cap',
          'identity_share', 'page_plus_one_share', 'modal_count_share', 'top1_share',
          'top2_share', 'primary_groups', 'split_counts', 'interpretive_allowed',
          'legacy_policy', 'coverage', 'human_sentence_review'}


def policy(raw):
    if set(raw) != FIELDS:
        raise ValueError('Missing/unknown selection policy fields')
    if raw['version'] != 'benchmark1000.policy.1' or raw['coverage'] != 'closed_or_explicit_closed_assumed' or raw['human_sentence_review'] != 'every_item':
        raise ValueError('Unsupported version/coverage/review policy')
    for key in ('target_items', 'minimum_chapters', 'maximum_per_chapter', 'minimum_identities',
                'minimum_long_relational', 'minimum_denominator', 'small_pool_absolute_cap'):
        if type(raw[key]) is not int or raw[key] < (1 if key in ('target_items', 'maximum_per_chapter', 'minimum_denominator') else 0):
            raise ValueError('Invalid policy integer: ' + key)
    for key in ('minimum_visual_character_share', 'two_option_share', 'identity_share',
                'page_plus_one_share', 'modal_count_share', 'top1_share', 'top2_share'):
        if type(raw[key]) not in (int, float) or not math.isfinite(raw[key]) or not 0 <= raw[key] <= 1:
            raise ValueError('Invalid policy share: ' + key)
    if raw['interpretive_allowed'] is not False or raw['legacy_policy'] != 'unchanged':
        raise ValueError('Interpretive items or legacy mutation prohibited')
    if not isinstance(raw['primary_groups'], dict) or any(type(v) is not int or v < 0 for v in raw['primary_groups'].values()):
        raise ValueError('Invalid primary group allocation')
    if sum(raw['primary_groups'].values()) != raw['target_items']:
        raise ValueError('Primary allocations must sum to target')
    if raw['split_counts'] is not None:
        if set(raw['split_counts']) != {'seen', 'unseen'} or any(type(v) is not int or v < 0 for v in raw['split_counts'].values()) or sum(raw['split_counts'].values()) != raw['target_items']:
            raise ValueError('Invalid split counts')
    return raw


def metrics(items):
    result = {}
    for split in sorted({i['split'] for i in items}):
        group = [i for i in items if i['split'] == split]
        chars = [i for i in group if i['features'].get('identity_id')]
        counts = [i for i in group if i['answer_format'] == 'count']
        pages = [i for i in group if i['answer_format'] == 'page' and i['features'].get('page_offset') is not None]
        def rate(n, d):
            return n / d if d else None
        ids = Counter(i['features']['identity_id'] for i in chars)
        values = Counter(stable(i['answer']['value']) for i in counts)
        top1_known = [i for i in chars if type(i['features'].get('is_top1_identity')) is bool]
        result[split] = {
            'items': len(group), 'chapters': len({i['chapter_id'] for i in group}),
            'character_targets': len(chars), 'distinct_identities': len(ids),
            'maximum_identity_share': rate(max(ids.values(), default=0), len(chars)),
            'top1_accuracy': rate(sum(i['features']['is_top1_identity'] for i in top1_known), len(chars)) if len(top1_known) == len(chars) else None,
            'top1_unknown': len(chars) - len(top1_known),
            'top2_oracle_accuracy': rate(sum(i['features']['is_top2_identity'] for i in chars), len(chars)) if all(type(i['features'].get('is_top2_identity')) is bool for i in chars) else None,
            'count_targets': len(counts), 'distinct_count_values': len(values),
            'modal_count_accuracy': rate(max(values.values(), default=0), len(counts)),
            'anchored_page_targets': len(pages),
            'page_plus_one_accuracy': rate(sum(i['features']['page_offset'] == 1 for i in pages), len(pages)),
            'two_option_share': rate(sum(i['features']['two_option'] for i in group), len(group)),
        }
    return result


def violations(items, p, final=False):
    errors = []
    if any(i.get('admission') == 'proposal' for i in items):
        errors.append('unadmitted_native_proposal')
    chapters = Counter(i['chapter_id'] for i in items)
    if any(n > p['maximum_per_chapter'] for n in chapters.values()):
        errors.append('maximum_per_chapter')
    if any(i['evidence_class'] == 'interpretive' for i in items):
        errors.append('interpretive_excluded')
    def over(n, d, cap):
        return d > 0 and Fraction(n, d) > Fraction(str(cap))
    if over(sum(i['features']['two_option'] for i in items), len(items), p['two_option_share']):
        errors.append('two_option_share')
    for split in {i['split'] for i in items}:
        group = [i for i in items if i['split'] == split]
        chars = [i for i in group if i['features'].get('identity_id')]
        counts = [i for i in group if i['answer_format'] == 'count']
        pages = [i for i in group if i['answer_format'] == 'page' and i['features'].get('page_offset') is not None]
        if len(chars) >= p['minimum_denominator']:
            ids = Counter(i['features']['identity_id'] for i in chars)
            if over(max(ids.values(), default=0), len(chars), p['identity_share']):
                errors.append(split + ':identity_share')
            if any(type(i['features'].get('is_top1_identity')) is not bool for i in chars):
                errors.append(split + ':unknown_top1_features')
            elif over(sum(i['features']['is_top1_identity'] for i in chars), len(chars), p['top1_share']):
                errors.append(split + ':top1_share')
            if any(type(i['features'].get('is_top2_identity')) is not bool for i in chars):
                errors.append(split + ':unknown_top2_features')
            elif over(sum(i['features']['is_top2_identity'] for i in chars), len(chars), p['top2_share']):
                errors.append(split + ':top2_share')
        else:
            same = Counter((i['chapter_id'], i['features']['identity_id']) for i in chars)
            if max(same.values(), default=0) > p['small_pool_absolute_cap']:
                errors.append(split + ':small_pool_identity_cap')
        for subset, key, cap, label in [
                (counts, lambda i: stable(i['answer']['value']), p['modal_count_share'], 'modal_count'),
                (pages, lambda i: i['features']['page_offset'] == 1, p['page_plus_one_share'], 'page_plus_one')]:
            if len(subset) >= p['minimum_denominator']:
                n = max(Counter(key(i) for i in subset).values()) if label == 'modal_count' else sum(key(i) for i in subset)
                if over(n, len(subset), cap):
                    errors.append(split + ':' + label)
            else:
                hist = Counter((i['chapter_id'], key(i)) for i in subset)
                # For page+1, only +1 is the shortcut; other gaps are not a single answer.
                if label == 'page_plus_one':
                    hist = Counter(i['chapter_id'] for i in subset if key(i))
                if max(hist.values(), default=0) > p['small_pool_absolute_cap']:
                    errors.append(split + ':small_pool_' + label)
    if final:
        if len(items) != p['target_items']:
            errors.append('target_items')
        if len(chapters) < p['minimum_chapters']:
            errors.append('minimum_chapters')
        chars = [i for i in items if i['features'].get('identity_id')]
        if len({i['features']['identity_id'] for i in chars}) < p['minimum_identities']:
            errors.append('minimum_identities')
        if sum('long_relational' in i.get('reasoning_tags', []) for i in items) < p['minimum_long_relational']:
            errors.append('minimum_long_relational')
        if chars and Fraction(sum(i['answer_format'] == 'visual_choice' for i in chars), len(chars)) < Fraction(str(p['minimum_visual_character_share'])):
            errors.append('minimum_visual_character_share')
        if Counter(i['primary_group'] for i in items) != Counter({k: v for k, v in p['primary_groups'].items() if v}):
            errors.append('primary_groups')
        if p['split_counts'] is None:
            errors.append('split_counts_unconfigured')
        elif Counter(i['split'] for i in items) != Counter({k: v for k, v in p['split_counts'].items() if v}):
            errors.append('split_counts')
        for item in items:
            group = item['primary_group']; complexity = item.get('complexity', {})
            if group == 'chain' and (type(complexity.get('meaningful_hops')) is not int or complexity['meaningful_hops'] < 3):
                errors.append('chain_complexity_uncertified')
            if group == 'branch_combine' and (type(complexity.get('branch_count')) is not int or complexity['branch_count'] < 2 or len(set(complexity.get('necessary_pages', []))) < 2):
                errors.append('branch_complexity_uncertified')
            if group == 'sentence' and (item['evidence_class'] != 'claim_verified' or item['verification'].get('claims') != 'verified'):
                errors.append('sentence_claims_unverified')
            if group == 'paired' and (not item.get('pair_id') or item.get('edit_verification') != 'verified'):
                errors.append('paired_edit_unverified')
            if 'long_relational' in item.get('reasoning_tags', []):
                cert = item.get('long_relational_certificate', {})
                if cert.get('eligible') is not True or cert.get('necessary_clauses', 0) < 3 or len(set(cert.get('necessary_pages', []))) < 3 or cert.get('page_span', 0) < 5:
                    errors.append('long_relational_certificate_missing')
        if any(i['verification'].get('proof') != 'verified' for i in items):
            errors.append('proof_revalidation_pending')
    # Pair closure is mandatory for pilot and final selections.
    pairs = defaultdict(list)
    for i in items:
        if i.get('pair_id'):
            pairs[i['pair_id']].append(i)
    if any(len(v) != 2 or len({i['split'] for i in v}) != 1 for v in pairs.values()):
        errors.append('pair_closure')
    from .contrast import conflict_groups
    if conflict_groups(items):
        errors.append('repeated_contrast_task')
    return sorted(set(errors))


def select(items, raw_policy, pilot=False, max_nodes=100000):
    p = policy(raw_policy)
    if type(max_nodes) is not int or max_nodes < 1:
        raise ValueError('Invalid search budget')
    # Dedup task semantics without dropping intentional contrast pairs.
    unique, discarded, seen = [], {}, set()
    for i in sorted(items, key=lambda x: x['item_id']):
        key = (i['chapter_id'], i['features']['semantic_target'], i.get('pair_id'), i['item_id'] if i.get('pair_id') else None)
        if key in seen:
            discarded[i['item_id']] = 'policy:duplicate_semantic_target'
        else:
            seen.add(key); unique.append(i)
    report = {'mode': 'pilot' if pilot else 'final', 'policy_sha256': stable(p),
              'before': metrics(unique), 'excluded': discarded, 'nodes_visited': 0,
              'release_status': 'not_approved', 'policy': p}
    if not pilot and len(unique) < p['target_items']:
        return [], {**report, 'status': 'infeasible', 'reason': 'too_few_distinct_candidates', 'after': {}}
    best, exhausted = [], False
    stack = [(0, [])]
    while stack and report['nodes_visited'] < max_nodes:
        at, chosen = stack.pop(); report['nodes_visited'] += 1
        if pilot and len(chosen) + len(unique) - at <= len(best):
            continue
        if not pilot and (len(chosen) > p['target_items'] or len(chosen) + len(unique) - at < p['target_items']):
            continue
        # Ratio violations can be repaired by later additions. Check only at leaves.
        if at == len(unique):
            if not violations(chosen, p, final=not pilot):
                if not pilot:
                    best = chosen; break
                if len(chosen) > len(best):
                    best = chosen
            continue
        stack.append((at + 1, chosen))
        if sum(i['chapter_id'] == unique[at]['chapter_id'] for i in chosen) < p['maximum_per_chapter']:
            stack.append((at + 1, chosen + [unique[at]]))
    else:
        exhausted = not stack
    if best:
        status = 'optimal' if pilot and exhausted else 'feasible'
    else:
        status = ('optimal' if pilot else 'infeasible') if exhausted else 'unknown_budget_exhausted'
    report.update(status=status, search_exhausted=exhausted, after=metrics(best),
                  selected_ids=[i['item_id'] for i in best],
                  limitations='Bounded exact enumeration; use a larger budget or future solver backend for large feasible pools. Pilot ignores final size/group/coverage floors, not baseline policy.')
    return best, report
