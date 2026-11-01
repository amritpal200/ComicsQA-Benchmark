"""One semantic-condition change above two independently admitted native tasks."""
import copy
from collections import defaultdict
from .io import stable
from .branch_relations import parse_question, VERSION
from .admission_store import validate as validate_admitted

PAIR = 'comics_qa.benchmark1000.contrast_pair.1'
MEMBER = 'comics_qa.benchmark1000.contrast_member.1'
STORE = 'comics_qa.benchmark1000.contrast_store.1'


def delta(a,b):
    a=parse_question(a['question'])['recipe'];b=parse_question(b['question'])['recipe']
    changed=[['steps',n] for n in range(2) if a['steps'][n]!=b['steps'][n]]
    changed += [[k] for k in a if k!='steps' and a[k]!=b[k]]
    if len(changed)!=1 or changed[0] not in (['steps',0],['steps',1],['start']):
        raise ValueError('Contrast must change exactly one supported condition')
    path=changed[0]
    before=a[path[0]] if len(path)==1 else a['steps'][path[1]]
    after=b[path[0]] if len(path)==1 else b['steps'][path[1]]
    if len(path)==2 and abs(before-after)!=1:raise ValueError('Contrast depth must differ by one navigation')
    return {'profile':VERSION,'path':path,'before':before,'after':after,
            'semantics':'one search-start boundary change; branch depths and other conditions fixed' if path==['start'] else
                        'one additional or removed next-speaking navigation; other conditions fixed'}



def build(a,b):
    body={'kind':'one_clause_change','members':[copy.deepcopy(a),copy.deepcopy(b)],'delta':delta(a,b),
          'human_review':'pending','release':'pending','images':'unchanged','world_edit':'none'}
    return validate_pair({'schema':PAIR,'pair_id':'b1000pair:'+stable(body),**body})


def validate_pair(pair):
    fields={'schema','pair_id','kind','members','delta','human_review','release','images','world_edit'}
    if set(pair)!=fields or pair['schema']!=PAIR or pair['pair_id']!='b1000pair:'+stable({k:v for k,v in pair.items() if k not in ('schema','pair_id')}):
        raise ValueError('Invalid contrast pair identity/schema')
    if pair['kind']!='one_clause_change' or pair['human_review']!='pending' or pair['release']!='pending' or pair['images']!='unchanged' or pair['world_edit']!='none':
        raise ValueError('Unsupported contrast/edit/review claim')
    if not isinstance(pair['members'],list) or len(pair['members'])!=2:raise ValueError('Two admitted members required')
    a,b=[validate_admitted(x) for x in pair['members']]
    if any(a[k]!=b[k] for k in ('chapter_id','split','source','context','answer_format')):raise ValueError('Contrast members differ in world/context/type')
    if a['answer_format'] not in ('sequence','count') or stable(a['answer']['value'])==stable(b['answer']['value']) or a['item_id']==b['item_id']:raise ValueError('Contrast needs distinct exact answers')
    if pair['delta']!=delta(a,b):raise ValueError('False contrast condition')
    if a['features']['semantic_target']==b['features']['semantic_target']:raise ValueError('Repeated semantic path')
    return pair


def member(pair,role):
    validate_pair(pair)
    if type(role) is not int or role not in (0,1):raise ValueError('Invalid pair role')
    body=copy.deepcopy(pair['members'][role]);body.pop('schema');body.pop('item_id')
    body.update(primary_group='paired',pair_id=pair['pair_id'],pair_role=role,edit_verification='verified',pair_certificate=copy.deepcopy(pair))
    body['reasoning_tags']+=['contrast_pair','one_clause_change']
    return {'schema':MEMBER,'item_id':'b1000contrast:'+stable(body),**body}


def validate_member(item):
    if item.get('schema')!=MEMBER or type(item.get('pair_role')) is not int or item['pair_role'] not in (0,1):raise ValueError('Invalid contrast member')
    pair=validate_pair(item['pair_certificate'])
    if item!=member(pair,item['pair_role']):raise ValueError('Changed contrast member view')
    return item


def units(items):
    groups=defaultdict(list)
    for item in items:
        if item.get('schema')==MEMBER:
            validate_member(item);groups[item['pair_id']].append(item)
    for pair_id,rows in groups.items():
        if len(rows)!=2 or {x['pair_role'] for x in rows}!={0,1} or rows[0]['pair_certificate']!=rows[1]['pair_certificate']:
            raise ValueError('Incomplete or mixed contrast pair')
    return {p:sorted(rows,key=lambda x:x['pair_role']) for p,rows in groups.items()}


def conflict_groups(items):
    """Do not select a paired task again as a standalone or another pair member."""
    grouped=defaultdict(list)
    for n,item in enumerate(items):
        grouped[stable([item['chapter_id'],item.get('source',{}).get('snapshots'),item['features']['semantic_target']])].append(n)
    return [ns for ns in grouped.values() if len(ns)>1 and any(items[n].get('schema')==MEMBER for n in ns)]


def public_input(item):
    validate_member(item)
    return {'item_id':item['item_id'],'question':item['question'],'answer_format':item['answer_format'],
            'images':[{'index':p['index'],'image_path':p['image_path'],'image_sha256':p['image_sha256']} for p in item['context']['pages']]}


def score(items,predictions):
    from .evaluation import exact,pair_accuracy
    pairs=units(items)
    if len(items)!=2*len(pairs) or not isinstance(predictions,dict) or set(predictions)-{x['item_id'] for x in items}:raise ValueError('Invalid contrast scoring inputs')
    results={x['item_id']:x['item_id'] in predictions and exact(x['answer_format'],predictions[x['item_id']],x['answer']['value']) for x in items}
    return {'member_accuracy':sum(results.values())/len(results) if results else None,
            'both_correct_pair_accuracy':pair_accuracy(results,{p:[x['item_id'] for x in rows] for p,rows in pairs.items()}),
            'members':len(items),'pairs':len(pairs),'missing':len(items)-len(predictions),'scores':results}
