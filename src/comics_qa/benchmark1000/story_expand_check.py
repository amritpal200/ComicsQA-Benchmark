"""Independent checker for story_expand families. Does not import the generator.

story_check.check has already validated every evidence line (transcript, page, dialogue, distinctiveness, single
speaker link). This module rebuilds the family-specific claims from raw graph facts and visibility.
"""
import json
import re
from functools import lru_cache
from pathlib import Path
from comics_qa.evidence.graph.rich.model import normalize

LETTERS = 'ABCD'
CLOSED = ('closed_assumed', 'closed_audited', 'closed_verified')


def _words(s):
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in normalize(s)).split())


def _mentions(text, forms):
    t = ' ' + _words(text) + ' '
    return any(' ' + _words(f) + ' ' in t for f in forms if _words(f))


def _name(vis, c):
    """Display name rule, reimplemented: verified canonical name, else the longest verified form."""
    x = vis.get(c)
    if not x or x.get('generic') or not x.get('verified_forms'): return None
    if x.get('canonical_visible') and x.get('canonical_name'): return x['canonical_name']
    return sorted(x['verified_forms'], key=lambda f: (-len(f), f))[0]


def _choice_options(item, vis, errors):
    options = item.get('options', [])
    if [o.get('letter') for o in options] != list(LETTERS) : errors.append('options')
    ids = [o.get('identity_id') for o in options]
    if 'identity_id' in (options[0] if options else {}):
        if len(set(ids)) != 4 or len({o.get('text') for o in options}) != 4: errors.append('duplicate_option')
        for o in options:
            if o.get('text') != _name(vis, o.get('identity_id')): errors.append('name_not_readable:' + str(o.get('text')))
    return options, ids


@lru_cache(maxsize=4)
def _core_order(core_root, chapter_id):
    """Reading order re-read from core v1 pages (independent of the generator's loader)."""
    out = {}
    for raw in (Path(core_root) / 'pages.jsonl').read_text().splitlines():
        page = json.loads(raw)
        if page['chapter_id'] == chapter_id:
            out.update({t['text_id']: (page['page_id'], t['reading_order']) for t in page.get('texts', []) if isinstance(t.get('reading_order'), int)})
    return out


