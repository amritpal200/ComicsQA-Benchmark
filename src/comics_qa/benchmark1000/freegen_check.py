"""Independent checker for free-generation items (freegen.1). Does not import the generator.

An item carries its claims already resolved to graph IDs. Each claim is re-checked against raw graph facts, coverage,
CKG-2 visibility, CKG-3 transcripts, core v1 reading order (model fact) and audited event facts (model fact). The
answer must be one of the cited entities (or, for line_sequence, the cited lines in their true order), the question
must contain no pack IDs, quote only verified distinct lines, and not contain the answer. Answer uniqueness is not
provable from claims, so items always keep needs_uniqueness_check.
"""
import difflib
import json
import re
from functools import lru_cache
from pathlib import Path
from comics_qa.evidence.graph.rich.model import normalize

CLOSED = ('closed_assumed', 'closed_audited', 'closed_verified')
PACK_ID = re.compile(r'\b[CPLE]\d+(\.\d+)?\b')
QUOTE = re.compile(r'"([^"]+)"')


@lru_cache(maxsize=4)
def _order(core_root, chapter_id):
    out = {}
    for raw in (Path(core_root) / 'pages.jsonl').read_text().splitlines():
        page = json.loads(raw)
        if page['chapter_id'] == chapter_id:
            out.update({t['text_id']: (page['page_id'], t['reading_order']) for t in page.get('texts', []) if isinstance(t.get('reading_order'), int)})
    return out


def _words(s):
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in normalize(s)).split())


def _name(x):
    if not x or x.get('generic') or not x.get('verified_forms'): return None
    if x.get('canonical_visible') and x.get('canonical_name'): return x['canonical_name']
    return sorted(x['verified_forms'], key=lambda f: (-len(f), f))[0]


def _distinct(quote, own_id, transcripts, threshold):
    q = normalize(quote)
    for t in transcripts:
        if t['id'] == own_id: continue
        for raw in (t.get('consensus'), t.get('magi_text'), t.get('paddle_text')):
            if not raw: continue
            r = normalize(raw)
            if r == q or q in r or (r in q and 2 * len(r) >= len(q)) or difflib.SequenceMatcher(None, q, r, autojunk=False).ratio() >= threshold:
                return False
    return True


class Facts:
    def __init__(self, g, v, rich, core_root, events):
        eligible = [f for f in g['facts'] if f['origin'] in ('H', 'V') and f['answer_eligible']]
        self.pages = g['page_ids']; self.pos = {p: i for i, p in enumerate(self.pages)}
        self.page_of = {f['args'][0]: f['args'][1] for f in eligible if f['rel'] == 'on_page'}
        app = {f['args'][0]: f['args'][1] for f in eligible if f['rel'] == 'is_char'}
        links = {}
        for f in eligible:
            if f['rel'] == 'spoken_by': links.setdefault(f['args'][0], []).append(app.get(f['args'][1]))
        self.speaker = {t: s[0] for t, s in links.items() if len(s) == 1 and s[0]}
        self.lines = {f['args'][0] for f in eligible if f['rel'] == 'is_line'}
        self.drawn = {}
        for f in eligible:
            if f['rel'] == 'present': self.drawn.setdefault(f['args'][0], set()).add(f['args'][1])
        self.cov = {(c['page_id'], c['family']): c['status'] for c in g['coverage']}
        self.vis = {x['identity_id']: x for x in v['visibility']}
        self.transcripts = rich['transcripts']
        self.text = {t['text_id']: t for t in rich['transcripts'] if t.get('text_id')}
        self.order = _order(core_root, g['chapter_id'])
        self.events = events

    def closed(self, page, families):
        return all(self.cov.get((page, f)) in CLOSED for f in families)

    def speaks_on(self, c, page):
        return any(s == c and self.page_of.get(t) == page for t, s in self.speaker.items())


