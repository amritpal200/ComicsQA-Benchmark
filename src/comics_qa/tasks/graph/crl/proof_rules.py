"""Independent CRL-1 semantic rules for proof checking. Never imports the interpreter.

Shared language syntax/types and CKG schemas are contracts; all value, coverage,
ordering, and support calculations below are checker-owned implementations.
"""
from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'evidence/graph'))
from ckg_schema import validate_graph
from build_ckg2 import validate_companion
from name_visibility import normalized

SUPPORT = ('facts', 'certificates', 'visibility_evidence', 'node_refs', 'range_pages')
TRUST = {'M': 0, 'A': 1, 'V': 2, 'H': 3}
CLOSED = frozenset(('closed_assumed', 'closed_audited', 'closed_verified'))


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def distinct(values):
    found = {}
    for value in values:
        found.setdefault(encoded(value), value)
    return list(found.values())


@dataclass
class Checked:
    value: object = None
    status: str = 'OK'
    exact: bool = True
    ordered: bool = False
    type: str = ''
    nid: int = -1
    support: dict = field(default_factory=lambda: {k: set() for k in SUPPORT})


def combine(value=None, inputs=(), status='OK', exact=None, ordered=False, **support):
    inputs = list(inputs)
    result = Checked(value=value, status=status, ordered=ordered,
                     exact=all(v.exact for v in inputs) if exact is None else exact)
    for name in SUPPORT:
        result.support[name] = set(support.get(name, ()))
        for child in inputs:
            result.support[name].update(child.support[name])
    return result


def unknown(inputs=()):
    return combine(inputs=inputs, status='UNKNOWN', exact=False)


def boolean(op, inputs):
    for item in inputs:
        if item.status not in ('OK', 'UNKNOWN'):
            return combine(inputs=inputs, status=item.status, exact=False)
    witnesses = [v for v in inputs if v.status == 'OK' and v.value is (op == 'or')]
    if witnesses:
        return combine(witnesses[0].value, [witnesses[0]])
    if any(v.status == 'UNKNOWN' for v in inputs):
        return unknown(inputs)
    return combine(op == 'and', inputs)


