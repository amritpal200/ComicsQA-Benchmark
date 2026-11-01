"""Native proposal contract, independent answer checks and explicit admission states."""
import copy
from .io import stable

SCHEMA = 'comics_qa.benchmark1000.native.1'


def validate(item):
    from .contract import EVIDENCE, MODES, STRUCTURES, FORMATS
    if item.get('schema') != SCHEMA:
        raise ValueError('Wrong native schema')
    for key, allowed in [('evidence_class', EVIDENCE), ('generation_mode', MODES),
                         ('reasoning_structure', STRUCTURES), ('answer_format', FORMATS)]:
        if item.get(key) not in allowed:
            raise ValueError('Invalid native ' + key)
    body = {k: v for k, v in item.items() if k not in ('schema', 'item_id')}
    if item['item_id'] != 'b1000n:' + stable(body):
        raise ValueError('Native content hash mismatch')
    if item['split'] not in ('seen', 'unseen') or not isinstance(item.get('chapter_id'), str) or not item['chapter_id'] or not isinstance(item.get('question'), str) or not item['question'].strip():
        raise ValueError('Missing native chapter/split/question')
    for key in ('context', 'answer', 'source', 'verification', 'complexity', 'features'):
        if not isinstance(item.get(key), dict):
            raise ValueError('Missing native ' + key)
    # This schema admits proposals, not unimplemented gate certifications.
    if item['admission'] != 'proposal' or item['verification']['gates'] != 'pending' or item['verification']['release'] != 'pending':
        raise ValueError('Native proposal cannot self-promote to a released candidate')
    if item['verification']['human'] != 'pending' or item['verification']['wording'] != 'pending':
        raise ValueError('Native approval needs a separate version-bound review record')
    if not isinstance(item['complexity'].get('necessary_pages'), list):
        raise ValueError('Native record needs explicit necessary_pages, possibly empty while pending')
    if not item['context'].get('pages') or len({p['page_id'] for p in item['context']['pages']}) != len(item['context']['pages']):
        raise ValueError('Missing/duplicate native context pages')
    if item['proof_engine'] not in ('crl', 'scan', 'relay', 'recipe', 'coverage_recipe', 'pending'):
        raise ValueError('Unknown native proof engine')
    if item['verification']['proof'] not in ('pending', 'verified'):
        raise ValueError('Invalid native proof status')
    if item['verification']['proof'] == 'verified':
        receipt = item.get('answer_check', {})
        if receipt.get('answer_supported') is not True or receipt.get('execution_sha256') != stable(item['execution']) or receipt.get('answer_sha256') != stable(item['answer']):
            raise ValueError('Native proof receipt mismatch')
    if item['proof_engine'] == 'pending':
        if item['verification']['proof'] != 'pending' or item['execution'] is not None:
            raise ValueError('Pending native record cannot claim an executed proof')
    elif item['proof_engine'] in ('crl', 'recipe', 'coverage_recipe'):
        # CRL execution canonicalises commutative operands and normalises its AST.
        # Bind with the same official canonical hash as the independent checker.
        from comics_qa.tasks.graph.crl.language import parse, program_hash
        if program_hash(parse(item['execution']['program'])) != program_hash(parse(item['program'])):
            raise ValueError('Native program/execution binding mismatch')
    elif stable(item['execution']['program']) != stable(item['program']):
        raise ValueError('Native program/execution binding mismatch')
    if item['answer_format'] == 'visual_choice':
        options = item.get('options')
        if not isinstance(options, list) or len(options) != 4 or {o['label'] for o in options} != set('ABCD') or item['answer']['value'] not in set('ABCD'):
            raise ValueError('Visual choice needs four labelled options and a valid answer')
    if item['answer_format'] == 'sentence':
        claims = item.get('claims')
        if not isinstance(claims, dict) or not claims.get('required') or item['verification'].get('claims') != 'pending':
            raise ValueError('Sentence proposal needs claims awaiting independent certification')
    return item


