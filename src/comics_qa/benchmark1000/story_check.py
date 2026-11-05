"""Independent checker for story_families items. Does not import or call the generator.

Rebuilds every claim from raw graph facts, the visibility companion and CKG-3 transcripts:
transcript and page of each line, its single human speaker link, readable option names,
distractors different from the speaker, no option name inside the quote, chapter-wide
distinctiveness of every quote and the order of pages.
"""
import difflib
import re
from comics_qa.evidence.graph.rich.model import normalize

LETTERS = 'ABCD'
CLOSED = ('closed_assumed', 'closed_audited', 'closed_verified')


def _words(s):
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in normalize(s)).split())


def _unique(quote, source_id, transcripts, threshold):
    q = normalize(quote)
    for record in transcripts:
        if record['id'] == source_id: continue
        for raw in (record.get('consensus'), record.get('magi_text'), record.get('paddle_text')):
            if not raw: continue
            r = normalize(raw)
            if r == q or q in r or (r in q and 2 * len(r) >= len(q)): return False
            if difflib.SequenceMatcher(None, q, r, autojunk=False).ratio() >= threshold: return False
    return True


def _visible(vis, form):
    return bool(vis) and not vis.get('generic') and form in vis.get('verified_forms', [])


def check(item, g, v, rich, cfg, events=None):
    errors = []
    facts = {f['fact_id']: f for f in g['facts'] if f['origin'] in ('H', 'V') and f['answer_eligible']}
    transcripts = {t['id']: t for t in rich['transcripts']}
    vis = {x['identity_id']: x for x in v['visibility']}
    position = {p: i for i, p in enumerate(g['page_ids'])}
    if item.get('chapter_id') != g['chapter_id']: errors.append('chapter')
    lines = item.get('evidence', {}).get('lines', [])
    for line in lines:
        t = transcripts.get(line.get('transcript_id'))
        if not t or t.get('text_id') != line['text_id'] or not t.get('quote_eligible') or t.get('consensus') != line['quote']:
            errors.append('transcript:' + str(line.get('text_id'))); continue
        page = facts.get(line['page_fact'])
        if not page or page['rel'] != 'on_page' or page['args'] != [line['text_id'], line['page_id']]: errors.append('page:' + line['text_id'])
        if not any(f['rel'] == 'is_line' and f['args'] == [line['text_id']] for f in facts.values()): errors.append('not_dialogue:' + line['text_id'])
        if len(line['quote'].split()) < cfg['min_words'] or len(normalize(line['quote'])) < cfg['min_chars']: errors.append('short:' + line['text_id'])
        if '"' in line['quote']: errors.append('inner_quote:' + line['text_id'])
        if not _unique(line['quote'], line['transcript_id'], rich['transcripts'], cfg['max_similarity']): errors.append('not_distinct:' + line['text_id'])
        links = [f for f in facts.values() if f['rel'] == 'spoken_by' and f['args'][0] == line['text_id']]
        if line.get('speaker') is not None:
            chars = [f for f in facts.values() if f['rel'] == 'is_char' and len(links) == 1 and f['args'][0] == links[0]['args'][1]]
            if len(links) != 1 or len(chars) != 1 or chars[0]['args'][1] != line['speaker'] or \
                    sorted(line['speaker_facts']) != sorted([links[0]['fact_id'], chars[0]['fact_id']]):
                errors.append('speaker:' + line['text_id'])
    if item['family'] in ('script_error', 'speaker_table', 'name_trap', 'line_of_character', 'next_line_speaker', 'page_line_order'):
        from .story_expand_check import check_expand  # expansion families (story_expand.1, story_experimental.1); existing families unchanged
        errors += check_expand(item, g, v, facts, vis, position, lines, cfg)
        return {'verified': not errors, 'errors': errors}
    options = item.get('options', [])
    open_answer = item['family'] in ('quote_speaker_open', 'conversation_partner', 'next_speech_partner', 'shared_character')
    if open_answer and options: errors.append('options')
    if not open_answer and ([o.get('letter') for o in options] != list(LETTERS[:len(options)]) or len(options) != 4): errors.append('options')
    if open_answer:
        gold = item['answer']; target = gold.get('identity_id'); v_target = vis.get(target)
        if len(lines) != (2 if item['family'] == 'shared_character' else 1): errors.append('lines')
        if gold.get('type') != 'character' or not _visible(v_target, gold.get('value')) or \
                not gold.get('accepted_forms') or any(not _visible(v_target, f) for f in gold['accepted_forms']):
            errors.append('name_not_readable:' + str(gold.get('value')))
        if any(' ' + _words(f) + ' ' in ' ' + _words(l['quote']) + ' ' for l in lines for f in gold.get('accepted_forms', [])):
            errors.append('name_in_quote')
    certs = {(c['page_id'], c['family']): c for c in g['coverage']}
    generic = {n['id'] for n in g['nodes'] if n['type'] == 'Character' and n.get('generic')}

    def closed(page, families):
        return all(certs.get((page, f), {}).get('status') in CLOSED for f in families)

    def identified(page):
        return {f['args'][0] for f in facts.values() if f['rel'] == 'present' and f['args'][1] == page} - generic
    if item['family'] == 'quote_speaker_open':
        if lines and (target != lines[0].get('speaker') or item.get('question') != 'Who says "' + lines[0]['quote'] + '"?'): errors.append('gold_or_wording')
    elif item['family'] == 'conversation_partner':
        if lines:
            line = lines[0]; page = line['page_id']
            certs = {(c['page_id'], c['family']): c for c in g['coverage']}
            if any(certs.get((page, f), {}).get('status') not in CLOSED for f in ('char_boxes', 'names')): errors.append('coverage_open')
            generic = {n['id'] for n in g['nodes'] if n['type'] == 'Character' and n.get('generic')}
            drawn = {f['args'][0] for f in facts.values() if f['rel'] == 'present' and f['args'][1] == page}
            if line.get('speaker') not in drawn: errors.append('speaker_not_drawn')
            if sorted(c for c in drawn if c != line.get('speaker') and c not in generic) != [target]: errors.append('partner_not_unique')
            expected = 'Someone says "' + line['quote'] + '". Which other named character is drawn on the same page as this line?'
            if item.get('question') != expected: errors.append('wording')
    elif item['family'] == 'next_speech_partner':
        if lines:
            line = lines[0]; s = line.get('speaker'); p = line['page_id']
            # Pages where s has a human-linked line, rebuilt from spoken_by + is_char + on_page.
            app_of = {f['args'][0]: f['args'][1] for f in facts.values() if f['rel'] == 'is_char'}
            page_of = {f['args'][0]: f['args'][1] for f in facts.values() if f['rel'] == 'on_page'}
            spoken = [f for f in facts.values() if f['rel'] == 'spoken_by' and app_of.get(f['args'][1]) == s and f['args'][0] in page_of]
            later = sorted({page_of[f['args'][0]] for f in spoken if position[page_of[f['args'][0]]] > position[p]}, key=position.get)
            if s is None or not later or item['evidence'].get('next_page') != later[0]: errors.append('next_page')
            else:
                q = later[0]
                if any(not closed(x, ('text_boxes', 'speaker_links')) for x in g['page_ids'] if position[p] < position[x] < position[q]):
                    errors.append('coverage_open_between')
                if not closed(q, ('char_boxes', 'names')): errors.append('coverage_open')
                if sorted(identified(q) - {s}) != [target]: errors.append('partner_not_unique')
            expected = ('The character who says "' + line['quote'] + '" speaks again later in the chapter. '
                        'On the next page where this character speaks, which other named character is drawn?')
            if item.get('question') != expected: errors.append('wording')
    elif item['family'] == 'shared_character':
        if len(lines) == 2:
            a, b = lines
            if a['page_id'] == b['page_id'] or abs(position[a['page_id']] - position[b['page_id']]) < 3: errors.append('pages_too_close')
            if not (closed(a['page_id'], ('char_boxes', 'names')) and closed(b['page_id'], ('char_boxes', 'names'))): errors.append('coverage_open')
            if sorted(identified(a['page_id']) & identified(b['page_id'])) != [target]: errors.append('shared_not_unique')
            if target in (a.get('speaker'), b.get('speaker')): errors.append('shared_is_speaker')
            expected = ('Which named character is drawn both on the page where someone says "' + a['quote'] +
                        '" and on the page where someone says "' + b['quote'] + '"?')
            if item.get('question') != expected: errors.append('wording')
    elif item['family'] == 'quote_speaker_choice':
        if len(lines) != 1: errors.append('lines')
        else:
            line = lines[0]; gold = item['answer']
            ids = [o.get('identity_id') for o in options]; texts = [o.get('text') for o in options]
            if len(set(ids)) != 4 or len(set(texts)) != 4: errors.append('duplicate_option')
            if ids.count(line.get('speaker')) != 1 or gold.get('identity_id') != line.get('speaker'): errors.append('gold_identity')
            elif gold.get('value') != LETTERS[ids.index(line['speaker'])] or gold.get('display') != texts[ids.index(line['speaker'])]:
                errors.append('gold_letter')
            for o in options:
                if not _visible(vis.get(o.get('identity_id')), o.get('text')): errors.append('name_not_readable:' + str(o.get('text')))
            quote = ' ' + _words(line['quote']) + ' '
            if any(' ' + _words(t) + ' ' in quote for t in texts if t): errors.append('name_in_quote')
            expected = 'Who says "' + line['quote'] + '"? Choose one: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.'
            if item.get('question') != expected: errors.append('wording')
    elif item['family'] == 'quote_order':
        pages = [l['page_id'] for l in lines]
        if len(lines) != 4 or len(set(pages)) != 4: errors.append('pages_not_distinct')
        elif any(p not in position for p in pages): errors.append('unknown_page')
        else:
            by_text = {l['text_id']: l for l in lines}
            if sorted(o.get('text_id') for o in options) != sorted(by_text) or any(o['text'] != by_text[o['text_id']]['quote'] for o in options):
                errors.append('options_lines')
            else:
                truth = [o['letter'] for o in sorted(options, key=lambda o: position[by_text[o['text_id']]['page_id']])]
                if item['answer'].get('value') != truth: errors.append('order')
                if truth == list(LETTERS): errors.append('already_sorted')
            expected = ('Put these lines in the order they appear in the chapter, first to last: '
                        + '; '.join(o['letter'] + ') "' + o['text'] + '"' for o in options) + '. Answer with the four letters.')
            if item.get('question') != expected: errors.append('wording')
    elif item['family'] in ('event_actor_choice', 'event_order'):
        errors += _check_event(item, facts, vis, position, events or {})
    else:
        errors.append('family')
    # Page numbers may appear inside a quoted line, never in the question's own words.
    if re.search(r'\bpages? \d', re.sub(r'"[^"]*"', '', item.get('question', '')), re.I): errors.append('page_number_in_question')
    return {'verified': not errors, 'errors': errors}


