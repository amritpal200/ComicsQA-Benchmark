"""Independent closed-template parser; unsupported natural wording stays pending."""
import json
import re
from comics_qa.tasks.graph.crl.language import call, parse, program_hash
from comics_qa.tasks.graph.generation.proposals import conjunction, named
from .io import stable

J = r'("(?:[^"\\]|\\.)*")'
INTRO = ('Find the one character who satisfies every condition below. Treat the page numbers as positions '
         'in the supplied chapter, starting at 1. All conditions must hold for the same person; matching '
         'only some of the conditions is not enough. ')
TAIL = ' Combine the evidence from these different pages and give the character’s name.'


def speaker(quote, page):
    return call('speaker_char', call('quote', quote, on=call('page', page)))


def parse_question(question):
    m = re.fullmatch(r'After page ([1-9]\d*), on which page does the speaker of the text ' + J + r' on that page next speak\?', question)
    if m:
        p, q = int(m[1]), json.loads(m[2])
        return {'kind': 'quote_next_speaks', 'engine': 'scan', 'program': {'op': 'next_speaks', 'characters': [speaker(q, p)], 'after': p}, 'relaxations': [], 'min_pages': 2}
    m = re.fullmatch(r'Start with the speaker of the text ' + J + r' on page ([1-9]\d*)\. Find the next page where that person speaks\. On that page identify the only different character who is drawn\. After that page, on which page is this other character next drawn\?', question)
    if m:
        p = {'op': 'speaker_relay', 'quote': json.loads(m[1]), 'page': int(m[2])}
        return {'kind': 'speaker_relay', 'engine': 'relay', 'program': p, 'relaxations': [('relay', {**p, 'other_rule': 'any'})], 'min_pages': 3}
    m = re.fullmatch(r'Identify the speakers of ' + J + r' on page ([1-9]\d*) and ' + J + r' on page ([1-9]\d*)\. After page ([1-9]\d*), on which page are both characters next drawn\?', question)
    if m:
        a, pa, b, pb, after = json.loads(m[1]), int(m[2]), json.loads(m[3]), int(m[4]), int(m[5])
        if after != max(pa, pb):
            raise ValueError('Joint anchor differs from the stated latest page')
        chars = [speaker(a, pa), speaker(b, pb)]
        return {'kind': 'two_quote_joint', 'engine': 'scan', 'program': {'op': 'next_joint', 'characters': chars, 'after': after},
                'relaxations': [('scan', {'op': 'next_presence', 'characters': [c], 'after': after}) for c in chars], 'min_pages': 3}
    if question.startswith(INTRO) and question.endswith(TAIL):
        remaining = question[len(INTRO):-len(TAIL)]
        clauses, keys = [], []
        for n in range(1, 4):
            prefix = rf'\({n}\) '
            present = re.match(prefix + r'On page ([1-9]\d*), this character is drawn in at least one character depiction\.', remaining)
            speech = re.match(prefix + r'At least one dialogue text region on page ([1-9]\d*) has this character as its speaker\.', remaining)
            m = present or speech
            if not m:
                raise ValueError('Unknown clue wording')
            page = int(m[1]); kind = 'present' if present else 'speaks_on'
            clause = call('chars_on', call('page', page)) if present else call('distinct', call('map', call('lines', call('page', page)), {'lambda': {'param': 't', 'body': call('speaker_char', {'var': 't'})}}))
            clauses.append(clause); keys.append([kind, page])
            remaining = remaining[m.end():]
            if n < 3:
                if not remaining.startswith(' '):
                    raise ValueError('Missing clue separator')
                remaining = remaining[1:]
        if remaining or len({p for _, p in keys}) != 3:
            raise ValueError('Expected three distinct clue pages')
        return {'kind': 'three_page_clue', 'engine': 'crl', 'program': call('the', named(conjunction(clauses))),
                'unrestricted': call('the', conjunction(clauses)), 'clue_keys': keys,
                'relaxations': [('crl', call('the', named(conjunction([c for i, c in enumerate(clauses) if i != j])))) for j in range(3)], 'min_pages': 3}
    if 'Keep the first and second person’s searches separate.' in question:
        from .branch_relations import parse_question as parse_branches
        return parse_branches(question)
    from .expanded_families import parse_question as parse_expanded
    return parse_expanded(question)


def bound(parsed, item):
    if parsed['engine'] != item['proof_engine']:
        return False
    if parsed['engine'] in ('crl', 'recipe', 'coverage_recipe'):
        return program_hash(parse(parsed['program'])) == program_hash(parse(item['program']))
    a, b = dict(parsed['program']), dict(item['program'])
    if parsed['engine'] == 'relay':
        a.setdefault('other_rule', 'different'); b.setdefault('other_rule', 'different')
    return stable(a) == stable(b)
