"""Budgeted executable pattern inventory. Never equates pattern depth with necessity."""
from collections import Counter, OrderedDict
from itertools import combinations, islice
import json
import sys
import fcntl
from pathlib import Path
from .io import stable, digest, read, publish, separate, verify_manifest, verify_snapshot
from .scan import ScanEngine, ScanChecker
from .relay import RelayEngine, RelayChecker
from .native import make
from .native_store import write as write_native
from .long_relational import propose as clue_proposals
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.language import call
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from comics_qa.tasks.graph.generation.gates import without_pages
from comics_qa.evidence.graph.rich.model import build as rebuild_rich


def patterns(graph, rich, per_pattern=4, clue_search=2000):
    if type(per_pattern) is not int or per_pattern < 1 or type(clue_search) is not int or clue_search < 1:
        raise ValueError('Positive pattern/search budgets required')
    index = {p: n + 1 for n, p in enumerate(graph['page_ids'])}
    closed_ocr = {c['page_id'] for c in rich['coverage'] if c['family'] == 'ocr' and c['status'] in ('closed_assumed', 'closed_verified', 'closed_audited')}
    raw_quote_count = sum(t['quote_eligible'] and 4 <= len(t['consensus'].split()) <= 35 for t in rich['transcripts'])
    quotes = sorted([t for t in rich['transcripts'] if t['page_id'] in closed_ocr and t['quote_eligible'] and 4 <= len(t['consensus'].split()) <= 35], key=lambda t: stable(t['id']))
    tasks = []; source_counts = {'quote_admission': {'transcripts_consensus_eligible': raw_quote_count, 'anchors_on_closed_ocr_pages': len(quotes), 'held_for_ocr_scope_coverage': raw_quote_count - len(quotes)}}
    for name in ('quote_next_speaks', 'speaker_relay'):
        source_counts[name] = {'available_anchors': len(quotes), 'truncated': len(quotes) > per_pattern}
        for text in quotes[:per_pattern]:
            p = index[text['page_id']]; quote = text['consensus']
            speaker = call('speaker_char', call('quote', quote, on=call('page', p)))
            if name == 'quote_next_speaks':
                program = {'op': 'next_speaks', 'characters': [speaker], 'after': p}
                question = f'After page {p}, on which page does the speaker of the text {json.dumps(quote, ensure_ascii=False)} on that page next speak?'
                engine, depth = 'scan', 2
            else:
                program = {'op': 'speaker_relay', 'quote': quote, 'page': p}
                question = (f'Start with the speaker of the text {json.dumps(quote, ensure_ascii=False)} on page {p}. '
                            'Find the next page where that person speaks. On that page identify the only different character who is drawn. '
                            'After that page, on which page is this other character next drawn?')
                engine, depth = 'relay', 4
            tasks.append({'pattern': name, 'engine': engine, 'program': program, 'question': question,
                          'structure': 'chain', 'pattern_depth': depth, 'branches': 0,
                          'stage_types': ['Text', 'Char', 'Page'] if depth == 2 else ['Text', 'Char', 'Page', 'Char', 'Page'],
                          'relaxations': [{'engine': 'relay', 'program': {**program, 'other_rule': 'any'}}] if engine == 'relay' else []})
    groups = {}
    for quote in quotes:
        groups.setdefault(quote['page_id'], []).append(quote)
    # Group first: a chapter with many quotes on one page must not trigger
    # quadratic same-page rejection work outside the pattern budget.
    pairs = []
    for left, right in combinations(sorted(groups), 2):
        for a in groups[left]:
            for b in groups[right]:
                pairs.append((a, b))
                if len(pairs) > per_pattern:
                    break
            if len(pairs) > per_pattern:
                break
        if len(pairs) > per_pattern:
            break
    source_counts['two_quote_joint'] = {'eligible_pairs_observed_lower_bound': len(pairs), 'truncated': len(pairs) > per_pattern}
    for a, b in pairs[:per_pattern]:
        pa, pb = index[a['page_id']], index[b['page_id']]
        chars = [call('speaker_char', call('quote', t['consensus'], on=call('page', p))) for t, p in ((a, pa), (b, pb))]
        after = max(pa, pb)
        tasks.append({'pattern': 'two_quote_joint', 'engine': 'scan',
                      'program': {'op': 'next_joint', 'characters': chars, 'after': after},
                      'question': f'Identify the speakers of {json.dumps(a["consensus"], ensure_ascii=False)} on page {pa} and {json.dumps(b["consensus"], ensure_ascii=False)} on page {pb}. After page {after}, on which page are both characters next drawn?',
                      'structure': 'branch_combine', 'pattern_depth': 2, 'branches': 2,
                      'stage_types': [['Text', 'Char'], ['Text', 'Char'], 'Page'],
                      'relaxations': [{'engine': 'scan', 'program': {'op': 'next_presence', 'characters': [c], 'after': after}}
                                      for c in chars]})
    stats = {}
    for proposal in clue_proposals(graph, per_pattern, clue_search, stats):
        tasks.append({'pattern': 'three_page_clue', 'engine': 'crl', 'program': proposal.ast,
                      'question': proposal.question, 'structure': 'branch_combine', 'pattern_depth': 1,
                      'branches': len(proposal.clauses), 'stage_types': [['Page', 'Set[Char]']] * len(proposal.clauses) + ['Char'],
                      'relaxations': [{'engine': 'crl', 'program': p} for p in proposal.relaxations]})
    source_counts['three_page_clue'] = stats
    return tasks, source_counts


