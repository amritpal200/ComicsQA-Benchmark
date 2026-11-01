"""Bounded semantic recipes compiled into unchanged, independently checked CRL."""
import json
import re
from comics_qa.tasks.graph.crl.language import call, infer
from .native_wording import speaker

VERSION = 'expanded_families.1'
COVERAGE_VERSION = 'coverage_windows.1'
KINDS = ('successive_speech', 'speaker_walk', 'speaking_gap', 'speaking_before',
         'shared_speaking_pages', 'shared_presence_pages', 'next_speech_line_count', 'last_presence_window')
FORMATS = dict(zip(KINDS, ('page', 'page', 'count', 'boolean', 'set', 'set', 'count', 'page')))
J = r'("(?:[^"\\]|\\.)*")'


def syntax(recipe):
    required = {'kind', 'references', 'start', 'end', 'steps'}
    if not isinstance(recipe, dict) or set(recipe) not in (required, required | {'profile'}) or recipe['kind'] not in KINDS:
        raise ValueError('Unknown expanded recipe')
    refs = recipe['references']; n = 2 if recipe['kind'] in ('speaking_gap', 'speaking_before', 'shared_speaking_pages', 'shared_presence_pages') else 1
    if not isinstance(refs, list) or len(refs) != n:
        raise ValueError('Wrong reference arity')
    for ref in refs:
        if set(ref) != {'quote', 'page'} or not isinstance(ref['quote'], str) or not ref['quote'].strip() or type(ref['page']) is not int or ref['page'] < 1:
            raise ValueError('Invalid quote/page reference')
    if recipe.get('profile') not in (None, COVERAGE_VERSION):
        raise ValueError('Unknown range profile')
    start, end, steps = recipe['start'], recipe['end'], recipe['steps']
    if any(type(x) is not int for x in (start, end, steps)) or start < max(r['page'] for r in refs) + 1 or end < start or recipe.get('profile') is None and start != max(r['page'] for r in refs) + 1:
        raise ValueError('Range must begin immediately after the latest reference')
    if steps not in ((2, 3) if recipe['kind'] in ('successive_speech', 'speaker_walk') else (1,)):
        raise ValueError('Invalid navigation count')
    return recipe


def compile_recipe(recipe, bypass=None):
    """Bypasses preserve variable types and replay the whole dependent suffix."""
    r = syntax(recipe); kind = r['kind']; bindings = []
    def bind(name, expr):
        bindings.append({'name': name, 'value': expr}); return {'var': name}
    chars = [bind('c' + str(i), speaker(x['quote'], x['page'])) for i, x in enumerate(r['references'])]
    span = call('pages', r['start'], r['end'])
    after = call('page', r['start'] - 1)
    def next_page(c, p):
        return call('first', call('pages_speaking', c, call('span_after', p, within=span)))
    if kind in ('successive_speech', 'speaker_walk'):
        c, p = chars[0], after
        for i in range(r['steps']):
            p = bind('p' + str(i), p if bypass == 'navigate:' + str(i) else next_page(c, p))
            if kind == 'speaker_walk' and i < r['steps'] - 1:
                other = call('the', call('filter', call('chars_on', p), {'lambda': {'param': 'x', 'body': call('neq', {'var': 'x'}, c)}}))
                c = bind('d' + str(i), c if bypass == 'switch:' + str(i) else other)
        result = p
    elif kind in ('speaking_gap', 'speaking_before'):
        a = bind('pa', call('page', r['start']) if bypass == 'branch:0' else call('page', r['end']) if bypass == 'branch:0:upper' else next_page(chars[0], after))
        b = bind('pb', call('page', r['start']) if bypass == 'branch:1' else call('page', r['end']) if bypass == 'branch:1:upper' else next_page(chars[1], after))
        result = call('gap' if kind == 'speaking_gap' else 'precedes', a, b)
    elif kind in ('shared_speaking_pages', 'shared_presence_pages'):
        op = 'speaks_on' if kind == 'shared_speaking_pages' else 'present'
        predicates = [call(op, c, {'var': 'p'}) for c in chars]
        predicate = predicates[1] if bypass == 'branch:0' else predicates[0] if bypass == 'branch:1' else call('and', *predicates)
        selected = call('filter', span, {'lambda': {'param': 'p', 'body': predicate}})
        result = call('intersect', selected, span)
    elif kind == 'next_speech_line_count':
        p = bind('pa', after if bypass == 'navigate:0' else next_page(chars[0], after))
        result = call('line_count', chars[0], p)
    else:
        result = call('last', call('pages_with', chars[0], span))
    program = {'let': bindings, 'in': result}
    infer(program)
    return program


