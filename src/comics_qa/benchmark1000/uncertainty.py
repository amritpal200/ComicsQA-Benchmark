"""Read-only explanations of checked UNKNOWN/inexact executions."""
from collections import Counter
from comics_qa.evidence.graph.ckg_schema import REGISTRY
from .io import stable

CLOSED = {'closed_assumed', 'closed_verified', 'closed_audited'}
EXTRA = {'chars_on': ['char_boxes', 'names'], 'speaker_char': ['char_boxes', 'names', 'text_boxes', 'speaker_links'],
         'speaker': ['text_boxes', 'speaker_links'], 'line_count': ['char_boxes', 'names', 'text_boxes', 'speaker_links'],
         'quote': ['rich_ocr']}


def explain_atomic(doc, graph, rich, limit=16):
    steps = {s['nid']: s for s in doc['proof']['steps']}; nodes = {n['id']: n for n in graph['nodes']}
    order = {p: i + 1 for i, p in enumerate(graph['page_ids'])}
    coverage = {(c['page_id'], c['family']): c for c in graph['coverage']}
    if rich is not None:
        coverage.update({(c['page_id'], 'rich_ocr'): c for c in rich['coverage']})
    details = []
    for s in steps.values():
        if s['status'] == 'OK' and (s.get('exact', True) or s['type'] == 'Bool3' and type(s['value']) is bool):
            continue
        families = REGISTRY.get(s['op'], {}).get('coverage_families', EXTRA.get(s['op'], []))
        if not families and s['op'] != 'the':
            continue
        children = [steps[n] for n in s['children']]
        def scope(values):
            found = set()
            for child in values:
                value = child['value']
                if child['type'] == 'Page' and value in order: found.add(value)
                elif child['type'] in ('Span', 'Seq[Page]', 'Set[Page]') and isinstance(value, list): found.update(p for p in value if p in order)
                elif child['type'] in ('Text', 'App') and value in nodes and nodes[value].get('page_id') in order: found.add(nodes[value]['page_id'])
            return found
        pages = scope(children)
        if not pages:
            # For source lookup/selection, inspect a bounded descendant frontier.
            frontier = children
            for _ in range(4):
                frontier = [steps[n] for c in frontier for n in c['children']]
                pages = scope(frontier)
                if pages: break
        identities = set()
        for child in [s, *children]:
            values = [child['value']] if child['type'] == 'Char' else child['value'] if child['type'] in ('Set[Char]', 'Seq[Char]') and isinstance(child['value'], list) else []
            identities.update(v for v in values if v in nodes and nodes[v]['type'] == 'Character')
        requirements = []
        for page in sorted(pages, key=order.get):
            for family in families:
                c = coverage.get((page, family))
                requirements.append({'page_id': page, 'page_index': order[page], 'family': family,
                    'coverage_id': c.get('coverage_id', c.get('id')) if c else None,
                    'status': c['status'] if c else 'missing'})
        blockers = [c for c in requirements if c['status'] not in CLOSED]
        category = ('ambiguous_selection' if s['status'] == 'AMBIGUOUS' else 'open_coverage' if blockers
                    else 'unresolved_identity_or_selection' if s['op'] in ('speaker_char', 'speaker', 'the')
                    else 'inexact_predicate' if not s.get('exact', True) else 'unknown_predicate')
        details.append({'category': category, 'operator': s['op'], 'node_id': s['nid'], 'status': s['status'],
            'exact': s.get('exact', False), 'reason': s.get('reason') or 'Result is not exact',
            'page_ids': sorted(pages, key=order.get), 'page_indices': sorted(order[p] for p in pages),
            'known_identity_ids': sorted(identities), 'coverage_requirements': requirements, 'open_requirements': blockers,
            'execution_sha256': stable(doc), 'expression': s['expression'],
            'interpretation': 'Evidence requirements for this unresolved operation; closing a family alone is not an approval of a fact.'})
    if not details and (doc['result']['status'] != 'OK' or not doc['result'].get('exact', False)):
        r = doc['result']
        details.append({'category': 'inexact_collection' if not r.get('exact', False) and r['status'] == 'OK' else 'unproved_result',
                        'operator': 'result', 'status': r['status'], 'exact': r.get('exact', False),
                        'reason': r.get('reason') or 'Result is inexact; known positives are not a complete answer',
                        'page_ids': [], 'known_identity_ids': [], 'coverage_requirements': [], 'open_requirements': [],
                        'execution_sha256': stable(doc)})
    return details[:limit], len(details) > limit


def explain(engine, document, graph, rich, limit=16):
    def atoms(kind, doc, binding='root'):
        if kind == 'crl': yield binding, doc
        elif kind in ('scan', 'membership'):
            from .membership import known_truth
            for p in doc['probes']:
                if not known_truth(p['execution']['result']):
                    yield binding + ':page:' + str(p['page_number']), p['execution']
        else:
            for stage in doc['stages']:
                yield from atoms(stage['engine'], stage['execution'], stage.get('name', binding))
    details = []; truncated = False
    for binding, atomic in atoms(engine, document):
        rows, cut = explain_atomic(atomic, graph, rich, limit)
        details.extend({**r, 'binding': binding} for r in rows); truncated |= cut
    summary = dict(Counter(d['category'] for d in details))
    reason = next(iter(summary), document['result'].get('reason') or document['result']['status'])
    return {'reason_code': reason, 'categories': summary, 'details': details[:limit],
            'truncated': truncated or len(details) > limit, 'execution_sha256': stable(document), 'review_status': 'not_reviewed'}
