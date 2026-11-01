"""Candidate-specific checked window discovery; never closes coverage or invents facts."""
from collections import Counter, deque, defaultdict
from itertools import combinations, islice
import re
from comics_qa.tasks.graph.crl import Interpreter
from comics_qa.tasks.graph.crl.language import call, program_hash, parse
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
from .expanded_families import KINDS, FORMATS, COVERAGE_VERSION, compile_recipe, render
from .native_wording import speaker
from .family_pilot import catalogue, predict
from .native import make
from .semantic import execute
from .io import stable
from .uncertainty import explain
from .membership import known_truth

VERSION = COVERAGE_VERSION
PAIR = {'speaking_gap', 'speaking_before', 'shared_speaking_pages', 'shared_presence_pages'}
PRIORITY = ('shared_presence_pages', 'shared_speaking_pages', 'speaker_walk', 'speaking_gap',
            'speaking_before', 'next_speech_line_count', 'successive_speech', 'last_presence_window')


class ProbeBudget(Exception):
    pass


class Probes:
    def __init__(self, g, v, rich, per_family=192, anchors=1000, diagnostic_limit=128):
        self.g, self.v, self.rich = g, v, rich
        self.interpreter = Interpreter(g, v, rich=rich); self.checker = ProofChecker(g, v, rich=rich)
        self.limits = defaultdict(lambda: per_family, _anchors=anchors)
        self.used = Counter(); self.hits = Counter(); self.cache = {}; self.records = []
        self.diagnostic_limit = diagnostic_limit; self.diagnostics_seen = 0; self.categories = Counter(); self.budget_requests = []

    def query(self, expression, family, key=None):
        cache_key = key or ('expression', program_hash(parse(expression)))
        if cache_key in self.cache:
            self.hits[family] += 1
            return self.cache[cache_key]
        if self.used[family] >= self.limits[family]:
            self.budget_requests.append({'family': family, 'program': expression, 'category': 'probe_budget_exhausted'})
            raise ProbeBudget(family)
        self.used[family] += 1
        doc = self.interpreter.execute(expression); check = self.checker.check(doc, expression)
        if not check['proof_valid']:
            raise ValueError('Coverage probe producer/checker disagreement')
        result = doc['result']; self.cache[cache_key] = result
        if not known_truth(result) and (result['status'] != 'OK' or not result['exact']):
            diagnostic = explain('crl', doc, self.g, self.rich)
            self.categories.update(diagnostic['categories']); self.diagnostics_seen += 1
            if len(self.records) < self.diagnostic_limit:
                self.records.append({'family': family, 'program': expression, 'result': result,
                                     'proof_valid': True, 'uncertainty': diagnostic})
        return result

    def actor(self, expression, family):
        result = self.query(expression, family)
        if result['status'] != 'OK' or not result['exact'] or result['type'] != 'Char':
            return None
        return {'id': result['value'], 'expression': expression}

    def predicate(self, op, actors, page, family):
        expressions = [call(op, a['expression'], call('page', page)) for a in actors]
        expression = expressions[0] if len(expressions) == 1 else call('and', *expressions)
        # Resolved identity keys only guide discovery. Every emitted question is
        # independently executed again using its own exact quote expressions.
        key = (op, tuple(sorted(a['id'] for a in actors)), page)
        return self.query(expression, family, key)

    def first(self, actor, after, end, family):
        for page in range(after + 1, end + 1):
            result = self.predicate('speaks_on', [actor], page, family)
            if not known_truth(result):
                return None
            if result['value'] is True:
                return page
        return None

    def report(self):
        return {'new_queries': dict(self.used), 'cache_hits': dict(self.hits),
                'probe_limit_per_family': self.limits['shared_presence_pages'], 'anchor_probe_limit': self.limits['_anchors'],
                'budget_exhaustion': self.budget_requests, 'uncertainty_categories': dict(self.categories), 'uncertainty_records': self.records,
                'uncertainty_records_truncated': self.diagnostics_seen > len(self.records),
                'authority': 'discovery_only; not admission or coverage review'}


def preview(recipe, actors, probes):
    kind = recipe['kind']; start, end = recipe['start'], recipe['end']
    if kind in ('successive_speech', 'speaker_walk'):
        actor, page = actors[0], start - 1
        for n in range(recipe['steps']):
            page = probes.first(actor, page, end, kind)
            if page is None: return None
            if kind == 'speaker_walk' and n < recipe['steps'] - 1:
                expression = call('the', call('filter', call('chars_on', call('page', page)),
                    {'lambda': {'param': 'x', 'body': call('neq', {'var': 'x'}, actor['expression'])}}))
                actor = probes.actor(expression, kind)
                if actor is None: return None
        return page
    if kind in ('speaking_gap', 'speaking_before'):
        a, b = [probes.first(actor, start - 1, end, kind) for actor in actors]
        if a is None or b is None or a == b: return None
        return max(0, abs(a - b) - 1) if kind == 'speaking_gap' else a < b
    if kind.startswith('shared_'):
        op = 'present' if kind == 'shared_presence_pages' else 'speaks_on'
        pages = []
        for page in range(start, end + 1):
            result = probes.predicate(op, actors, page, kind)
            if not known_truth(result): return None
            if result['value'] is True: pages.append(page)
        return pages if 2 <= len(pages) < end - start + 1 else None
    if kind == 'next_speech_line_count':
        page = probes.first(actors[0], start - 1, end, kind)
        if page is None: return None
        expression = call('line_count', actors[0]['expression'], call('page', page))
    else:
        for page in range(end, start - 1, -1):
            result = probes.predicate('present', actors, page, kind)
            if not known_truth(result): return None
            if result['value']: return page
        return None
    result = probes.query(expression, kind)
    return result['display'] if result['status'] == 'OK' and result['exact'] else None