def render(recipe):
    r = syntax(recipe)
    refs = [f'{json.dumps(x["quote"], ensure_ascii=False)} on page {x["page"]}' for x in r['references']]
    if len(refs) == 1:
        intro = 'Identify the speaker of the text ' + refs[0] + '. '
    else:
        intro = 'Identify the speakers of the texts ' + refs[0] + ' and ' + refs[1] + ', respectively. '
    scope = (f'Search only the inclusive range from page {r["start"]} to page {r["end"]}. ' if r.get('profile') == COVERAGE_VERSION else
             f'Use only pages {r["start"]} through {r["end"]}, inclusive, for the following search. ')
    if r['kind'] in ('successive_speech', 'speaker_walk'):
        count = 'two' if r['steps'] == 2 else 'three'
        middle = ('Keep following the same person. ' if r['kind'] == 'successive_speech' else
                  'After each step except the last, switch to the only different character drawn on the page just found. ')
        tail = (f'Start immediately before this range and follow the current person to their next speaking page {count} times. '
                + middle + 'Each new search starts strictly after the page just found. Which page does the final step reach?')
    else:
        tail = {
            'speaking_gap': 'Find each person’s first speaking page in this range. How many pages lie strictly between those two pages?',
            'speaking_before': 'Does the first person’s first speaking page in this range precede the second person’s first speaking page?',
            'shared_speaking_pages': 'List all pages in this range on which both people speak.',
            'shared_presence_pages': 'List all pages in this range on which both people are drawn.',
            'next_speech_line_count': 'Find this person’s first speaking page in this range. How many dialogue text regions belong to this person on that page?',
            'last_presence_window': 'On which page in this range is this person drawn for the last time?',
        }[r['kind']]
    return intro + scope + tail


def parse_question(question):
    """Closed grammar recovers every reference, bound, quantifier and switch rule."""
    single = re.match(r'Identify the speaker of the text ' + J + r' on page ([1-9]\d*)\. ', question)
    pair = re.match(r'Identify the speakers of the texts ' + J + r' on page ([1-9]\d*) and ' + J + r' on page ([1-9]\d*), respectively\. ', question)
    match = pair or single
    if not match:
        raise ValueError('Unrecognized expanded wording')
    refs = [{'quote': json.loads(match[1]), 'page': int(match[2])}]
    if pair:
        refs.append({'quote': json.loads(match[3]), 'page': int(match[4])})
    scope = re.match(r'Use only pages ([1-9]\d*) through ([1-9]\d*), inclusive, for the following search\. ', question[match.end():])
    shifted_scope = re.match(r'Search only the inclusive range from page ([1-9]\d*) to page ([1-9]\d*)\. ', question[match.end():])
    scope = scope or shifted_scope
    if not scope:
        raise ValueError('Missing expanded search range')
    # Enumeration of this finite grammar does not inspect the saved program/answer.
    for kind in KINDS:
        for steps in ((2, 3) if kind in ('successive_speech', 'speaker_walk') else (1,)):
            recipe = {'kind': kind, 'references': refs, 'start': int(scope[1]), 'end': int(scope[2]), 'steps': steps}
            if shifted_scope:
                recipe['profile'] = COVERAGE_VERSION
            try:
                if render(recipe) != question:
                    continue
            except ValueError:
                continue
            labels = ([label for i in range(steps) for label in (['navigate:' + str(i), 'switch:' + str(i)] if kind == 'speaker_walk' and i < steps - 1 else ['navigate:' + str(i)])]
                      if kind in ('successive_speech', 'speaker_walk') else ['branch:0', 'branch:1'] if len(refs) == 2 else ['navigate:0'] if kind == 'next_speech_line_count' else [])
            execution_engine = 'coverage_recipe' if shifted_scope else 'recipe'
            return {'kind': kind, 'engine': execution_engine, 'program': compile_recipe(recipe), 'recipe': recipe, 'profile_version': recipe.get('profile', VERSION),
                    'relaxation_labels': labels, 'relaxations': [(execution_engine, compile_recipe(recipe, label)) for label in labels],
                    'alternative_relaxations': [(execution_engine, compile_recipe(recipe, label + ':upper')) for label in labels] if kind in ('speaking_gap', 'speaking_before') else [],
                    'allow_ambiguous_relaxations': False,
                    'min_pages': steps + 1 if kind in ('successive_speech', 'speaker_walk') else len({x['page'] for x in refs}) + 2 if len(refs) == 2 else 2}
    raise ValueError('Unrecognized expanded constraint/wording')
