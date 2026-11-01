"""Target-first clue puzzles with executable clause-removal certificates."""
from itertools import combinations
from collections import defaultdict
from comics_qa.tasks.graph.crl.language import call
from comics_qa.tasks.graph.generation.proposals import Proposal, conjunction, named
from .io import stable


def propose(graph, budget=20, search_budget=2000, statistics=None):
    if type(budget) is not int or type(search_budget) is not int or min(budget, search_budget) < 1:
        raise ValueError('Positive proposal/search budgets required')
    stats = statistics if statistics is not None else {}
    stats.update(combinations_tested=0, proposals_emitted=0, search_budget_hit=False, proposal_budget_hit=False, search_exhausted=False)
    nodes = {n['id']: n for n in graph['nodes']}
    index = {p: i + 1 for i, p in enumerate(graph['page_ids'])}
    members = defaultdict(set)
    for f in graph['facts']:
        if f['answer_eligible'] and f['origin'] in ('H', 'V') and f['rel'] in ('present', 'speaks_on'):
            cid, pid = f['args']
            if not nodes[cid]['generic']:
                members[pid, f['rel']].add(cid)
    targets = sorted({c for values in members.values() for c in values}, key=stable)
    tried = emitted = 0
    seen = set()
    for target in targets:
        choices = sorted([key for key, values in members.items() if target in values], key=lambda key: stable([target, key]))
        for keys in combinations(choices, 3):
            tried += 1
            if tried > search_budget:
                stats['search_budget_hit'] = True
                return
            stats['combinations_tested'] = tried
            pages = [pid for pid, _ in keys]
            if len(set(pages)) < 3 or max(index[p] for p in pages) - min(index[p] for p in pages) < 5:
                continue
            if len({rel for _, rel in keys}) < 2:
                continue
            candidates = set.intersection(*(members[key] for key in keys))
            if candidates != {target}:
                continue
            # Cheap known-member necessity filter; the actual gate proves exactness.
            if any(set.intersection(*(members[k] for j, k in enumerate(keys) if j != at)) == {target} for at in range(3)):
                continue
            clauses = []
            descriptions = []
            for pid, rel in keys:
                p = index[pid]
                if rel == 'present':
                    clauses.append(call('chars_on', call('page', p)))
                    descriptions.append(f'On page {p}, this character is drawn in at least one character depiction.')
                else:
                    clauses.append(call('distinct', call('map', call('lines', call('page', p)),
                                                       {'lambda': {'param': 't', 'body': call('speaker_char', {'var': 't'})}})))
                    descriptions.append(f'At least one dialogue text region on page {p} has this character as its speaker.')
            ast = call('the', named(conjunction(clauses)))
            key = stable(ast)
            if key in seen:
                continue
            seen.add(key)
            question = ('Find the one character who satisfies every condition below. Treat the page numbers as positions '
                        'in the supplied chapter, starting at 1. All conditions must hold for the same person; matching '
                        'only some of the conditions is not enough. ' +
                        ' '.join(f'({n + 1}) {text}' for n, text in enumerate(descriptions)) +
                        ' Combine the evidence from these different pages and give the character’s name.')
            relaxations = [call('the', named(conjunction([c for n, c in enumerate(clauses) if n != remove]))) for remove in range(3)]
            stats['proposals_emitted'] = emitted + 1
            yield Proposal('long_relational_clue', 'target_first_constraint_accretion', ast, question,
                           level='L2', anchors=[index[p] for p in pages], clauses=descriptions,
                           relaxations=relaxations, target_answer=target)
            emitted += 1
            if emitted >= budget:
                stats['proposal_budget_hit'] = True
                return
    stats['search_exhausted'] = True


def certify(item):
    """Certify only measured dimensions. Word count is not a difficulty claim."""
    removals = item['gates']['G6']['removals']
    pages = item['dimensions']['necessary_pages']
    order = {p['page_id']: p['index'] for p in item['context']['pages']}
    span = max((order[p] for p in pages), default=0) - min((order[p] for p in pages), default=0)
    words = len(item['question'].split())
    return {'eligible': len(removals) >= 3 and len(set(pages)) >= 3 and span >= 5 and words >= 81,
            'necessary_clauses': len(removals), 'necessary_pages': pages, 'page_span': span,
            'word_count': words, 'length_class': 'XL' if words > 250 else 'L' if words >= 81 else 'short',
            'meaningful_hops': None, 'branch_count': len(removals),
            'limitations': 'Clue conjunction only; relation walks/maps, comparison stories, multi-part and noise forms remain separate work.'}
