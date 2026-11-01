"""GEN-2 v2 name eligibility, semantic deduplication and measured shortcut limits."""
from collections import Counter
from fractions import Fraction
import math
from pathlib import Path
import sys

# Existing graph modules use direct sibling imports. Match the CRL bootstrap.
GRAPH=Path(__file__).resolve().parents[3] / "evidence/graph"
sys.path.insert(0,str(GRAPH))
from ..generation.policy import configure as base_configure, stable
from ..generation.balance import select as base_select
from name_visibility import normalized, form_is_visible

VERSION='gen2.2'
DEFAULT={'name_forms':'visible_canonical_only','max_count_share':0.70,
         'max_count_value_share':0.35,'max_page_offset_share':0.50}


def configure(raw=None):
    if raw is not None and not isinstance(raw,dict):raise ValueError('Generation policy must be an object')
    raw=dict(raw or {});extra=raw.pop('quality',{})
    if not isinstance(extra,dict) or set(extra)-set(DEFAULT):raise ValueError('Unknown GEN-2 quality policy fields')
    quality={**DEFAULT,**extra}
    if quality['name_forms']!=DEFAULT['name_forms']:raise ValueError('Unsupported name eligibility policy')
    for k in ('max_count_share','max_count_value_share','max_page_offset_share'):
        x=quality[k]
        if type(x) not in (int,float) or not math.isfinite(x) or not 0<x<=1:raise ValueError('Invalid quality share: '+k)
    return {**base_configure(raw),'quality':quality}


def usable_name(graph,visibility,cid,form,reviews=()):
    n=next((n for n in graph['nodes'] if n['id']==cid and n['type']=='Character'),None)
    return bool(n and not n['generic'] and (normalized(form)==normalized(n['canonical_name']) or any(r['identity_id']==cid and normalized(r['form'])==normalized(form) for r in reviews))
                and form_is_visible(visibility,cid,form))


def target(item,graph):
    """Read resolved values from the already independently checked execution trace."""
    steps={s['nid']:s for s in item['execution']['proof']['steps']}
    def one(op):
        found=[s for s in steps.values() if s['op']==op]
        if len(found)!=1:raise ValueError('Unsupported GEN-2 target shape: '+op)
        return found[0]
    speaker=one('speaker_char');cid=speaker['value']
    family=item['family'];offset=None
    if family.endswith('_speaker_depictions'):
        step=one('apps_of');pages=[steps[k]['value'] for k in step['children'] if steps[k]['type']=='Page']
        if len(pages)!=1:raise ValueError('Depiction target needs one page')
        key=['depictions',cid,pages[0]]
    elif family.endswith('_speaker_next_page'):
        step=one('next_app');pages=[steps[k]['value'] for k in step['children'] if steps[k]['type']=='Page']
        if len(pages)!=1:raise ValueError('Next-page target needs one anchor page')
        anchor=pages[0];offset=item['answer']['value']-(graph['page_ids'].index(anchor)+1)
        if offset<=0:raise ValueError('Next-page answer must follow anchor')
        key=['next_page',cid,anchor]
    elif family.endswith('_speaker'):
        key=['speaker',steps[speaker['children'][0]]['value']]
    else:raise ValueError('Unsupported GEN-2 family: '+family)
    return {'semantic_target':key,'semantic_target_sha256':stable([graph['chapter_id'],key]),'page_offset':offset}


def metrics(items):
    counts=Counter(str(i['answer']['value']) for i in items if i['answer']['type']=='int')
    offsets=Counter(str(i['quality']['page_offset']) for i in items if i['answer']['type']=='page')
    nc=sum(counts.values());np=sum(offsets.values())
    return {'items':len(items),'count_answers':nc,'count_share':nc/len(items) if items else None,
            'count_values':dict(sorted(counts.items())), 'max_count_value_share':max(counts.values())/nc if nc else None,
            'page_answers':np,'page_offsets':dict(sorted(offsets.items())),
            'max_page_offset_share':max(offsets.values())/np if np else None,
            'always_next_page_accuracy':offsets.get('1',0)/np if np else None,
            'semantic_targets':len({i['quality']['semantic_target_sha256'] for i in items})}


def select(pool,graph,policy):
    """Deterministic conservative trimming; all old and new caps hold simultaneously.

    Not a maximum-yield optimizer. Never refill after trimming: that could reintroduce
    skew or break name/two-option denominators. Zero yield is explicit, not relaxed.
    """
    quality=policy.get('quality',DEFAULT);ranked=sorted(pool,key=lambda i:stable([policy['seed'],i['item_id']]))
    reasons={};unique=[];seen=set()
    for i in ranked:
        i['quality']={**target(i,graph),'policy_version':VERSION}
        key=i['quality']['semantic_target_sha256']
        if key in seen:reasons[i['item_id']]='duplicate_semantic_target'
        else:seen.add(key);unique.append(i)
    selected,_,_=base_select(unique,graph,policy)
    for i in unique:
        if i not in selected:reasons[i['item_id']]='quota_or_capacity'
    def over(n,d,cap):return d and Fraction(n,d)>Fraction(str(cap))
    while selected:
        counts=[i for i in selected if i['answer']['type']=='int'];pages=[i for i in selected if i['answer']['type']=='page']
        candidates=[];reason=None
        for subset,field,cap,label in [(counts,lambda i:i['answer']['value'],quality['max_count_value_share'],'count_value_concentration'),
                                      (pages,lambda i:i['quality']['page_offset'],quality['max_page_offset_share'],'page_offset_shortcut')]:
            histogram=Counter(field(i) for i in subset)
            if histogram:
                value,n=max(histogram.items(),key=lambda x:(x[1],str(x[0])))
                if over(n,len(subset),cap):
                    candidates=[i for i in subset if field(i)==value];reason=label;break
        if not candidates and over(len(counts),len(selected),quality['max_count_share']):
            # Remove a modal count first, then check value caps again.
            hist=Counter(i['answer']['value'] for i in counts)
            value=max(hist,key=lambda x:(hist[x],x));candidates=[i for i in counts if i['answer']['value']==value];reason='count_type_concentration'
        if not candidates:break
        victim=max(candidates,key=lambda i:stable([policy['seed'],i['item_id']]))
        reasons[victim['item_id']]=reason;selected.remove(victim)
        kept,_,_=base_select(selected,graph,policy)
        kept_ids={i['item_id'] for i in kept}
        for i in selected:
            if i['item_id'] not in kept_ids:reasons[i['item_id']]='quota_after_quality_trim'
        selected=kept
    selected,_,report=base_select(selected,graph,policy)
    kept_ids={i['item_id'] for i in selected}
    for i in selected:
        i['gates']['G11']['quality']={'status':'pass','policy_version':VERSION,'semantic_target':i['quality']['semantic_target_sha256']}
    rejected=[{'program_sha256':i['program_sha256'],'program':i['canonical'],'family':i['family'],
               'strategy':i['strategy'],'gate':'quality_selection','reason':reasons.get(i['item_id'],'quota_or_capacity'),
               'answer':i['answer']} for i in pool if i['item_id'] not in kept_ids]
    report['quality']={'policy':quality,'before':metrics(pool),'after':metrics(selected),
                       'selection':'deterministic conservative trimming; no refill; no quota relaxation'}
    # base_select sees only the survivors on its final call; keep original pool totals explicit.
    from ..generation.balance import proportions,frequent_characters
    report['pool']=proportions(pool,frequent_characters(graph,policy)[0])
    return selected,rejected,report
