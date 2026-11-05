"""Story families from trusted H/V evidence (improvement plan S3): no page numbers in the wording.

Families (version story_families.1):
- quote_speaker_choice: 'Who says "<quote>"?' with four named characters of the chapter as options.
- quote_speaker_open (v2): the same question without options, where the chapter has too few readable names.
- quote_order: four lines from four different pages; answer their chapter order.
- conversation_partner (v2): the only other identified character drawn on the page of a line.
- next_speech_partner (v3): line -> its speaker -> the next page where they speak -> the only other identified character there.
- shared_character (v3): the only identified character drawn on both pages of two lines (neither line's speaker).
- contrast pairs (v4): two members that differ in one condition and have different answers, scored both-correct:
  `choice` = 'Who says ...?' for two lines with identical options; `partner` = conversation_partner for two
  lines of the same speaker with different partners. Members keep their family and pass its checker.

A quote is located without a page number. It must pass a distinctiveness certificate: no other text
region of the chapter has a raw OCR reading (consensus, MAGI or PaddleOCR) that contains, is contained
in, or is similar to it. Speaker, transcript, page and name evidence are H/V graph facts. Every item is
re-verified by `story_check` (separate implementation) before publication.
"""
import difflib
import fcntl
import random
from collections import Counter, defaultdict
from pathlib import Path
from comics_qa.evidence.graph.rich.model import normalize
from .io import digest, member, publish, read, separate, stable, verify_manifest

VERSION = 'story_families.4'
VERSIONS = ('story_families.1', 'story_families.2', 'story_families.3', VERSION, 'story_events.1', 'story_expand.1',
            'story_experimental.1', 'freegen.1')
CLOSED = ('closed_assumed', 'closed_audited', 'closed_verified')
ITEM = 'comics_qa.benchmark1000.story_item.1'
STORE = 'comics_qa.benchmark1000.story_store.1'
FAMILIES = ('quote_speaker_choice', 'quote_speaker_open', 'quote_order', 'conversation_partner', 'next_speech_partner', 'shared_character',
            'event_actor_choice', 'event_order', 'script_error', 'speaker_table', 'name_trap', 'line_of_character',
            'next_line_speaker', 'page_line_order', 'free_generation')
LETTERS = 'ABCD'
DEFAULTS = {'min_words': 4, 'min_chars': 16, 'max_similarity': 0.6, 'per_family': 12, 'per_answer_identity': 3,
            'order_lines': 4, 'seed': 0, 'pairs_per_kind': 3}


def display_name(vis):
    """Readable display form: verified canonical name, else the longest verified form."""
    if vis.get('generic') or not vis.get('verified_forms'): return None
    if vis.get('canonical_visible') and vis.get('canonical_name'): return vis['canonical_name']
    return sorted(vis['verified_forms'], key=lambda f: (-len(f), f))[0]


def readings(record):
    return [normalize(t) for t in (record.get('consensus'), record.get('magi_text'), record.get('paddle_text')) if t]