class World:
    def __init__(self, graph, visibility, closed=CLOSED, rich=None):
        validate_graph(graph)
        validate_companion(visibility, graph)
        if graph['chapter_id'] != visibility['chapter_id']:
            raise ValueError('Visibility chapter mismatch')
        self.graph = graph
        self.nodes = {n['id']: n for n in graph['nodes']}
        self.facts = {f['fact_id']: f for f in graph['facts']}
        self.rows = [f for f in graph['facts'] if f['answer_eligible'] and f['origin'] in ('H', 'V')]
        self.pages = list(graph['page_ids'])
        self.index = {p: i for i, p in enumerate(self.pages)}
        self.cover = {(c['page_id'], c['family']): c for c in graph['coverage']}
        self.visibility = {v['identity_id']: v for v in visibility['visibility']}
        self.evidence = {e['evidence_id']: e for e in visibility['evidence']}
        self.closed = closed
        try:
            from .rich_contract import prepare, fingerprint
        except ImportError:
            from rich_contract import prepare, fingerprint
        self.rich_hash = fingerprint(rich)
        fs, cs = prepare(graph, visibility, rich)
        self.facts.update({f['fact_id']: f for f in fs})
        self.rows.extend(fs)
        self.cover.update({(c['page_id'], c['family']): c for c in cs})

    def rich_query(self, op, args):
        # Checker-owned enumeration and matching; never calls producer query logic.
        import re
        import unicodedata
        def normalized_quote(s):
            return ' '.join(unicodedata.normalize('NFKC',s).casefold().replace('’',"'").split())
        def word_sequence(s):
            return re.findall(r"[^\W_]+(?:'[^\W_]+)*",unicodedata.normalize('NFKC',s).casefold().replace('’',"'"))
        scope = self.scope(args['on']); text = args['s'].value
        transcripts = [f for f in self.rows if f['rel']=='transcript' and self.page(f['args'][0]) in scope]
        inputs = list(args.values()); used = {f['fact_id'] for f in transcripts}
        if op == 'quote':
            target = normalized_quote(text)
            found = self.sort(f['args'][0] for f in transcripts if target and normalized_quote(f['args'][1])==target)
            collection = self.scan(found,scope,['text_boxes','rich_ocr'],inputs,facts=used)
            if len(found)>1:return combine(inputs=[collection],status='AMBIGUOUS',exact=False)
            if not collection.exact:return unknown([collection])
            if not found:return combine(inputs=[collection],status='EMPTY')
            return combine(found[0],[collection])
        identity = self.name(text); inputs.append(identity)
        if identity.status!='OK':return combine(inputs=inputs,status=identity.status,exact=False)
        target=word_sequence(text); found=set()
        for f in transcripts:
            sequence=word_sequence(f['args'][1])
            if target and any(sequence[j:j+len(target)]==target for j in range(len(sequence)-len(target)+1)):
                found.add(f['args'][0])
        full=set(found)
        for f in self.rows:
            if f['rel']=='name_occurs' and self.page(f['args'][0]) in scope and f['args'][1]==identity.value and normalized(f['args'][2])==normalized(text):
                found.add(f['args'][0]);used.add(f['fact_id'])
        values=self.sort(found)
        result=self.scan(values,scope,['text_boxes','rich_ocr'],inputs,facts=used,ordered=self.ordered(values))
        if result.exact and found!=full:result.exact=False
        return result

    def page(self, value):
        node = self.nodes.get(value, {}) if isinstance(value, str) else {}
        return value if node.get('type') == 'Page' else node.get('page_id')

    def ordered(self, values):
        positions = [self.index.get(self.page(v)) for v in values]
        return len(values) < 2 or (None not in positions and all(a < b for a, b in zip(positions, positions[1:])))

    def sort(self, values):
        return sorted(distinct(values), key=lambda v: (self.index.get(self.page(v), len(self.pages)), encoded(v)))

    @staticmethod
    def scope(value):
        return [value.value] if value.type == 'Page' else value.value

    def scan(self, value, pages, families, inputs=(), **support):
        certificates = [self.cover[(p, f)] for p in pages for f in families]
        out = combine(value, inputs, certificates={c['coverage_id'] for c in certificates},
                      range_pages=pages, **support)
        out.exact = out.exact and all(c['status'] in self.closed for c in certificates)
        return out

    def query(self, op, pages, character=None):
        # Enumerate the full trusted relation table, never the submitted proof's subset.
        families = ['char_boxes', 'names']
        if op == 'apps': families = ['char_boxes']
        if op == 'texts': families = ['text_boxes']
        if op == 'lines': families = ['text_boxes', 'speaker_links']
        if op in ('lines_of', 'pages_speaking'):
            families = ['char_boxes', 'names', 'text_boxes', 'speaker_links']
        values, used = [], set()
        for f in self.rows:
            r, a = f['rel'], f['args']
            item = None
            if op in ('apps', 'texts') and r == 'on_page' and a[1] in pages:
                kind = 'Appearance' if op == 'apps' else 'Text'
                if self.nodes[a[0]]['type'] == kind: item = a[0]
            elif op == 'lines' and r == 'is_line' and self.page(a[0]) in pages:
                item = a[0]
            elif op == 'apps_of' and r == 'is_char' and a[1] == character and self.page(a[0]) in pages:
                item = a[0]
            elif op == 'lines_of' and r == 'spoken_by' and self.page(a[0]) in pages:
                links = [x for x in self.rows if x['rel'] == 'is_char' and x['args'] == [a[1], character]]
                if links:
                    item = a[0]
                    used.update(x['fact_id'] for x in links)
            elif op == 'chars' and r == 'present' and a[1] in pages:
                item = a[0]
            elif op in ('pages_with', 'pages_speaking') and r == ('present' if op == 'pages_with' else 'speaks_on'):
                if a[0] == character and a[1] in pages: item = a[1]
            elif op == 'co_present' and r == 'co_present' and a[2] in pages and character in a[:2]:
                item = a[1] if a[0] == character else a[0]
            if item is not None:
                values.append(item)
                used.add(f['fact_id'])
        values = self.sort(values)
        return self.scan(values, pages, families, facts=used, ordered=self.ordered(values))

    def name(self, form):
        form = normalized(form)
        candidates = [n for n in self.nodes.values() if n['type'] == 'Character' and not n['generic']
                      and any(normalized(s) == form for s in [n['canonical_name'], *n['aliases']])]
        if len(candidates) > 1: return combine(status='AMBIGUOUS', exact=False)
        if not candidates: return unknown()
        cid = candidates[0]['id']
        evidence = sorted(e['evidence_id'] for e in self.evidence.values()
                          if e['identity_id'] == cid and e['status'] == 'verified' and e['normalized_form'] == form)
        facts = [f['fact_id'] for f in self.rows if f['rel'] in ('named', 'alias')
                 and f['args'][0] == cid and normalized(f['args'][1]) == form]
        if not evidence or not facts: return unknown()
        return combine(cid, facts=facts, visibility_evidence=evidence[:1], node_refs=[cid])

    def relation(self, op, source):
        if op == 'page_of' and source in self.pages:
            return combine(source, node_refs=[source], range_pages=[source])
        rel = {'page_of': 'on_page', 'char_of': 'is_char', 'speaker': 'spoken_by'}[op]
        rows = [f for f in self.rows if f['rel'] == rel and f['args'][0] == source]
        targets = distinct(f['args'][1] for f in rows)
        page = self.page(source)
        base = combine(facts=[f['fact_id'] for f in rows], node_refs=[source], range_pages=[page] if page else [])
        if len(targets) > 1: return combine(inputs=[base], status='AMBIGUOUS')
        if op == 'speaker':
            base = self.scan(None, [page], ['text_boxes', 'speaker_links'], [base])
            if not base.exact: return unknown([base])
        if not targets: return unknown([base])
        return combine(targets[0], [base], node_refs=targets)

    def speaking_character(self, text):
        speaker = self.relation('speaker', text)
        if speaker.status != 'OK': return speaker
        char = self.relation('char_of', speaker.value)
        return combine(char.value, [speaker, char], status=char.status)

    def predicate(self, rel, c, p):
        facts = [f['fact_id'] for f in self.rows if f['rel'] == rel and f['args'] == [c, p]]
        families = ['char_boxes', 'names'] + (['text_boxes', 'speaker_links'] if rel == 'speaks_on' else [])
        result = self.scan(bool(facts), [p], families, facts=facts)
        return unknown([result]) if not facts and not result.exact else result

    def select(self, op, sequence, index=None, anchor=None):
        values = sequence.value
        if op == 'the' and len(values) > 1:
            return combine(inputs=[sequence], status='AMBIGUOUS', exact=False)
        if not sequence.exact: return unknown([sequence])
        if not values: return combine(inputs=[sequence], status='EMPTY')
        if op == 'the': return combine(values[0], [sequence])
        positions = []
        if op in ('next', 'prev', 'rank'):
            hits = [i for i, x in enumerate(values) if x == anchor]
            if len(hits) != 1:
                return combine(inputs=[sequence], status='AMBIGUOUS' if hits else 'EMPTY')
            positions.append(hits[0])
            selected = hits[0] + {'next': 1, 'prev': -1, 'rank': 0}[op]
        elif op == 'first': selected = 0
        elif op == 'last': selected = len(values) - 1
        else:
            if index < 1: return combine(inputs=[sequence], status='ERROR', exact=False)
            selected = index - 1
        if selected < 0 or selected >= len(values): return combine(inputs=[sequence], status='EMPTY')
        positions.append(selected)
        if not sequence.ordered:
            pages = [self.page(x) for x in values]
            if any(pages[i] is None or pages.count(pages[i]) != 1 for i in positions):
                return unknown([sequence])
        return combine(selected + 1 if op == 'rank' else values[selected], [sequence])

    def discourse(self, op, args):
        lines = self.query('lines', self.scope(args['span']) if 'span' in args else self.pages)
        if not lines.exact or not lines.ordered: return unknown([lines])
        if op in ('next_line', 'prev_line'):
            return self.select('next' if op == 'next_line' else 'prev', lines, anchor=args['t'].value)
        support, speakers = [lines], []
        for text in lines.value:
            char = self.speaking_character(text)
            support.append(char)
            if char.status != 'OK': return unknown(support)
            speakers.append(char.value)
        if op == 'next_other_speaker':
            if args['t'].value in lines.value:
                i = lines.value.index(args['t'].value)
                for speaker in speakers[i+1:]:
                    if speaker != speakers[i]: return combine(speaker, support)
            return combine(inputs=support, status='EMPTY')
        if op == 'exchanges':
            pair = {args['c1'].value, args['c2'].value}
            count = sum({x, y} == pair for x, y in zip(speakers, speakers[1:])) if len(pair) == 2 else 0
            return combine(count, support)
        turns = []
        for text, speaker in zip(lines.value, speakers):
            if not turns or turns[-1]['speaker'] != speaker:
                turns.append({'speaker': speaker, 'lines': [], 'pages': []})
            turns[-1]['lines'].append(text)
            p = self.page(text)
            if p not in turns[-1]['pages']: turns[-1]['pages'].append(p)
        return combine(turns, support, ordered=True)

    def operation(self, op, args):
        vals = {k: x.value for k, x in args.items()}
        inputs = list(args.values())
        def attached(out):
            return combine(out.value, inputs + [out], status=out.status, ordered=out.ordered)
        if op == 'unknown': return unknown()
        if op in ('ctx', 'page', 'pages'):
            lo, hi = (1, len(self.pages)) if op == 'ctx' else (vals['i'], vals.get('j', vals['i']))
            if not 1 <= lo <= hi <= len(self.pages): return combine(status='ERROR', exact=False)
            pages = self.pages[lo-1:hi]
            return self.scan(pages[0] if op == 'page' else pages, pages, ['page_sequence'], inputs,
                             node_refs=pages, ordered=True)
        if op == 'char': return self.name(vals['name'])
        if op in ('chars', 'apps', 'texts', 'lines', 'apps_of', 'lines_of', 'pages_with', 'pages_speaking', 'co_present', 'chars_on'):
            if op == 'co_present' and vals['unit'] != 'page': return unknown(inputs)
            scope = self.scope(args['p' if op == 'chars_on' else 'span'])
            return attached(self.query('chars' if op == 'chars_on' else op, scope, vals.get('c')))
        if op in ('page_of', 'char_of', 'speaker', 'speaker_char'):
            source = next(iter(vals.values()))
            return attached(self.speaking_character(source) if op == 'speaker_char' else self.relation(op, source))
        if op in ('present', 'speaks_on'):
            return attached(self.predicate(op, vals['c'], vals['p']))
        if op == 'silent_on':
            speech = self.predicate('speaks_on', vals['c'], vals['p'])
            negative = combine(not speech.value, [speech]) if speech.status == 'OK' and speech.exact else unknown([speech])
            return attached(boolean('and', [self.predicate('present', vals['c'], vals['p']), negative]))
        if op == 'together':
            return attached(boolean('and', [self.predicate('present', vals[c], vals['unit']) for c in ('c1', 'c2')]))
        if op == 'is_named': return combine(not self.nodes[vals['c']]['generic'], inputs, node_refs=[vals['c']])
        if op in ('eq', 'neq'):
            if not all(x.exact for x in inputs): return unknown(inputs)
            x, y = vals['x'], vals['y']
            equal = set(map(encoded, x)) == set(map(encoded, y)) if args['x'].type.startswith('Set[') else x == y
            return combine(equal if op == 'eq' else not equal, inputs)
        if op == 'in':
            if vals['x'] in vals['S']: return combine(True, inputs)
            return combine(False, inputs) if args['S'].exact else unknown(inputs)
        if op in ('first', 'last', 'nth', 'next', 'prev', 'rank', 'the'):
            return attached(self.select(op, args['S'], vals.get('k'), vals.get('x')))
        if op in ('span_before', 'span_after', 'between', 'gap', 'precedes'):
            p, q = self.page(vals['x']), self.page(vals['y']) if 'y' in vals else None
            if p is None or ('y' in vals and q is None): return unknown(inputs)
            if op == 'precedes':
                if p == q and vals['x'] != vals['y']: return unknown(inputs)
                return attached(self.scan(self.index[p] < self.index[q], [p, q], ['page_sequence']))
            if op == 'gap': return attached(self.scan(max(0, abs(self.index[p]-self.index[q])-1), [p, q], ['page_sequence']))
            if op == 'between':
                a, b = sorted([self.index[p], self.index[q]])
                pages = self.pages[a+1:b]
            else:
                pages = [v for v in self.scope(args['within']) if
                         (self.index[v] < self.index[p] if op == 'span_before' else self.index[v] > self.index[p])]
            return attached(self.scan(pages, pages, ['page_sequence'], ordered=True))
        if op in ('first_app', 'last_app', 'next_app', 'first_line', 'nth_line', 'line_count'):
            pages = self.pages[self.index[self.page(vals['after'])]+1:] if op == 'next_app' else self.scope(args['span'])
            sequence = self.query('apps_of' if 'app' in op else 'lines_of', pages, vals['c'])
            if op == 'next_app' and sequence.value:
                end = min(self.index[self.page(v)] for v in sequence.value)
                sequence = self.query('apps_of', [p for p in pages if self.index[p] <= end], vals['c'])
            if op == 'line_count':
                return attached(combine(len(sequence.value), [sequence]) if sequence.exact else unknown([sequence]))
            return attached(self.select('last' if op == 'last_app' else 'nth' if op == 'nth_line' else 'first', sequence, vals.get('k')))
        if op == 'longest_streak':
            sequence = self.query('pages_with', self.scope(args['span']), vals['c'])
            if not sequence.exact: return attached(unknown([sequence]))
            best = run = 0
            indices = sorted(self.index[p] for p in sequence.value)
            for i, number in enumerate(indices):
                run = run + 1 if i and number == indices[i-1] + 1 else 1
                best = max(best, run)
            return attached(combine(best, [sequence]))
        if op in ('next_line', 'prev_line', 'next_other_speaker', 'turns', 'exchanges'):
            return attached(self.discourse(op, args))
        if op in ('union', 'intersect', 'diff'):
            if op == 'diff' and not all(x.exact for x in inputs): return unknown(inputs)
            left, right = {encoded(x): x for x in vals['A']}, {encoded(x): x for x in vals['B']}
            keys = set(left) | set(right) if op == 'union' else set(left) & set(right) if op == 'intersect' else set(left) - set(right)
            values = self.sort([{**left, **right}[k] for k in keys])
            return combine(values, inputs, ordered=self.ordered(values))
        if op == 'distinct': return combine(distinct(vals['S']), inputs, ordered=args['S'].ordered)
        if op in ('exists', 'none'):
            if op == 'exists' and vals['S']: return combine(True, inputs)
            if not args['S'].exact: return unknown(inputs)
            return combine(bool(vals['S']) if op == 'exists' else not vals['S'], inputs)
        if op == 'not': return combine(not vals['p'], inputs) if args['p'].exact else unknown(inputs)
        if op == 'at_least':
            if vals['n'] < 0: return combine(status='ERROR', exact=False)
            if len(vals['S']) >= vals['n']: return combine(True, inputs)
            return combine(False, inputs) if args['S'].exact else unknown(inputs)
        if op in ('count', 'sum', 'min', 'max', 'mode'):
            if not args['S'].exact: return unknown(inputs)
            values = vals['S']
            if op == 'count': return combine(len(values), inputs)
            if op == 'sum': return combine(sum(values), inputs)
            if not values: return combine(inputs=inputs, status='EMPTY')
            if op == 'mode':
                freq = Counter(map(encoded, values)); best = max(freq.values())
                winners = [k for k, v in freq.items() if v == best]
                if len(winners) != 1: return combine(inputs=inputs, status='AMBIGUOUS')
                value = json.loads(winners[0])
            else: value = min(values) if op == 'min' else max(values)
            return combine(value, inputs)
        if op in ('minus', 'compare'):
            if not all(x.exact for x in inputs): return unknown(inputs)
            difference = vals['x'] - vals['y']
            return combine(difference if op == 'minus' else 'more' if difference > 0 else 'fewer' if difference < 0 else 'equal', inputs)
        raise ValueError('Unsupported checker operation: ' + op)

    def functional(self, op, args, evaluated):
        sequence = args['S']; inputs = list(args.values()) + evaluated
        failures = [v for v in evaluated if v.status not in ('OK', 'UNKNOWN')]
        if failures: return combine(inputs=inputs, status=failures[0].status, exact=False)
        if op in ('exists', 'forall', 'none'):
            if op == 'none' and (not sequence.exact or any(v.status != 'OK' or not v.exact for v in evaluated)):
                return unknown(inputs)
            deciding = [v for v in evaluated if v.status == 'OK' and v.value is (op != 'forall')]
            if deciding: return combine(op == 'exists', [sequence, deciding[0]])
            if not sequence.exact or any(v.status == 'UNKNOWN' for v in evaluated): return unknown(inputs)
            return combine(op != 'exists', inputs)
        if op == 'filter':
            values = [x for x, test in zip(sequence.value, evaluated) if test.status == 'OK' and test.value is True]
            return combine(values, inputs, exact=sequence.exact and all(v.status == 'OK' and v.exact for v in evaluated),
                           ordered=sequence.ordered or self.ordered(values))
        if any(v.status != 'OK' for v in evaluated): return unknown(inputs)
        if op == 'map': return combine([v.value for v in evaluated], inputs, ordered=sequence.ordered)
        if not sequence.exact or any(not v.exact for v in evaluated): return unknown(inputs)
        if op == 'group_count':
            counts = Counter(encoded(v.value) for v in evaluated)
            return combine([[json.loads(k), counts[k]] for k in sorted(counts)], inputs)
        keys = [self.index[v.value] if v.type == 'Page' else v.value for v in evaluated]
        if op == 'sort_by':
            if len(set(map(encoded, keys))) != len(keys): return combine(inputs=inputs, status='AMBIGUOUS')
            return combine([v for _, v in sorted(zip(keys, sequence.value), key=lambda pair: pair[0])], inputs, ordered=True)
        if not keys: return combine(inputs=inputs, status='EMPTY')
        count = args['k'].value if op == 'top_k' else 1
        if count < 1: return combine(inputs=inputs, status='ERROR', exact=False)
        if count > len(keys): return combine(inputs=inputs, status='EMPTY')
        ranking = sorted(range(len(keys)), key=lambda i: (keys[i] if op == 'argmin' else -keys[i], encoded(sequence.value[i])))
        if count < len(keys):
            boundary, runner = keys[ranking[count-1]], keys[ranking[count]]
            distance = runner - boundary if op == 'argmin' else boundary - runner
            if distance < max(2, boundary / 4): return combine(inputs=inputs, status='AMBIGUOUS')
        if op == 'top_k' and len({keys[i] for i in ranking[:count]}) != count:
            return combine(inputs=inputs, status='AMBIGUOUS')
        selected = [sequence.value[i] for i in ranking[:count]]
        return combine(selected if op == 'top_k' else selected[0], inputs, ordered=op == 'top_k')
