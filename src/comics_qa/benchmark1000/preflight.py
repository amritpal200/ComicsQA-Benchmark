"""Bounded capability inventory, not a claim that raw walks are valid QA proofs."""
from collections import Counter, defaultdict
from pathlib import Path
from .io import digest, member, read, verify_manifest
from .selection import metrics


def inspect_graphs(root, chapters=None, max_states=10000, depth=5):
    root = Path(root).resolve(); m = verify_manifest(root)
    if type(max_states) is not int or max_states < 1 or type(depth) is not int or not 1 <= depth <= 5:
        raise ValueError('Invalid preflight budget/depth')
    scope = sorted(chapters or m['config']['chapters'])
    if not set(scope) <= set(m['config']['chapters']):
        raise ValueError('Unknown chapter')
    reports = []
    for cid in scope:
        path = member(root, 'chapters/' + cid + '.json')
        if 'chapters/' + cid + '.json' not in m['outputs_sha256']:
            raise ValueError('Unmanifested graph')
        g = read(path)
        if g['chapter_id'] != cid:
            raise ValueError('Graph chapter mismatch')
        nodes = {n['id']: n for n in g['nodes']}
        # Only positive eligible links. Text, depiction, identity and page types remain distinct.
        adjacency = defaultdict(list)
        admitted = [f for f in g['facts'] if f['answer_eligible'] and f['origin'] in ('H', 'V')]
        for f in admitted:
            if f['rel'] in ('spoken_by', 'is_char', 'on_page', 'present', 'speaks_on', 'co_present'):
                args = [x for x in f['args'] if x in nodes]
                if len(args) >= 2:
                    adjacency[args[0]].append((args[1], f['rel']))
        pending = [(node, (node,), ()) for node in sorted(adjacency)]
        counts = Counter(); states = 0
        while pending and states < max_states:
            node, visited, rels = pending.pop(); states += 1
            if rels:
                counts[len(rels)] += 1
            if len(rels) == depth:
                continue
            for target, relation in sorted(adjacency[node]):
                if target not in visited:
                    pending.append((target, (*visited, target), (*rels, relation)))
        presence = defaultdict(set)
        for f in admitted:
            if f['rel'] == 'present':
                presence[f['args'][0]].add(f['args'][1])
        eligible = [n['id'] for n in g['nodes'] if n['type'] == 'Character' and not n['generic'] and len(presence[n['id']]) >= 2]
        coverage = Counter(c['family'] + ':' + c['status'] for c in g['coverage'])
        reports.append({'chapter_id': cid, 'split': g['split'], 'graph_sha256': digest(path),
                        'pages': len(g['page_ids']), 'named_cross_page_targets': sorted(eligible),
                        'coverage': dict(sorted(coverage.items())),
                        'eligible_relations': dict(Counter(f['rel'] for f in admitted)),
                        'structural_walks_by_depth': dict(counts), 'states_visited': states,
                        'truncated': bool(pending), 'gated_yield': None,
                        'limitations': 'Directed positive graph walks only; not meaningful-hop/necessity measurements or a QA yield estimate. Unreviewed ordering, panels and semantic mentions are not promoted.'})
    return {'chapters': reports, 'manifest_sha256': digest(root / 'manifest.json'),
            'status': 'structural_inventory_only', 'scope': 'selected_chapters' if chapters else 'full_collection', 'depth_budget': depth, 'state_budget_per_chapter': max_states}


def pool_report(items):
    nonfrequent = defaultdict(set)
    frequency_unknown = Counter()
    for i in items:
        cid = i['features'].get('identity_id')
        if cid and i['features'].get('is_frequent_legacy') is False:
            nonfrequent[i['split']].add(cid)
        elif cid and type(i['features'].get('is_frequent_legacy')) is not bool:
            frequency_unknown[i['split']] += 1
    return {'legacy_frequency_unknown': dict(frequency_unknown), 'distribution': metrics(items), 'nonfrequent_identities': {k: sorted(v) for k, v in nonfrequent.items()},
            'proofs_archived': sum(i['verification']['proof'] == 'archived_check' for i in items),
            'proofs_revalidated': sum(i['verification']['proof'] == 'verified' for i in items),
            'meaningful_depth_available': False, 'long_relational_yield': None}
