# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "torch==2.9.0", "torchvision==0.24.0", "transformers==5.16.1", "pillow>=11,<13",
# ]
# ///
"""OCR every text box with PaddleOCR-VL-1.6 (element-level recognition on crops, prompt "OCR:").

Boxes: the human PopManga text boxes; on pages without ground truth, the MAGI v3 text boxes
(labelled model boxes, for context only). Each box is cropped from the original page with a small
margin and recognised separately. Inputs (images, human, MAGI v3) are read-only; output is one JSON
per page under --out. Text is model-inferred, not ground truth.

Output: <out>/<relative image path>.json = {"schema": "comics_qa.ocr.v1", "page": {...},
"ocr": {"boxes_source": "human" | "model:magi3", "texts": [...], "_meta": {...}}}
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'magi3'))
from run_magi3 import atomic_write_json, list_images, log, output_path, sha256_file  # noqa: E402

SCHEMA = 'comics_qa.ocr.v1'
PROMPT = 'OCR:'
VERSION = 1


def settings(args):
    return {'version': VERSION, 'normalization': 'nfkc+hyphen-join+whitespace', 'prompt': PROMPT, 'dtype': args.dtype, 'margin': args.margin,
            'max_new_tokens': args.max_new_tokens, 'model_revision': args.revision}


def signature(image_sha, boxes, args):
    blob = json.dumps({'image': image_sha, 'boxes': boxes, 'settings': settings(args)}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def page_boxes(relative, args):
    """(source, [(index, box)]): human text boxes when ground truth exists, else MAGI v3 text boxes."""
    human_path = output_path(args.human, relative)
    if human_path.exists():
        doc = json.loads(human_path.read_text())
        return 'human', [(t['index'], t['box']) for t in doc['human']['texts']], doc['page']['image_sha256']
    magi_path = output_path(args.magi3, relative)
    if magi_path.exists():
        doc = json.loads(magi_path.read_text())
        return 'model:magi3', list(enumerate(doc['magi3']['texts'])), doc['page'].get('image_sha256')
    return None, [], None


def normalize(text):
    """NFKC (full-width -> ASCII), join words split across lines with a hyphen ("FOR-\nTIFIED"),
    then line breaks and runs of whitespace -> one space. The raw text is kept separately."""
    text = unicodedata.normalize('NFKC', text)
    text = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', text)
    return ' '.join(text.split())


def crop_box(box, margin, width, height):
    x1, y1, x2, y2 = box
    return [max(0, int(x1) - margin), max(0, int(y1) - margin),
            min(width, int(x2 + 0.9999) + margin), min(height, int(y2 + 0.9999) + margin)]


class Recognizer:
    def __init__(self, args):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import torch
        import transformers
        from transformers import AutoModelForImageTextToText, AutoProcessor
        self.torch = torch
        device = args.device if args.device != 'auto' else ('cuda' if torch.cuda.is_available() else 'cpu')
        dtype_name = args.dtype
        if device.startswith('cuda'):
            (torch.ones(1, device=device) + 1).sum().item()
            capability = torch.cuda.get_device_capability(device)
            log(f'GPU: {torch.cuda.get_device_name(device)} (sm_{capability[0]}{capability[1]}); torch {torch.__version__}')
            if dtype_name == 'auto':
                # fp16 matched fp32 exactly on Turing; Pascal (sm_6x) runs fp16 very slowly, so use fp32 there
                dtype_name = 'float16' if capability >= (7, 0) else 'float32'
        elif dtype_name == 'auto':
            dtype_name = 'float32'
        dtype = getattr(torch, dtype_name)
        log(f'Loading PaddleOCR-VL from {args.model} on {device}, {dtype_name}')
        self.processor = AutoProcessor.from_pretrained(args.model, local_files_only=True)
        self.model = AutoModelForImageTextToText.from_pretrained(
            args.model, dtype=dtype, local_files_only=True).to(device).eval()
        self.dtype, self.device, self.max_new_tokens = dtype, device, args.max_new_tokens
        self.metadata = {'model_path': str(args.model), 'model_revision': args.revision,
                         'config_sha256': sha256_file(args.model / 'config.json'),
                         'torch': torch.__version__, 'transformers': transformers.__version__,
                         'device': device, 'dtype_used': dtype_name, 'prompt': PROMPT}

    def recognise(self, image):
        messages = [{'role': 'user', 'content': [{'type': 'image', 'image': image},
                                                 {'type': 'text', 'text': PROMPT}]}]
        inputs = self.processor.apply_chat_template(messages, add_generation_prompt=True, tokenize=True,
                                                    return_dict=True, return_tensors='pt').to(self.device)
        for key, value in inputs.items():
            if self.torch.is_floating_point(value):
                inputs[key] = value.to(self.dtype)
        with self.torch.inference_mode():
            out = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        new = out[0][inputs['input_ids'].shape[-1]:]
        eos = self.processor.tokenizer.eos_token_id
        tokens = new.tolist()
        finished = eos in tokens
        length = tokens.index(eos) if finished else len(tokens)
        text = self.processor.decode(new[:length], skip_special_tokens=True).strip()
        return text, length, not finished


def process_page(relative, engine, args, counts):
    from PIL import Image
    source, boxes, expected_sha = page_boxes(relative, args)
    image_path = args.images / relative
    image_sha = sha256_file(image_path)
    if expected_sha and expected_sha != image_sha:
        raise ValueError('image differs from the annotated one (sha256 mismatch)')
    target = output_path(args.out, relative)
    sig = signature(image_sha, boxes, args)
    if target.exists() and not args.overwrite:
        meta = json.loads(target.read_text())['ocr']['_meta']
        if meta.get('status') == 'complete' and meta.get('signature') == sig:
            counts['skipped_existing'] += 1
            return
    texts, failed = [], 0
    with Image.open(image_path) as handle:
        page = handle.convert('RGB')
    try:
        for index, box in boxes:
            crop = crop_box(box, args.margin, page.width, page.height)
            entry = {'index': index, 'box': box, 'crop_box': crop}
            if crop[2] - crop[0] < 2 or crop[3] - crop[1] < 2:
                entry.update(status='empty_box', text='', text_normalized='')
                counts['empty_box'] += 1
            else:
                try:
                    text, length, truncated = engine.recognise(page.crop(crop))
                    entry.update(text=text, text_normalized=normalize(text), generated_tokens=length,
                                 truncated=truncated,
                                 status='truncated' if truncated else ('empty' if not text else 'ok'))
                    counts[entry['status']] += 1
                except Exception as exc:
                    if 'CUDA' in str(exc) and 'out of memory' not in str(exc).lower():
                        raise
                    entry.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                    failed += 1
                    counts['failed'] += 1
            texts.append(entry)
    finally:
        page.close()
    atomic_write_json(target, {
        'schema': SCHEMA,
        'page': {'relative_path': relative.as_posix(), 'image_sha256': image_sha,
                 'has_ground_truth': source == 'human'},
        'ocr': {'boxes_source': source, 'texts': texts, '_meta': {
            **engine.metadata, **settings(args), 'signature': sig,
            'status': 'complete' if failed == 0 else 'partial',
            'coordinates': 'xyxy pixels in the original page; index = position in the source text list',
            'created_at': datetime.now(timezone.utc).isoformat()}}})
    counts['pages_written'] += 1
    counts['boxes'] += len(boxes)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ('images', 'human', 'magi3', 'out', 'model'):
        p.add_argument(f'--{name}', type=Path, required=True)
    p.add_argument('--revision', default='c5630abae1d940eafe0697512a0325494b02ab42',
                   help='model revision recorded in the output')
    p.add_argument('--device', default='auto')
    p.add_argument('--dtype', choices=['auto', 'float16', 'float32', 'bfloat16'], default='auto',
                   help='auto: float16 on sm_70+ (matched float32 exactly on Turing), float32 on older GPUs')
    p.add_argument('--margin', type=int, default=4, help='pixels added around each box before cropping')
    p.add_argument('--max-new-tokens', type=int, default=256)
    p.add_argument('--limit', type=int)
    p.add_argument('--match', help='only pages whose relative path contains this text')
    p.add_argument('--shard', default='0/1')
    p.add_argument('--overwrite', action='store_true')
    args = p.parse_args(argv)
    k, n = (int(v) for v in args.shard.split('/'))
    if not 0 <= k < n:
        p.error('--shard must be K/N with 0 <= K < N')
    args.shard_index, args.shard_count = k, n
    for name in ('images', 'human', 'magi3', 'out', 'model'):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    for name in ('images', 'human', 'magi3'):
        if args.out == getattr(args, name) or getattr(args, name) in args.out.parents:
            p.error(f'--out must be outside --{name} (inputs are read-only)')
    return args


def main(argv=None):
    args = parse_args(argv)
    start = time.monotonic()
    started = datetime.now().astimezone()
    counts, status, lock = Counter(), 'failed', None
    try:
        pages = list_images(args.images)
        if args.match:
            pages = [p for p in pages if args.match in p.as_posix()]
        pages = pages[args.shard_index::args.shard_count]
        if args.limit:
            pages = pages[:args.limit]
        counts['pages'] = len(pages)
        log(f'{len(pages)} pages (shard {args.shard})')
        args.out.mkdir(parents=True, exist_ok=True)
        lock = open(args.out / f'.ocr.shard{args.shard_index}of{args.shard_count}.lock', 'a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another runner holds this shard lock') from None
        engine = Recognizer(args) if pages else None
        for n, relative in enumerate(pages, 1):
            try:
                process_page(relative, engine, args, counts)
            except Exception as exc:
                if 'CUDA' in str(exc) and 'out of memory' not in str(exc).lower():
                    raise
                counts['pages_failed'] += 1
                log(f'ERROR {relative}: {type(exc).__name__}: {exc}')
            minutes = (time.monotonic() - start) / 60
            log(f'[{n}/{len(pages)}] {relative.name}: {counts["boxes"] / max(minutes, 1e-6):.0f} boxes/min {dict(counts)}')
        status = ('limited' if args.limit or args.match else
                  'completed_with_errors' if counts['pages_failed'] or counts['failed'] else 'complete')
        return 1 if counts['pages_failed'] or counts['failed'] else 0
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
                                         'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
                                         'settings': settings(args), 'counts': dict(counts)}) + '\n')
            lock.close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        log(f'FATAL {type(exc).__name__}: {exc}')
        sys.exit(1)
