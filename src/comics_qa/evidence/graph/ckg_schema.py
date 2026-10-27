"""CKG-1 typed relation contract and structural validation (not a CRL proof checker)."""
import hashlib
import json

SCHEMA = 'comics_qa.ckg.v1'
BUILDER_VERSION = 'ckg1.1'
TRUST = {'M': 0, 'A': 1, 'V': 2, 'H': 3}
CLOSED = {'closed_assumed', 'closed_verified', 'closed_audited'}


def stable_id(prefix, value):
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return prefix + hashlib.sha256(data.encode()).hexdigest()


def relation(signature, families, gloss, *, functional=False, derivation='S', symmetric=False):
    return {'signature': signature, 'coverage_families': families, 'functional': functional,
            'monotonicity': 'positive', 'derivation': derivation, 'symmetric': symmetric,
            'hop_weight': 1, 'gloss': gloss,
            'origin_policy': 'minimum premise/source trust; panel facts M; human and dataset structure H'}


REGISTRY = {
    'page_in': relation(['Page', 'Chapter'], ['page_sequence'], 'page belongs to chapter', functional=True),
    'next_page': relation(['Page', 'Page'], ['page_sequence'], 'next supplied image in chapter order', functional=True),
    'on_page': relation(['Appearance|Text|Tail|Panel', 'Page'], [], 'region is on page', functional=True),
    'is_char': relation(['Appearance', 'Character'], ['char_boxes', 'names'], 'appearance represents character', functional=True, derivation='R'),
    'named': relation(['Character', 'Str'], ['names'], 'character has exact human name', functional=True),
    'alias': relation(['Character', 'Str'], ['names'], 'unambiguous stored alias of character', derivation='R'),
    'spoken_by': relation(['Text', 'Appearance'], ['text_boxes', 'speaker_links'], 'human text-to-speaker link'),
    'has_tail': relation(['Text', 'Tail'], ['text_boxes', 'speaker_links'], 'human text-to-tail link'),
    'is_line': relation(['Text'], ['text_boxes', 'speaker_links'], 'text has a human speaker link', derivation='R'),
    'present': relation(['Character', 'Page'], ['char_boxes', 'names'], 'at least one appearance of character on page', derivation='R'),
    'speaks_on': relation(['Character', 'Page'], ['char_boxes', 'names', 'text_boxes', 'speaker_links'], 'character has a linked line on page', derivation='R'),
    'co_present': relation(['Character', 'Character', 'Page'], ['char_boxes', 'names'], 'two distinct characters present on page', derivation='R', symmetric=True),
}


def scope_is_closed(graph, page_ids, families):
    """Coverage helper only; callers must supply the complete operation scope/families."""
    known = set(graph['page_ids'])
    if not page_ids or not families or not set(page_ids) <= known:
        return False
    certs = {(c['page_id'], c['family']): c['status'] for c in graph['coverage']}
    return all(certs.get((p, f)) in CLOSED for p in page_ids for f in families)


