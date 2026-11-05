"""Expansion families X1 (expansion_plan.md; ideas 8C.2/8C.3 of Free_QA_generation.md), from human annotations only.

- script_error:      six lines with speaker names, two names swapped; answer = the two line numbers.
- speaker_table:     four lines and four named options; answer = one letter per line.
- name_trap:         'Who says "<line naming another character>"?'; the named character is an option, not the speaker.
- line_of_character: 'On the page where someone says "<anchor>", which of these does X say?' Three lines from that page
                     plus "X says nothing on that page". Half the items have X speaking there, half not (false premise).

Lines come from the story-family line pool (verified OCR, human dialogue, distinctiveness certificate). Within-page
order is never claimed (decision E2). Checked by story_expand_check (separate implementation) via story_check.
"""
from collections import Counter, defaultdict
from .story_families import LETTERS, World, key, make, names_in

VERSION = 'story_expand.1'
FAMILIES = ('script_error', 'speaker_table', 'name_trap', 'line_of_character')
FORMS = {'script_error': 'script_error', 'speaker_table': 'speaker_table', 'name_trap': 'name_trap', 'line_of_character': 'line_of_character'}
DEFAULTS = {'per_family': 8, 'script_lines': 6, 'table_lines': 4}


def nothing(name):
    return name + ' says nothing on that page'


def _readable(w, lines):
    return [l for l in lines if l['speaker'] in w.names]


def script_error(w, lines, cfg):
    items, used = [], set()
    pool = sorted(_readable(w, lines), key=lambda l: key(cfg['seed'], 'se', l['text_id']))
    n = cfg['script_lines']
    for start in range(len(pool)):
        if len(items) >= cfg['per_family']: break
        picked, speakers = [], set()
        for l in pool[start:] + pool[:start]:
            if l['text_id'] in used or len(picked) == n: continue
            picked.append(l); speakers.add(l['speaker'])
        if len(picked) < n or len(speakers) < 3: continue
        shown = sorted(picked, key=lambda l: (w.pos[l['page_id']], key(cfg['seed'], 'se-in', l['text_id'])))
        names = [w.names[l['speaker']] for l in shown]
        if names_in(' '.join(l['quote'] for l in shown), [f for l in shown for f in w.forms(l['speaker'])]): continue
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n) if names[i] != names[j]]
        i, j = sorted(pairs, key=lambda p: key(cfg['seed'], 'se-swap', shown[p[0]]['text_id'], shown[p[1]]['text_id']))[0]
        names[i], names[j] = names[j], names[i]
        rows = [{'number': k + 1, 'text_id': l['text_id'], 'name': names[k], 'quote': l['quote']} for k, l in enumerate(shown)]
        question = ('Here are six lines from this chapter, each shown with a speaker name. Exactly two of the names are wrong '
                    '(they were swapped with each other). Which two lines have the wrong speaker? '
                    + ' '.join(f'({r["number"]}) {r["name"]}: "{r["quote"]}"' for r in rows) + ' Answer with the two line numbers.')
        evidence = {'lines': shown, 'rows': rows}
        items.append(make(w, 'script_error', question, [], {'type': 'set', 'value': [i + 1, j + 1]}, 'set', 'aggregate', evidence,
                          sorted({l['page_id'] for l in shown}, key=w.pos.get), len(shown), None))
        used.update(l['text_id'] for l in shown)
    return items


def speaker_table(w, lines, cfg):
    items, used = [], set()
    pool = sorted(_readable(w, lines), key=lambda l: key(cfg['seed'], 'st', l['text_id']))
    n = cfg['table_lines']
    for start in range(len(pool)):
        if len(items) >= cfg['per_family']: break
        picked = []
        for l in pool[start:] + pool[:start]:
            if l['text_id'] not in used and len(picked) < n and l['page_id'] not in {p['page_id'] for p in picked}: picked.append(l)
        speakers = sorted({l['speaker'] for l in picked}, key=lambda c: key(cfg['seed'], 'st-o', c))
        if len(picked) < n or len(speakers) < 3: continue
        extra = sorted((c for c in w.names if c not in speakers and w.names[c] not in {w.names[s] for s in speakers}),
                       key=lambda c: (c not in w.speaks, key(cfg['seed'], 'st-x', picked[0]['text_id'], c)))
        order = (speakers + extra)[:4]
        if len(order) < 4 or len({w.names[c] for c in order}) < 4: continue
        if names_in(' '.join(l['quote'] for l in picked), [f for c in order for f in w.forms(c)]): continue
        order = sorted(order, key=lambda c: key(cfg['seed'], 'st-letter', picked[0]['text_id'], c))
        options = [{'letter': LETTERS[i], 'identity_id': c, 'text': w.names[c]} for i, c in enumerate(order)]
        question = ('Who says each of these lines? Options: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '. Lines: '
                    + ' '.join(f'({k + 1}) "{l["quote"]}"' for k, l in enumerate(picked)) + ' Answer with one letter per line, in order.')
        items.append(make(w, 'speaker_table', question, options, {'type': 'sequence', 'value': [LETTERS[order.index(l['speaker'])] for l in picked]},
                          'multi_part', 'aggregate', {'lines': picked, 'option_visibility': {c: w.vis[c]['verified_evidence_ids'] for c in order}},
                          sorted({l['page_id'] for l in picked}, key=w.pos.get), n, None))
        used.update(l['text_id'] for l in picked)
    return items


