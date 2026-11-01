"""Versioned ordered task-specific packs; no automatic natural-language certification."""
from .io import stable
from .claims import validate_claims


def prepare(item, mode='paraphrase', claims=None, crops=(), max_characters=60000):
    if mode not in ('paraphrase', 'synthesis'):
        raise ValueError('Unknown wording mode')
    if mode == 'paraphrase' and crops:
        raise ValueError('Paraphrase is text-only')
    if mode == 'synthesis':
        validate_claims(claims)
        if not crops:
            raise ValueError('Synthesis needs explicitly verified evidence crops')
    legacy = item['legacy']; proof = legacy['execution']['proof']
    # Ordered pages are retained in full; irrelevant fact bodies are not supplied.
    page_order = [{'page_id': p['page_id'], 'index': p['index']} for p in legacy['context']['pages']]
    steps = [{'node': s['nid'], 'op': s['op'], 'children': s['children'],
              'value': s['value'], 'status': s['status'], 'facts': s['facts']}
             for s in proof['steps']]
    pack = {'schema': 'comics_qa.benchmark1000.pack.1', 'mode': mode,
            'item_id': item['item_id'], 'item_sha256': stable(item),
            'chapter_context': {'pages': page_order, 'page_numbering': '1-based displayed chapter order'},
            'target': {'program': legacy['program'], 'answer': item['answer']} if mode == 'paraphrase' else {'claims': claims},
            'template': item['question'], 'dependency_steps': steps,
            'evidence': {'fact_ids': proof['facts'], 'coverage_ids': proof['certificates'],
                         'source_pins': legacy['execution']['inputs_sha256']},
            'evidence_crops': list(crops),
            'boundaries': ['No motives, cause, addressee or unverified narrative chronology',
                           'No extra relations or changed scope; preserve every necessary clause',
                           'Page order differs from dependency traversal order'],
            'validation_status': 'pending_evidence_hydration'}
    # Fact IDs alone are not the fact bodies required by the final MN5 contract.
    if len(str(pack)) > max_characters:
        raise ValueError('Pack exceeds context preflight budget; no silent truncation')
    pack['pack_id'] = 'b1000-pack:' + stable(pack)
    return pack


def hydrate(pack, graph, rich=None, visibility=None, verified_pins=None):
    """Resolve cited facts/nodes only; preserve source provenance and coverage."""
    if verified_pins is None or visibility is None:
        raise ValueError('Hydration requires a validated graph/visibility loader and its pins')
    def roles(mapping):
        return {str(p).split('/evidence/', 1)[1]: sha for p, sha in mapping.items() if '/evidence/' in str(p)}
    if roles(verified_pins) != roles(pack['evidence']['source_pins']):
        raise ValueError('Evidence pack sources differ from loaded snapshots')
    if [p['page_id'] for p in pack['chapter_context']['pages']] != graph['page_ids']:
        raise ValueError('Pack page order differs from graph')
    lookup = {f['fact_id']: f for f in graph['facts']}
    if rich:
        lookup.update({f['id']: f for f in rich['facts']})
    facts = []
    nodes = {n['id']: n for n in graph['nodes']}
    refs = set()
    for fid in pack['evidence']['fact_ids']:
        if fid not in lookup:
            raise ValueError('Evidence fact unavailable: ' + fid)
        fact = lookup[fid]
        if not fact['answer_eligible'] or fact['origin'] not in ('H', 'V'):
            raise ValueError('Unadmitted pack fact')
        facts.append(fact)
        refs.update(x for x in fact['args'] if x in nodes)
    readable = {row['identity_id']: row['verified_forms'] for row in visibility['visibility']}
    safe_nodes = []
    for nid in sorted(refs):
        allowed = {'id', 'type', 'origin', 'page_id', 'box', 'width', 'height', 'image_sha256', 'generic', 'scope', 'chapter_id'}
        node = {k: value for k, value in nodes[nid].items() if k in allowed}
        if node['type'] == 'Character':
            node.pop('canonical_name', None); node.pop('aliases', None)
            node['readable_name_forms'] = readable.get(nid, [])
        safe_nodes.append(node)
    certificates = {c['coverage_id']: c for c in graph['coverage']}
    if rich:
        certificates.update({c['id']: c for c in rich['coverage']})
    missing = set(pack['evidence']['coverage_ids']) - certificates.keys()
    if missing:
        raise ValueError('Pack coverage certificate unresolved: ' + str(sorted(missing)))
    result = {**pack, 'fact_bodies': facts, 'node_bodies': safe_nodes,
              'coverage_bodies': [certificates[c] for c in pack['evidence']['coverage_ids']],
              'validation_status': 'hydrated_not_wording_verified'}
    if len(str(result)) > 60000:
        raise ValueError('Hydrated pack exceeds context preflight budget; no silent truncation')
    result['pack_id'] = 'b1000-pack:' + stable({k: v for k, v in result.items() if k != 'pack_id'})
    return result


def validate_paraphrase(item, response, checker, interpreter):
    """Response must include independently back-parsed CRL; matching answer alone fails."""
    from comics_qa.tasks.graph.crl.language import parse, program_hash
    if set(response) != {'question', 'back_parsed_program', 'parser_provenance'}:
        raise ValueError('Malformed paraphrase response')
    if not response['question'].strip() or not response['parser_provenance']:
        raise ValueError('Question/parser provenance missing')
    expected = item['legacy']['program']
    parsed = parse(response['back_parsed_program'])
    # Conservative syntactic equivalence: semantically different rewrites need an explicit checker.
    if program_hash(parsed) != program_hash(parse(expected)):
        return {'status': 'held', 'reason': 'program_meaning_not_matched'}
    document = interpreter.execute(parsed)
    checked = checker.check(document, expected)
    if not checked['accepted_for_generation']:
        return {'status': 'held', 'reason': 'proof_not_verified'}
    return {'status': 'held', 'reason': 'program_matched_but_independent_question_alignment_pending',
            'check': checked, 'response_sha256': stable(response)}
