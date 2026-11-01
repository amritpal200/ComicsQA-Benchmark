"""Answer-first, resource-bounded native family discovery; no production inference."""
import fcntl
from collections import Counter, defaultdict
from itertools import combinations, islice
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from .expanded_families import VERSION, KINDS, FORMATS, compile_recipe, render
from .io import stable, digest, read, publish, separate, verify_snapshot, verify_manifest
from .native import make, validate
from .native_store import write
from .semantic import execute


def catalogue(g, rich):
    facts = [f for f in g['facts'] if f['answer_eligible'] and f['origin'] in ('H', 'V')]
    nodes = {n['id']: n for n in g['nodes']}
    positions = {p: i + 1 for i, p in enumerate(g['page_ids'])}
    chars = {f['args'][0]: f['args'][1] for f in facts if f['rel'] == 'is_char'}
    speakers = defaultdict(set)
    for f in facts:
        if f['rel'] == 'spoken_by' and f['args'][1] in chars:
            speakers[f['args'][0]].add(chars[f['args'][1]])
    speech, present, people, counts = defaultdict(set), defaultdict(set), defaultdict(set), Counter()
    for f in facts:
        if f['rel'] in ('present', 'speaks_on'):
            c, p = f['args']; at = positions[p]
            (speech if f['rel'] == 'speaks_on' else present)[c].add(at)
            if f['rel'] == 'present':
                people[at].add(c)
    for tid, cs in speakers.items():
        if len(cs) == 1:
            node = nodes[tid]
            counts[next(iter(cs)), positions[node['page_id']]] += 1
    closed = {c['page_id'] for c in rich['coverage'] if c['status'] in ('closed_assumed', 'closed_verified', 'closed_audited')}
    lines = {f['args'][0] for f in facts if f['rel'] == 'is_line'}
    anchors = []
    for t in rich['transcripts']:
        cs = speakers[t['text_id']]
        if t['text_id'] in lines and t['quote_eligible'] and t['page_id'] in closed and len(cs) == 1 and 4 <= len(t['consensus'].split()) <= 35:
            anchors.append({'quote': t['consensus'], 'page': positions[t['page_id']], 'identity': next(iter(cs))})
    return sorted(anchors, key=stable), speech, present, people, counts


def predict(recipe, speech, present, people, counts):
    """Cheap known-fact search only; neither coverage nor proof is inferred here."""
    kind = recipe['kind']; refs = recipe['references']; start, end = recipe['start'], recipe['end']
    def later(c, p):
        return min((x for x in speech[c] if max(p + 1, start) <= x <= end), default=None)
    if kind in ('successive_speech', 'speaker_walk'):
        c, p = refs[0]['identity'], start - 1
        for i in range(recipe['steps']):
            p = later(c, p)
            if p is None:
                return None
            if kind == 'speaker_walk' and i < recipe['steps'] - 1:
                others = people[p] - {c}
                if len(others) != 1:
                    return None
                c = next(iter(others))
        return p
    if kind in ('speaking_gap', 'speaking_before'):
        a, b = [later(x['identity'], start - 1) for x in refs]
        if a is None or b is None or a == b:
            return None
        return max(0, abs(a - b) - 1) if kind == 'speaking_gap' else a < b
    if kind.startswith('shared_'):
        relation = speech if kind == 'shared_speaking_pages' else present
        pages = sorted({p for p in relation[refs[0]['identity']] & relation[refs[1]['identity']] if start <= p <= end})
        return pages if 2 <= len(pages) < end - start + 1 else None
    c = refs[0]['identity']
    if kind == 'next_speech_line_count':
        p = later(c, start - 1)
        return counts[c, p] if p is not None else None
    return max((p for p in present[c] if start <= p <= end), default=None)