def execute(engine, program, g, v, r):
    if engine == 'crl':
        doc = Interpreter(g, v, rich=r).execute(program)
        checked = ProofChecker(g, v, rich=r).check(doc, program)
        supported = checked['proof_valid'] and doc['result']['status'] == 'OK' and doc['result']['exact']
    elif engine == 'scan':
        doc = ScanEngine(g, v, r).execute(program)
        checked = ScanChecker(g, v, r).check(doc)
        supported = checked['proof_valid'] and checked['answer_supported']
    elif engine == 'relay':
        doc = RelayEngine(g, v, r).execute(program)
        checked = RelayChecker(g, v, r).check(doc)
        supported = checked['proof_valid'] and checked['answer_supported']
    elif engine in ('recipe', 'coverage_recipe'):
        from .recipe_engine import RecipeEngine, RecipeChecker
        doc = RecipeEngine(g, v, r, membership_refinement=engine == 'coverage_recipe').execute(program)
        checked = RecipeChecker(g, v, r, membership_refinement=engine == 'coverage_recipe').check(doc, program)
        supported = checked['proof_valid'] and checked['answer_supported']
    else:
        raise ValueError('Unknown semantic engine')
    if not checked['proof_valid']:
        raise ValueError('Semantic producer/checker disagreement: ' + str(checked))
    return doc, checked, supported


def atomic_executions(engine, doc):
    if engine == 'crl':
        yield doc
    elif engine in ('scan', 'membership'):
        for p in doc['probes']:
            yield p['execution']
    else:
        for stage in doc['stages']:
            yield from atomic_executions(stage['engine'], stage['execution'])


def support(engine, doc, graph, rich):
    facts, certificates, pages = set(), set(), set()
    coverage = {c['coverage_id']: c for c in graph['coverage']}
    coverage.update({c['id']: {**c, 'family': 'rich_ocr'} for c in rich['coverage']})
    for atomic in atomic_executions(engine, doc):
        proof = atomic['proof']; facts.update(proof['facts']); certificates.update(proof['certificates'])
        pages.update(proof['key_support_pages'])
        for cid in proof['certificates']:
            c = coverage[cid]
            if c['family'] != 'page_sequence':
                pages.add(c['page_id'])
    return {'facts': sorted(facts), 'certificates': sorted(certificates),
            'pages': sorted(pages, key=graph['page_ids'].index)}


