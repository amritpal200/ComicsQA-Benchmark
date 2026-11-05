"""Experimental track (expansion_plan.md E1/E2): families whose answer depends on within-page reading order.

Reading order = core v1 `reading_order` of each human text box (MAGI-3 ordering rules applied to human boxes). It is
an unaudited model fact, so every item has track=experimental, uses_model_facts=['magi_reading_order'] and
needs_human_verification. Items stay in their own store until a reading-order audit promotes or removes them.

- next_line_speaker: 'Right after someone says "<line>", who says the next line on the same page?' (4 named options).
- page_line_order:   four lines from one page; answer their reading order.
"""
import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from .story_families import LETTERS, World, key, make, names_in

VERSION = 'story_experimental.1'
FAMILIES = ('next_line_speaker', 'page_line_order')
DEFAULTS = {'per_family': 8, 'core_root': '/data/151-3/comics/ComicsQA_Benchmark/core/v1'}
FLAGS = {'track': 'experimental', 'uses_model_facts': ['magi_reading_order']}


@lru_cache(maxsize=4)
def reading_order(core_root, chapter_id):
    """text_id -> (page_id, reading_order) for every human text box of the chapter."""
    out = {}
    with open(Path(core_root) / 'pages.jsonl') as f:
        for line in f:
            page = json.loads(line)
            if page['chapter_id'] != chapter_id: continue
            for t in page.get('texts', []):
                if isinstance(t.get('reading_order'), int): out[t['text_id']] = (page['page_id'], t['reading_order'])
    return out


def next_line_speaker(w, lines, order, cfg):
    items, per_identity = [], Counter()
    by_page = defaultdict(list)
    for tid, (page, k) in order.items(): by_page[page].append((k, tid))
    for l in sorted(lines, key=lambda x: key(cfg['seed'], 'nls', x['text_id'])):
        if len(items) >= cfg['per_family']: break
        p = l['page_id']
        if l['text_id'] not in order or not w.closed(p, ('text_boxes', 'speaker_links')): continue
        seq = [t for _, t in sorted(by_page[p])]
        i = seq.index(l['text_id'])
        if i + 1 >= len(seq): continue
        nxt = seq[i + 1]
        if nxt not in w.is_line: continue
        s2, _ = w.speaker(nxt)
        if s2 is None or s2 not in w.names or s2 == l['speaker'] or per_identity[s2] >= cfg['per_answer_identity']: continue
        pool = [c for c in ([l['speaker']] if l['speaker'] in w.names else []) +
                sorted(w.names, key=lambda c: (p not in w.presence[c], key(cfg['seed'], 'nls-x', l['text_id'], c))) if c != s2]
        chosen, shown = [], {w.names[s2]}
        for c in pool:
            if w.names[c] not in shown: chosen.append(c); shown.add(w.names[c])
            if len(chosen) == 3: break
        if len(chosen) < 3 or names_in(l['quote'], [f for c in [s2] + chosen for f in w.forms(c)]): continue
        opts = sorted(chosen, key=lambda c: key(cfg['seed'], 'nls-o', l['text_id'], c)); opts.insert(len(items) % 4, s2)
        options = [{'letter': LETTERS[k], 'identity_id': c, 'text': w.names[c]} for k, c in enumerate(opts)]
        question = ('Right after someone says "' + l['quote'] + '", who says the next line on the same page? Choose one: '
                    + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.')
        evidence = {'lines': [l], 'next_text_id': nxt, 'reading_order': {t: order[t][1] for t in seq},
                    'coverage': [w.coverage[(p, f)]['coverage_id'] for f in ('text_boxes', 'speaker_links')]}
        items.append(make(w, 'next_line_speaker', question, options, {'type': 'choice', 'value': LETTERS[opts.index(s2)], 'identity_id': s2,
                          'display': w.names[s2]}, 'multiple_choice', 'chain', evidence, [p], 2, s2))
        per_identity[s2] += 1
    return items


def page_line_order(w, lines, order, cfg):
    items = []
    by_page = defaultdict(list)
    for l in lines:
        if l['text_id'] in order: by_page[l['page_id']].append(l)
    for p in sorted(by_page, key=lambda p: key(cfg['seed'], 'plo', p)):
        if len(items) >= cfg['per_family']: break
        here = sorted(by_page[p], key=lambda l: key(cfg['seed'], 'plo-l', l['text_id']))[:4]
        if len(here) < 4 or len({l['speaker'] for l in here}) < 2: continue
        truth = sorted(here, key=lambda l: order[l['text_id']][1])
        shown = here if here != truth else here[1:] + here[:1]
        options = [{'letter': LETTERS[k], 'text_id': l['text_id'], 'text': l['quote']} for k, l in enumerate(shown)]
        question = ('These four lines are on the same page. Put them in reading order, first to last: '
                    + '; '.join(o['letter'] + ') "' + o['text'] + '"' for o in options) + '. Answer with the four letters.')
        evidence = {'lines': shown, 'reading_order': {l['text_id']: order[l['text_id']][1] for l in shown}}
        items.append(make(w, 'page_line_order', question, options, {'type': 'sequence', 'value': [LETTERS[shown.index(l)] for l in truth]},
                          'sequence', 'compare', evidence, [p], 1, None))
    return items


def chapter(g, v, rich, cfg):
    from .story_check import check
    w = World(g, v, rich); lines = w.lines(cfg); order = reading_order(cfg['core_root'], g['chapter_id'])
    items = next_line_speaker(w, lines, order, cfg) + page_line_order(w, lines, order, cfg)
    kept, rejected = [], []
    for item in items:
        item['version'] = VERSION; item['question_form'] = item['family']; item.update(FLAGS)
        item['verification'] = {**item['verification'], 'human': 'required',
                                'flags': ['needs_human_verification', 'experimental_track', 'uses_magi_reading_order']}
        r = check(item, g, v, rich, cfg)
        (kept if r['verified'] else rejected).append(item if r['verified'] else {'item_id': item['item_id'], 'errors': r['errors']})
    return {'chapter_id': g['chapter_id'], 'eligible_lines': len(lines), 'items': kept, 'rejected': rejected,
            'counts': dict(Counter(i['family'] for i in kept))}


def run(bench_root, out, chapters=None, overrides=None):
    from .story_families import run as story_run
    cfg = dict(DEFAULTS, **(overrides or {}))
    cfg['core_root'] = str(Path(bench_root).resolve() / 'core/v1')
    return story_run(bench_root, out, chapters, cfg, chapter_fn=chapter, version=VERSION)
