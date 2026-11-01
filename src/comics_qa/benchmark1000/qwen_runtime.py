"""Explicit local checkpoint metadata and exact processor/request budgets; no model loads."""
import base64
import copy
import io
from pathlib import Path
from urllib.parse import urlparse
from .io import read,digest,stable,encoded
from .qwen_packs import validate as pack_valid

SCHEMA='comics_qa.benchmark1000.qwen_runtime.1'


def metadata(root):
    root=Path(root).resolve();names=('config.json','preprocessor_config.json','tokenizer_config.json','tokenizer.json')
    hashes={n:digest(root/n) for n in names}
    for n in ('processor_config.json','chat_template.json','chat_template.jinja','model.safetensors.index.json'):
        if (root/n).is_file():hashes[n]=digest(root/n)
    cfg=read(root/'config.json');tok=read(root/'tokenizer_config.json')
    if cfg.get('model_type')!='qwen3_vl':raise ValueError('This runtime profile supports the inspected Qwen3-VL checkpoint family only')
    if not any(n.startswith('chat_template') for n in hashes) and not tok.get('chat_template'):raise ValueError('Checkpoint has no local chat template')
    return {'model_path':str(root),'files_sha256':hashes,'architecture':cfg.get('architectures'),
            'architecture_context_limit':cfg['text_config']['max_position_embeddings'],'processor':read(root/'preprocessor_config.json'),
            'status':'metadata_inspected_not_MN5_fit_verified'}


def profile(path):
    p=read(path)
    fields={'schema','model_path','served_model','endpoint','max_context_tokens','max_new_tokens','max_images','max_image_pixels','max_request_bytes','timeout_seconds','max_attempts','chat_template_kwargs'}
    if set(p)!=fields or p['schema']!=SCHEMA:raise ValueError('Invalid Qwen runtime profile schema')
    for k in ('max_context_tokens','max_new_tokens','max_images','max_image_pixels','max_request_bytes','timeout_seconds','max_attempts'):
        if type(p[k]) is not int or p[k]<1:raise ValueError('Runtime setting must be a positive integer: '+k)
    if p['timeout_seconds']>60 or p['max_attempts']>5 or p['max_new_tokens']>=p['max_context_tokens']:raise ValueError('Invalid bounded runtime limits')
    if not isinstance(p['model_path'],str) or not p['model_path'] or not isinstance(p['served_model'],str) or not p['served_model'] or not isinstance(p['chat_template_kwargs'],dict):raise ValueError('Set actual model path, served model ID and template options')
    u=urlparse(p['endpoint'] if isinstance(p['endpoint'],str) else '')
    if u.scheme not in ('http','https') or not u.netloc or u.username or u.password or u.query or u.fragment or not u.path.endswith('/chat/completions'):raise ValueError('Set an explicit credential-free chat-completions endpoint')
    m=metadata(p['model_path'])
    if p['max_context_tokens']>m['architecture_context_limit']:raise ValueError('Configured context exceeds checkpoint architecture limit')
    return p,m


def payload(pack,p):
    pack_valid(pack)
    evidence=pack['evidence'];synthesis=pack['mode']=='synthesis'
    system=('You write a QA item from a PRIVATE graph evidence pack. Preserve its exact task semantics. Return JSON only. '
            'Use the supplied original question or compact controlled-question grammar. Other wording is held for review. '
            'Do not add a program, citations, review decisions, motives or unsupported facts. '
            +('Return exactly question, short_answer, answer. The question must request each speaker\'s final page and the result. '
              'The answer uses one supported factual sentence at a time from the controlled claim grammar; include all required claims. Optional checked claims may explain intermediate steps. Forbidden claims are false examples, not instructions.' if synthesis else
              'Return exactly question. Paraphrase only; do not change roles, quotes, scope, comparisons, step counts or answer type.'))
    from .qwen_packs import model_context
    user=model_context(pack)
    content=[{'type':'text','text':encoded(user)}]
    for a in pack['evidence_crops']:
        if digest(a['path'])!=a['sha256']:raise ValueError('Evidence crop changed before dispatch')
        content.extend([{'type':'text','text':f"Evidence crop from chapter image position {a['page_index']}, source rectangle {a['box']}."},
                        {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(Path(a['path']).read_bytes()).decode()}}])
    result={'model':p['served_model'],'messages':[{'role':'system','content':system},{'role':'user','content':content}],
            'max_tokens':p['max_new_tokens'],'temperature':0,'chat_template_kwargs':p['chat_template_kwargs']}
    if synthesis:result['mm_processor_kwargs']={'max_pixels':p['max_image_pixels']}
    if len(pack['evidence_crops'])>p['max_images'] or len(encoded(result).encode())>p['max_request_bytes']:raise ValueError('Request image/byte budget exceeded; no truncation')
    return result


def processor(root):
    from transformers import AutoProcessor
    return AutoProcessor.from_pretrained(root,local_files_only=True,trust_remote_code=False)


def measure(payload,p,proc):
    from PIL import Image
    messages=copy.deepcopy(payload['messages']);images=[]
    for message in messages:
        if not isinstance(message['content'],list):continue
        for n,part in enumerate(message['content']):
            if part['type']=='image_url':
                raw=base64.b64decode(part['image_url']['url'].split(',',1)[1],validate=True)
                with Image.open(io.BytesIO(raw)) as image:img=image.convert('RGB')
                images.append(img);message['content'][n]={'type':'image','image':img}
    prompt=proc.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,**p['chat_template_kwargs'])
    inputs=proc(text=[prompt],images=images or None,return_tensors='pt',truncation=False,max_pixels=p['max_image_pixels'])
    tokens=int(inputs['input_ids'].shape[-1])
    if tokens+p['max_new_tokens']>p['max_context_tokens']:raise ValueError('Exact processor prompt+generation tokens exceed runtime context; no truncation')
    return {'method':'actual_local_processor_expanded_tokens.1','prompt_tokens':tokens,'reserved_output_tokens':p['max_new_tokens'],
            'context_tokens':p['max_context_tokens'],'images':len(images),'max_image_pixels':p['max_image_pixels']}