def validate_graph(graph):
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    require(graph['schema'] == SCHEMA, 'Unsupported graph schema')
    nodes = {n['id']: n for n in graph['nodes']}
    facts = {f['fact_id']: f for f in graph['facts']}
    certs = {c['coverage_id']: c for c in graph['coverage']}
    require(len(nodes) == len(graph['nodes']), 'Duplicate node ID')
    require(len(facts) == len(graph['facts']), 'Duplicate fact ID')
    require(len(certs) == len(graph['coverage']), 'Duplicate coverage ID')
    require(nodes[graph['chapter_id']]['type'] == 'Chapter', 'Missing chapter node')
    page_ids = graph['page_ids']
    require(len(page_ids) == len(set(page_ids)), 'Duplicate chapter page')
    require({n['id'] for n in nodes.values() if n['type'] == 'Page'} == set(page_ids), 'Chapter page set differs')
    for c in certs.values():
        require(c['page_id'] in page_ids and c['status'] in CLOSED | {'open', 'absent'}, 'Invalid coverage')
    require(len({(c['page_id'], c['family']) for c in certs.values()}) == len(certs), 'Duplicate family coverage')
    families = {'char_boxes','names','text_boxes','speaker_links','panels','reading_order','ocr','page_sequence'}
    require({(c['page_id'], c['family']) for c in certs.values()} == {(p,f) for p in page_ids for f in families},
            'Incomplete page/family coverage')
    by_family = {(c['page_id'], c['family']): c['coverage_id'] for c in certs.values()}
    for n in nodes.values():
        require(n['origin'] in TRUST and n['sources'], 'Node lacks provenance')
        if 'page_id' in n:
            require(n['page_id'] in page_ids, 'Node refers outside chapter')
        if n['type'] == 'Character' and n['generic']:
            require(n['canonical_name'] is None and not n['aliases'], 'Generic identity has name/aliases')
    functional = {}
    for f in facts.values():
        require(f['rel'] in REGISTRY, 'Unknown relation')
        reg = REGISTRY[f['rel']]
        require(len(f['args']) == len(reg['signature']), 'Wrong relation arity')
        for value, expected in zip(f['args'], reg['signature']):
            if expected == 'Str':
                require(isinstance(value, str) and bool(value), 'Invalid string literal')
            else:
                require(value in nodes and nodes[value]['type'] in expected.split('|'), 'Relation type/reference mismatch')
        require(f['origin'] in TRUST and f['sources'], 'Fact lacks source provenance')
        require(f['derivation'] == reg['derivation'], 'Wrong relation derivation')
        require(set(f['coverage_refs']) <= certs.keys(), 'Missing fact coverage reference')
        require(f['page_ids'] and set(f['page_ids']) <= set(page_ids), 'Fact scope outside chapter')
        needed = reg['coverage_families']
        if f['rel'] == 'on_page':
            needed = {'Appearance':['char_boxes'], 'Text':['text_boxes'], 'Tail':['speaker_links'], 'Panel':['panels']}[nodes[f['args'][0]]['type']]
            require(nodes[f['args'][0]]['page_id'] == f['args'][1], 'Incorrect region page')
        if f['rel'] in ('spoken_by', 'has_tail'):
            require(nodes[f['args'][0]]['page_id'] == nodes[f['args'][1]]['page_id'], 'Cross-page human link')
        require(set(f['coverage_refs']) == {by_family[p,family] for p in f['page_ids'] for family in needed},
                'Fact coverage does not match relation/scope')
        require(f['answer_eligible'] == (f['origin'] in ('H', 'V')), 'Incorrect trust eligibility')
        if reg['functional']:
            key = (f['rel'], f['args'][0])
            require(key not in functional or functional[key] == f['args'][1], 'Functional relation conflict')
            functional[key] = f['args'][1]
        if reg['symmetric']:
            require(f['args'][0] < f['args'][1], 'Symmetric relation must use canonical distinct pair')
        if f['rel'] in ('named', 'alias'):
            require(not nodes[f['args'][0]]['generic'], 'Generic character has naming fact')
        require(f['derivation'] != 'R' or f['premises'], 'Derived fact lacks premises')
        for pid in f['premises']:
            require(pid in facts, 'Missing premise')
            require(TRUST[f['origin']] <= TRUST[facts[pid]['origin']], 'Derived fact promotes trust')
        for arg, expected in zip(f['args'], reg['signature']):
            if expected != 'Str':
                require(TRUST[f['origin']] <= TRUST[nodes[arg]['origin']], 'Fact promotes node trust')
    # Check premise DAG, including cycles that contain only existing IDs.
    done, active = set(), set()
    def visit(fid):
        require(fid not in active, 'Cyclic fact premises')
        if fid in done:
            return
        active.add(fid)
        for premise in facts[fid]['premises']:
            visit(premise)
        active.remove(fid)
        done.add(fid)
    for fid in facts:
        visit(fid)
    require({tuple(f['args']) for f in facts.values() if f['rel'] == 'next_page'} == set(zip(page_ids, page_ids[1:])),
            'Chapter adjacency differs from complete page sequence')
    require({tuple(f['args']) for f in facts.values() if f['rel'] == 'page_in'} == {(p,graph['chapter_id']) for p in page_ids},
            'Incomplete chapter membership')
    return True