def check_claim(F, claim):
    """Returns (ok, tier) with tier H (human/verified), M (reading order) or A (audited event fact)."""
    kind, a = claim.get('type'), claim.get('args', [])
    try:
        if kind == 'SAYS': return F.speaker.get(a[0]) == a[1] and a[0] in F.lines, 'H'
        if kind == 'ON_PAGE': return F.page_of.get(a[0]) == a[1], 'H'
        if kind == 'DRAWN': return a[1] in F.drawn.get(a[0], set()), 'H'
        if kind == 'NOT_DRAWN': return F.closed(a[1], ('char_boxes', 'names')) and a[1] not in F.drawn.get(a[0], set()), 'H'
        if kind == 'SILENT': return F.closed(a[1], ('text_boxes', 'speaker_links')) and not F.speaks_on(a[0], a[1]), 'H'
        if kind == 'FIRST_DRAWN':
            first = F.pos[a[1]]
            return (a[1] in F.drawn.get(a[0], set()) and all(F.closed(p, ('char_boxes', 'names')) and p not in F.drawn.get(a[0], set())
                                                             for p in F.pages[:first])), 'H'
        if kind in ('BEFORE', 'NEXT_LINE'):
            p1, p2 = F.page_of.get(a[0]), F.page_of.get(a[1])
            if p1 is None or p2 is None: return False, 'H'
            if kind == 'BEFORE' and p1 != p2: return F.pos[p1] < F.pos[p2], 'H'
            if p1 != p2 or a[0] not in F.order or a[1] not in F.order: return False, 'M'
            k1, k2 = F.order[a[0]][1], F.order[a[1]][1]
            if kind == 'BEFORE': return k1 < k2, 'M'
            between = [t for t, (p, k) in F.order.items() if p == p1 and k1 < k < k2]
            return k2 > k1 and not between, 'M'
        if kind == 'EVENT':
            e = F.events.get(a[0])
            return bool(e) and e['identity_id'] == a[1] and e.get('confirmation', {}).get('control') == 'no', 'A'
    except (IndexError, KeyError, TypeError):
        return False, 'H'
    return False, 'H'


def display(F, ref_type, ref):
    if ref_type == 'C': return _name(F.vis.get(ref))
    if ref_type == 'P': return F.pos[ref] + 1 if ref in F.pos else None
    if ref_type == 'L':
        t = F.text.get(ref)
        return t['consensus'] if t and t.get('quote_eligible') else None
    return None


def check_item(item, g, v, rich, cfg, events):
    F = Facts(g, v, rich, cfg.get('core_root', '/data/151-3/comics/ComicsQA_Benchmark/core/v1'), events)
    errors, tiers = [], set()
    ev = item.get('evidence', {}); claims = ev.get('claims', []); q = item.get('question', '')
    if not claims: errors.append('no_claims')
    for c in claims:
        ok, tier = check_claim(F, c)
        if not ok: errors.append('claim_false:' + c.get('type', '?'))
        tiers.add(tier)
    if PACK_ID.search(q): errors.append('pack_id_in_question')
    for quote in QUOTE.findall(q):
        match = [t for t in F.transcripts if t.get('text_id') and t.get('quote_eligible') and normalize(t['consensus']) == normalize(quote)]
        if len(match) != 1 or not _distinct(quote, match[0]['id'], F.transcripts, cfg.get('max_similarity', 0.6)): errors.append('quote_not_distinct')
    fmt, ans = item.get('answer_format'), item.get('answer', {})
    cited = {x for c in claims for x in c.get('args', [])}
    if fmt == 'sequence':
        refs = ans.get('refs', [])
        if len(refs) < 3 or any(r not in cited for r in refs): errors.append('answer_not_cited')
        else:
            if any(r not in F.page_of or r not in F.order for r in refs): return {'verified': False, 'errors': errors + ['answer_ref']}
            truth = sorted(refs, key=lambda r: (F.pos[F.page_of[r]], F.order[r][1]))
            if truth != refs: errors.append('sequence_order')
            if len({F.page_of[r] for r in refs}) < len(refs): tiers.add('M')
            if ans.get('value') != [display(F, 'L', r) for r in refs] or None in ans.get('value', [None]): errors.append('answer_value')
    else:
        ref = ans.get('ref'); kind = {'character': 'C', 'page': 'P', 'quote': 'L'}.get(fmt)
        if kind is None or ref not in cited: errors.append('answer_not_cited')
        value = display(F, kind, ref) if kind else None
        if value is None or ans.get('value') != value: errors.append('answer_value')
        if kind == 'C' and any(' ' + _words(f) + ' ' in ' ' + _words(q) + ' ' for f in F.vis.get(ref, {}).get('verified_forms', [])):
            errors.append('answer_in_question')
        if kind == 'L' and value and normalize(value) in normalize(q): errors.append('answer_in_question')
        if kind == 'P' and value and re.search(r'\bpage %d\b' % value, q, re.I): errors.append('answer_in_question')
    used = sorted({'M': 'magi_reading_order', 'A': 'audited_event_facts'}[t] for t in tiers if t in ('M', 'A'))
    if item.get('uses_model_facts', []) != used: errors.append('model_fact_tags')
    flags = item.get('verification', {}).get('flags', [])
    if item.get('track') != 'experimental' or not {'needs_human_verification', 'needs_uniqueness_check'} <= set(flags): errors.append('flags')
    return {'verified': not errors, 'errors': errors}