def name_trap(w, lines, cfg):
    items, per_identity = [], Counter()
    for l in sorted(_readable(w, lines), key=lambda l: (l['speaker'] in w.frequent, key(cfg['seed'], 'nt', l['text_id']))):
        if len(items) >= cfg['per_family']: break
        s = l['speaker']
        if per_identity[s] >= 2 or names_in(l['quote'], w.forms(s)): continue
        named = sorted(c for c in w.names if c != s and names_in(l['quote'], w.forms(c)))
        if len(named) != 1 or w.names[named[0]] == w.names[s]: continue
        t = named[0]
        pool = sorted((c for c in w.names if c not in (s, t) and not names_in(l['quote'], w.forms(c))
                       and w.names[c] not in (w.names[s], w.names[t])), key=lambda c: (c not in w.speaks, key(cfg['seed'], 'nt-x', l['text_id'], c)))
        chosen, shown = [], {w.names[s], w.names[t]}
        for c in pool:
            if w.names[c] not in shown: chosen.append(c); shown.add(w.names[c])
            if len(chosen) == 2: break
        if len(chosen) < 2: continue
        order = sorted([t] + chosen, key=lambda c: key(cfg['seed'], 'nt-o', l['text_id'], c)); order.insert(len(items) % 4, s)
        options = [{'letter': LETTERS[i], 'identity_id': c, 'text': w.names[c]} for i, c in enumerate(order)]
        question = 'Who says "' + l['quote'] + '"? Choose one: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.'
        items.append(make(w, 'name_trap', question, options, {'type': 'choice', 'value': LETTERS[order.index(s)], 'identity_id': s, 'display': w.names[s]},
                          'multiple_choice', 'direct', {'lines': [l], 'named': t, 'option_visibility': {c: w.vis[c]['verified_evidence_ids'] for c in order}},
                          [l['page_id']], 1, s))
        per_identity[s] += 1
    return items


def line_of_character(w, lines, cfg):
    """Pages with complete text boxes and speaker links; X either says one shown line or says nothing there."""
    items, used = [], set()
    by_page = defaultdict(list)
    for l in lines:
        if l['speaker'] is not None: by_page[l['page_id']].append(l)
    pages = sorted((p for p in by_page if w.closed(p, ('text_boxes', 'speaker_links')) and len(by_page[p]) >= 3),
                   key=lambda p: key(cfg['seed'], 'lc', p))
    for p in pages:
        if len(items) >= cfg['per_family']: break
        here = sorted(by_page[p], key=lambda l: key(cfg['seed'], 'lc-l', l['text_id']))
        speaking = {c for c, pages_ in w.speaking.items() if p in pages_}
        absent = len(items) % 2 == 1
        if absent:
            cands = sorted((c for c in w.names if c not in speaking and c in w.speaks),
                           key=lambda c: (p not in w.presence[c], key(cfg['seed'], 'lc-x', p, c)))  # drawn-but-silent first
            if not cands: continue
            x = cands[0]; anchor = here[0]; shown = [l for l in here[1:] if l['speaker'] != x][:3]
            gold_line = None
        else:
            mine = [l for l in here if l['speaker'] in w.names]
            if not mine: continue
            gold_line = mine[0]; x = gold_line['speaker']
            others = [l for l in here if l['speaker'] != x]
            if len(others) < 3: continue
            anchor = others[0]; shown = [gold_line] + others[1:3]
        if len(shown) < 3 or anchor['speaker'] == x or {l['text_id'] for l in shown + [anchor]} & used: continue
        if names_in(' '.join(l['quote'] for l in shown + [anchor]), w.forms(x)): continue
        shown = sorted(shown, key=lambda l: key(cfg['seed'], 'lc-o', l['text_id']))
        texts = ['"' + l['quote'] + '"' for l in shown]
        slot = len(items) % 4
        texts.insert(slot, nothing(w.names[x])); shown.insert(slot, None)
        options = [{'letter': LETTERS[i], 'text_id': None if l is None else l['text_id'], 'text': t} for i, (l, t) in enumerate(zip(shown, texts))]
        gold = LETTERS[slot] if gold_line is None else LETTERS[shown.index(gold_line)]
        question = ('On the page where someone says "' + anchor['quote'] + '", which of these does ' + w.names[x] + ' say? Choose one: '
                    + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.')
        evidence = {'lines': [anchor] + [l for l in shown if l is not None], 'anchor': anchor['text_id'], 'target': x,
                    'coverage': [w.coverage[(p, f)]['coverage_id'] for f in ('text_boxes', 'speaker_links')],
                    'option_visibility': {x: w.vis[x]['verified_evidence_ids']}}
        items.append(make(w, 'line_of_character', question, options, {'type': 'choice', 'value': gold, 'identity_id': x, 'says_nothing': gold_line is None},
                          'multiple_choice', 'chain', evidence, [p], 2, x))
        used.update(l['text_id'] for l in [anchor] + [l for l in shown if l is not None])
    return items


def generate(g, v, rich, cfg):
    w = World(g, v, rich); lines = w.lines(cfg)
    items = script_error(w, lines, cfg) + speaker_table(w, lines, cfg) + name_trap(w, lines, cfg) + line_of_character(w, lines, cfg)
    for item in items:
        item['version'] = VERSION
        item['question_form'] = FORMS[item['family']]
    return items, len(lines)


def chapter(g, v, rich, cfg):
    from .story_check import check
    items, eligible = generate(g, v, rich, cfg)
    kept, rejected = [], []
    for item in items:
        r = check(item, g, v, rich, cfg)
        (kept if r['verified'] else rejected).append(item if r['verified'] else {'item_id': item['item_id'], 'errors': r['errors']})
    return {'chapter_id': g['chapter_id'], 'eligible_lines': eligible, 'items': kept, 'rejected': rejected,
            'counts': dict(Counter(i['family'] for i in kept))}


def run(bench_root, out, chapters=None, overrides=None):
    from .story_families import run as story_run
    return story_run(bench_root, out, chapters, dict(DEFAULTS, **(overrides or {})), chapter_fn=chapter, version=VERSION)
