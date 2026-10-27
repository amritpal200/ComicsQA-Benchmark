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
"""Run MAGI v3 on a read-only image tree and write one annotation JSON per page elsewhere.

Model calls, saved fields and robustness (score capture, killable reading-order worker,
OOM batch splitting, fatal-CUDA detection) follow /home/asingh/Comics/annotations/magi3/annotate.py.
Differences: the image tree is never modified (no sidecar edits, no folder rename); output
mirrors the tree under --out as <relative path>.json; traversal is sorted, so --limit and
reruns are deterministic. Resume: pages whose output has _meta.status == "complete" are
skipped unless --overwrite.

Output file: {"schema": "comics_qa.magi3.v1", "page": {...}, "magi3": {...}}
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import gc
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time

SCHEMA = 'comics_qa.magi3.v1'
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}
SCORE_FIELDS = {
    'character_character_affinity_matrices': 'character_character_affinity',
    'text_character_association_matrices': 'text_character',
    'text_tail_association_matrices': 'text_tail',
    'essential_text_logits': 'essential_text',
}
MODEL_FILES = ('config.json', 'model.safetensors', 'modeling_florence2.py', 'configuration_florence2.py',
               'processing_florence2.py', 'utils.py', 'tokenizer.json', 'preprocessor_config.json')
HASHED_FILES = ('config.json', 'modeling_florence2.py', 'processing_florence2.py', 'utils.py')


def log(message):
    print(message, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- input / output

def list_images(root):
    """Sorted relative paths of regular image files under root (symlinks and hidden files skipped)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith('.'))
        for name in filenames:
            path = Path(dirpath) / name
            if (not name.startswith('.') and Path(name).suffix.lower() in EXTENSIONS
                    and path.is_file() and not path.is_symlink()):
                found.append(path.relative_to(root))
    return sorted(found, key=lambda p: p.as_posix())


def output_path(out_root, relative):
    return Path(out_root) / relative.with_suffix(relative.suffix + '.json')


