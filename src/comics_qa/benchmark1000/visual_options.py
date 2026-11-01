"""Deterministic visual-option assets over existing trusted appearance links."""
import io
from collections import Counter, defaultdict
from pathlib import Path
from .assets import box_pixels, image_library, render, binary_publish
from .visual import bind_reference
from .io import digest, stable

VERSION = 'visual_options.1'
GLYPHS = ('01110 10001 10001 11111 10001 10001 10001',
          '11110 10001 10001 11110 10001 10001 11110',
          '01111 10000 10000 10000 10000 10000 01111',
          '11110 10001 10001 10001 10001 10001 11110')


def appearances(g, min_edge=48):
    if type(min_edge) is not int or min_edge < 1: raise ValueError('Positive crop edge required')
    nodes = {n['id']: n for n in g['nodes']}; links = defaultdict(list); by_page = defaultdict(list); others = defaultdict(list)
    for f in g['facts']:
        if f['rel'] == 'is_char' and f['origin'] in ('H', 'V') and f['answer_eligible']:
            links[f['args'][0]].append(f)
    for n in g['nodes']:
        if n['type'] == 'Text': by_page[n['page_id']].append(n)
        if n['type'] == 'Appearance': others[n['page_id']].append(n)
    eligible = defaultdict(list); rejected = Counter()
    for app in (n for n in g['nodes'] if n['type'] == 'Appearance'):
        identity = nodes.get(app.get('identity_id'), {}); page = nodes[app['page_id']]
        reason = None
        if identity.get('generic', True): reason = 'generic_identity'
        elif len(links[app['id']]) != 1 or links[app['id']][0]['args'][1] != app['identity_id']: reason = 'identity_link_not_unique'
        elif app.get('geometry_review_required') or app.get('outside_image'): reason = 'geometry_review_required'
        else:
            try: box = box_pixels(app['box'], page['width'], page['height'])
            except ValueError: reason = 'invalid_box'
            if reason is None:
                w, h = box[2] - box[0], box[3] - box[1]
                if min(w, h) < min_edge or max(w, h) > 6 * min(w, h): reason = 'crop_size_or_aspect'
                elif not Path(page['image_path']).is_file(): reason = 'image_missing'
                elif any(min(box[2], t['box'][2]) > max(box[0], t['box'][0]) and min(box[3], t['box'][3]) > max(box[1], t['box'][1]) for t in by_page[app['page_id']]):
                    reason = 'known_text_overlap'
                elif any(max(0,min(box[2],n['box'][2])-max(box[0],n['box'][0])) * max(0,min(box[3],n['box'][3])-max(box[1],n['box'][1])) > .20 * w * h
                         for n in others[app['page_id']] if n['id'] != app['id']): reason = 'other_character_overlap'
        if reason: rejected[reason] += 1
        else: eligible[app['identity_id']].append(app['id'])
    for cid in eligible:
        eligible[cid].sort(key=lambda aid: (-(nodes[aid]['box'][2] - nodes[aid]['box'][0]) * (nodes[aid]['box'][3] - nodes[aid]['box'][1]), aid))
    return dict(eligible), dict(rejected)


def crop(g, aid, out):
    nodes = {n['id']: n for n in g['nodes']}; app = nodes[aid]; page = nodes[app['page_id']]
    Image, _ = image_library()
    with Image.open(page['image_path']) as image:
        if image.size != (page['width'], page['height']): raise ValueError('Page dimensions changed')
    path = Path(out) / 'assets' / (stable([page['image_sha256'], app['box'], VERSION]) + '.png')
    render(page['image_path'], page['image_sha256'], [app['box']], path, 'crop')
    return bind_reference(g, aid, path)


def sheet_bytes(refs):
    Image, Draw = image_library(); canvas = Image.new('RGB', (640, 760), 'white'); draw = Draw.Draw(canvas)
    for n, ref in enumerate(refs):
        x, y = (n % 2) * 320, (n // 2) * 380
        for row, bits in enumerate(GLYPHS[n].split()):
            for col, bit in enumerate(bits):
                if bit == '1': draw.rectangle((x + 12 + 4*col, y + 8 + 4*row, x + 15 + 4*col, y + 11 + 4*row), fill='black')
        with Image.open(ref['crop_path']) as source:
            image = source.convert('RGB'); factor = min(296/image.width, 328/image.height)
            image = image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))),Image.Resampling.LANCZOS)
            canvas.paste(image, (x + (320 - image.width)//2, y + 44 + (328 - image.height)//2))
        draw.rectangle((x, y, x + 319, y + 379), outline=(160,160,160))
    raw = io.BytesIO(); canvas.save(raw, format='PNG'); return raw.getvalue()


def make_sheet(refs, out):
    raw = sheet_bytes(refs); import hashlib
    sha = hashlib.sha256(raw).hexdigest(); path = Path(out) / 'assets' / (sha + '.png'); binary_publish(path, raw)
    return {'path': str(path.resolve()), 'sha256': sha, 'layout': 'AB-CD-contain-320x380.1'}