def similar(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def distinctiveness(quote, source_id, transcripts, max_similarity):
    """Compare a normalized quote with every reading of every other text region in the chapter."""
    q = normalize(quote); best, nearest, n = 0.0, None, 0
    for record in transcripts:
        if record['id'] == source_id: continue
        for r in readings(record):
            n += 1
            if r == q or q in r or (r in q and len(r) >= len(q) / 2):
                return {'passed': False, 'reason': 'contains_or_contained', 'nearest': record['id'], 'compared_readings': n}
            s = similar(q, r)
            if s > best: best, nearest = s, record['id']
    passed = best < max_similarity
    return {'passed': passed, 'reason': None if passed else 'similar_reading', 'max_similarity': round(best, 4),
            'nearest': nearest, 'compared_readings': n, 'threshold': max_similarity}


class World:
    """Indexes of one chapter's trusted facts."""
    def __init__(self, g, v, rich):
        self.g, self.v, self.rich = g, v, rich
        self.pos = {p: i + 1 for i, p in enumerate(g['page_ids'])}
        eligible = [f for f in g['facts'] if f['origin'] in ('H', 'V') and f['answer_eligible']]
        self.on_page = {f['args'][0]: f for f in eligible if f['rel'] == 'on_page'}
        self.is_char = {f['args'][0]: f for f in eligible if f['rel'] == 'is_char'}
        self.spoken_by = defaultdict(list)
        for f in eligible:
            if f['rel'] == 'spoken_by': self.spoken_by[f['args'][0]].append(f)
        self.is_line = {f['args'][0] for f in eligible if f['rel'] == 'is_line'}
        self.presence = defaultdict(set)
        for f in eligible:
            if f['rel'] == 'present': self.presence[f['args'][0]].add(f['args'][1])
        self.speaks = {self.is_char[f[0]['args'][1]]['args'][1] for f in self.spoken_by.values()
                       if len(f) == 1 and f[0]['args'][1] in self.is_char}
        self.names = {x['identity_id']: display_name(x) for x in v['visibility']}
        self.names = {k: n for k, n in self.names.items() if n}
        self.vis = {x['identity_id']: x for x in v['visibility']}
        self.generic = {n['id'] for n in g['nodes'] if n['type'] == 'Character' and n.get('generic')}
        self.coverage = {(c['page_id'], c['family']): c for c in g['coverage']}
        self.on_page_ids = defaultdict(set)
        for c, pages in self.presence.items():
            for p in pages: self.on_page_ids[p].add(c)
        self.speaking = defaultdict(dict)  # identity -> page -> [spoken_by fact, is_char fact]
        for text, links in self.spoken_by.items():
            if len(links) == 1 and links[0]['args'][1] in self.is_char and text in self.on_page:
                c = self.is_char[links[0]['args'][1]]['args'][1]
                self.speaking[c].setdefault(self.on_page[text]['args'][1], [links[0]['fact_id'], self.is_char[links[0]['args'][1]]['fact_id']])
        self.transcripts = rich['transcripts']
        top = sorted(self.presence, key=lambda c: (-len(self.presence[c]), c))
        self.frequent = [c for c in top if c in self.names][:2]

    def closed(self, page, families):
        return all(self.coverage.get((page, f), {}).get('status') in CLOSED for f in families)

    def identified(self, page):
        return {c for c in self.on_page_ids[page] if c not in self.generic}

    def forms(self, c):
        return sorted(self.vis[c]['verified_forms']) if c in self.vis else []

    def speaker(self, text_id):
        links = self.spoken_by.get(text_id, [])
        if len(links) != 1 or links[0]['args'][1] not in self.is_char: return None, []
        char_fact = self.is_char[links[0]['args'][1]]
        return char_fact['args'][1], [links[0]['fact_id'], char_fact['fact_id']]

    def lines(self, cfg):
        """Dialogue lines with a verified transcript, a page, enough length and a distinctiveness certificate."""
        out = []
        for t in self.transcripts:
            tid, quote = t.get('text_id'), t.get('consensus')
            if not (t.get('quote_eligible') and tid and quote and tid in self.is_line and tid in self.on_page): continue
            if len(quote.split()) < cfg['min_words'] or len(normalize(quote)) < cfg['min_chars']: continue
            if '"' in quote: continue  # inner double quotes would make the question's quoting ambiguous
            cert = distinctiveness(quote, t['id'], self.transcripts, cfg['max_similarity'])
            if not cert['passed']: continue
            identity, facts = self.speaker(tid)
            out.append({'text_id': tid, 'transcript_id': t['id'], 'quote': quote, 'page_id': self.on_page[tid]['args'][1],
                        'speaker': identity, 'speaker_facts': facts, 'page_fact': self.on_page[tid]['fact_id'], 'distinctiveness': cert})
        return out


def names_in(quote, names):
    q = ' ' + ''.join(c if c.isalnum() else ' ' for c in normalize(quote)) + ' '
    return [n for n in names if ' ' + ' '.join(''.join(c if c.isalnum() else ' ' for c in normalize(n)).split()) + ' ' in q]


def key(seed, *parts):
    return stable([seed, *parts])


def quote_speaker_choice(w, lines, cfg):
    items, per_identity = [], Counter()
    # Less frequent speakers first, so the <=30% frequent-name rule leaves enough items at selection.
    for line in sorted(lines, key=lambda x: (x['speaker'] in w.frequent, key(cfg['seed'], 'qsc', x['text_id']))):
        s = line['speaker']
        if s not in w.names or per_identity[s] >= cfg['per_answer_identity']: continue
        if len(items) >= cfg['per_family']: break
        page = line['page_id']
        pool = [c for c in w.names if c != s and w.names[c] != w.names[s]]
        # Hardest plausible distractors first: drawn on the same page, then other speakers of the chapter.
        pool.sort(key=lambda c: (page not in w.presence[c], c not in w.speaks, key(cfg['seed'], line['text_id'], c)))
        chosen, shown = [], {w.names[s]}
        for c in pool:
            if w.names[c] not in shown: chosen.append(c); shown.add(w.names[c])
            if len(chosen) == 3: break
        if len(chosen) < 3:
            if names_in(line['quote'], w.forms(s)): continue
            # Too few readable names in this chapter for four options: ask without options.
            evidence = {'lines': [line], 'option_visibility': {s: w.vis[s]['verified_evidence_ids']}}
            items.append(make(w, 'quote_speaker_open', 'Who says "' + line['quote'] + '"?', [],
                              {'type': 'character', 'value': w.names[s], 'identity_id': s, 'accepted_forms': sorted(w.vis[s]['verified_forms'])},
                              'character', 'direct', evidence, [page], 1, s))
            per_identity[s] += 1
            continue
        if names_in(line['quote'], [f for c in [s] + chosen for f in w.forms(c)]): continue
        # Distractors in seeded order; the gold letter rotates A-D within a chapter for exact balance.
        order = sorted(chosen, key=lambda c: key(cfg['seed'], 'order', line['text_id'], c))
        order.insert(len(items) % 4, s)
        options = [{'letter': LETTERS[i], 'identity_id': c, 'text': w.names[c]} for i, c in enumerate(order)]
        gold = LETTERS[order.index(s)]
        question = 'Who says "' + line['quote'] + '"? Choose one: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.'
        evidence = {'lines': [line], 'option_visibility': {c: w.vis[c]['verified_evidence_ids'] for c in order}}
        items.append(make(w, 'quote_speaker_choice', question, options, {'type': 'choice', 'value': gold, 'identity_id': s,
                          'display': w.names[s]}, 'multiple_choice', 'direct', evidence, [page], 1, s))
        per_identity[s] += 1
    return items


def conversation_partner(w, lines, cfg):
    """Line -> its page -> the only other identified character drawn there (complete character/name annotation)."""
    items, per_identity = [], Counter()
    for line in sorted(lines, key=lambda x: key(cfg['seed'], 'cp', x['text_id'])):
        if len(items) >= cfg['per_family']: break
        s, page = line['speaker'], line['page_id']
        if s is None or any(w.coverage.get((page, f), {}).get('status') not in CLOSED for f in ('char_boxes', 'names')): continue
        others = sorted(c for c in w.on_page_ids[page] if c != s and c not in w.generic)
        if len(others) != 1 or others[0] not in w.names: continue
        partner = others[0]
        if partner in w.frequent and per_identity[partner] >= 1 or per_identity[partner] >= cfg['per_answer_identity']: continue
        if names_in(line['quote'], w.forms(partner)): continue
        question = 'Someone says "' + line['quote'] + '". Which other named character is drawn on the same page as this line?'
        evidence = {'lines': [line], 'partner': partner, 'coverage': [w.coverage[(page, f)]['coverage_id'] for f in ('char_boxes', 'names')],
                    'option_visibility': {partner: w.vis[partner]['verified_evidence_ids']}}
        items.append(make(w, 'conversation_partner', question, [], {'type': 'character', 'value': w.names[partner], 'identity_id': partner,
                          'accepted_forms': sorted(w.vis[partner]['verified_forms'])}, 'character', 'chain', evidence, [page], 2, partner))
        per_identity[partner] += 1
    return items


def choice_question(line, options):
    return 'Who says "' + line['quote'] + '"? Choose one: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.'


def partner_of(w, line):
    """The only other identified character on the line's page, if the page's character/name annotation is closed."""
    s, page = line['speaker'], line['page_id']
    if s is None or not w.closed(page, ('char_boxes', 'names')): return None
    others = sorted(w.identified(page) - {s})
    return others[0] if len(others) == 1 and others[0] in w.names and not names_in(line['quote'], w.forms(others[0])) else None


def paired(a, b, kind):
    """Tag two items as a contrast pair; the tag is part of each member's ID."""
    pair_id = 'pair:' + stable([kind, a['item_id'], b['item_id']])
    for role, item in enumerate((a, b)):
        item['contrast'] = {'pair_id': pair_id, 'role': role, 'kind': kind}
        item['item_id'] = 'story:' + stable(core_of(item))
        item['reasoning_tags'] = item['reasoning_tags'] + ['contrast']
    return [a, b]


def contrast_pairs(w, lines, cfg):
    items, used = [], set()
    # Partner pairs are rarer, so they choose lines first.
    # partner: two lines by the same speaker on different pages, each with a different unique partner.
    with_partner = [(l, partner_of(w, l)) for l in lines]
    with_partner = [(l, c) for l, c in with_partner if c is not None and l['text_id'] not in used]
    n = 0
    for (a, ca), (b, cb) in sorted(((x, y) for i, x in enumerate(with_partner) for y in with_partner[i + 1:]
                                    if x[0]['speaker'] == y[0]['speaker'] and x[1] != y[1] and x[0]['page_id'] != y[0]['page_id']),
                                   key=lambda x: key(cfg['seed'], 'pp', x[0][0]['text_id'], x[1][0]['text_id'])):
        if n >= cfg['pairs_per_kind']: break
        if {a['text_id'], b['text_id']} & used: continue
        members = []
        for l, c in ((a, ca), (b, cb)):
            question = 'Someone says "' + l['quote'] + '". Which other named character is drawn on the same page as this line?'
            evidence = {'lines': [l], 'partner': c, 'coverage': [w.coverage[(l['page_id'], f)]['coverage_id'] for f in ('char_boxes', 'names')],
                        'option_visibility': {c: w.vis[c]['verified_evidence_ids']}}
            members.append(make(w, 'conversation_partner', question, [], character_answer(w, c), 'character', 'chain', evidence, [l['page_id']], 2, c))
        items += paired(*members, 'partner'); used.update((a['text_id'], b['text_id'])); n += 1
    # choice: two lines by different readable speakers, the same four options, different gold letters.
    named = [l for l in lines if l['speaker'] in w.names]
    pairs = [(a, b) for i, a in enumerate(named) for b in named[i + 1:] if a['speaker'] != b['speaker'] and w.names[a['speaker']] != w.names[b['speaker']]]
    n = 0
    for a, b in sorted(pairs, key=lambda x: key(cfg['seed'], 'pc', x[0]['text_id'], x[1]['text_id'])):
        if n >= cfg['pairs_per_kind']: break
        if {a['text_id'], b['text_id']} & used: continue
        both = a['quote'] + ' ' + b['quote']
        pool = sorted((c for c in w.names if c not in (a['speaker'], b['speaker'])
                       and w.names[c] not in (w.names[a['speaker']], w.names[b['speaker']])),
                      key=lambda c: (a['page_id'] not in w.presence[c] and b['page_id'] not in w.presence[c], c not in w.speaks,
                                     key(cfg['seed'], a['text_id'], b['text_id'], c)))
        chosen, shown = [], {w.names[a['speaker']], w.names[b['speaker']]}
        for c in pool:
            if w.names[c] not in shown: chosen.append(c); shown.add(w.names[c])
            if len(chosen) == 2: break
        if len(chosen) < 2 or names_in(both, [f for c in [a['speaker'], b['speaker']] + chosen for f in w.forms(c)]): continue
        order = sorted([a['speaker'], b['speaker']] + chosen, key=lambda c: key(cfg['seed'], 'pc-order', a['text_id'], c))
        options = [{'letter': LETTERS[i], 'identity_id': c, 'text': w.names[c]} for i, c in enumerate(order)]
        members = [make(w, 'quote_speaker_choice', choice_question(l, options), options,
                        {'type': 'choice', 'value': LETTERS[order.index(l['speaker'])], 'identity_id': l['speaker'], 'display': w.names[l['speaker']]},
                        'multiple_choice', 'direct', {'lines': [l], 'option_visibility': {c: w.vis[c]['verified_evidence_ids'] for c in order}},
                        [l['page_id']], 1, l['speaker']) for l in (a, b)]
        items += paired(*members, 'choice'); used.update((a['text_id'], b['text_id'])); n += 1
    return items


def character_answer(w, c):
    return {'type': 'character', 'value': w.names[c], 'identity_id': c, 'accepted_forms': w.forms(c)}


def next_speech_partner(w, lines, cfg):
    """Line -> speaker -> their next speaking page (complete speaker links in between) -> only other identified character."""
    items, per_identity = [], Counter()
    for line in sorted(lines, key=lambda x: key(cfg['seed'], 'nsp', x['text_id'])):
        if len(items) >= cfg['per_family']: break
        s, p = line['speaker'], line['page_id']
        if s is None: continue
        later = sorted((q for q in w.speaking[s] if w.pos[q] > w.pos[p]), key=w.pos.get)
        if not later: continue
        q = later[0]; between = [x for x in w.g['page_ids'] if w.pos[p] < w.pos[x] < w.pos[q]]
        if not all(w.closed(x, ('text_boxes', 'speaker_links')) for x in between) or not w.closed(q, ('char_boxes', 'names')): continue
        others = sorted(w.identified(q) - {s})
        if len(others) != 1 or others[0] not in w.names: continue
        partner = others[0]
        if per_identity[partner] >= (1 if partner in w.frequent else cfg['per_answer_identity']) or names_in(line['quote'], w.forms(partner)): continue
        question = ('The character who says "' + line['quote'] + '" speaks again later in the chapter. '
                    'On the next page where this character speaks, which other named character is drawn?')
        evidence = {'lines': [line], 'next_page': q, 'next_speech_facts': w.speaking[s][q], 'partner': partner,
                    'coverage': {x: [w.coverage[(x, f)]['coverage_id'] for f in ('text_boxes', 'speaker_links')] for x in between},
                    'partner_coverage': [w.coverage[(q, f)]['coverage_id'] for f in ('char_boxes', 'names')]}
        items.append(make(w, 'next_speech_partner', question, [], character_answer(w, partner), 'character', 'chain', evidence, [p, q], 3, partner))
        per_identity[partner] += 1
    return items


def shared_character(w, lines, cfg):
    """Two lines on different pages -> the only identified character drawn on both pages (not a speaker of either line)."""
    items, used, per_identity = [], set(), Counter()
    ok = [l for l in lines if l['speaker'] is not None and w.closed(l['page_id'], ('char_boxes', 'names'))]
    pairs = [(a, b) for i, a in enumerate(ok) for b in ok[i + 1:] if abs(w.pos[a['page_id']] - w.pos[b['page_id']]) >= 3]
    for a, b in sorted(pairs, key=lambda x: key(cfg['seed'], 'sc', x[0]['text_id'], x[1]['text_id'])):
        if len(items) >= cfg['per_family']: break
        if a['text_id'] in used or b['text_id'] in used: continue
        common = sorted(w.identified(a['page_id']) & w.identified(b['page_id']))
        if len(common) != 1 or common[0] in (a['speaker'], b['speaker']) or common[0] not in w.names: continue
        c = common[0]
        if per_identity[c] >= (1 if c in w.frequent else cfg['per_answer_identity']): continue
        if names_in(a['quote'] + ' ' + b['quote'], w.forms(c)): continue
        first, second = sorted([a, b], key=lambda l: key(cfg['seed'], 'sc-show', l['text_id']))
        question = ('Which named character is drawn both on the page where someone says "' + first['quote'] +
                    '" and on the page where someone says "' + second['quote'] + '"?')
        evidence = {'lines': [first, second], 'shared': c,
                    'coverage': {l['page_id']: [w.coverage[(l['page_id'], f)]['coverage_id'] for f in ('char_boxes', 'names')] for l in (a, b)}}
        items.append(make(w, 'shared_character', question, [], character_answer(w, c), 'character', 'branch_combine', evidence,
                          [a['page_id'], b['page_id']], 3, c))
        used.update((a['text_id'], b['text_id'])); per_identity[c] += 1
    return items


def quote_order(w, lines, cfg):
    items, used = [], set()
    rng = random.Random(key(cfg['seed'], 'qo', w.g['chapter_id']))
    by_page = defaultdict(list)
    for line in sorted(lines, key=lambda x: key(cfg['seed'], 'qo-line', x['text_id'])): by_page[line['page_id']].append(line)
    pages = sorted(by_page, key=w.pos.get); n = cfg['order_lines']
    for _ in range(cfg['per_family'] * 20):
        if len(items) >= cfg['per_family']: break
        free = [p for p in pages if any(l['text_id'] not in used for l in by_page[p])]
        if len(free) < n: break
        chosen_pages = sorted(rng.sample(free, n), key=w.pos.get)
        picked = [next(l for l in by_page[p] if l['text_id'] not in used) for p in chosen_pages]
        if len({l['speaker'] for l in picked}) < 2: continue
        shown = sorted(picked, key=lambda l: key(cfg['seed'], 'qo-show', l['text_id']))
        if shown == picked: shown = picked[1:] + picked[:1]
        options = [{'letter': LETTERS[i], 'text_id': l['text_id'], 'text': l['quote']} for i, l in enumerate(shown)]
        answer = [LETTERS[shown.index(l)] for l in picked]
        question = ('Put these lines in the order they appear in the chapter, first to last: '
                    + '; '.join(o['letter'] + ') "' + o['text'] + '"' for o in options) + '. Answer with the four letters.')
        items.append(make(w, 'quote_order', question, options, {'type': 'sequence', 'value': answer}, 'sequence', 'compare',
                          {'lines': picked}, chosen_pages, n, None))
        used.update(l['text_id'] for l in picked)
    return items


def make(w, family, question, options, answer, fmt, structure, evidence, pages, hops, identity):
    g = w.g
    core = {'family': family, 'chapter_id': g['chapter_id'], 'question': question, 'options': options, 'answer': answer}
    return {'schema': ITEM, 'version': VERSION, 'item_id': 'story:' + stable(core), 'family': family,
            'chapter_id': g['chapter_id'], 'split': next(n['split'] for n in g['nodes'] if n['type'] == 'Chapter'),
            'question': question, 'options': options, 'answer': answer, 'answer_format': fmt,
            'evidence_class': 'executed', 'generation_mode': 'template', 'reasoning_structure': structure,
            'primary_group': 'short', 'reasoning_tags': ['story', family], 'evidence': evidence,
            'source': {'snapshots': {'graph': stable(g), 'visibility': stable(w.v), 'rich': stable(w.rich)}},
            'features': {'identity_id': identity, 'frequent_ids': w.frequent, 'is_frequent': identity in w.frequent,
                         'two_option': False, 'semantic_target': stable([family, sorted(l['text_id'] for l in evidence['lines'])])},
            'complexity': {'necessary_pages': sorted(pages, key=w.pos.get), 'story_hops': hops, 'meaningful_hops': None},
            'verification': {'proof': 'story_checked', 'human': 'pending', 'release': 'pending'}}


def core_of(item):
    core = {k: item[k] for k in ('family', 'chapter_id', 'question', 'options', 'answer')}
    if 'contrast' in item: core['contrast'] = item['contrast']
    return core


def validate(item):
    if item.get('schema') != ITEM or item.get('version') not in VERSIONS or item.get('family') not in FAMILIES: raise ValueError('Not a story item')
    if item['item_id'] != 'story:' + stable(core_of(item)): raise ValueError('Story item ID mismatch')
    if item['split'] not in ('seen', 'unseen'): raise ValueError('Unknown source split')
    return item


def chapter(g, v, rich, cfg):
    from .story_check import check, check_pair
    w = World(g, v, rich); lines = w.lines(cfg)
    items = (quote_speaker_choice(w, lines, cfg) + quote_order(w, lines, cfg) + conversation_partner(w, lines, cfg)
             + next_speech_partner(w, lines, cfg) + shared_character(w, lines, cfg) + contrast_pairs(w, lines, cfg))
    results = {i['item_id']: check(i, g, v, rich, cfg) for i in items}
    members = defaultdict(list)
    for i in items:
        if 'contrast' in i: members[i['contrast']['pair_id']].append(i)
    for pid, pair in members.items():
        errors = check_pair(pair)
        if errors or not all(results[i['item_id']]['verified'] for i in pair):
            for i in pair: results[i['item_id']] = {'verified': False, 'errors': results[i['item_id']]['errors'] + errors + ['pair_member_failed']}
    kept, rejected = [], []
    for item in items:
        result = results[item['item_id']]
        (kept if result['verified'] else rejected).append(item if result['verified'] else {'item_id': item['item_id'], 'errors': result['errors']})
    return {'chapter_id': g['chapter_id'], 'eligible_lines': len(lines), 'items': kept, 'rejected': rejected,
            'counts': dict(Counter(i['family'] for i in kept))}


def run(bench_root, out, chapters=None, overrides=None, chapter_fn=None, version=VERSION):
    """Story store build. chapter_fn/version let other family sets (e.g. story_expand) reuse it; defaults are unchanged."""
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    cfg = dict(DEFAULTS, **(overrides or {}))
    root = Path(bench_root).resolve(); roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    out = separate(out, roots + [root / 'core'])
    available = read(roots[0] / 'manifest.json')['config']['chapters']; chosen = sorted(chapters or available)
    if not chosen or not set(chosen) <= set(available): raise ValueError('Unknown chapter scope')
    config = {'schema': STORE, 'version': version, 'chapters': chosen, 'settings': cfg,
              'source_manifests_sha256': {str(p): digest(p / 'manifest.json') for p in roots},
              'code_sha256': {p.name: digest(p) for p in Path(__file__).parent.glob('story_*.py')}}
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.story-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        outputs, report = {}, {'chapters': {}, 'families': Counter(), 'rejected': 0}
        for cid in chosen:
            path = out / 'chapters' / (cid + '.json')
            if path.exists():
                saved = read(path)
                if saved['config_sha256'] != stable(config): raise ValueError('Stale story checkpoint')
                result = saved['payload']
            else:
                g, v, pins = load_world(roots[0], roots[1], cid); rich = load_optional(*roots, cid, pins)
                result = (chapter_fn or chapter)(g, v, rich, cfg)
                publish(path, {'config_sha256': stable(config), 'payload': result})
            outputs[str(path.relative_to(out))] = digest(path)
            for item in result['items']:
                name = 'candidates/' + stable(item['item_id']) + '.json'; publish(out / name, item); outputs[name] = digest(out / name)
            report['chapters'][cid] = {'eligible_lines': result['eligible_lines'], **result['counts'], 'rejected': len(result['rejected'])}
            report['families'].update(result['counts']); report['rejected'] += len(result['rejected'])
        report['families'] = dict(report['families']); report['candidates'] = sum(report['families'].values())
        publish(out / 'report.json', report); outputs['report.json'] = digest(out / 'report.json')
        publish(out / 'manifest.json', {'schema': STORE, 'config': config, 'config_sha256': stable(config), 'outputs_sha256': outputs,
                                        'counts': {'candidates': report['candidates']}, 'release_status': 'not_approved'})
    return report


def recheck(bench_root, store):
    """Fresh independent check of every saved item against the current evidence files."""
    from comics_qa.tasks.graph.crl.artifacts import load_world
    from comics_qa.tasks.graph.crl.rich_contract import load_optional
    from .story_check import check, check_pair
    config = read(Path(store) / 'config.json'); items = load(store); cfg = config['settings']
    events = None
    if 'facts_root' in config:  # event stores: re-read the confirmed facts they were built from
        if digest(Path(config['facts_root']) / 'facts.json') != config['facts_sha256']: raise ValueError('Event facts changed since the store was built')
        events = {f['fact_id']: f for f in read(Path(config['facts_root']) / 'facts.json')['facts']}
    root = Path(bench_root).resolve(); roots = [root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1')]
    by_chapter = defaultdict(list)
    for item in items: by_chapter[item['chapter_id']].append(item)
    results = []
    for cid, group in sorted(by_chapter.items()):
        g, v, pins = load_world(roots[0], roots[1], cid); rich = load_optional(*roots, cid, pins)
        snapshots = {'graph': stable(g), 'visibility': stable(v), 'rich': stable(rich)}
        for item in group:
            result = check(item, g, v, rich, cfg, events=events)
            if 'contrast' in item:
                pair = [i for i in items if i.get('contrast', {}).get('pair_id') == item['contrast']['pair_id']]
                errors = check_pair(pair)
                if errors: result = {'verified': False, 'errors': result['errors'] + errors}
            if item['source']['snapshots'] != snapshots: result = {'verified': False, 'errors': result['errors'] + ['stale_snapshot']}
            results.append({'item_id': item['item_id'], **result})
    return {'schema': 'comics_qa.benchmark1000.story_check.1', 'store_manifest_sha256': digest(Path(store) / 'manifest.json'),
            'verified': sum(r['verified'] for r in results), 'rejected': sum(not r['verified'] for r in results), 'items': results}


def load(root):
    root = Path(root).resolve(); m = verify_manifest(root)
    if m.get('schema') != STORE or read(root / 'config.json') != m['config'] or stable(m['config']) != m['config_sha256']:
        raise ValueError('Invalid story store')
    items = [validate(read(member(root, n))) for n in sorted(m['outputs_sha256']) if n.startswith('candidates/')]
    if len(items) != m['counts']['candidates'] or len({i['item_id'] for i in items}) != len(items): raise ValueError('Story store count mismatch')
    return items