def window_options(refs, last, minimum, maximum, shift, kind):
    first = max(a['page'] for a in refs) + 1
    maximum = min(maximum, last - first + 1)
    shift = min(shift, max(0, last - minimum + 1 - first))
    if maximum < minimum: return
    lengths = []; low, high = minimum, maximum
    while low <= high:
        lengths.append(high)
        if low != high: lengths.append(low)
        low += 1; high -= 1
    choices = ((offset, diagonal - offset, lengths[diagonal - offset])
               for diagonal in range(shift + len(lengths))
               for offset in range(max(0, diagonal - len(lengths) + 1), min(shift, diagonal) + 1))
    seen = set()
    for offset, _, size in choices:
        start = first + offset; end = min(last, start + size - 1)
        if end - start + 1 < minimum or (start, end) in seen: continue
        seen.add((start, end))
        for steps in ((3, 2) if kind in ('successive_speech', 'speaker_walk') else (1,)):
            yield {'kind': kind, 'references': refs, 'start': start, 'end': end, 'steps': steps, 'profile': VERSION}


def discover(g, v, rich, search_budget=1000, window=10, min_window=4, max_shift=20, probe_budget=192, max_windows=4, dependency_budget=None):
    probes = Probes(g, v, rich, probe_budget, search_budget)
    raw, speech, presence, people, counts = catalogue(g, rich)
    anchors = []; actors = {}
    for a in raw[:search_budget]:
        expression = speaker(a['quote'], a['page']); actor = probes.actor(expression, '_anchors')
        if actor and actor['id'] == a['identity']:
            anchors.append(a); actors[stable([a['quote'], a['page']])] = actor
    pools = {k: [] for k in KINDS}; tested = Counter(); positive_trials = Counter(); rejected = defaultdict(Counter); probe_hit = {}; trial_hit = {}
    dependencies = None
    if dependency_budget is not None:
        from .switch_search import Dependencies, DependencyBudget
        dependencies = Dependencies(g, v, rich, dependency_budget)
    for kind in (('speaker_walk',) if dependencies else PRIORITY):
        refs = (list(p) for p in islice(combinations(anchors, 2), search_budget) if p[0]['identity'] != p[1]['identity']) if kind in PAIR else ([a] for a in anchors)
        streams = deque((n, iter(window_options(r, len(g['page_ids']), min_window, window, max_shift, kind))) for n, r in enumerate(islice(refs, search_budget)))
        selected = Counter(); seen = set()
        while streams and tested[kind] < search_budget:
            number, stream = streams.popleft()
            try: recipe = next(stream)
            except StopIteration: continue
            tested[kind] += 1
            estimate = predict(recipe, speech, presence, people, counts)
            if estimate is None or kind == 'speaking_gap' and estimate == 0:
                rejected[kind]['no_known_target'] += 1
            else:
                positive_trials[kind] += 1
                # A complete shared set also needs evidence distinguishing both
                # branches. This prefilter never asserts an absent membership.
                s, e = recipe['start'], recipe['end']; ids = [a['identity'] for a in recipe['references']]
                members = speech if kind == 'shared_speaking_pages' else presence
                distinct = True
                if kind.startswith('shared_'):
                    left, right = ({p for p in members[c] if s <= p <= e} for c in ids)
                    distinct = bool(left - right and right - left)
                if not distinct:
                    rejected[kind]['no_known_branch_distinction'] += 1
                else:
                    aa = [actors[stable([a['quote'], a['page']])] for a in recipe['references']]
                    try: predicted = preview(recipe, aa, probes)
                    except ProbeBudget:
                        probe_hit[kind] = True; rejected[kind]['probe_budget_exhausted'] += 1; break
                    if predicted is None:
                        rejected[kind]['unproved_required_probe'] += 1
                    else:
                        clean = {**recipe, 'references': [{k: a[k] for k in ('quote', 'page')} for a in recipe['references']]}
                        # Respect the existing literal-overlap gate during search,
                        # rather than spending a proposal slot on a known hold.
                        if kind in ('successive_speech', 'speaker_walk', 'last_presence_window', 'next_speech_line_count', 'speaking_gap') and type(predicted) is int and re.search(r'(?<!\w)' + re.escape(str(predicted)) + r'(?!\w)', render(clean)):
                            rejected[kind]['known_numeric_overlap'] += 1
                            if selected[number] < max_windows: streams.append((number, stream))
                            continue
                        if kind == 'next_speech_line_count':
                            try:
                                baseline = probes.query(call('line_count', aa[0]['expression'], call('page', s - 1)), kind)
                            except ProbeBudget:
                                probe_hit[kind] = True; rejected[kind]['probe_budget_exhausted'] += 1; break
                            if baseline['status'] != 'OK' or not baseline['exact'] or baseline['value'] == predicted:
                                rejected[kind]['count_bypass_unchanged' if baseline['status'] == 'OK' and baseline['exact'] else 'count_bypass_unproved'] += 1
                                if selected[number] < max_windows: streams.append((number, stream))
                                continue
                        dependency = None
                        if dependencies:
                            try: dependency = dependencies.assess(clean)
                            except DependencyBudget:
                                rejected[kind]['dependency_budget_exhausted'] += 1
                                break
                            if not dependency['passed']:
                                rejected[kind][dependency['reason']] += 1
                                if selected[number] < max_windows: streams.append((number, stream))
                                continue
                        key = stable(compile_recipe(clean))
                        if key not in seen:
                            pools[kind].append({'recipe': clean, 'predicted': predicted, 'identity_targets': ids, **({'dependency_discovery': dependency} if dependencies else {})})
                            seen.add(key); selected[number] += 1
            if selected[number] < max_windows: streams.append((number, stream))
        trial_hit[kind] = bool(streams and tested[kind] >= search_budget)
    stats = {'anchor_count': len(anchors), 'raw_anchor_count': len(raw), 'source_anchor_checks': probes.used['_anchors'],
             'source_anchor_budget_hit': len(raw) > search_budget, 'recipes_tested': dict(tested),
             'search_budget_per_family': search_budget, 'search_budget_hit': {k: bool(trial_hit.get(k)) for k in KINDS},
             'reference_budget_hit': {k: (len(anchors) * (len(anchors) - 1) // 2 if k in PAIR else len(anchors)) > search_budget for k in KINDS},
             'probe_budget_hit': {k: bool(probe_hit.get(k)) for k in KINDS},
             'known_fact_targets': {k: len(pool) for k, pool in pools.items()},
             'eligible_windows': {k: len(pool) for k, pool in pools.items()}, 'known_positive_window_trials': dict(positive_trials),
             'discovery_rejections': {k: dict(v) for k, v in rejected.items()}, 'exhaustive': False,
             'limitation': 'Candidate-specific proof probes guide discovery only; full recipe and admission remain mandatory.'}
    diagnostics = probes.report()
    if dependencies:
        diagnostics['dependency_search'] = dependencies.report()
    return pools, stats, diagnostics


def chapter(g, v, rich, pins, per_family, max_executions, search_budget, window, min_window=4, max_shift=20, probe_budget=192, max_windows=4, dependency_budget=None):
    pools, stats, diagnostics = discover(g, v, rich, search_budget, window, min_window, max_shift, probe_budget, max_windows, dependency_budget)
    rows, items = [], []
    for kind, pool in pools.items():
        opportunities = Counter(stable(t['predicted']) for t in pool); used = Counter(); attempts = 0
        ids = set()
        while pool and len(ids) < per_family and attempts < max_executions:
            at = min(range(len(pool)), key=lambda n: (used[stable(pool[n]['predicted'])], opportunities[stable(pool[n]['predicted'])], stable(pool[n]['recipe'])))
            task = pool.pop(at); recipe = task['recipe']; program = compile_recipe(recipe)
            doc, check, known = execute('coverage_recipe', program, g, v, rich); attempts += 1
            row = {'kind': kind, 'recipe': recipe, 'result': doc['result'], 'proof_valid': check['proof_valid'], 'answer_proved': bool(known)}
            if 'dependency_discovery' in task: row['dependency_discovery'] = task['dependency_discovery']
            rows.append(row)
            if not known or doc['result']['display'] is None:
                row['uncertainty'] = explain('recipe', doc, g, rich)
                continue
            fmt = FORMATS[kind]; answer = {'type': 'bool' if fmt == 'boolean' else fmt, 'value': doc['result']['display'], 'identity_id': None}
            structure = 'chain' if kind in ('successive_speech', 'speaker_walk') else 'branch_combine' if kind.startswith('shared_') else 'compare' if kind in ('speaking_gap', 'speaking_before') else 'aggregate' if kind == 'next_speech_line_count' else 'direct'
            item = make(g, v, rich, pins, question=render(recipe), answer=answer, answer_format=fmt, structure=structure,
                engine='coverage_recipe', program=program, execution=doc, complexity={'meaningful_hops': None, 'branch_count': None, 'necessary_pages': [], 'profile_version': VERSION})
            if item['item_id'] not in ids:
                ids.add(item['item_id']); items.append(item); row['native_item_id'] = item['item_id']; used[stable(answer['value'])] += 1
    return {'chapter_id': g['chapter_id'], 'snapshots': {'graph': stable(g), 'visibility': stable(v), 'rich': stable(rich)},
            'search': stats, 'discovery_diagnostics': diagnostics, 'executions': rows, 'proposals': items,
            'counts': {'executed': len(rows), 'answer_proved': sum(r['answer_proved'] for r in rows), 'proposals': len(items)}}