def chapter_inventory(g, v, r, pins, per_pattern=4, max_ablation_pages=8, clue_search=2000):
    if type(max_ablation_pages) is not int or max_ablation_pages < 0:
        raise ValueError('Invalid page ablation budget')
    if r['decisions']:
        raise ValueError('Reviewed-rich ablation is not enabled; no decisions are silently ignored')
    tasks, enumeration = patterns(g, r, per_pattern, clue_search)
    rows = []; proposals = []; cache = OrderedDict()
    for task in tasks:
        doc, checked, supported = execute(task['engine'], task['program'], g, v, r)
        evidence = support(task['engine'], doc, g, r)
        row = {k: task[k] for k in ('pattern', 'engine', 'program', 'question', 'structure', 'pattern_depth', 'branches', 'stage_types')}
        row.update(result=doc['result'], check=checked, answer_supported=bool(supported), evidence=evidence,
                   meaningful_hops=None, required_pages=None, ablations=[], clause_removals=[])
        if supported:
            for relaxed in task['relaxations']:
                variant, _, known = execute(relaxed['engine'], relaxed['program'], g, v, r)
                result = variant['result']
                # UNKNOWN cannot certify clause necessity. A known ambiguity can.
                necessary = result['status'] != 'UNKNOWN' and stable((result['status'], result['value'])) != stable(('OK', doc['result']['value']))
                row['clause_removals'].append({'program': relaxed['program'], 'result': result, 'necessary': necessary})
            if len(evidence['pages']) <= max_ablation_pages:
                necessary_pages = []
                for pid in evidence['pages']:
                    if pid not in cache:
                        gg, vv = without_pages(g, v, [pid])
                        vv['alignments'] = [a for a in vv['alignments'] if a['page_id'] != pid]
                        rr = rebuild_rich(gg, vv, r['sources'], ())
                        cache[pid] = (gg, vv, rr)
                        if len(cache) > max(1, max_ablation_pages):
                            cache.popitem(last=False)
                    variant, _, _ = execute(task['engine'], task['program'], *cache[pid])
                    result = variant['result']
                    changed = stable((result['status'], result['value'])) != stable(('OK', doc['result']['value']))
                    row['ablations'].append({'removed_page': pid, 'result': result, 'changes_or_breaks_answer': changed})
                    if changed:
                        necessary_pages.append(pid)
                row['required_pages'] = necessary_pages; row['ablation_status'] = 'measured'
            else:
                row['ablation_status'] = 'not_measured_page_budget'
            row['necessary_clause_count'] = sum(c['necessary'] for c in row['clause_removals'])
            row['necessary_page_count'] = len(row['required_pages']) if row['required_pages'] is not None else None
            result = doc['result']; typ = result.get('type', 'Page')
            fmt = {'Page': 'page', 'Int': 'count', 'Char': 'character', 'Bool3': 'boolean'}.get(typ)
            if fmt and result['display'] is not None:
                positions = [g['page_ids'].index(p) + 1 for p in (row['required_pages'] or [])]
                complexity = {'meaningful_hops': None, 'pattern_depth': task['pattern_depth'],
                              'branch_count': task['branches'], 'necessary_pages': row['required_pages'] or [],
                              'necessity_status': row['ablation_status'],
                              'page_span': max(positions) - min(positions) if positions else None,
                              'clause_necessity': row['clause_removals']}
                record = make(g, v, r, pins, question=task['question'],
                              answer={'type': fmt, 'value': result['display'],
                                      'identity_id': result['value'] if fmt == 'character' else None},
                              answer_format=fmt, structure=task['structure'], engine=task['engine'],
                              program=task['program'], execution=doc, complexity=complexity)
                row['native_item_id'] = record['item_id']; proposals.append(record)
        else:
            row['ablation_status'] = 'not_applicable_unproved_answer'
        rows.append(row)
    by_pattern = {}
    for name in sorted({q['pattern'] for q in rows}):
        members = [q for q in rows if q['pattern'] == name]
        by_pattern[name] = {'executed': len(members), 'answer_proved': sum(q['answer_supported'] for q in members), 'result_statuses': dict(Counter(q['result']['status'] for q in members)), 'measured_multi_page': sum(len(q['required_pages'] or []) >= 2 for q in members)}
    return {'chapter_id': g['chapter_id'], 'split': g['split'], 'source_pins': pins,
            'enumeration': enumeration, 'by_pattern': by_pattern, 'queries': rows, 'proposals': proposals,
            'counts': {'executed': len(rows), 'answer_proved': sum(x['answer_supported'] for x in rows),
                       'multi_page_dependencies_measured': sum(len(x['required_pages'] or []) >= 2 for x in rows),
                       'native_proposals': len(proposals)},
            'status': 'budgeted_semantic_patterns',
            'limitations': ['Pattern depth is a typed template property, not meaningful-hop certification',
                           'Page ablation uses annotation dependencies; it is not a proof of visual unknowability',
                           'Answer proof does not certify question wording or all generation gates']}


