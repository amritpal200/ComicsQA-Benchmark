"""Strict read-only import of existing GEN outputs. No legacy engine imports."""
import copy
from collections import defaultdict, Counter
from pathlib import Path
from .contract import SCHEMA, validate
from .io import digest, read, stable, member, verify_manifest


def adapt(item, source, frequent=()):
    original = copy.deepcopy(item)
    check = item.get('proof_check', {})
    if not check.get('accepted_for_generation') or not check.get('proof_valid'):
        raise ValueError('Legacy item has no accepted saved proof check')
    if item['execution']['program'] != item['program']:
        raise ValueError('Program mismatch')
    answer = item['answer']
    fmt = {'char': 'character', 'int': 'count', 'bool': 'boolean', 'page': 'page',
           'set[char]': 'set', 'set[page]': 'set', 'seq[char]': 'sequence', 'cmp': 'multiple_choice'}.get(answer['type'].lower())
    if fmt is None:
        raise ValueError('Unsupported legacy answer format: ' + answer['type'])
    dimensions = item.get('dimensions', {})
    quality = item.get('quality', {})
    h = stable(original)
    candidate = {
        'schema': SCHEMA, 'item_id': 'b1000:' + stable([item['item_id'], h]),
        'source_item_id': item['item_id'], 'chapter_id': item['chapter_id'], 'split': item['split'],
        'question': item['question'], 'answer': copy.deepcopy(answer),
        'evidence_class': 'executed', 'generation_mode': 'template',
        # Do not invent meaningful hops from operation count.
        'reasoning_structure': 'direct', 'reasoning_tags': ['legacy_import'],
        'answer_format': fmt, 'primary_group': 'short',
        'complexity': {'meaningful_hops': None, 'branch_count': None,
                       'necessary_pages': dimensions.get('necessary_pages', []),
                       'page_span': dimensions.get('visual_page_span'),
                       'operation_steps': dimensions.get('operation_steps')},
        'features': {'identity_id': answer.get('identity_id'),
                     'frequent_ids': sorted(frequent),
                     'is_frequent_legacy': answer.get('identity_id') in frequent,
                     'is_top2_identity': None, 'is_top1_identity': None,
                     'page_offset': quality.get('page_offset'),
                     'two_option': bool(item.get('two_option')),
                     'semantic_target': quality.get('semantic_target_sha256', item['program_sha256'])},
        'verification': {'proof': 'archived_check', 'wording': 'legacy_template',
                         'source': 'pinned_legacy', 'human': 'pending', 'release': 'pending'},
        'source': {**source, 'item_sha256': h}, 'legacy': original,
    }
    return validate(candidate)


def records(root, chapters=None):
    from pathlib import Path
    root = Path(root).resolve()
    manifest = verify_manifest(root)
    manifest_sha = digest(root / 'manifest.json')
    all_chapters = manifest['config']['chapters']
    chosen = sorted(chapters or all_chapters)
    if not chosen or not set(chosen) <= set(all_chapters):
        raise ValueError('Unknown or empty chapter scope')
    pooled = any(name.startswith('candidate_pools/') for name in manifest['outputs_sha256'])
    for cid in chosen:
        name = ('candidate_pools/' if pooled else 'chapters/') + cid + '.json'
        if name not in manifest['outputs_sha256']:
            raise ValueError('Shard missing from manifest')
        path = member(root, name)
        wrapper = read(path)
        payload = wrapper['payload']
        if stable(payload) != wrapper['payload_sha256']:
            raise ValueError('Shard payload mismatch')
        if payload['chapter_id'] != cid:
            raise ValueError('Shard chapter mismatch')
        counts = payload.get('balance', {}).get('trusted_page_frequencies')
        if counts is None:
            graph_pins = [(Path(p), sha) for p, sha in payload.get('inputs_sha256', {}).items()
                          if '/evidence/ckg/' in p and '/chapters/' in p]
            if len(graph_pins) == 1 and graph_pins[0][0].is_file():
                graph_path, expected = graph_pins[0]
                if digest(graph_path) != expected:
                    raise ValueError('Pinned frequency graph changed')
                counts = frequencies(read(graph_path))
        for item in payload['candidates' if pooled else 'items']:
            if item['chapter_id'] != cid or item['split'] != payload['split']:
                raise ValueError('Item split/chapter mismatch')
            source = {'root': str(root), 'manifest_sha256': manifest_sha,
                      'shard': name, 'shard_sha256': digest(path),
                      'record_kind': 'retained_pool' if pooled else 'selected_only'}
            candidate = adapt(item, source, payload.get('frequent_ids', payload.get('balance', {}).get('frequent_ids', [])))
            if counts is not None:
                enrich_frequencies(candidate, counts)
            yield candidate


def frequencies(graph):
    nodes = {n['id']: n for n in graph['nodes']}
    pages = defaultdict(set)
    for fact in graph['facts']:
        if fact['rel'] == 'present' and fact['answer_eligible'] and fact['origin'] in ('H', 'V'):
            cid, page = fact['args']
            if not nodes[cid]['generic']:
                pages[cid].add(page)
    return {cid: len(values) for cid, values in pages.items()}


def enrich_frequencies(item, counts):
    ordered = sorted(counts, key=lambda cid: (-counts[cid], cid))
    identity = item['features']['identity_id']
    item['features'].update(is_top1_identity=bool(ordered and identity == ordered[0]),
                            is_top2_identity=identity in ordered[:2],
                            frequency_definition='trusted distinct pages; deterministic ID tie-break for fixed top1/top2 baseline')
    return item