def check_expand(item, g, v, facts, vis, position, lines, cfg=None):
    errors = []
    speakers = {l['text_id']: l.get('speaker') for l in lines}
    fam = item['family']
    if fam == 'script_error':
        rows = item['evidence'].get('rows', [])
        if len(rows) != 6 or len(lines) != 6 or [r['text_id'] for r in rows] != [l['text_id'] for l in lines]: return ['rows']
        if any(speakers[r['text_id']] is None or _name(vis, speakers[r['text_id']]) is None for r in rows): return ['speaker_not_readable']
        if len({speakers[r['text_id']] for r in rows}) < 3: errors.append('too_few_speakers')
        if any(r['quote'] != l['quote'] or r['number'] != k + 1 for k, (r, l) in enumerate(zip(rows, lines))): errors.append('rows')
        wrong = [r['number'] for r in rows if r['name'] != _name(vis, speakers[r['text_id']])]
        if len(wrong) != 2 or item['answer'].get('value') != wrong: errors.append('answer')
        else:
            a, b = (rows[n - 1] for n in wrong)
            if (a['name'], b['name']) != (_name(vis, speakers[b['text_id']]), _name(vis, speakers[a['text_id']])): errors.append('not_a_swap')
        if any(_mentions(r['quote'], vis.get(speakers[x['text_id']], {}).get('verified_forms', [])) for r in rows for x in rows):
            errors.append('name_in_quote')
        expected = ('Here are six lines from this chapter, each shown with a speaker name. Exactly two of the names are wrong '
                    '(they were swapped with each other). Which two lines have the wrong speaker? '
                    + ' '.join(f'({r["number"]}) {r["name"]}: "{r["quote"]}"' for r in rows) + ' Answer with the two line numbers.')
        if item.get('question') != expected: errors.append('wording')
    elif fam == 'speaker_table':
        options, ids = _choice_options(item, vis, errors)
        if len(lines) != 4 or len({l['page_id'] for l in lines}) != 4: errors.append('lines')
        if len({speakers[l['text_id']] for l in lines}) < 3: errors.append('too_few_speakers')
        try:
            truth = [LETTERS[ids.index(speakers[l['text_id']])] for l in lines]
        except ValueError:
            return errors + ['speaker_not_an_option']
        if item['answer'].get('value') != truth: errors.append('answer')
        if any(_mentions(l['quote'], vis.get(c, {}).get('verified_forms', [])) for l in lines for c in ids): errors.append('name_in_quote')
        expected = ('Who says each of these lines? Options: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '. Lines: '
                    + ' '.join(f'({k + 1}) "{l["quote"]}"' for k, l in enumerate(lines)) + ' Answer with one letter per line, in order.')
        if item.get('question') != expected: errors.append('wording')
    elif fam == 'name_trap':
        options, ids = _choice_options(item, vis, errors)
        if len(lines) != 1: return errors + ['lines']
        l = lines[0]; s = speakers[l['text_id']]; t = item['evidence'].get('named')
        if s is None or ids.count(s) != 1 or item['answer'].get('identity_id') != s or item['answer'].get('value') != LETTERS[ids.index(s)]:
            errors.append('gold')
        if t not in ids or t == s or not _mentions(l['quote'], vis.get(t, {}).get('verified_forms', [])): errors.append('trap_name_missing')
        if _mentions(l['quote'], vis.get(s, {}).get('verified_forms', [])): errors.append('speaker_named_in_quote')
        if any(_mentions(l['quote'], vis.get(c, {}).get('verified_forms', [])) for c in ids if c not in (t,)): errors.append('other_name_in_quote')
        expected = 'Who says "' + l['quote'] + '"? Choose one: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.'
        if item.get('question') != expected: errors.append('wording')
    elif fam == 'line_of_character':
        options = item.get('options', [])
        if [o.get('letter') for o in options] != list(LETTERS): return ['options']
        x = item['evidence'].get('target'); name = _name(vis, x)
        if name is None: return ['name_not_readable']
        anchor = next((l for l in lines if l['text_id'] == item['evidence'].get('anchor')), None)
        if anchor is None: return ['anchor']
        page = anchor['page_id']
        certs = {(c['page_id'], c['family']): c['status'] for c in g['coverage']}
        if any(certs.get((page, f)) not in CLOSED for f in ('text_boxes', 'speaker_links')): errors.append('coverage_open')
        if any(l['page_id'] != page for l in lines): errors.append('lines_not_on_page')
        if speakers[anchor['text_id']] == x: errors.append('anchor_by_target')
        none = [o for o in options if o.get('text_id') is None]
        if len(none) != 1 or none[0]['text'] != name + ' says nothing on that page': return errors + ['none_option']
        by_id = {l['text_id']: l for l in lines}
        shown = [o for o in options if o.get('text_id') is not None]
        if len(shown) != 3 or any(o['text_id'] not in by_id or o['text_id'] == anchor['text_id'] or o['text'] != '"' + by_id[o['text_id']]['quote'] + '"'
                                  for o in shown): return errors + ['option_lines']
        # Does x speak on this page? Rebuilt from spoken_by + is_char + on_page over all eligible facts.
        app_of = {f['args'][0]: f['args'][1] for f in facts.values() if f['rel'] == 'is_char'}
        page_of = {f['args'][0]: f['args'][1] for f in facts.values() if f['rel'] == 'on_page'}
        x_speaks_here = any(f['rel'] == 'spoken_by' and app_of.get(f['args'][1]) == x and page_of.get(f['args'][0]) == page for f in facts.values())
        mine = [o for o in shown if speakers[o['text_id']] == x]
        if x_speaks_here:
            truth = mine[0]['letter'] if len(mine) == 1 else None
        else:
            truth = none[0]['letter'] if not mine else None
        if truth is None or item['answer'].get('value') != truth: errors.append('answer')
        if item['answer'].get('says_nothing') != (not x_speaks_here): errors.append('says_nothing_flag')
        if any(_mentions(l['quote'], vis.get(x, {}).get('verified_forms', [])) for l in lines): errors.append('name_in_quote')
        expected = ('On the page where someone says "' + anchor['quote'] + '", which of these does ' + name + ' say? Choose one: '
                    + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.')
        if item.get('question') != expected: errors.append('wording')
    elif fam in ('next_line_speaker', 'page_line_order'):
        if item.get('track') != 'experimental' or 'magi_reading_order' not in item.get('uses_model_facts', []) or \
                'needs_human_verification' not in item.get('verification', {}).get('flags', []):
            errors.append('experimental_flags')
        order = _core_order((cfg or {}).get('core_root', '/data/151-3/comics/ComicsQA_Benchmark/core/v1'), g['chapter_id'])
        if any(l['text_id'] not in order or order[l['text_id']][0] != l['page_id'] for l in lines): return errors + ['reading_order_missing']
        if fam == 'next_line_speaker':
            options, ids = _choice_options(item, vis, errors)
            if len(lines) != 1: return errors + ['lines']
            l = lines[0]; page = l['page_id']
            certs = {(c['page_id'], c['family']): c['status'] for c in g['coverage']}
            if any(certs.get((page, f)) not in CLOSED for f in ('text_boxes', 'speaker_links')): errors.append('coverage_open')
            seq = sorted((k, t) for t, (p, k) in order.items() if p == page)
            pos = [t for _, t in seq].index(l['text_id'])
            nxt = seq[pos + 1][1] if pos + 1 < len(seq) else None
            if nxt is None or nxt != item['evidence'].get('next_text_id'): return errors + ['next_text']
            if not any(f['rel'] == 'is_line' and f['args'] == [nxt] for f in facts.values()): errors.append('next_not_dialogue')
            links = [f for f in facts.values() if f['rel'] == 'spoken_by' and f['args'][0] == nxt]
            chars = [f for f in facts.values() if f['rel'] == 'is_char' and len(links) == 1 and f['args'][0] == links[0]['args'][1]]
            s2 = chars[0]['args'][1] if len(chars) == 1 else None
            if s2 is None or s2 == speakers[l['text_id']]: return errors + ['next_speaker']
            if ids.count(s2) != 1 or item['answer'].get('identity_id') != s2 or item['answer'].get('value') != LETTERS[ids.index(s2)]: errors.append('gold')
            if any(_mentions(l['quote'], vis.get(c, {}).get('verified_forms', [])) for c in ids): errors.append('name_in_quote')
            expected = ('Right after someone says "' + l['quote'] + '", who says the next line on the same page? Choose one: '
                        + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.')
        else:
            options = item.get('options', [])
            if [o.get('letter') for o in options] != list(LETTERS) or len(lines) != 4 or len({l['page_id'] for l in lines}) != 1: return errors + ['shape']
            by_id = {l['text_id']: l for l in lines}
            if sorted(o.get('text_id') for o in options) != sorted(by_id) or any(o['text'] != by_id[o['text_id']]['quote'] for o in options):
                return errors + ['options_lines']
            truth = [o['letter'] for o in sorted(options, key=lambda o: order[o['text_id']][1])]
            if item['answer'].get('value') != truth: errors.append('order')
            if truth == list(LETTERS): errors.append('already_sorted')
            expected = ('These four lines are on the same page. Put them in reading order, first to last: '
                        + '; '.join(o['letter'] + ') "' + o['text'] + '"' for o in options) + '. Answer with the four letters.')
        if item.get('question') != expected: errors.append('wording')
    else:
        errors.append('family')
    if re.search(r'\bpages? \d', re.sub(r'"[^"]*"', '', item.get('question', '')), re.I): errors.append('page_number_in_question')
    return errors
