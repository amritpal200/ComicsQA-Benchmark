"""Bounded new families composed from unchanged executable/checker operations."""
import json
from itertools import combinations, islice
from comics_qa.tasks.graph.crl.language import call
from comics_qa.tasks.graph.generation.proposals import Proposal
from .reasoning import next_speaking_page, next_joint_page, last_presence, page_gap
from .io import stable


def propose(graph, visibility, rich, budget=60):
    if type(budget) is not int or budget < 1:
        raise ValueError('Invalid candidate budget')
    forms = {v['identity_id']: v['canonical_name'] for v in visibility['visibility']
             if v['canonical_visible'] and not v['generic']}
    pages = graph['page_ids']; pos = {p: i + 1 for i, p in enumerate(pages)}
    quotes = sorted((t for t in rich['transcripts'] if t['quote_eligible'] and 4 <= len(t['consensus'].split()) <= 35), key=lambda t: stable(t['id']))
    streams = []
    def quote_queries():
        for t in quotes:
            p = pos[t['page_id']]; page = call('page', p)
            speaker = call('speaker_char', call('quote', t['consensus'], on=page))
            label = 'the speaker of the text ' + json.dumps(t['consensus'], ensure_ascii=False) + f' on page {p}'
            yield Proposal('quote_next_speaking', 'new_layer_composition', next_speaking_page(speaker, page),
                           f'After page {p}, on which page does {label} next speak?', level='L2', anchors=[p])
            yield Proposal('quote_last_presence', 'new_layer_composition', last_presence(speaker),
                           f'On which page is {label} drawn for the last time in this chapter?', level='L2', anchors=[p])
            yield Proposal('quote_speaking_gap', 'new_layer_composition', page_gap(page, next_speaking_page(speaker, page)),
                           f'How many intervening pages separate page {p} from the next page where {label} speaks?', level='L2', anchors=[p])
    def pair_queries():
        identities = sorted(forms, key=stable)
        for a, b in combinations(identities, 2):
            x, y = call('char', forms[a]), call('char', forms[b])
            for p in range(1, len(pages)):
                yield Proposal('next_joint_presence', 'new_layer_composition', next_joint_page(x, y, call('page', p)),
                               f'After page {p}, on which page are {forms[a]} and {forms[b]} next both drawn?',
                               level='L2', names=[(a, forms[a]), (b, forms[b])], anchors=[p])
    streams = [iter(quote_queries()), iter(pair_queries())]
    seen = set(); emitted = 0
    while streams and emitted < budget:
        for stream in list(streams):
            try:
                q = next(stream)
            except StopIteration:
                streams.remove(stream); continue
            h = stable(q.ast)
            if h not in seen:
                seen.add(h); emitted += 1; yield q
            if emitted == budget:
                return
