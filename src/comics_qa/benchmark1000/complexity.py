"""Measured semantic-step certificates, never raw AST length or graph-walk depth."""
from .io import stable
from .expanded_families import VERSION


def bindings(item):
    """The independent CRL checker binds let children to these exact expressions."""
    program = item['program']; doc = item['execution']
    if item['proof_engine'] in ('recipe', 'coverage_recipe'):
        from .recipe_engine import result
        return {s['name']: {k: result(s)[k] for k in ('type', 'status', 'value')} for s in doc['stages'] if s['name'] != '__result__'}
    steps = {s['nid']: s for s in doc['proof']['steps']}
    root = steps[doc['proof']['root']]
    if root['op'] != 'let' or len(root['children']) != len(program['let']) + 1:
        raise ValueError('Missing checked recipe bindings')
    return {b['name']: {'type': steps[n]['type'], 'status': steps[n]['status'], 'value': steps[n]['value']}
            for b, n in zip(program['let'], root['children'][:-1])}


def resolved(item, parsed):
    if parsed.get('profile_version') == 'branch_relations.1':
        from .branch_relations import resolved as branch_resolved
        return branch_resolved(item, parsed)
    values = bindings(item)
    # Ignore alternate OCR anchors for the same resolved person on the same page.
    refs = [[x['page'], values['c' + str(i)]['value']] for i, x in enumerate(parsed['recipe']['references'])]
    sequence = [[k, v['type'], v['status'], v['value']] for k, v in values.items() if not k.startswith('c')]
    r = parsed['recipe']; scope = [r['start'], r['end']] if r['kind'] in ('shared_speaking_pages', 'shared_presence_pages', 'last_presence_window') else [r['start']]
    if r.get('profile') == 'coverage_windows.1' and (r['kind'].startswith('shared_') or r['kind'] == 'speaking_gap'):
        if r['kind'] == 'speaking_gap':
            sequence = sorted([[*ref, values[name]['value']] for ref, name in zip(refs, ('pa', 'pb'))])
        refs = sorted(refs)
    return [item['chapter_id'], parsed['kind'], refs, scope, sequence, item['execution']['result']['value']]


def certify(item, parsed, checks):
    """Recomputable certificate over exact bypass outcomes and visual ablations."""
    if parsed.get('profile_version') == 'branch_relations.1':
        from .branch_relations import certificate
        return certificate(item, parsed, checks)
    labels = parsed['relaxation_labels']; removals = checks['clause_removals']
    if len(removals) != len(labels):
        raise ValueError('Missing recipe bypass checks')
    required = all(row['necessary'] and row['result']['status'] in ('OK', 'EMPTY') for row in removals)
    if parsed['kind'].startswith('shared_'):
        required = all(row['result']['status'] == 'OK' and isinstance(row['result']['value'], list) and row.get('known_extra_members') == sorted(set(row['result']['value']) - set(item['execution']['result']['value'])) and bool(row.get('known_extra_members')) for row in removals)
    kind = parsed['kind']; recipe = parsed['recipe']
    chain = kind in ('successive_speech', 'speaker_walk')
    branches = 2 if kind in ('speaking_gap', 'speaking_before', 'shared_speaking_pages', 'shared_presence_pages') else 0
    hops = len(labels) if chain else 1 if labels else 0
    group = ('chain' if hops >= 3 else 'short') if chain else 'branch_combine' if kind.startswith('shared_') else 'aggregate_compare' if kind in ('speaking_gap', 'speaking_before', 'next_speech_line_count') else 'short'
    pages = checks['necessary_pages']; order = {p['page_id']: p['index'] for p in item['context']['pages']}
    span = max((order[p] for p in pages), default=0) - min((order[p] for p in pages), default=0)
    return {'version': parsed.get('profile_version', VERSION), 'method': 'typed_dependency_bypass_and_visual_ablation.1',
            'certified': required and len(checks['necessary_visual_pages']) >= parsed['min_pages'],
            'meaningful_hops': hops if required else None, 'branch_count': branches if required else None,
            'combine_count': 1 if branches else 0, 'necessary_steps': labels if required else [],
            'necessary_pages': pages, 'necessary_visual_pages': checks['necessary_visual_pages'], 'page_span': span,
            'word_count': len(item['question'].split()), 'primary_group': group,
            'bypass_checks_sha256': stable(removals),
            'definition': 'Sequential necessary navigations/identity switches; parallel branch depths are not added. Quote lookup, AST primitives and word count are excluded.',
            'limitations': 'Operational bypass witnesses, not universal graph minimality or a narrative-difficulty judgement.'}
