"""Independent closed GEN-2 wording grammar; no access to a supplied target AST."""
import json
import re
from ..crl.language import call, infer


def parse_gloss(text):
    if not isinstance(text,str) or not 0<len(text)<=10000:raise ValueError('Invalid question')
    # Explicit equivalent variants; arbitrary natural language is not certified.
    text=re.sub(r'^Which character is the speaker of ', 'Who is the speaker of ',text)
    text=re.sub(r'^How many appearances of the speaker of ', 'How many depictions of the speaker of ',text)
    outer=None
    if text.startswith('Who is the speaker of ') and text.endswith('?'):
        label=text[len('Who is the speaker of '):-1];outer='speaker'
    elif text.startswith('How many depictions of the speaker of ') and text.endswith(' appear on that same page?'):
        label=text[len('How many depictions of the speaker of '):-len(' appear on that same page?')];outer='count'
    elif m:=re.fullmatch(r'After page ([1-9][0-9]*), on which page is the speaker of (.+) next drawn\?',text):
        label=m[2];after=int(m[1]);outer='next'
    else:raise ValueError('Wording outside closed GEN-2 grammar')
    prefixes={'the text region reading ':'quote','the only text region containing the name form ':'name_texts'}
    prefix=next((x for x in prefixes if label.startswith(x)),None)
    if prefix is None:raise ValueError('Unknown anchor wording')
    try:form,end=json.JSONDecoder().raw_decode(label[len(prefix):])
    except (ValueError,TypeError) as exc:raise ValueError('Anchor must contain a JSON string') from exc
    if not isinstance(form,str) or not form:raise ValueError('Empty/non-string anchor')
    suffix=label[len(prefix)+end:];m=re.fullmatch(r' on page ([1-9][0-9]*)',suffix)
    if not m:raise ValueError('Invalid page scope')
    index=int(m[1]);page=call('page',index);anchor=call(prefixes[prefix],form,on=page)
    if prefixes[prefix]=='name_texts':anchor=call('the',anchor)
    speaker=call('speaker_char',anchor)
    if outer=='speaker':ast=speaker
    elif outer=='count':ast=call('count',call('apps_of',speaker,page))
    else:
        if after!=index:raise ValueError('Conflicting anchor pages')
        ast=call('page_of',call('next_app',speaker,after=page))
    infer(ast);return ast