def check_pair(members):
    """Contrast pair: two members, one changed condition, different answers."""
    errors = []
    if len(members) != 2: return ['pair_incomplete']
    a, b = sorted(members, key=lambda m: m['contrast']['role'])
    ca, cb = a['contrast'], b['contrast']
    if (ca['pair_id'], ca['kind']) != (cb['pair_id'], cb['kind']) or [ca['role'], cb['role']] != [0, 1]: errors.append('pair_tags')
    if a['chapter_id'] != b['chapter_id'] or a['family'] != b['family'] or a['question'] == b['question']: errors.append('pair_shape')
    if a['answer'].get('identity_id') == b['answer'].get('identity_id') or a['answer'].get('value') == b['answer'].get('value'):
        errors.append('pair_same_answer')
    la, lb = a['evidence']['lines'][0], b['evidence']['lines'][0]
    if ca['kind'] == 'choice':
        if a['family'] != 'quote_speaker_choice' or a['options'] != b['options']: errors.append('pair_options_differ')
    elif ca['kind'] == 'partner':
        if a['family'] != 'conversation_partner' or la.get('speaker') != lb.get('speaker') or la['page_id'] == lb['page_id']:
            errors.append('pair_not_same_speaker')
    else:
        errors.append('pair_kind')
    return errors