def check_answer(item, graph, visibility, rich):
    from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
    from .scan import ScanChecker
    from .relay import RelayChecker
    validate(item)
    expected_sources = {'graph': stable(graph), 'visibility': stable(visibility), 'rich': stable(rich)}
    if item['source']['snapshots'] != expected_sources or item['chapter_id'] != graph['chapter_id'] or item['split'] != graph['split']:
        raise ValueError('Native proposal sources differ from loaded snapshots')
    nodes = {n['id']: n for n in graph['nodes']}
    expected_context = [{'page_id': p, 'index': n + 1, 'image_path': nodes[p]['image_path'],
                         'image_sha256': nodes[p]['image_sha256'], 'relative_path': nodes[p]['relative_path']}
                        for n, p in enumerate(graph['page_ids'])]
    if item['context']['pages'] != expected_context:
        raise ValueError('Native context differs from loaded chapter')
    if item.get('evidence') != execution_evidence(item['proof_engine'], item['execution'], graph, rich):
        raise ValueError('Native evidence provenance differs from executed support')
    if item['proof_engine'] == 'pending':
        return {'proof_valid': False, 'answer_supported': False, 'status': 'PENDING_CERTIFICATION'}
    doc = item['execution']
    if item['proof_engine'] in ('recipe', 'coverage_recipe'):
        from .recipe_engine import RecipeChecker
        result = RecipeChecker(graph, visibility, rich, membership_refinement=item['proof_engine'] == 'coverage_recipe').check(doc, item['program'])
        supported = result['proof_valid'] and result['answer_supported']
    elif item['proof_engine'] == 'crl':
        result = ProofChecker(graph, visibility, rich=rich).check(doc, item['program'])
        supported = result['proof_valid'] and doc['result']['status'] == 'OK' and doc['result']['exact']
    else:
        result = (ScanChecker(graph, visibility, rich) if item['proof_engine'] == 'scan' else RelayChecker(graph, visibility, rich)).check(doc)
        supported = result.get('proof_valid') and result.get('answer_supported')
    if supported and item['proof_engine'] not in ('crl', 'recipe', 'coverage_recipe') and item['answer_format'] != 'page':
        supported = False
    if supported and item['proof_engine'] in ('crl', 'recipe', 'coverage_recipe'):
        expected_types = {'page': 'Page', 'count': 'Int', 'character': 'Char', 'boolean': 'Bool3', 'visual_choice': 'Char'}
        if item['answer_format'] in expected_types and doc['result'].get('type') != expected_types[item['answer_format']]:
            supported = False
        result_type = doc['result'].get('type', '')
        if item['answer_format'] == 'set' and not result_type.startswith('Set['):
            supported = False
        if item['answer_format'] == 'sequence' and not result_type.startswith('Seq['):
            supported = False
        if item['answer_format'] == 'quote' and result_type != 'Str':
            supported = False
        if item['answer_format'] == 'multiple_choice' and result_type != 'Cmp':
            supported = False
        if item['answer_format'] == 'multi_part':
            supported = False
    if supported:
        expected = doc['result']['display']
        if item['answer_format'] == 'visual_choice':
            choices = [o for o in item['options'] if o['label'] == item['answer']['value']]
            supported = len(choices) == 1 and choices[0].get('identity_id') == doc['result']['value']
        elif item['answer_format'] == 'sentence':
            supported = False  # Atomic sentence certification is not an execution display comparison.
        else:
            supported = stable(item['answer']['value']) == stable(expected)
    return {'proof_valid': bool(result.get('proof_valid')), 'answer_supported': bool(supported),
            'execution_sha256': stable(doc), 'answer_sha256': stable(item['answer']),
            'engine_check': result, 'status': 'ANSWER_PROVED' if supported else 'ANSWER_UNPROVED'}