def run(bench_root, out, chapters=None, per_pattern=4, max_ablation_pages=8, clue_search=2000, reuse_from=None):
    if type(per_pattern) is not int or per_pattern < 1 or type(clue_search) is not int or clue_search < 1 or type(max_ablation_pages) is not int or max_ablation_pages < 0:
        raise ValueError('Invalid semantic execution/search/ablation budgets')
    root = Path(bench_root).resolve(); out = separate(out, [root / 'evidence/ckg', root / 'evidence/name_visibility', root / 'evidence/ckg3'])
    reuse = Path(reuse_from).resolve() if reuse_from else None
    if reuse is not None:
        separate(out, [reuse])
    roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    manifests = [read(p / 'manifest.json') for p in roots]
    available = set(manifests[0]['config']['chapters']); chosen = sorted(set(chapters) if chapters else available)
    if not chosen or not set(chosen) <= available or any(not set(chosen) <= set(m['config']['chapters']) for m in manifests):
        raise ValueError('Unknown/missing semantic inventory chapter')
    repo = Path(__file__).resolve().parents[3]
    baseline_path = repo / 'configs/benchmark1000/legacy_baseline_v1.json'
    verify_snapshot(repo, read(baseline_path)['files'])
    modules = ('semantic.py', 'relay.py', 'scan.py', 'long_relational.py', 'native.py', 'native_store.py', 'contract.py', 'io.py')
    config = {'schema': 'comics_qa.benchmark1000.semantic_config.1', 'chapters': chosen,
              'scope': 'selected_chapters' if chapters else 'full_collection', 'per_pattern': per_pattern,
              'max_ablation_pages': max_ablation_pages, 'clue_search': clue_search,
              'sources': {str(p / 'manifest.json'): digest(p / 'manifest.json') for p in roots},
              'legacy_baseline_sha256': digest(baseline_path),
              'code_sha256': {name: digest(Path(__file__).with_name(name)) for name in modules}}
    reused_config = None
    if reuse is not None:
        reused_config = read(reuse / 'config.json')
        def generation_config(c):
            return {k: v for k, v in c.items() if k not in ('code_sha256', 'reuse_from', 'reuse_config_sha256')}
        if generation_config(reused_config) != generation_config(config):
            raise ValueError('Reuse source inputs, chapter scope or budgets differ')
        if (reuse / 'manifest.json').exists():
            verify_manifest(reuse)
        config['reuse_from'] = str(reuse)
        config['reuse_config_sha256'] = digest(reuse / 'config.json')
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.semantic-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        if (out / 'manifest.json').exists():
            saved_manifest = verify_manifest(out)
            if saved_manifest['config'] != config or saved_manifest['config_sha256'] != stable(config):
                raise ValueError('Completed semantic inventory config differs')
        reports, proposals, outputs = [], [], {}
        for cid in chosen:
            g, v, pins = load_world(*roots[:2], cid); r = load_optional(*roots, cid, pins)
            name = 'chapters/' + cid + '.json'; path = out / name
            checkpoint_action = 'resumed'
            if path.exists():
                saved = read(path)
                if saved['config_sha256'] != stable(config) or saved['payload_sha256'] != stable(saved['payload']) or saved['payload']['source_pins'] != pins:
                    raise ValueError('Semantic chapter checkpoint differs')
                report = saved['payload']
            else:
                checkpoint_action = 'built'
                original = reuse / name if reuse is not None else None
                source_checkpoint = None
                if original is not None and original.exists():
                    # A changed-code recovery never trusts old verdict flags alone.
                    # Re-execute with the current producer/checkers and compare the
                    # full report before referencing a completed checkpoint.
                    saved = read(original)
                    if saved['config_sha256'] != stable(reused_config) or saved['payload_sha256'] != stable(saved['payload']) or saved['payload']['source_pins'] != pins:
                        raise ValueError('Reuse checkpoint checksum or source binding differs')
                    checkpoint_action = 'revalidated_previous'
                    source_checkpoint = {'path': str(original), 'sha256': digest(original),
                                         'validation': 'full_current_code_reexecution'}
                report = chapter_inventory(g, v, r, pins, per_pattern, max_ablation_pages, clue_search)
                if source_checkpoint is not None and stable(report) != saved['payload_sha256']:
                    raise ValueError('Completed chapter changed under current code; use a fresh run without --reuse-from')
                wrapper = {'config_sha256': stable(config), 'payload_sha256': stable(report), 'payload': report}
                if source_checkpoint is not None:
                    wrapper['reused_checkpoint'] = source_checkpoint
                publish(path, wrapper)
            print(f"{cid}: {checkpoint_action}; executed={report['counts']['executed']}, proved={report['counts']['answer_proved']}, proposals={report['counts']['native_proposals']}", file=sys.stderr)
            proposals.extend(report['proposals']); reports.append({k: v for k, v in report.items() if k not in ('proposals', 'queries')})
            outputs[name] = digest(path)
        native = write_native(proposals, out / 'native_store', {'semantic_config_sha256': stable(config)}, roots)
        result = {'schema': 'comics_qa.benchmark1000.semantic_inventory.1', 'config': config, 'chapters': reports,
                  'counts': {k: sum(report['counts'][k] for report in reports) for k in ('executed', 'answer_proved', 'multi_page_dependencies_measured', 'native_proposals')},
                  'native_store': {'path': 'native_store', 'manifest_sha256': digest(out / 'native_store/manifest.json'), 'counts': native['counts']},
                  'release_status': 'not_approved', 'exhaustive': False}
        publish(out / 'report.json', result)
        outputs['report.json'] = digest(out / 'report.json'); outputs['native_store/manifest.json'] = digest(out / 'native_store/manifest.json')
        publish(out / 'manifest.json', {'schema': 'comics_qa.benchmark1000.semantic_artifacts.1', 'config': config,
                                       'config_sha256': stable(config), 'outputs_sha256': outputs})
        return result