def _replace_subject(statement, by):
    i = statement.lower().find('the outlined character')
    return None if i < 0 else statement[:i] + by + statement[i + len('the outlined character'):]


def _check_event(item, facts, vis, position, events):
    """Event items: confirmed facts (yes for subject, no for control) and human page/presence facts."""
    errors = []
    saved = item['evidence'].get('events', [])
    for e in saved:
        f = events.get(e.get('fact_id'))
        if f is None or f != e: errors.append('event_not_confirmed:' + str(e.get('fact_id'))); continue
        if f.get('confirmation', {}).get('positive') != 'yes' or f['confirmation'].get('control') != 'no': errors.append('event_gate')
        char = [x for x in facts.values() if x['rel'] == 'is_char' and x['args'][0] == f['appearance_id']]
        if len(char) != 1 or char[0]['args'][1] != f['identity_id']: errors.append('event_identity')
        if f['page_id'] not in position: errors.append('event_page')
    if errors: return errors
    options = item.get('options', [])
    if item['family'] == 'event_actor_choice':
        lines = item['evidence'].get('lines', [])
        if len(saved) != 1 or len(lines) != 1: return ['event_shape']
        f, line = saved[0], lines[0]; page = f['page_id']; gold = item['answer']
        if line['page_id'] != page: errors.append('anchor_not_on_event_page')
        ids = [o.get('identity_id') for o in options]; texts = [o.get('text') for o in options]
        if len(set(ids)) != 4 or len(set(texts)) != 4: errors.append('duplicate_option')
        if ids.count(f['identity_id']) != 1 or gold.get('identity_id') != f['identity_id'] or \
                gold.get('value') != LETTERS[ids.index(f['identity_id'])] or gold.get('display') != texts[ids.index(f['identity_id'])]:
            errors.append('gold')
        drawn = {x['args'][0] for x in facts.values() if x['rel'] == 'present' and x['args'][1] == page}
        if any(c in drawn for c in ids if c != f['identity_id']): errors.append('distractor_drawn_on_page')
        for o in options:
            if not _visible(vis.get(o.get('identity_id')), o.get('text')): errors.append('name_not_readable:' + str(o.get('text')))
        text = ' ' + _words(line['quote'] + ' ' + f['statement']) + ' '
        if any(' ' + _words(x) + ' ' in text for o in options for x in vis.get(o.get('identity_id'), {}).get('verified_forms', [])):
            errors.append('name_in_text')
        clause = _replace_subject(f['statement'].strip().rstrip('.!'), 'which named character')
        expected = None if clause is None else ('On the page where someone says "' + line['quote'] + '", ' + clause[0].lower() + clause[1:]
                                                + '? Choose one: ' + '; '.join(o['letter'] + ') ' + o['text'] for o in options) + '.')
        if item.get('question') != expected: errors.append('wording')
    else:
        pages = [f['page_id'] for f in saved]
        if len(saved) != 4 or len(set(pages)) != 4: return ['pages_not_distinct']
        if len({f['identity_id'] for f in saved}) < 2: errors.append('single_identity')
        by_id = {f['fact_id']: f for f in saved}
        if sorted(o.get('fact_id') for o in options) != sorted(by_id): return errors + ['options_events']
        texts = {}
        for o in options:
            t = _replace_subject(by_id[o['fact_id']]['statement'].strip(), 'someone')
            texts[o['fact_id']] = None if t is None else t[0].upper() + t[1:]
            if o['text'] != texts[o['fact_id']]: errors.append('option_text')
        truth = [o['letter'] for o in sorted(options, key=lambda o: position[by_id[o['fact_id']]['page_id']])]
        if item['answer'].get('value') != truth: errors.append('order')
        if truth == list(LETTERS): errors.append('already_sorted')
        expected = ('Put these moments in the order they happen in the chapter, first to last: '
                    + ' '.join(o['letter'] + ') ' + o['text'] for o in options) + ' Answer with the four letters.')
        if item.get('question') != expected: errors.append('wording')
    return errors