def execution_evidence(engine, execution, graph, rich):
    def atoms(kind, doc):
        if doc is None:
            return
        if kind == 'crl':
            yield doc
        elif kind in ('scan', 'membership'):
            for probe in doc['probes']:
                yield probe['execution']
        elif kind in ('relay', 'recipe', 'coverage_recipe'):
            for stage in doc['stages']:
                yield from atoms(stage['engine'], stage['execution'])
    facts, certs, visibility_ids = set(), set(), set()
    for doc in atoms(engine, execution):
        facts.update(doc['proof']['facts']); certs.update(doc['proof']['certificates'])
        visibility_ids.update(doc['proof']['visibility_evidence'])
    coverage = {c['coverage_id']: c for c in graph['coverage']}
    origins = {f['fact_id']: f['origin'] for f in graph['facts']}
    if rich is not None:
        coverage.update({c['id']: c for c in rich['coverage']})
        origins.update({f['id']: f['origin'] for f in rich['facts']})
    from collections import Counter
    return {'fact_ids': sorted(facts), 'certificate_ids': sorted(certs),
            'visibility_evidence_ids': sorted(visibility_ids),
            'closed_assumed_certificates': sorted(c for c in certs if coverage[c]['status'] == 'closed_assumed'),
            'fact_origin_counts': dict(Counter(origins[f] for f in facts)),
            'scope': 'saved_execution_support_only' if execution else 'not_executed'}


def make(graph, visibility, rich, pins, *, question, answer, answer_format, structure,
         engine='pending', program=None, execution=None, claims=None, options=None, complexity=None):
    from .adapters import enrich_frequencies, frequencies
    nodes = {n['id']: n for n in graph['nodes']}
    body = {'chapter_id': graph['chapter_id'], 'split': graph['split'], 'question': question,
            'answer': copy.deepcopy(answer), 'answer_format': answer_format,
            'evidence_class': 'claim_verified' if answer_format == 'sentence' else 'executed',
            'generation_mode': 'synthesis' if answer_format == 'sentence' else 'template',
            'reasoning_structure': structure, 'reasoning_tags': ['native_proposal'], 'primary_group': 'unassigned',
            'proof_engine': engine, 'program': copy.deepcopy(program), 'execution': copy.deepcopy(execution),
            'context': {'pages': [{'page_id': p, 'index': n + 1, 'image_path': nodes[p]['image_path'],
                                   'image_sha256': nodes[p]['image_sha256'], 'relative_path': nodes[p]['relative_path']}
                                  for n, p in enumerate(graph['page_ids'])]},
            'source': {'pins': copy.deepcopy(pins), 'snapshots': {'graph': stable(graph), 'visibility': stable(visibility), 'rich': stable(rich)}},
            'complexity': complexity or {'meaningful_hops': None, 'branch_count': None, 'necessary_pages': []},
            'features': {'identity_id': answer.get('identity_id'), 'page_offset': None,
                         'two_option': answer_format == 'boolean', 'semantic_target': stable([engine, program, answer])},
            'verification': {'proof': 'pending', 'gates': 'pending', 'wording': 'pending',
                             'human': 'pending', 'claims': 'pending' if claims else 'not_applicable',
                             'assets': 'pending' if options else 'not_applicable', 'release': 'pending'},
            'claims': copy.deepcopy(claims), 'options': copy.deepcopy(options), 'admission': 'proposal',
            'evidence': execution_evidence(engine, execution, graph, rich)}
    enrich_frequencies(body, frequencies(graph))
    candidate = {'schema': SCHEMA, 'item_id': 'b1000n:' + stable(body), **body}
    checked = check_answer(candidate, graph, visibility, rich)
    body['answer_check'] = checked
    if checked['answer_supported']:
        body['verification']['proof'] = 'verified'
    candidate = {'schema': SCHEMA, 'item_id': 'b1000n:' + stable(body), **body}
    return validate(candidate)
