"""Independent, closed grammar for GEN-1 template questions.

This is deliberately not a general natural-language parser. Unknown wording fails
closed; it must never be certified just because a model repeats the target AST.
"""
import re
from ..crl.language import call, infer


def parse_gloss(text):
    if not isinstance(text, str) or len(text) > 10000:
        raise ValueError('Invalid question')
    page = lambda n: call('page', int(n))
    m = re.fullmatch(r'How many (character depictions|text regions) are shown on page ([1-9][0-9]*)\?', text)
    if m:
        ast = call('count', call('apps' if m[1] == 'character depictions' else 'texts', page(m[2])))
    elif m := re.fullmatch(r'How many text regions on page ([1-9][0-9]*) have (.+) as their speaker\?', text):
        ast = call('line_count', call('char', m[2]), page(m[1]))
    elif m := re.fullmatch(r'Who is the speaker of the only dialogue text region on page ([1-9][0-9]*)\?', text):
        ast = call('speaker_char', call('the', call('lines', page(m[1]))))
    elif m := re.fullmatch(r'After (.+) appears on page ([1-9][0-9]*), on which later page is this character next drawn\?', text):
        c = call('char', m[1])
        ast = call('page_of', call('next_app', c, after=call('the', call('pages_with', c, page(m[2])))))
    elif m := re.fullmatch(r'Is (.+) drawn on page ([1-9][0-9]*)\?', text):
        ast = call('at_least', call('apps_of', call('char', m[1]), page(m[2])), 1)
    elif m := re.fullmatch(r'Compared with page ([1-9][0-9]*), does page ([1-9][0-9]*) contain more text regions, fewer, or the same number\?', text):
        ast = call('compare', call('count', call('texts', page(m[2]))), call('count', call('texts', page(m[1]))))
    elif text.startswith('Which named character ') and text.endswith('?'):
        clauses = text[len('Which named character '):-1].split(' and ')
        if len(clauses) not in (2, 3):
            raise ValueError('Unsupported number of constraints')
        collections = []
        for clause in clauses:
            m = re.fullmatch(r'is (drawn|a speaker) on page ([1-9][0-9]*)', clause)
            if not m:
                raise ValueError('Unsupported constraint')
            base = call('chars', page(m[2])) if m[1] == 'drawn' else call('distinct', call('map', call('lines', page(m[2])), {'lambda': {'param': 't', 'body': call('speaker_char', {'var': 't'})}}))
            collections.append(call('filter', base, {'lambda': {'param': 'c', 'body': call('is_named', {'var': 'c'})}}))
        ast = collections[0]
        for collection in collections[1:]:
            ast = call('intersect', ast, collection)
        ast = call('the', ast)
    else:
        raise ValueError('Question is outside the supported template grammar')
    infer(ast)
    return ast