def existing_status(path):
    """'complete', 'partial', 'invalid' or None (no file)."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data['magi3']['_meta']['status']
    except (OSError, ValueError, KeyError, TypeError):
        return 'invalid'


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while block := handle.read(1 << 22):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=1)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.',
                                     suffix='.tmp', delete=False) as handle:
        temp = Path(handle.name)
        handle.write(text + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o644)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


# ---------------------------------------------------------------- model

def check_model(folder):
    for name in MODEL_FILES:
        if not (folder / name).is_file() or (folder / name).stat().st_size == 0:
            raise ValueError(f'Missing/empty model file: {folder / name}')
    config = json.loads((folder / 'config.json').read_text())
    source = (folder / 'modeling_florence2.py').read_text()
    if config.get('_name_or_path') != 'magiv3' or not all(
            f'def {name}(' in source for name in (
                'predict_detections_and_associations', 'predict_ocr', 'predict_character_grounding')):
        raise ValueError('The model config/code does not identify the expected MAGI v3 API')
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in HASHED_FILES}


def reading_order_job(model_path, detections, ocr, direction):
    """Native geometry from the checkpoint's utils.py, in a killable process (cycle search can hang)."""
    spec = importlib.util.spec_from_file_location('magi3_order_utils', Path(model_path) / 'utils.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def prepare(boxes):
        if any(len(b) != 4 or not all(math.isfinite(x) for x in b) or b[2] <= b[0] or b[3] <= b[1]
               for b in boxes):
            raise ValueError('Reading order requires finite, positive-area boxes')
        return [[-b[2], b[1], -b[0], b[3]] for b in boxes] if direction == 'ltr' else boxes

    panels = prepare(detections['panels'])
    texts = prepare(detections['texts'])
    ocr_boxes = prepare(ocr['bboxes'])
    panel_order = module.sort_panels(panels)
    sorted_panels = [panels[i] for i in panel_order]
    return {
        'status': 'complete', 'source': 'derived_from_magiv3_utils_geometry',
        'direction': direction, 'panels': panel_order,
        'texts': module.sort_text_boxes_in_reading_order(texts, sorted_panels),
        'ocr': module.sort_text_boxes_in_reading_order(ocr_boxes, sorted_panels),
        'text_to_panel': module.get_text_to_panel_mapping(texts, panels),
        'ocr_to_panel': module.get_text_to_panel_mapping(ocr_boxes, panels),
    }


class ReadingOrder:
    def __init__(self, args):
        self.args = args
        self.pool = None

    def close(self):
        if self.pool is not None:
            self.pool.terminate()
            self.pool.join()
            self.pool = None

    def predict(self, detections, ocr):
        if self.pool is None:
            self.pool = multiprocessing.get_context('spawn').Pool(1)
        try:
            return self.pool.apply_async(reading_order_job, (
                str(self.args.model), detections, ocr, self.args.reading_direction,
            )).get(timeout=self.args.reading_order_timeout)
        except Exception as exc:
            self.close()
            return {'status': 'error', 'source': 'derived_from_magiv3_utils_geometry',
                    'direction': self.args.reading_direction, 'error': f'{type(exc).__name__}: {exc}'}


def check_cuda_kernels(torch, device):
    """Validate a real kernel before loading weights or attempting batches."""
    name = torch.cuda.get_device_name(device)
    capability = torch.cuda.get_device_capability(device)
    log(f'GPU: {name}; capability sm_{capability[0]}{capability[1]}; '
        f'PyTorch {torch.__version__}; CUDA build {torch.version.cuda}')
    try:
        (torch.ones(1, device=device) + 1).sum().item()
        torch.cuda.synchronize(device)
    except RuntimeError as exc:
        raise RuntimeError(f'GPU kernel preflight failed on {name} (sm_{capability[0]}{capability[1]}); '
                           f'this PyTorch build includes {torch.cuda.get_arch_list()}. '
                           f'No images were attempted. Original error: {exc}') from exc


def fatal_cuda_error(exc):
    message = str(exc).lower()
    return any(fragment in message for fragment in (
        'no kernel image is available', 'invalid device function', 'cuda driver initialization failed',
        'device-side assert triggered', 'an illegal memory access was encountered'))


class Magi:
    def __init__(self, args, hashes):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ.setdefault('MPLBACKEND', 'Agg')
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoProcessor
        if transformers.__version__ != '4.45.2':
            raise RuntimeError('transformers==4.45.2 is required (run through scripts/annotate_magi3.sh)')
        self.torch = torch
        self.args = args
        device = args.device
        if device == 'auto':
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
        if device.startswith('cuda'):
            if not torch.cuda.is_available():
                raise RuntimeError(f'CUDA unavailable (PyTorch {torch.__version__}, CUDA {torch.version.cuda}); '
                                   'use --device cpu or another GPU/host')
            check_cuda_kernels(torch, device)
        dtype_name = args.dtype if args.dtype != 'auto' else ('float16' if device.startswith('cuda') else 'float32')
        log(f'Loading MAGI v3 on {device}, {dtype_name}')
        self.processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            args.model, trust_remote_code=True, local_files_only=True,
            torch_dtype=getattr(torch, dtype_name), attn_implementation='eager',
        ).to(device).eval()
        self.metadata = {
            'model_path': str(args.model), 'model_code_sha256': hashes,
            'torch': torch.__version__, 'transformers': transformers.__version__,
            'device': device, 'dtype': dtype_name,
            'generation': {'num_beams': args.num_beams, 'max_new_tokens': args.max_new_tokens, 'do_sample': False},
            'thresholds': {'character_character': 0.5, 'text_character': 0.8,
                           'text_tail': 0.8, 'essential_text': 0.8},
        }
        # Keep native prediction/postprocessing while exposing its generation options.
        self.native_generate = self.model.generate
        self.model.generate = self.generate
        self.model.register_forward_hook(self.capture_scores)
        self.order = ReadingOrder(args)

    def generate(self, *args, **kwargs):
        kwargs.update(max_new_tokens=self.args.max_new_tokens, num_beams=self.args.num_beams)
        ids = self.native_generate(*args, **kwargs)
        self.generated = ids.detach().cpu().tolist()
        return ids

    def capture_scores(self, module, inputs, output):
        for native, name in SCORE_FIELDS.items():
            values = getattr(output, native, None)
            if values is not None:
                self.scores[name] = [value.detach().float().cpu().tolist() for value in values]

    def generation_details(self):
        result = []
        tokenizer = self.processor.tokenizer
        for ids in self.generated:
            tail = ids[1:]  # the decoder's first token is itself EOS
            length = next((i + 1 for i, token in enumerate(tail) if token == tokenizer.eos_token_id), len(tail))
            result.append({'raw_output': tokenizer.decode(ids, skip_special_tokens=False),
                           'generated_tokens': length,
                           'possibly_truncated': length >= self.args.max_new_tokens})
        return result

    def predict(self, images):
        self.scores = {}
        with self.torch.inference_mode():
            detections = self.model.predict_detections_and_associations(images, self.processor)
            detection_generation = self.generation_details()
            scores = self.scores
            ocr = self.model.predict_ocr(images, self.processor)
            ocr_generation = self.generation_details()
        if len(detections) != len(images) or len(ocr) != len(images):
            raise RuntimeError('Model returned the wrong number of predictions')
        results = []
        for i, (image, detection, transcription) in enumerate(zip(images, detections, ocr)):
            order = self.order.predict(detection, transcription)
            results.append({
                **detection, 'ocr': transcription, 'reading_order': order,
                'association_scores': {key: value[i] for key, value in scores.items()},
                'generation': {'detections_and_associations': detection_generation[i], 'ocr': ocr_generation[i]},
                'character_grounding': {'status': 'deferred', 'reason': 'Requires captions from a VLM'},
                '_meta': {**self.metadata, 'schema_version': 1,
                          'status': 'complete' if order['status'] == 'complete' else 'partial',
                          'created_at': datetime.now(timezone.utc).isoformat(),
                          'image_size': [image.width, image.height],
                          'coordinates': 'xyxy pixels in original image raster; zero-based indices',
                          'batch_size': len(images)},
            })
        return results


