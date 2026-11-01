"""Blind, bounded question back-parser. No target program or answer is an input."""
import json
import re
from .branch_relations import J,VERSION,compile_recipe

ROLE_SUFFIX=" In your answer, state each speaker's final speaking page and the result."
PARSER_VERSION='qwen_question_parser.1'


def parse_question(text):
    if not isinstance(text,str) or not text or len(text)>20000:raise ValueError('Invalid generated question')
    roles=text.endswith(ROLE_SUFFIX)
    if roles:text=text[:-len(ROLE_SUFFIX)]
    # Compact equivalent with explicit witnesses, bounded ranges and strict steps.
    m=re.fullmatch(r'Within pages ([1-9]\d*) to ([1-9]\d*), identify the speakers of '+J+r' on page ([1-9]\d*) and '+J+r' on page ([1-9]\d*)\. Follow the first speaker to their next speaking page (two|three|2|3) times and the second speaker (two|three|2|3) times, always moving strictly forward within this range and starting immediately before it\. (List their two final pages in increasing chapter order\.|How many pages lie strictly between their final pages\?)',text)
    if m:
        nums={'two':2,'three':3,'2':2,'3':3}
        recipe={'kind':'branch_chain_pages' if m[9].startswith('List') else 'branch_chain_gap','references':[{'quote':json.loads(m[3]),'page':int(m[4])},{'quote':json.loads(m[5]),'page':int(m[6])}],
                'start':int(m[1]),'end':int(m[2]),'steps':[nums[m[7]],nums[m[8]]],'profile':VERSION}
        return {'engine':'coverage_recipe','program':compile_recipe(recipe),'requires_roles':roles}
    from .native_wording import parse_question as native
    try:
        result=native(text)
        return {'engine':result['engine'],'program':result['program'],'requires_roles':roles}
    except ValueError:pass
    from comics_qa.tasks.graph.verbalization.gloss import parse_gloss
    from comics_qa.tasks.graph.verbalization.gen2_gloss import parse_gloss as gen2
    # Explicit elementary aliases; unknown extra clauses are never stripped.
    if m:=re.fullmatch(r'On page ([1-9]\d*), how many (text regions|character depictions) are there\?',text):
        text=f'How many {m[2]} are shown on page {m[1]}?'
    elif m:=re.fullmatch(r'On page ([1-9]\d*), how many text regions have (.+) as their speaker\?',text):
        text=f'How many text regions on page {m[1]} have {m[2]} as their speaker?'
    elif m:=re.fullmatch(r'What is the next page after page ([1-9]\d*) where (.+) is drawn\?',text):
        text=f'After {m[2]} appears on page {m[1]}, on which later page is this character next drawn?'
    elif m:=re.fullmatch(r'Does (.+) appear on page ([1-9]\d*)\?',text):
        text=f'Is {m[1]} drawn on page {m[2]}?'
    elif m:=re.fullmatch(r'Does page ([1-9]\d*) contain more text regions than page ([1-9]\d*), fewer, or the same number\?',text):
        text=f'Compared with page {m[2]}, does page {m[1]} contain more text regions, fewer, or the same number?'
    elif text.startswith('Identify the named character who ') and text.endswith('?'):
        text='Which named character '+text[len('Identify the named character who '):]
    for parser in (parse_gloss,gen2):
        try:return {'engine':'crl','program':parser(text),'requires_roles':roles}
        except ValueError:pass
    raise ValueError('Question outside independently verified language; hold for review')


def compact(recipe,roles=False):
    a,b=recipe['references'];n=recipe['steps']
    tail='List their two final pages in increasing chapter order.' if recipe['kind']=='branch_chain_pages' else 'How many pages lie strictly between their final pages?'
    return f'Within pages {recipe["start"]} to {recipe["end"]}, identify the speakers of {json.dumps(a["quote"],ensure_ascii=False)} on page {a["page"]} and {json.dumps(b["quote"],ensure_ascii=False)} on page {b["page"]}. Follow the first speaker to their next speaking page {n[0]} times and the second speaker {n[1]} times, always moving strictly forward within this range and starting immediately before it. '+tail+(ROLE_SUFFIX if roles else '')


def alternatives(text,roles=False):
    from .branch_relations import parse_question as branch
    try:return [compact(branch(text)['recipe'],roles)]
    except ValueError:pass
    if roles:return []
    if m:=re.fullmatch(r'How many (text regions|character depictions) are shown on page ([1-9]\d*)\?',text):return [f'On page {m[2]}, how many {m[1]} are there?']
    if m:=re.fullmatch(r'How many text regions on page ([1-9]\d*) have (.+) as their speaker\?',text):return [f'On page {m[1]}, how many text regions have {m[2]} as their speaker?']
    if m:=re.fullmatch(r'After (.+) appears on page ([1-9]\d*), on which later page is this character next drawn\?',text):return [f'What is the next page after page {m[2]} where {m[1]} is drawn?']
    if m:=re.fullmatch(r'Is (.+) drawn on page ([1-9]\d*)\?',text):return [f'Does {m[1]} appear on page {m[2]}?']
    if m:=re.fullmatch(r'Compared with page ([1-9]\d*), does page ([1-9]\d*) contain more text regions, fewer, or the same number\?',text):return [f'Does page {m[2]} contain more text regions than page {m[1]}, fewer, or the same number?']
    if text.startswith('Which named character '):return ['Identify the named character who '+text[len('Which named character '):]]
    if text.startswith('Who is the speaker of '):return ['Which character is the speaker of '+text[len('Who is the speaker of '):]]
    if text.startswith('How many depictions of the speaker of '):return ['How many appearances of the speaker of '+text[len('How many depictions of the speaker of '):]]
    return []
