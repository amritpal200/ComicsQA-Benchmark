"""Select within dataset splits; preserve chapter-level agreed legacy quotas."""
import copy
from collections import Counter,defaultdict
from fractions import Fraction
from .quality import metrics
from ..generation.policy import stable

DEFAULT={'max_name_answer_share':0.50}


def summarize(items):
    names=[i for i in items if i['answer']['type']=='char']
    identities=Counter(i['answer']['identity_id'] for i in names)
    from name_visibility import normalized
    forms=Counter(normalized(i['answer']['value']) for i in names)
    return {**metrics(items),'chapters':len({i['chapter_id'] for i in items}),
            'chapter_counts':dict(sorted(Counter(i['chapter_id'] for i in items).items())),
            'families':dict(sorted(Counter(i['family'] for i in items).items())),
            'answer_types':dict(sorted(Counter(i['answer']['type'] for i in items).items())),
            'name_answers':len(names),'name_identities':dict(sorted(identities.items())),
            'name_forms':dict(sorted(forms.items())),
            'max_name_identity_share':max(identities.values())/len(names) if names else None,
            'max_name_form_share':max(forms.values())/len(names) if names else None}


def select(pools,policy,limits=None):
    limits={**DEFAULT,**(limits or {})}
    if set(limits)!=set(DEFAULT) or type(limits['max_name_answer_share']) not in (float,int) or not 0<limits['max_name_answer_share']<=1:raise ValueError('Invalid collection policy')
    quality=policy['quality'];by_split=defaultdict(list);frequent={};all_items=[]
    for pool in pools:
        frequent[pool['chapter_id']]=set(pool['frequent_ids'])
        for original in pool['candidates']:
            i=copy.deepcopy(original);all_items.append(i);by_split[pool['split']].append(i)
    rejected={};selected=[];reports={}
    def over(n,d,c):return bool(d) and Fraction(n,d)>Fraction(str(c))
    def rank(i):return stable([policy['seed'],i['item_id']])
    from name_visibility import normalized
    for split,items in sorted(by_split.items()):
        # Round-robin over chapters before enforcing capacity and family limits.
        buckets=defaultdict(list)
        for i in sorted(items,key=rank):buckets[i['chapter_id']].append(i)
        ordered=[]
        while any(buckets.values()):
            for cid in sorted(buckets):
                if buckets[cid]:ordered.append(buckets[cid].pop(0))
        seen=set();programs=set();counts=Counter();families=Counter();supports=Counter();kept=[]
        for i in ordered:
            cid=i['chapter_id'];key=i['quality']['semantic_target_sha256'];program=(cid,i['program_sha256'])
            support=stable([i['answer'],i['execution']['proof']['facts'],i['execution']['proof']['certificates']])
            reason=None
            if key in seen or program in programs:reason='duplicate_semantic_target_or_program'
            elif counts[cid]>=policy['max_items_per_chapter'] or families[cid,i['family']]>=policy['max_per_family'] or supports[cid,support]>=policy['max_per_answer_support']:reason='chapter_capacity'
            if reason:rejected[i['item_id']]=reason;continue
            seen.add(key);programs.add(program);counts[cid]+=1;families[cid,i['family']]+=1;supports[cid,support]+=1;kept.append(i)
        # All constraints are checked on the current set after every removal.
        while kept:
            candidates=[];reason=None
            for cid in sorted({i['chapter_id'] for i in kept}):
                chapter=[i for i in kept if i['chapter_id']==cid];names=[i for i in chapter if i['answer']['type']=='char']
                common=[i for i in names if i['answer']['identity_id'] in frequent[cid]]
                binary=[i for i in chapter if i['two_option']]
                if over(len(common),len(names),policy['max_frequent_name_share']):candidates=common;reason='chapter_frequent_name_quota';break
                if over(len(binary),len(chapter),policy['max_two_option_share']):candidates=binary;reason='chapter_two_option_quota';break
            ints=[i for i in kept if i['answer']['type']=='int'];pages=[i for i in kept if i['answer']['type']=='page'];names=[i for i in kept if i['answer']['type']=='char']
            checks=[(ints,lambda i:i['answer']['value'],quality['max_count_value_share'],'split_count_value'),
                    (pages,lambda i:i['quality']['page_offset'],quality['max_page_offset_share'],'split_page_offset'),
                    (names,lambda i:i['answer']['identity_id'],limits['max_name_answer_share'],'split_name_identity'),
                    (names,lambda i:normalized(i['answer']['value']),limits['max_name_answer_share'],'split_name_form')]
            if not candidates:
                for subset,key,cap,label in checks:
                    hist=Counter(key(i) for i in subset)
                    if not hist:continue
                    value,n=max(hist.items(),key=lambda x:(x[1],str(x[0])))
                    if over(n,len(subset),cap):candidates=[i for i in subset if key(i)==value];reason=label;break
            if not candidates and over(len(ints),len(kept),quality['max_count_share']):candidates=ints;reason='split_count_type'
            if not candidates:break
            chapters=Counter(i['chapter_id'] for i in kept)
            # Prefer dropping from a well-represented chapter; coverage is a tie-break,
            # never a reason to relax proof/name/answer limits.
            victim=max(candidates,key=lambda i:(chapters[i['chapter_id']],rank(i)))
            rejected[victim['item_id']]=reason;kept.remove(victim)
        for i in kept:i['gates']['G11']={'status':'pass','scope':'split','semantic_target':i['quality']['semantic_target_sha256'],'legacy_quotas':'per_chapter'}
        reports[split]={'before':summarize(items),'after':summarize(kept),
            'status':'selected' if kept else 'no_feasible_subset_retained',
            'limitations':'Deterministic trimming, not a maximum-yield or infeasibility proof; no refill.',
            'chapters_without_selection':sorted({i['chapter_id'] for i in items}-{i['chapter_id'] for i in kept})}
        selected.extend(kept)
    return selected,rejected,{'scope':'within_each_split','limits':{**quality,**limits},'splits':reports,'limits_relaxed':False}
