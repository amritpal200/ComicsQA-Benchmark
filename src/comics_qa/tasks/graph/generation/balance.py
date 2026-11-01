"""Deterministic per-chapter quotas with explicit denominators and tie handling."""
from collections import Counter,defaultdict
from fractions import Fraction
from .policy import stable


def frequent_characters(graph,policy):
    nodes={n['id']:n for n in graph['nodes']};pages=defaultdict(set)
    for f in graph['facts']:
        if f['rel']=='present' and f['answer_eligible'] and f['origin'] in ('H','V') and not nodes[f['args'][0]]['generic']:
            pages[f['args'][0]].add(f['args'][1])
    counts={c:len(ps) for c,ps in pages.items()}
    values=sorted(counts.values(),reverse=True)
    cutoff=values[min(policy['frequent_top_k'],len(values))-1] if values else None
    return {c for c,n in counts.items() if n>=cutoff},counts


def proportions(items,frequent):
    names=[i for i in items if i['answer']['type']=='char']
    f=sum(i['answer']['identity_id'] in frequent for i in names)
    two=sum(i['two_option'] for i in items)
    booleans=[i for i in items if i['answer']['type']=='bool'];yes=sum(i['answer']['value'] is True for i in booleans)
    return {'items':len(items),'name_answers':len(names),'frequent_name_answers':f,'frequent_name_share':f/len(names) if names else None,
            'two_option_answers':two,'two_option_share':two/len(items) if items else None,'boolean_answers':len(booleans),
            'boolean_true':yes,'boolean_true_share':yes/len(booleans) if booleans else None}


def select(pool,graph,policy):
    frequent,counts=frequent_characters(graph,policy);selected=[];used=set();used_programs=set();family=Counter();support=Counter()
    # Round robin over family and answer buckets spreads count values and answer types.
    buckets=defaultdict(list)
    for item in pool:
        buckets[(item['family'],str(item['answer']['value']))].append(item)
    for items in buckets.values(): items.sort(key=lambda i:stable([policy['seed'],i['item_id']]))
    ranked=[]
    while any(buckets.values()):
        for k in sorted(buckets,key=lambda x:stable([policy['seed'],x])):
            if buckets[k]: ranked.append(buckets[k].pop())
    true=[i for i in ranked if i['answer']['type']=='bool' and i['answer']['value'] is True]
    false=[i for i in ranked if i['answer']['type']=='bool' and i['answer']['value'] is False]
    binary_slots=int(policy['max_items_per_chapter']*Fraction(str(policy['max_two_option_share'])))
    reserve=2*min(len(true),len(false),binary_slots//2)
    def signature(i): return stable([i['answer'],i['execution']['proof']['facts'],i['execution']['proof']['certificates']])
    def permitted(batch):
        if any(i['program_sha256'] in used_programs for i in batch) or len({i['program_sha256'] for i in batch})!=len(batch): return False
        proposed=selected+batch
        if len(proposed)>policy['max_items_per_chapter']: return False
        stats=proportions(proposed,frequent)
        if stats['name_answers'] and Fraction(stats['frequent_name_answers'],stats['name_answers'])>Fraction(str(policy['max_frequent_name_share'])): return False
        if Fraction(stats['two_option_answers'],len(proposed))>Fraction(str(policy['max_two_option_share'])): return False
        fs=family+Counter(i['family'] for i in batch);ss=support+Counter(signature(i) for i in batch)
        return max(fs.values())<=policy['max_per_family'] and max(ss.values())<=policy['max_per_answer_support']
    def accept(batch):
        for i in batch:
            i['gates']['G11']={'status':'pass','dedup':'canonical program and answer/support cap'}
            selected.append(i);used.add(i['item_id']);used_programs.add(i['program_sha256']);family[i['family']]+=1;support[signature(i)]+=1
    remaining=[i for i in ranked if i['answer']['type']!='bool']
    while len(selected)<policy['max_items_per_chapter']-reserve:
        chosen=next((i for i in remaining if i['item_id'] not in used and permitted([i])),None)
        if chosen is None: break
        accept([chosen])
    for t,f in zip(true,false):
        if permitted([t,f]): accept([t,f])
    stats=proportions(selected,frequent)
    rejected=[{'program_sha256':i['program_sha256'],'program':i['canonical'],'family':i['family'],'strategy':i['strategy'],
               'gate':'balance','reason':'quota_or_capacity','answer':i['answer']} for i in pool if i['item_id'] not in used]
    report={'definition':{'metric':policy['frequent_metric'],'top_k':policy['frequent_top_k'],'ties':policy['frequent_ties'],
                         'name_denominator':'selected scalar character-name answers in this chapter','two_option_denominator':'all selected items in this chapter'},
            'frequent_ids':sorted(frequent),'trusted_page_frequencies':counts,'selected':stats,'pool':proportions(pool,frequent),
            'families':dict(sorted(family.items())),'answer_types':dict(sorted(Counter(i['answer']['type'] for i in selected).items())),
            'count_values':dict(sorted(Counter(str(i['answer']['value']) for i in selected if i['answer']['type']=='int').items())),
            'shortfall':policy['max_items_per_chapter']-len(selected),'limits_relaxed':False}
    return selected,rejected,report