# ---------------------------------------------------------------- batches

def process_batch(items, engine, args, counts):
    """items: list of relative paths. Splits the batch recursively on non-fatal failures."""
    from PIL import Image
    opened, valid = [], []
    try:
        for relative in items:
            path = args.images / relative
            try:
                with Image.open(path) as source:
                    opened.append(source.convert('RGB'))
                valid.append(relative)
            except Exception as exc:
                counts['failed'] += 1
                log(f'ERROR {path}: {type(exc).__name__}: {exc}')
        if not valid:
            return
        predictions = None
        try:
            predictions = engine.predict(opened)
        except Exception as exc:
            if fatal_cuda_error(exc):
                raise RuntimeError(f'Fatal CUDA error; stopping: {exc}') from exc
            log(f'Prediction failed for batch of {len(valid)}: {type(exc).__name__}: {exc}')
            if len(valid) == 1:
                counts['failed'] += 1
                log(f'ERROR {valid[0]}: no output written')
        if predictions is not None:
            for relative, prediction in zip(valid, predictions):
                target = output_path(args.out, relative)
                try:
                    if prediction['_meta']['status'] != 'complete':
                        counts['partial'] += 1
                        log(f'SKIP {relative}: incomplete prediction, not written; {prediction.get("reading_order")}')
                        continue
                    image_path = args.images / relative
                    atomic_write_json(target, {
                        'schema': SCHEMA,
                        'page': {'relative_path': relative.as_posix(),
                                 'images_root': str(args.images),
                                 'image_sha256': sha256_file(image_path),
                                 'width': prediction['_meta']['image_size'][0],
                                 'height': prediction['_meta']['image_size'][1]},
                        'magi3': prediction,
                    })
                    counts['written'] += 1
                    limited = [name for name, d in prediction['generation'].items() if d['possibly_truncated']]
                    if limited:
                        counts['possibly_truncated'] += 1
                        log(f'WARNING {relative}: token limit reached for {", ".join(limited)}')
                except Exception as exc:
                    counts['failed'] += 1
                    log(f'ERROR {target}: {type(exc).__name__}: {exc}')
            return
    finally:
        for image in opened:
            image.close()
    gc.collect()
    if engine.torch.cuda.is_available():
        engine.torch.cuda.empty_cache()
    if len(valid) > 1:
        midpoint = len(valid) // 2
        log(f'Retrying as smaller batches ({midpoint} + {len(valid) - midpoint})')
        process_batch(valid[:midpoint], engine, args, counts)
        process_batch(valid[midpoint:], engine, args, counts)