def search(g, rich, search_budget=1000, window=10, check_anchor=None):
    anchors, speech, present, people, counts = catalogue(g, rich)
    raw_anchor_count = len(anchors)
    checked_anchors = 0
    if check_anchor is not None:
        candidates = anchors[:search_budget]; checked_anchors = len(candidates)
        anchors = [a for a in candidates if check_anchor(a)]
    pools = {kind: [] for kind in KINDS}; tested = Counter(); last = len(g['page_ids'])
    def refs_for(kind):
        if kind in ('speaking_gap', 'speaking_before', 'shared_speaking_pages', 'shared_presence_pages'):
            return (list(pair) for pair in islice(combinations(anchors, 2), search_budget) if pair[0]['identity'] != pair[1]['identity'])
        return ([a] for a in anchors)
    for kind in KINDS:
        for refs in islice(refs_for(kind), search_budget):
            start = max(a['page'] for a in refs) + 1; end = min(last, start + window - 1)
            for steps in ((3, 2) if kind in ('successive_speech', 'speaker_walk') else (1,)):
                tested[kind] += 1
                if end - start < 3:
                    continue
                recipe = {'kind': kind, 'references': refs, 'start': start, 'end': end, 'steps': steps}
                predicted = predict(recipe, speech, present, people, counts)
                if predicted is None or kind == 'speaking_gap' and predicted == 0:
                    continue
                clean = {**recipe, 'references': [{k: a[k] for k in ('quote', 'page')} for a in refs]}
                pools[kind].append({'recipe': clean, 'predicted': predicted, 'identity_targets': [a['identity'] for a in refs]})
    stats = {'anchor_count': len(anchors), 'raw_anchor_count': raw_anchor_count, 'source_anchor_checks': checked_anchors, 'source_anchor_budget_hit': raw_anchor_count > search_budget, 'recipes_tested': dict(tested), 'search_budget_per_family': search_budget,
             'search_budget_hit': {k: (len(anchors) * (len(anchors) - 1) // 2 if k in ('speaking_gap', 'speaking_before', 'shared_speaking_pages', 'shared_presence_pages') else len(anchors)) > search_budget for k in KINDS},
             'known_fact_targets': {k: len(v) for k, v in pools.items()}, 'exhaustive': False,
             'limitation': 'Known-positive target discovery only; full CRL execution and admission decide validity.'}
    return pools, stats


def chapter(g, v, rich, pins, per_family, max_executions, search_budget, window):
    from comics_qa.tasks.graph.crl import Interpreter
    from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
    from .native_wording import speaker
    interpreter = Interpreter(g, v, rich=rich); checker = ProofChecker(g, v, rich=rich)
    def eligible(anchor):
        ast = speaker(anchor['quote'], anchor['page']); doc = interpreter.execute(ast)
        checked = checker.check(doc, ast)
        if not checked['proof_valid']:
            raise ValueError('Source-anchor producer/checker disagreement')
        return doc['result']['status'] == 'OK' and doc['result']['exact'] and doc['result']['value'] == anchor['identity']
    pools, stats = search(g, rich, search_budget, window, eligible)
    rows, items = [], []
    for kind, pool in pools.items():
        opportunities = Counter(stable(x['predicted']) for x in pool)
        used = Counter(); emitted = 0; attempted = 0
        while pool and emitted < per_family and attempted < max_executions:
            # Prefer underrepresented proved outputs, then rarer known target values.
            pick = min(range(len(pool)), key=lambda i: (used[stable(pool[i]['predicted'])], opportunities[stable(pool[i]['predicted'])], stable(pool[i]['recipe'])))
            task = pool.pop(pick); recipe = task['recipe']; program = compile_recipe(recipe)
            doc, check, known = execute('recipe', program, g, v, rich)
            row = {'kind': kind, 'recipe': recipe, 'result': doc['result'], 'proof_valid': check['proof_valid'], 'answer_proved': bool(known)}
            rows.append(row); attempted += 1
            if not known or doc['result']['display'] is None:
                continue
            fmt = FORMATS[kind]
            answer = {'type': 'bool' if fmt == 'boolean' else fmt, 'value': doc['result']['display'], 'identity_id': None}
            structure = 'chain' if kind in ('successive_speech', 'speaker_walk') else 'branch_combine' if kind.startswith('shared_') else 'compare' if kind in ('speaking_gap', 'speaking_before') else 'aggregate' if kind == 'next_speech_line_count' else 'direct'
            item = make(g, v, rich, pins, question=render(recipe), answer=answer, answer_format=fmt, structure=structure,
                        engine='recipe', program=program, execution=doc,
                        complexity={'meaningful_hops': None, 'branch_count': None, 'necessary_pages': [], 'profile_version': VERSION})
            row['native_item_id'] = item['item_id']; items.append(item); emitted += 1
            used[stable(answer['value'])] += 1
    return {'chapter_id': g['chapter_id'], 'snapshots': {'graph': stable(g), 'visibility': stable(v), 'rich': stable(rich)},
            'search': stats, 'executions': rows, 'proposals': items,
            'counts': {'executed': len(rows), 'answer_proved': sum(x['answer_proved'] for x in rows), 'proposals': len(items)}}


def run(bench_root, out, chapters=None, per_family=3, max_executions=9, search_budget=1000, window=10, coverage_aware=False, min_window=4, max_shift=20, probe_budget=192, max_windows=4, dependency_budget=None):
    if any(type(x) is not int or x < 1 for x in (per_family, max_executions, search_budget, window)) or window < 4 or max_executions < per_family:
        raise ValueError('Positive budgets, window >=4 and execution budget >= proposal cap required')
    if coverage_aware and (any(type(x) is not int for x in (min_window, max_shift, probe_budget, max_windows)) or not 4 <= min_window <= window or max_shift < 0 or min(probe_budget, max_windows) < 1):
        raise ValueError('Invalid coverage window/probe budgets')
    if dependency_budget is not None and (not coverage_aware or type(dependency_budget) is not int or dependency_budget < 1):
        raise ValueError('Positive dependency budget requires coverage-aware search')
    root = Path(bench_root).resolve(); roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    out = separate(out, roots + [root / 'core'])
    manifests = [read(p / 'manifest.json') for p in roots]
    available = set(manifests[0]['config']['chapters']); chosen = sorted(set(chapters) if chapters else available)
    if not chosen or any(not set(chosen) <= set(m['config']['chapters']) for m in manifests):
        raise ValueError('Unknown/missing chapter scope')
    repo = Path(__file__).resolve().parents[3]; baseline = repo / 'configs/benchmark1000/legacy_baseline_v1.json'
    verify_snapshot(repo, read(baseline)['files'])
    config = {'schema': 'comics_qa.benchmark1000.family_config.1', 'version': VERSION, 'chapters': chosen,
              'per_family': per_family, 'max_executions_per_family': max_executions, 'search_budget': search_budget, 'window': window,
              'source_manifests_sha256': {str(p): digest(p / 'manifest.json') for p in roots},
              'legacy_baseline_sha256': digest(baseline), 'code_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('*.py')}}
    if coverage_aware:
        config.update(version='coverage_windows.1', coverage_aware=True, min_window=min_window, max_shift=max_shift, probe_budget_per_family=probe_budget, max_windows_per_reference=max_windows)
    if dependency_budget is not None:
        config.update(version='necessary_switches.1', families=['speaker_walk'], dependency_execution_budget=dependency_budget)
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.family-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        if (out / 'manifest.json').exists():
            verify_manifest(out)
        outputs, results, items = {}, [], []
        for cid in chosen:
            g, v, pins = load_world(roots[0], roots[1], cid)
            rich = load_optional(*roots, cid, pins)
            if rich is None or rich['decisions']:
                raise ValueError('Automatic rich evidence required; reviewed counterfactuals remain unsupported')
            path = out / 'chapters' / (cid + '.json')
            if path.exists():
                checkpoint = read(path)
                if checkpoint['config_sha256'] != stable(config) or checkpoint['payload_sha256'] != stable(checkpoint['payload']):
                    raise ValueError('Stale/tampered family checkpoint')
                result = checkpoint['payload']
                if result['snapshots'] != {'graph': stable(g), 'visibility': stable(v), 'rich': stable(rich)}:
                    raise ValueError('Family checkpoint snapshot mismatch')
                for i in result['proposals']:
                    validate(i)
            else:
                if coverage_aware:
                    from .coverage_windows import chapter as coverage_chapter
                    result = coverage_chapter(g, v, rich, pins, per_family, max_executions, search_budget, window, min_window, max_shift, probe_budget, max_windows, dependency_budget)
                else:
                    result = chapter(g, v, rich, pins, per_family, max_executions, search_budget, window)
                publish(path, {'config_sha256': stable(config), 'payload_sha256': stable(result), 'payload': result})
            results.append(result); items.extend(result['proposals']); outputs[str(path.relative_to(out))] = digest(path)
            print(f"{cid}: executed={result['counts']['executed']}, proposals={result['counts']['proposals']}", flush=True)
        write(items, out / 'native_store', {'version': config['version'], 'family_config_sha256': stable(config)}, protected=roots)
        outputs['native_store/manifest.json'] = digest(out / 'native_store/manifest.json')
        report = {'schema': 'comics_qa.benchmark1000.family_report.1', 'config_sha256': stable(config),
                  'counts': {k: sum(r['counts'][k] for r in results) for k in ('executed', 'answer_proved', 'proposals')},
                  'families': dict(Counter(x['kind'] for r in results for x in r['executions'] if 'native_item_id' in x)),
                  'next': 'Run admit-native --proposal-root on this completed output before scaling generation.',
                  'deferred': ['unreviewed order/turns', 'caption claims', 'Qwen wording', 'paired/sentence release'], 'release_status': 'not_approved'}
        report['family_yield'] = {kind: {
            'known_fact_targets': sum(r['search']['known_fact_targets'][kind] for r in results),
            'executed': sum(x['kind'] == kind for r in results for x in r['executions']),
            'answer_proved': sum(x['kind'] == kind and x['answer_proved'] for r in results for x in r['executions']),
            'proposals': report['families'].get(kind, 0),
            'unproved_reasons': dict(Counter(x.get('uncertainty', {}).get('reason_code') or x['result'].get('reason') or ('inexact_result' if x['result']['status'] == 'OK' else x['result']['status']) for r in results for x in r['executions'] if x['kind'] == kind and not x['answer_proved'])),
            'search_truncated_chapters': sum(r['search']['search_budget_hit'][kind] for r in results)} for kind in KINDS}
        if coverage_aware:
            diagnostics = {'schema': 'comics_qa.benchmark1000.coverage_diagnostics.1', 'config_sha256': stable(config),
                           'chapters': {r['chapter_id']: {'snapshots': r['snapshots'], 'search': r['search'], 'probes': r['discovery_diagnostics'],
                              'unproved_executions': [x for x in r['executions'] if not x['answer_proved']]} for r in results},
                           'authority': 'diagnosis only; no facts, coverage, aliases or release status changed'}
            publish(out / 'diagnostics.json', diagnostics); outputs['diagnostics.json'] = digest(out / 'diagnostics.json')
            report['coverage_discovery'] = {'new_queries': sum(sum(r['discovery_diagnostics']['new_queries'].values()) for r in results),
                'uncertainty_categories': dict(Counter({k: sum(r['discovery_diagnostics']['uncertainty_categories'].get(k, 0) for r in results) for k in sorted({k for r in results for k in r['discovery_diagnostics']['uncertainty_categories']})})),
                'probe_budget_hit_chapters': {k: sum(r['search']['probe_budget_hit'].get(k, False) for r in results) for k in KINDS},
                'discovery_rejections': {kind: dict(sum((Counter(r['search']['discovery_rejections'].get(kind, {})) for r in results), Counter())) for kind in KINDS},
                'diagnostics': 'diagnostics.json', 'exhaustive': False}
        if dependency_budget is not None:
            report['dependency_search'] = {'new_executions': sum(r['discovery_diagnostics']['dependency_search']['new_executions'] for r in results),
                'outcomes': dict(sum((Counter(r['discovery_diagnostics']['dependency_search']['outcomes']) for r in results), Counter())),
                'budget_hit_chapters': sum(r['discovery_diagnostics']['dependency_search']['budget_exhausted'] for r in results),
                'authority': 'preselection only; unchanged native admission required'}
        publish(out / 'report.json', report); outputs['report.json'] = digest(out / 'report.json')
        publish(out / 'manifest.json', {'schema': 'comics_qa.benchmark1000.family_artifacts.1', 'config': config,
                                      'config_sha256': stable(config), 'outputs_sha256': outputs})
    return report
