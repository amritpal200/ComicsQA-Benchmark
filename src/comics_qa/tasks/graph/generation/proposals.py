"""Bounded typed shapes, target-first constraint accretion, answer-first counts."""
from dataclasses import dataclass, field
from itertools import combinations, islice
from ..crl.language import call, canonical, infer
from .policy import stable


def lam(name, body): return {'lambda': {'param': name, 'body': body}}
def var(name): return {'var': name}
def page(index): return call('page', index)
def named(collection): return call('filter', collection, lam('c', call('is_named', var('c'))))


def conjunction(collections):
    out = collections[0]
    for collection in collections[1:]: out = call('intersect', out, collection)
    return out


@dataclass
class Proposal:
    family: str
    strategy: str
    ast: dict
    question: str
    level: str = 'L1'
    names: list = field(default_factory=list)  # Exact strings actually used in wording.
    anchors: list = field(default_factory=list)
    clauses: list = field(default_factory=list)
    relaxations: list = field(default_factory=list)
    elimination: list = field(default_factory=list)
    target_answer: object = None


def visible_forms(graph, visibility):
    nodes = {n['id']: n for n in graph['nodes']}
    forms = {}
    for row in visibility['visibility']:
        if nodes[row['identity_id']]['generic'] or not row['verified_forms']: continue
        forms[row['identity_id']] = row['canonical_name'] if row['canonical_visible'] else min(row['verified_forms'],key=lambda s:(len(s),s))
    return forms


def propose(graph, visibility, policy):
    forms = visible_forms(graph, visibility)
    seed = [policy['seed'], graph['chapter_id']]
    pages = sorted(range(1,len(graph['page_ids'])+1),key=lambda p:stable([seed,'page',p]))
    chars = sorted(forms,key=lambda c:stable([seed,'char',c]))
    index = {p:i+1 for i,p in enumerate(graph['page_ids'])}
    nodes = {n['id']:n for n in graph['nodes']}
    trusted = [f for f in graph['facts'] if f['answer_eligible'] and f['origin'] in ('H','V')]
    members = {(kind,p):set() for kind in ('drawn','speaker') for p in pages}
    for f in trusted:
        if f['rel'] in ('present','speaks_on') and not nodes[f['args'][0]]['generic']:
            members[('drawn' if f['rel']=='present' else 'speaker',index[f['args'][1]])].add(f['args'][0])

    def counts():
        # Desired answers fixed first; search bounded shapes for each target.
        targets = sorted(policy['count_targets'],key=lambda n:stable([seed,'count_target',n]))
        choices = []
        for p in pages:
            pid=graph['page_ids'][p-1]
            for kind,typ,label in [('apps','Appearance','character depictions'),('texts','Text','text regions')]:
                count=sum(f['rel']=='on_page' and f['args'][1]==pid and nodes[f['args'][0]]['type']==typ for f in trusted)
                choices.append((count,Proposal('count_'+kind,'answer_first',call('count',call(kind,page(p))),
                    f'How many {label} are shown on page {p}?',anchors=[p],target_answer=count)))
            for cid in chars:
                count=sum(f['rel']=='spoken_by' and nodes[f['args'][0]]['page_id']==pid and nodes[f['args'][1]].get('identity_id')==cid for f in trusted)
                choices.append((count,Proposal('line_count','answer_first',call('line_count',call('char',forms[cid]),page(p)),
                    f'How many text regions on page {p} have {forms[cid]} as their speaker?',names=[(cid,forms[cid])],anchors=[p],target_answer=count)))
        for target in targets:
            for count,proposal in choices:
                if count==target: yield proposal

    def navigation():
        for p in pages:
            yield Proposal('single_speaker','forward',call('speaker_char',call('the',call('lines',page(p)))),
                f'Who is the speaker of the only dialogue text region on page {p}?',anchors=[p])
            for cid in chars:
                c=call('char',forms[cid])
                yield Proposal('next_appearance','forward',call('page_of',call('next_app',c,after=call('the',call('pages_with',c,page(p))))),
                    f'After {forms[cid]} appears on page {p}, on which later page is this character next drawn?',level='L2',names=[(cid,forms[cid])],anchors=[p])
                yield Proposal('presence','forward',call('at_least',call('apps_of',c,page(p)),1),
                    f'Is {forms[cid]} drawn on page {p}?',names=[(cid,forms[cid])],anchors=[p])
        for p,q in combinations(pages,2):
            p,q=sorted((p,q))
            a=call('count',call('texts',page(p)));b=call('count',call('texts',page(q)))
            yield Proposal('compare_text_count','forward',call('compare',a,b),
                f'Compared with page {q}, does page {p} contain more text regions, fewer, or the same number?',level='L2',anchors=[p,q])

    def constraints():
        # Accrete positive clauses around balanced targets, stopping at a unique
        # intersection. Every clause is subsequently tested by actual CRL removal.
        for cid in chars:
            choices=[(kind,p) for kind in ('drawn','speaker') for p in pages if cid in members[kind,p] and len(members[kind,p])>1]
            choices.sort(key=lambda x:stable([seed,cid,x]))
            emitted=0
            for size in range(2,policy['max_clauses']+1):
                for chosen in islice(combinations(choices,size),policy['max_constraint_candidates_per_target']*64):
                    if len({p for _,p in chosen})<2: continue
                    sets=[members[k,p] for k,p in chosen]
                    if set.intersection(*sets)!={cid}: continue
                    if any(set.intersection(*(s for j,s in enumerate(sets) if j!=i))=={cid} for i in range(size)): continue
                    collections=[];labels=[]
                    for kind,p in chosen:
                        base=call('chars',page(p)) if kind=='drawn' else call('distinct',call('map',call('lines',page(p)),lam('t',call('speaker_char',var('t')))))
                        collections.append(named(base))
                        labels.append(f'is drawn on page {p}' if kind=='drawn' else f'is a speaker on page {p}')
                    candidates=set.union(*sets);profile=[]
                    for label,match in zip(labels,sets):
                        after=candidates&match
                        profile.append({'clause':label,'before':sorted(candidates),'after':sorted(after),'removed':sorted(candidates-after)})
                        candidates=after
                    yield Proposal('character_constraints','constraint_accretion',call('the',conjunction(collections)),
                        'Which named character '+ ' and '.join(labels)+'?',level='L2',anchors=[p for _,p in chosen],clauses=labels,
                        relaxations=[call('the',conjunction([c for j,c in enumerate(collections) if j!=i])) for i in range(size)],elimination=profile)
                    emitted+=1
                    if emitted>=policy['max_constraint_candidates_per_target']: break
                if emitted>=policy['max_constraint_candidates_per_target']: break

    streams=[iter(counts()),iter(navigation()),iter(constraints())]
    seen=set();total=0
    while streams and total<policy['max_candidates_per_chapter']:
        for stream in list(streams):
            try: proposal=next(stream)
            except StopIteration:
                streams.remove(stream);continue
            key=canonical(proposal.ast)
            if key in seen: continue
            infer(proposal.ast)
            seen.add(key);total+=1;yield proposal
            if total>=policy['max_candidates_per_chapter']: break