# ---------------------------------------------------------------- main

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--images', type=Path, required=True, help='Root of the read-only image tree')
    parser.add_argument('--out', type=Path, required=True, help='Output root (mirrors the image tree)')
    parser.add_argument('--model', type=Path, required=True, help='Local MAGI v3 checkpoint folder')
    parser.add_argument('--batch-size', type=int, default=1)
    parser.add_argument('--device', default='auto', help='auto, cpu, cuda, or cuda:N')
    parser.add_argument('--dtype', choices=['auto', 'float16', 'bfloat16', 'float32'], default='auto')
    parser.add_argument('--num-beams', type=int, default=3)
    parser.add_argument('--max-new-tokens', type=int, default=1024)
    parser.add_argument('--reading-direction', choices=['rtl', 'ltr'], default='rtl')
    parser.add_argument('--reading-order-timeout', type=int, default=60)
    parser.add_argument('--limit', type=int, help='Process at most N pending pages (in sorted order)')
    parser.add_argument('--shard', default='0/1', help='K/N: process every N-th pending page starting at K '
                                                        '(run N processes on N GPUs)')
    parser.add_argument('--overwrite', action='store_true', help='Recompute pages that already have output')
    parser.add_argument('--check-only', action='store_true', help='List pending pages; load nothing')
    args = parser.parse_args(argv)
    for name in ('batch_size', 'num_beams', 'max_new_tokens', 'reading_order_timeout', 'limit'):
        if getattr(args, name) is not None and getattr(args, name) < 1:
            parser.error(f'--{name.replace("_", "-")} must be positive')
    if args.max_new_tokens > 1024:
        parser.error('--max-new-tokens cannot exceed the checkpoint positional limit (1024)')
    try:
        k, n = (int(v) for v in args.shard.split('/'))
        assert 0 <= k < n
    except (ValueError, AssertionError):
        parser.error('--shard must look like K/N with 0 <= K < N')
    args.shard_index, args.shard_count = k, n
    args.images = args.images.expanduser().resolve()
    args.out = args.out.expanduser().resolve()
    args.model = args.model.expanduser().resolve()
    if not args.images.is_dir():
        parser.error(f'Image root does not exist: {args.images}')
    if args.out == args.images or args.images in args.out.parents:
        parser.error('--out must be outside the image tree (source data is read-only)')
    return args


def main(argv=None):
    args = parse_args(argv)
    start = time.monotonic()
    started = datetime.now().astimezone()
    counts = Counter()
    engine = None
    lock = None
    outcome = 'failed'
    try:
        hashes = check_model(args.model)
        log(f'Confirmed MAGI v3 config and APIs: {args.model}')
        images = list_images(args.images)
        # Shard the full sorted list (not the pending list), so shard membership never depends on
        # what other shards have already written.
        images = images[args.shard_index::args.shard_count]
        counts['images_seen'] = len(images)
        pending = []
        for relative in images:
            status = existing_status(output_path(args.out, relative))
            if status == 'complete' and not args.overwrite:
                counts['skipped_existing'] += 1
            else:
                pending.append(relative)
        if args.limit is not None:
            pending = pending[:args.limit]
        counts['pending'] = len(pending)
        log(f'{len(images)} images, {counts["skipped_existing"]} already annotated, '
            f'{len(pending)} to process (shard {args.shard})')
        if args.check_only:
            for relative in pending[:20]:
                log(f'PENDING {relative}')
            outcome = 'check_only'
            return 0
        args.out.mkdir(parents=True, exist_ok=True)
        lock = open(args.out / f'.magi3.shard{args.shard_index}of{args.shard_count}.lock', 'a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another runner holds this shard lock') from None
        if pending:
            engine = Magi(args, hashes)
        for i in range(0, len(pending), args.batch_size):
            process_batch(pending[i:i + args.batch_size], engine, args, counts)
            done = min(i + args.batch_size, len(pending))
            rate = done / max(time.monotonic() - start, 1e-6) * 60
            log(f'Progress: {done}/{len(pending)} ({rate:.1f} pages/min) {dict(counts)}')
        problems = counts['failed'] or counts['partial']
        outcome = 'limited' if args.limit else 'completed_with_errors' if problems else 'complete'
    except KeyboardInterrupt:
        outcome = 'interrupted'
        raise
    finally:
        if engine is not None:
            engine.order.close()
        minutes = (time.monotonic() - start) / 60
        log(f'Run summary [{outcome}] in {minutes:.1f} min: {dict(counts)}')
        if lock is not None:
            report = {'started_at': started.isoformat(), 'ended_at': datetime.now().astimezone().isoformat(),
                      'elapsed_minutes': round(minutes, 3), 'status': outcome, 'shard': args.shard,
                      'images': str(args.images), 'model': str(args.model), 'host': os.uname().nodename,
                      'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'),
                      'settings': {'batch_size': args.batch_size, 'num_beams': args.num_beams,
                                   'max_new_tokens': args.max_new_tokens, 'dtype': args.dtype,
                                   'reading_direction': args.reading_direction},
                      'counts': dict(counts)}
            with open(args.out / 'runs.jsonl', 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(report, ensure_ascii=False) + '\n')
            lock.close()
    return 1 if counts['failed'] or counts['partial'] else 0


def cli():
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log('Interrupted. Written pages are kept; rerun to resume.')
        sys.exit(130)
    except Exception as exc:
        log(f'FATAL {type(exc).__name__}: {exc}')
        sys.exit(1)


if __name__ == '__main__':
    cli()
