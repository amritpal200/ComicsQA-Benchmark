"""Bounded replay of failed family recipes into a private uncertainty report."""
from pathlib import Path
from collections import Counter
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from .io import read, stable, digest, publish, separate, verify_manifest, member
from .expanded_families import compile_recipe, render, parse_question, KINDS
from .semantic import execute
from .uncertainty import explain


def run(source, bench_root, out, chapters=None, max_queries=12, families=None):
    if type(max_queries) is not int or max_queries < 1:
        raise ValueError('Positive diagnosis query budget required')
    if families and not set(families) <= set(KINDS):
        raise ValueError('Unknown diagnosis family')
    source, root = Path(source).resolve(), Path(bench_root).resolve()
    out = separate(out, [source, root / 'evidence', root / 'core'])
    m = verify_manifest(source)
    if (m.get('schema') != 'comics_qa.benchmark1000.family_artifacts.1' or stable(m['config']) != m['config_sha256']
            or read(source / 'config.json') != m['config']):
        raise ValueError('Expected a complete pinned family run')
    chosen = set(chapters or m['config']['chapters'])
    if not chosen <= set(m['config']['chapters']): raise ValueError('Unknown diagnosis chapter')
    worlds = {}; rows = []; eligible = 0
    for cid in sorted(chosen):
        path = member(source, 'chapters/' + cid + '.json'); checkpoint = read(path); payload = checkpoint['payload']
        if checkpoint['payload_sha256'] != stable(payload) or checkpoint['config_sha256'] != m['config_sha256']:
            raise ValueError('Invalid diagnosis checkpoint binding')
        for row in payload['executions']:
            if row['answer_proved'] or families and row['kind'] not in families: continue
            eligible += 1
            if len(rows) >= max_queries: continue
            if cid not in worlds:
                gr, vr, rr = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
                g, v, pins = load_world(gr, vr, cid); r = load_optional(gr, vr, rr, cid, pins)
                if payload['snapshots'] != {'graph': stable(g), 'visibility': stable(v), 'rich': stable(r)}:
                    raise ValueError('Baseline diagnosis source snapshots changed')
                worlds[cid] = (g, v, r)
            g, v, r = worlds[cid]; recipe = row['recipe']; program = compile_recipe(recipe)
            engine = parse_question(render(recipe))['engine']
            doc, check, supported = execute(engine, program, g, v, r)
            if doc['result'] != row['result']: raise ValueError('Baseline result did not reproduce; use a versioned comparison')
            rows.append({'chapter_id': cid, 'kind': row['kind'], 'recipe': recipe,
                         'result': doc['result'], 'proof_valid': check['proof_valid'], 'answer_supported': bool(supported),
                         'result_reproduced': True, 'uncertainty': explain(engine, doc, g, r)})
    report = {'schema': 'comics_qa.benchmark1000.baseline_uncertainty.1',
              'source_manifest_sha256': digest(source / 'manifest.json'), 'chapters': sorted(chosen), 'query_budget': max_queries,
              'eligible_queries': eligible, 'replayed_queries': len(rows), 'truncated': eligible > len(rows), 'items': rows,
              'categories': dict(Counter(k for row in rows for k in row['uncertainty']['categories'])),
              'code_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')},
              'review_status': 'not_reviewed', 'coverage_changes': 'none', 'release_status': 'not_approved'}
    publish(out, report)
    return report
