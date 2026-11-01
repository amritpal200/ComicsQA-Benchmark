"""Verified exact-text and literal-name anchors composed with visual graph facts."""
import json
from ..crl.language import call, canonical
from ..generation.proposals import Proposal
from ..generation.policy import stable


def propose(graph, visibility, rich, policy):
    positions={p:i+1 for i,p in enumerate(graph['page_ids'])}
    closed={c['page_id'] for c in rich['coverage'] if c['family']=='ocr' and c['status'] in ('closed_assumed','closed_verified','closed_audited')}
    quotes=sorted({(t['page_id'],t['consensus']) for t in rich['transcripts'] if t['quote_eligible'] and t['page_id'] in closed and 3<=len(t['consensus'].split())<=35},key=lambda x:stable([policy['seed'],x]))
    names=sorted({(f['page_id'],f['args'][1],f['args'][2]) for f in rich['facts'] if f['rel']=='name_occurs' and f['answer_eligible'] and f['page_id'] in closed},key=lambda x:stable([policy['seed'],x]))
    streams=[]
    for kind, rows in [('quote',quotes),('name',names)]:
        stream=[]
        for row in rows:
            pid,form=row[0],row[-1];p=positions[pid];page=call('page',p)
            anchor=call('quote',form,on=page) if kind=='quote' else call('the',call('name_texts',form,on=page))
            speaker=call('speaker_char',anchor)
            label=(f'the text region reading {json.dumps(form,ensure_ascii=False)} on page {p}' if kind=='quote' else
                   f'the only text region containing the name form {json.dumps(form,ensure_ascii=False)} on page {p}')
            name_refs=[] if kind=='quote' else [(row[1],form)]
            stream.append(Proposal(kind+'_speaker','ocr_anchor',speaker,
                f'Who is the speaker of {label}?',names=name_refs,anchors=[p]))
            stream.append(Proposal(kind+'_speaker_depictions','ocr_anchor',call('count',call('apps_of',speaker,page)),
                f'How many depictions of the speaker of {label} appear on that same page?',names=name_refs,anchors=[p]))
            stream.append(Proposal(kind+'_speaker_next_page','ocr_anchor',call('page_of',call('next_app',speaker,after=page)),
                f'After page {p}, on which page is the speaker of {label} next drawn?',level='L2',names=name_refs,anchors=[p]))
        streams.append(iter(stream))
    seen=set();count=0
    while streams and count<policy['max_candidates_per_chapter']:
        for stream in list(streams):
            try:q=next(stream)
            except StopIteration:streams.remove(stream);continue
            key=canonical(q.ast)
            if key not in seen:
                seen.add(key);count+=1;yield q
            if count>=policy['max_candidates_per_chapter']:break
