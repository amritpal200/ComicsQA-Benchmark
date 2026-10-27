# /// script
# requires-python = ">=3.11"
# dependencies = ["pyarrow>=15", "pillow>=11,<13"]
# ///
"""Export the PopManga human annotations to one read-only JSON per page (never modifies the source).

Reads the saved Hugging Face dataset (dataset/<split>/data-*.arrow) directly with pyarrow. Each row's
`image_path` points to the original download location; it is mapped to --images by its path after
the last "/images/" component, and the image must exist there.

Verified on the local copy (2026-10-23): labels 0=character, 1=text, 2=panel, 3=tail; relation
indices refer to the category-filtered lists; text_char_matches are [text, character] and
text_tail_matches are [text, tail] pairs. Panel boxes in this export are model proxies, not human.
text_classification is kept as the raw 0/1 value; its meaning is not verified here.

Output: <out>/<relative image path>.json = {"schema": "comics_qa.human.v1", "page": {...},
"human": {"characters": [...], "texts": [...], "tails": [...], "panels_proxy": [...],
"text_character": [...], "text_tail": [...]}, "raw": <original row, unchanged>}
"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 'comics_qa.human.v1'
LABELS = {0: 'character', 1: 'text', 2: 'panel', 3: 'tail'}


def log(message):
    print(message, file=sys.stderr, flush=True)


def read_split(path):
    import pyarrow as pa
    with pa.memory_map(str(path)) as source:
        try:
            table = pa.ipc.open_stream(source).read_all()
        except pa.ArrowInvalid:
            table = pa.ipc.open_file(source).read_all()
    return table.to_pylist()


def relative_image_path(stored):
    """'/old/root/PopManga_Test/images/Naruto/ch/p.jpg' -> 'Naruto/ch/p.jpg'."""
    marker = '/images/'
    if marker not in stored:
        raise ValueError(f'image_path has no "/images/" component: {stored}')
    return stored.rsplit(marker, 1)[1]


def convert_row(row):
    """Split the flat box list by label; validate relation indices. Returns the 'human' record."""
    boxes = row['magi_annotations']['bboxes_as_x1y1x2y2']
    labels = row['magi_annotations']['labels']
    if len(boxes) != len(labels):
        raise ValueError('bbox/label length mismatch')
    by_kind = {kind: [] for kind in LABELS.values()}
    for box, label in zip(boxes, labels):
        if label not in LABELS:
            raise ValueError(f'unknown label {label}')
        by_kind[LABELS[label]].append([float(v) for v in box])
    chars, texts, tails = by_kind['character'], by_kind['text'], by_kind['tail']
    names, clusters, classes = row['character_names'], row['character_clusters'], row['text_classification']
    if not (len(names) == len(clusters) == len(chars)):
        raise ValueError('character names/clusters do not match character boxes')
    if len(classes) != len(texts):
        raise ValueError('text_classification does not match text boxes')
    for t, c in row['text_char_matches']:
        if not (0 <= t < len(texts) and 0 <= c < len(chars)):
            raise ValueError(f'text_char_matches out of range: {[t, c]}')
    for t, tl in row['text_tail_matches']:
        if not (0 <= t < len(texts) and 0 <= tl < len(tails)):
            raise ValueError(f'text_tail_matches out of range: {[t, tl]}')
    return {
        'characters': [{'index': i, 'box': box, 'name': name, 'named': name.strip().lower() != 'none',
                        'cluster': cluster}
                       for i, (box, name, cluster) in enumerate(zip(chars, names, clusters))],
        'texts': [{'index': i, 'box': box, 'text_classification': cls}
                  for i, (box, cls) in enumerate(zip(texts, classes))],
        'tails': [{'index': i, 'box': box} for i, box in enumerate(tails)],
        'panels_proxy': [{'index': i, 'box': box} for i, box in enumerate(by_kind['panel'])],
        'text_character': [list(pair) for pair in row['text_char_matches']],
        'text_tail': [list(pair) for pair in row['text_tail_matches']],
        'notes': {'coordinates': 'xyxy pixels in the original image raster; indices into the lists above',
                  'text_character': '[text index, character index]',
                  'text_tail': '[text index, tail index]',
                  'panels_proxy': 'model-generated panel proxies included in the export, not human',
                  'name_none': '"none" marks an unnamed character',
                  'text_classification': 'raw 0/1 value; meaning not verified'},
    }


def atomic_write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.',
                                     suffix='.tmp', delete=False) as handle:
        temp = Path(handle.name)
        handle.write(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=1) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o644)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while block := handle.read(1 << 22):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--dataset', type=Path, required=True, help='PopManga_Test/dataset (read-only)')
    p.add_argument('--images', type=Path, required=True, help='PopManga_Test/images (read-only)')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--overwrite', action='store_true')
    args = p.parse_args(argv)
    args.dataset, args.images, args.out = (x.expanduser().resolve() for x in (args.dataset, args.images, args.out))
    source_root = args.dataset.parent
    if args.out == source_root or source_root in args.out.parents:
        p.error('--out must be outside the PopManga folder (ground truth is read-only)')
    from PIL import Image
    counts = Counter()
    seen = {}
    for split in json.loads((args.dataset / 'dataset_dict.json').read_text())['splits']:
        files = sorted((args.dataset / split).glob('data-*.arrow'))
        if not files:
            raise SystemExit(f'no arrow files for split {split}')
        row_index = 0
        for file in files:
            for row in read_split(file):
                rel = relative_image_path(row['image_path'])
                if rel in seen:
                    raise SystemExit(f'duplicate page {rel} in {split} and {seen[rel]}')
                seen[rel] = split
                image = args.images / rel
                if not image.is_file():
                    raise SystemExit(f'image missing for {split} row {row_index}: {image}')
                target = args.out / (rel + '.json')
                if target.exists() and not args.overwrite:
                    counts['skipped_existing'] += 1
                    row_index += 1
                    continue
                with Image.open(image) as handle:
                    width, height = handle.size
                human = convert_row(row)
                atomic_write_json(target, {
                    'schema': SCHEMA,
                    'page': {'relative_path': rel, 'split': split, 'row_index': row_index,
                             'source_file': str(file.relative_to(source_root)),
                             'original_image_path': row['image_path'], 'images_root': str(args.images),
                             'image_sha256': sha256_file(image), 'width': width, 'height': height},
                    'human': human,
                    'raw': row,
                })
                counts[f'pages_{split}'] += 1
                counts['characters'] += len(human['characters'])
                counts['named_characters'] += sum(c['named'] for c in human['characters'])
                counts['texts'] += len(human['texts'])
                row_index += 1
    report = {'time': datetime.now(timezone.utc).isoformat(), 'dataset': str(args.dataset),
              'images': str(args.images), 'counts': dict(counts)}
    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / 'runs.jsonl', 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(report) + '\n')
    log(f'Done: {dict(counts)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
