"""Exact derived images. Originals and graph snapshots are always read-only."""
import copy
import hashlib
import io
import math
import os
from pathlib import Path
import random
import tempfile
from .io import digest, publish, separate, stable


def image_library():
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise ImportError('Install configs/benchmark1000/requirements.txt in a dedicated uv environment') from exc
    return Image, ImageDraw


def binary_publish(path, raw):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing symlink asset')
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Existing image differs')
        return
    fd, temp = tempfile.mkstemp(prefix='.b1000-image-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw); f.flush(); os.fsync(f.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != raw:
                raise ValueError('Concurrent asset differs')
    finally:
        os.unlink(temp)


def box_pixels(box, width, height):
    if len(box) != 4 or any(type(v) not in (int, float) or not math.isfinite(v) for v in box):
        raise ValueError('Invalid crop/mask coordinates')
    x0, y0, x1, y1 = box
    if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
        raise ValueError('Box outside image or non-positive area')
    return (math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1))


def render(source, expected_sha256, boxes, out, mode):
    if mode not in ('crop', 'mask') or (mode == 'crop' and len(boxes) != 1) or not boxes:
        raise ValueError('Invalid image transform')
    source = Path(source).resolve(); out = separate(out, [source])
    if digest(source) != expected_sha256:
        raise ValueError('Source image hash mismatch')
    Image, ImageDraw = image_library()
    with Image.open(source) as source_image:
        original = source_image.convert('RGB')
    pixels = [box_pixels(b, *original.size) for b in boxes]
    if mode == 'crop':
        result = original.crop(pixels[0])
    else:
        result = original.copy(); draw = ImageDraw.Draw(result)
        for x0, y0, x1, y1 in pixels:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=(0, 0, 0))
    buffer = io.BytesIO(); result.save(buffer, format='PNG')
    raw = buffer.getvalue()
    manifest = {'schema': 'comics_qa.benchmark1000.image_transform.1', 'mode': mode,
                'source_image_sha256': expected_sha256, 'source_size': list(original.size),
                'boxes_pixels_half_open': [list(b) for b in pixels], 'image_sha256': hashlib.sha256(raw).hexdigest(),
                'output_size': list(result.size), 'transform': 'rgb-png-integer-box.1'}
    binary_publish(out, raw)
    publish(out.with_suffix(out.suffix + '.json'), manifest)
    return manifest


def masked_overlay(graph, page_id, boxes):
    """Conservative dependency invalidation, never asserts absence of story events."""
    nodes = {n['id']: n for n in graph['nodes']}
    page = nodes.get(page_id)
    if not page or page['type'] != 'Page':
        raise ValueError('Unknown page')
    masks = [box_pixels(b, page['width'], page['height']) for b in boxes]
    def overlaps(a, b):
        return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])
    hidden = {n['id'] for n in nodes.values() if n.get('page_id') == page_id and 'box' in n
              and any(overlaps(n['box'], b) for b in masks)}
    # Invalidate all page-local model facts as captions may describe multiple regions.
    removed = {f['fact_id'] for f in graph['facts'] if set(f['args']) & hidden
               or page_id in f['page_ids'] and f['origin'] not in ('H', 'V')}
    while True:
        changed = removed | {f['fact_id'] for f in graph['facts'] if set(f['premises']) & removed}
        if changed == removed:
            break
        removed = changed
    return {'schema': 'comics_qa.benchmark1000.mask_overlay.1', 'base_graph_sha256': stable(graph),
            'page_id': page_id, 'mask_boxes': [list(b) for b in masks], 'hidden_node_ids': sorted(hidden),
            'invalidated_fact_ids': sorted(removed),
            'invalidate_external_companions_on_pages': [page_id],
            'coverage_overrides': [{'coverage_id': c['coverage_id'], 'status': 'open'} for c in graph['coverage']
                                   if c['page_id'] == page_id and c['family'] != 'page_sequence'],
            'semantics': 'visible_evidence_only', 'status': 'requires_render_binding_and_residual_clue_review',
            'determinability_certificate': None}


def choice_manifest(graph, target, evidence_pages, option_appearances, seed):
    """Validate reference identity links; pixel rendering is a separate transform."""
    if len(option_appearances) != 4 or len(set(option_appearances)) != 4:
        raise ValueError('Require four distinct reference appearances')
    nodes = {n['id']: n for n in graph['nodes']}
    links = {(f['args'][0], f['args'][1]): f['fact_id'] for f in graph['facts']
             if f['rel'] == 'is_char' and f['answer_eligible'] and f['origin'] in ('H', 'V')}
    options = []
    for aid in option_appearances:
        app = nodes[aid]; cid = app.get('identity_id'); identity = nodes.get(cid, {})
        if (aid, cid) not in links or identity.get('generic', True):
            raise ValueError('No admitted stable identity link for reference crop')
        if app['page_id'] in evidence_pages:
            raise ValueError('References must be on different pages from necessary evidence')
        options.append({'appearance_id': aid, 'identity_id': cid, 'page_id': app['page_id'],
                        'box': app['box'], 'identity_fact_id': links[aid, cid]})
    if len({o['identity_id'] for o in options}) != 4 or sum(o['identity_id'] == target for o in options) != 1:
        raise ValueError('Ambiguous choices or target missing')
    random.Random(seed).shuffle(options)
    for label, option in zip('ABCD', options):
        option['label'] = label
    return {'options': options, 'correct_label': next(o['label'] for o in options if o['identity_id'] == target),
            'seed': seed, 'distractor_review': 'pending', 'release_status': 'pending'}
