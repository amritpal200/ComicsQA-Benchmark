# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "torch==2.7.1+cu128", "torchvision==0.22.1+cu128",
#   "transformers==4.45.2", "timm>=1.0,<1.1", "einops>=0.8,<0.9",
#   "pytorch-metric-learning>=2.8,<3", "pillow>=11,<13", "numpy>=1.26,<3",
#   "matplotlib>=3.9,<4", "shapely>=2,<3", "networkx>=3,<4",
# ]
# [tool.uv.sources]
# torch = { index = "pytorch-cu128" }
# torchvision = { index = "pytorch-cu128" }
# [[tool.uv.index]]
# name = "pytorch-cu128"
# url = "https://download.pytorch.org/whl/cu128"
# explicit = true
# ///
"""Second MAGI v3 pass: ground the characters mentioned in Qwen panel captions, then link them to
human (and MAGI v3) character boxes.

For every MAGI v3 panel with a complete Qwen caption: the panel crop + caption go to MAGI v3
`predict_character_grounding` (strict mode by default: the caption text is kept exactly). Each
grounded phrase ("the boy with spiky hair", "he") gets one or more boxes; near-duplicate boxes are
merged into entities; entities are matched one-to-one by IoU (Hungarian) to the human character
boxes whose centre lies in the panel (name + cluster from ground truth) and to the MAGI v3 character
boxes. Inputs (images, human, MAGI v3, Qwen) are read-only; output goes to --out.

Output: <out>/<relative image path>.json = {"schema": "comics_qa.magi3_grounding.v1", "page": {...},
"grounding": {"panels": [...], "_meta": {...}}}
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'magi3'))
import matching  # noqa: E402
from run_magi3 import (atomic_write_json, check_cuda_kernels, check_model,  # noqa: E402
                       fatal_cuda_error, log, output_path)

SCHEMA = 'comics_qa.magi3_grounding.v1'
QWEN_SCHEMA = 'comics_qa.qwen32B.v1'
VERSION = 1


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def list_pages(qwen_root):
    pages = []
    for path in qwen_root.rglob('*.json'):
        rel = path.relative_to(qwen_root)
        if any(part.startswith('.') for part in rel.parts) or not path.name.endswith('.json') \
                or rel.name == 'runs.jsonl':
            continue
        pages.append(Path(rel.as_posix()[:-len('.json')]))
    return sorted(pages, key=lambda p: p.as_posix())


def settings(args):
    return {'version': VERSION, 'strict': args.strict, 'merge_iou': args.merge_iou,
            'match_iou': args.match_iou, 'ambiguity_margin': args.ambiguity_margin}


def load_page(relative, args):
    """Collect everything the page needs; validate that all sources describe the same image."""
    qwen = read_json(output_path(args.qwen, relative))
    if qwen.get('schema') != QWEN_SCHEMA or qwen['qwen32B']['_meta'].get('status') != 'complete':
        raise ValueError('Qwen annotation missing or not complete')
    magi = read_json(output_path(args.magi3, relative))
    image_sha = qwen['page']['image_sha256']
    if magi['page'].get('image_sha256') not in (None, image_sha):
        raise ValueError('MAGI v3 and Qwen annotations refer to different images')
    human_path = output_path(args.human, relative)
    human = read_json(human_path) if human_path.exists() else None
    if human is not None:
        if human['page']['image_sha256'] != image_sha:
            raise ValueError('Human annotation refers to a different image')
        if [human['page']['width'], human['page']['height']] != magi['magi3']['_meta']['image_size']:
            raise ValueError('Human annotation image size differs from MAGI v3')
    return qwen, magi, human


def signature(qwen, args):
    captions = [(p['panel_index'], p['crop_bbox'], text_sha(p.get('caption', '')))
                for p in qwen['qwen32B']['panels']]
    blob = json.dumps({'captions': captions, 'qwen_signature': qwen['qwen32B']['_meta']['signature'],
                       'settings': settings(args)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def phrases_from_output(output, crop_box):
    """MAGI v3 grounding output -> phrases with spans and page-coordinate boxes."""
    x0, y0 = crop_box[0], crop_box[1]
    text = output['grounded_caption']
    phrases = []
    for k, (boxes, (start, end)) in enumerate(zip(output['bboxes'], output['indices_of_bboxes_in_caption'])):
        page_boxes = [[b[0] + x0, b[1] + y0, b[2] + x0, b[3] + y0] for b in boxes]
        phrases.append({'phrase_index': k, 'text': text[start:end], 'span': [start, end],
                        'kind': 'phrase' if end > start else 'box_only',
                        'boxes_crop': [list(map(float, b)) for b in boxes],
                        'boxes_page': [[round(float(v), 2) for v in b] for b in page_boxes]})
    return phrases


BOUNDARY = '.,;:!?()\n'
LEADING_LINKS = {'and', 'while', 'as', 'but', 'then', 'where', 'who', 'whom', 'which', 'whereas', 'also'}


def position_maps(grounded, caption):
    """Map positions in the grounded text to the caption. MAGI v3 can drop characters (e.g. commas
    next to a grounded phrase) even in strict mode. At block edges an end position belongs to the
    earlier aligned block and a start position to the later one."""
    import difflib
    starts, ends = [None] * (len(grounded) + 1), [None] * (len(grounded) + 1)
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, grounded, caption, autojunk=False).get_opcodes():
        if tag == 'equal':
            for k in range(i2 - i1 + 1):
                starts[i1 + k] = j1 + k
                if ends[i1 + k] is None:
                    ends[i1 + k] = j1 + k
    for table in (starts, ends):
        last = 0
        for i, value in enumerate(table):
            table[i] = last = value if value is not None else last
    return starts, ends


PRONOUNS = {'he', 'she', 'they', 'him', 'her', 'his', 'hers', 'their', 'theirs', 'them', 'it', 'its',
            'himself', 'herself', 'themselves', 'itself'}


LOCATIVE = {'to', 'on', 'in', 'at', 'behind', 'beside', 'next', 'near', 'above', 'below', 'under',
             'from', 'across', 'between', 'around', 'inside', 'outside', 'further', 'farther'}
AFTER_STOP = re.compile(r'\s(?:with|in|wearing|holding|who|is|are|has|have|looks?|stands?|sits?)\s|[.,;:!?]')


def reconstruct_phrase(caption, anchor, floor):
    """Approximate referring phrase for a box inserted at `anchor` (strict-mode MAGI v3 inserts box
    tokens without marking the phrase). Usually the box follows its head noun ("a boy⟦⟧ with...") or
    pronoun ("his⟦⟧"); after a locative lead-in ("On the far right,⟦⟧ a girl ...") it refers to the
    following noun phrase. Returns (start, end, direction)."""
    before = caption[floor:anchor]
    last = re.search(r'(\w+)\W*$', before)
    if last and last.group(1).lower() in PRONOUNS:
        return floor + last.start(1), floor + last.end(1), 'before'
    start = floor
    for i in range(anchor - 1, floor - 1, -1):
        if caption[i] in BOUNDARY and caption[i + 1:anchor].strip():
            start = i + 1
            break
    segment = caption[start:anchor].strip(' ,;:')
    first = segment.split()[0].lower() if segment else ''
    if not segment or first in LOCATIVE:
        rest = caption[anchor:]
        lead = len(rest) - len(rest.lstrip(' ,;:'))
        stop = AFTER_STOP.search(rest, lead)
        end = anchor + (stop.start() if stop else len(rest))
        return anchor + lead, end, 'after'
    while True:
        while start < anchor and caption[start] in ' ,;:':
            start += 1
        word = re.match(r'(\w+)\s+', caption[start:anchor])
        if word and word.group(1).lower() in LEADING_LINKS and start + word.end() < anchor:
            start += word.end()
            continue
        return start, anchor, 'before'


def map_spans_to_caption(phrases, grounded, caption):
    """Give every phrase a span and text in the original Qwen caption.
    Tagged phrases (<grounding>...</grounding>) keep their mapped span. Box-only outputs (strict mode
    inserts boxes right after a phrase without marking its start) get an exact end and a
    reconstructed start (`reconstructed: true`)."""
    starts, ends = position_maps(grounded, caption)
    previous_anchor = 0
    for phrase in phrases:
        start, end = phrase['span']
        anchor = ends[end]
        phrase['anchor_in_caption'] = anchor
        if phrase['kind'] == 'phrase':
            s, e, direction = starts[start], anchor, 'tagged'
        else:
            s, e, direction = reconstruct_phrase(caption, anchor, min(previous_anchor, anchor))
        phrase['span_in_caption'] = [s, e]
        phrase['text_in_caption'] = caption[s:e].strip()
        phrase['reconstructed'] = direction != 'tagged'
        phrase['phrase_direction'] = direction
        previous_anchor = max(previous_anchor, anchor)


def named_caption(caption, phrases, entities):
    """Character-aware caption ("From Panels to Prose", step 4): insert [Name] / [unnamed] at each
    grounded box position whose entity is matched to a human character. Anchors are exact; no
    phrase boundaries are needed."""
    insertions = []
    for phrase in phrases:
        labels = []
        for e in phrase['entity_ids']:
            human = entities[e]['human_character']
            if human.get('status') == 'matched':
                labels.append(human['name'] if human.get('named') else 'unnamed')
        if labels:
            insertions.append((phrase['anchor_in_caption'], '[' + ', '.join(dict.fromkeys(labels)) + ']'))
    text = caption
    for anchor, tag in sorted(insertions, reverse=True):
        text = text[:anchor] + (' ' if anchor and not text[anchor - 1].isspace() else '') + tag + text[anchor:]
    return text


def link_panel(panel, phrases, magi_chars, human, args):
    """Merge phrase boxes into entities and match entities to human and MAGI v3 characters."""
    flat, owner_of = [], []
    for phrase in phrases:
        for box in phrase['boxes_page']:
            flat.append(box)
            owner_of.append(phrase['phrase_index'])
    entities, box_entity = matching.merge_boxes(flat, args.merge_iou)
    for phrase in phrases:
        phrase['entity_ids'] = sorted({box_entity[i] for i, o in enumerate(owner_of) if o == phrase['phrase_index']})
    region = panel['crop_bbox']
    magi_refs = [(i, box) for i, box in enumerate(magi_chars) if matching.center_inside(box, region)]
    magi_links = matching.match_entities(entities, magi_refs, args.match_iou, args.ambiguity_margin)
    if human is not None:
        chars = human['human']['characters']
        human_refs = [(c['index'], c['box']) for c in chars if matching.center_inside(c['box'], region)]
        human_links = matching.match_entities(entities, human_refs, args.match_iou, args.ambiguity_margin)
    else:
        human_links = [None] * len(entities)
    result = []
    for e, (box, magi_link, human_link) in enumerate(zip(entities, magi_links, human_links)):
        entry = {'entity_id': e, 'box_page': [round(v, 2) for v in box], 'magi3_character': magi_link}
        if human_link is None:
            entry['human_character'] = {'status': 'no_ground_truth'}
        else:
            if human_link['ref'] is not None:
                c = human['human']['characters'][human_link['ref']]
                human_link = {**human_link, 'name': c['name'], 'named': c['named'], 'cluster': c['cluster']}
            entry['human_character'] = human_link
        result.append(entry)
    for phrase in phrases:
        names = [result[e]['human_character'].get('name') for e in phrase['entity_ids']
                 if result[e]['human_character'].get('status') == 'matched'
                 and result[e]['human_character'].get('named')]
        phrase['names'] = sorted(set(names))
    return result


class Grounder:
    def __init__(self, args, hashes):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ.setdefault('MPLBACKEND', 'Agg')
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoProcessor
        if transformers.__version__ != '4.45.2':
            raise RuntimeError('transformers==4.45.2 is required (run through scripts/ground_magi3.sh)')
        self.torch = torch
        device = args.device if args.device != 'auto' else ('cuda' if torch.cuda.is_available() else 'cpu')
        if device.startswith('cuda'):
            check_cuda_kernels(torch, device)
        dtype = args.dtype if args.dtype != 'auto' else ('float16' if device.startswith('cuda') else 'float32')
        log(f'Loading MAGI v3 on {device}, {dtype}')
        self.processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            args.model, trust_remote_code=True, local_files_only=True,
            torch_dtype=getattr(torch, dtype), attn_implementation='eager').to(device).eval()
        self.strict = args.strict
        self.metadata = {'model_path': str(args.model), 'model_code_sha256': hashes,
                         'torch': torch.__version__, 'transformers': transformers.__version__,
                         'device': device, 'dtype': dtype}

    def ground(self, crops, captions):
        with self.torch.inference_mode():
            return self.model.predict_character_grounding(crops, captions, self.processor, strict=self.strict)


def ground_batch(engine, crops, captions):
    """Run a batch; on non-fatal failure split it. Returns a list of outputs or exceptions."""
    try:
        return engine.ground(crops, captions)
    except Exception as exc:
        if fatal_cuda_error(exc):
            raise RuntimeError(f'Fatal CUDA error; stopping: {exc}') from exc
        log(f'Grounding failed for {len(crops)} panel(s): {type(exc).__name__}: {str(exc)[:300]}')
        if len(crops) == 1:
            return [exc]
    gc.collect()
    if engine.torch.cuda.is_available():
        engine.torch.cuda.empty_cache()
    mid = len(crops) // 2
    log(f'Grounding batch of {len(crops)} failed; retrying as {mid} + {len(crops) - mid}')
    return ground_batch(engine, crops[:mid], captions[:mid]) + ground_batch(engine, crops[mid:], captions[mid:])


def process_page(relative, engine, args, counts):
    from PIL import Image
    qwen, magi, human = load_page(relative, args)
    target = output_path(args.out, relative)
    sig = signature(qwen, args)
    if target.exists() and not args.overwrite:
        old = read_json(target)['grounding']['_meta']
        if old.get('status') == 'complete' and old.get('signature') == sig:
            counts['skipped_existing'] += 1
            return
    panels = qwen['qwen32B']['panels']
    todo = [p for p in panels if isinstance(p.get('caption'), str) and p['caption'].strip()]
    with Image.open(args.images / relative) as source:
        image = source.convert('RGB')
    try:
        crops = [image.crop(p['crop_bbox']) for p in todo]
        outputs = []
        # MAGI v3's strict decoding (slowly_generate_grounded_caption) fails on batches whose
        # captions differ in token length, so strict mode runs one panel per call.
        step = 1 if args.strict else args.batch_size
        for i in range(0, len(todo), step):
            outputs += ground_batch(engine, crops[i:i + step],
                                    [p['caption'] for p in todo[i:i + step]])
    finally:
        image.close()
    magi_chars = magi['magi3']['characters']
    results, failed = [], 0
    by_index = {p['panel_index']: (p, out) for p, out in zip(todo, outputs)}
    for panel in panels:
        entry = {'panel_index': panel['panel_index'], 'crop_bbox': panel['crop_bbox'],
                 'caption': panel.get('caption'), 'caption_sha256': text_sha(panel.get('caption') or '')}
        if panel['panel_index'] not in by_index:
            entry['status'] = 'no_caption'
        else:
            out = by_index[panel['panel_index']][1]
            if isinstance(out, Exception):
                entry.update(status='failed', error=f'{type(out).__name__}: {out}')
                failed += 1
            else:
                phrases = phrases_from_output(out, panel['crop_bbox'])
                map_spans_to_caption(phrases, out['grounded_caption'], panel['caption'])
                entities = link_panel(panel, phrases, magi_chars, human, args)
                entry.update(status='complete', caption_exact=out['grounded_caption'] == panel['caption'],
                             grounded_caption=out['grounded_caption'],
                             named_caption=named_caption(panel['caption'], phrases, entities),
                             phrases=phrases, entities=entities)
                counts['phrases'] += len(phrases)
                counts['entities'] += len(entities)
                for e in entities:
                    counts[f"human_{e['human_character']['status']}"] += 1
                counts['caption_not_exact'] += not entry['caption_exact']
        results.append(entry)
    status = 'complete' if failed == 0 else 'partial'
    atomic_write_json(target, {
        'schema': SCHEMA,
        'page': {'relative_path': relative.as_posix(), 'image_sha256': qwen['page']['image_sha256'],
                 'has_ground_truth': human is not None, 'qwen_root': str(args.qwen),
                 'magi3_root': str(args.magi3), 'human_root': str(args.human)},
        'grounding': {'panels': results, '_meta': {
            **engine.metadata, **settings(args), 'status': status, 'signature': sig,
            'qwen_prompt_version': qwen['qwen32B']['_meta'].get('prompt_version'),
            'coordinates': 'xyxy pixels in the original page raster',
            'created_at': datetime.now(timezone.utc).isoformat()}},
    })
    counts['pages_written'] += 1
    counts['panels_grounded'] += sum(r['status'] == 'complete' for r in results)
    counts['panels_failed'] += failed
    if failed:
        counts['pages_partial'] += 1


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ('images', 'magi3', 'qwen', 'human', 'out', 'model'):
        p.add_argument(f'--{name}', type=Path, required=True)
    p.add_argument('--batch-size', type=int, default=8, help='panels per model call (non-strict mode only)')
    p.add_argument('--device', default='auto')
    p.add_argument('--dtype', choices=['auto', 'float16', 'bfloat16', 'float32'], default='auto')
    p.add_argument('--no-strict', dest='strict', action='store_false',
                   help='let the model rewrite the caption while grounding (faster, text may drift)')
    p.add_argument('--merge-iou', type=float, default=0.8, help='merge grounded boxes into one entity')
    p.add_argument('--match-iou', type=float, default=0.5, help='minimum IoU to link an entity to a character')
    p.add_argument('--ambiguity-margin', type=float, default=0.1)
    p.add_argument('--limit', type=int)
    p.add_argument('--match', help='only pages whose relative path contains this text')
    p.add_argument('--shard', default='0/1')
    p.add_argument('--overwrite', action='store_true')
    args = p.parse_args(argv)
    k, n = (int(v) for v in args.shard.split('/'))
    if not 0 <= k < n:
        p.error('--shard must be K/N with 0 <= K < N')
    args.shard_index, args.shard_count = k, n
    for name in ('images', 'magi3', 'qwen', 'human', 'out', 'model'):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    for name in ('images', 'magi3', 'qwen', 'human'):
        if args.out == getattr(args, name) or getattr(args, name) in args.out.parents:
            p.error(f'--out must be outside --{name} (inputs are read-only)')
    return args


def main(argv=None):
    args = parse_args(argv)
    start = time.monotonic()
    started = datetime.now().astimezone()
    counts, status, lock = Counter(), 'failed', None
    try:
        hashes = check_model(args.model)
        pages = list_pages(args.qwen)
        if args.match:
            pages = [p for p in pages if args.match in p.as_posix()]
        pages = pages[args.shard_index::args.shard_count]
        if args.limit:
            pages = pages[:args.limit]
        counts['pages'] = len(pages)
        log(f'{len(pages)} pages with Qwen captions (shard {args.shard})')
        args.out.mkdir(parents=True, exist_ok=True)
        lock = open(args.out / f'.grounding.shard{args.shard_index}of{args.shard_count}.lock', 'a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another runner holds this shard lock') from None
        engine = Grounder(args, hashes) if pages else None
        for n, relative in enumerate(pages, 1):
            try:
                process_page(relative, engine, args, counts)
            except Exception as exc:
                if 'Fatal CUDA error' in str(exc):
                    raise
                counts['pages_failed'] += 1
                log(f'ERROR {relative}: {type(exc).__name__}: {exc}')
            rate = n / max(time.monotonic() - start, 1e-6) * 60
            log(f'[{n}/{len(pages)}] {relative.name}: {rate:.1f} pages/min {dict(counts)}')
        status = ('limited' if args.limit or args.match else
                  'completed_with_errors' if counts['pages_failed'] or counts['pages_partial'] else 'complete')
        return 1 if counts['pages_failed'] or counts['pages_partial'] else 0
    except KeyboardInterrupt:
        status = 'interrupted'
        return 130
    finally:
        minutes = (time.monotonic() - start) / 60
        log(f'Run summary [{status}] in {minutes:.1f} min: {dict(counts)}')
        if lock is not None:
            with open(args.out / 'runs.jsonl', 'a', encoding='utf-8') as handle:
                handle.write(json.dumps({'started_at': started.isoformat(), 'elapsed_minutes': round(minutes, 3),
                                         'status': status, 'shard': args.shard, 'host': os.uname().nodename,
                                         'settings': settings(args), 'counts': dict(counts)}) + '\n')
            lock.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        log(f'FATAL {type(exc).__name__}: {exc}')
        sys.exit(1)
