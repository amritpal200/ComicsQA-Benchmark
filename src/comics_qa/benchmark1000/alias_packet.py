"""Private, portable alias evidence crops. No approvals or source-image edits."""
import base64
import html
import io
from pathlib import Path
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.gen2.aliases import validate_reviews
from .io import digest, read, separate
from .assets import binary_publish


def create(requests_path, bench_root, out, max_evidence=3):
    if type(max_evidence) is not int or max_evidence < 1:
        raise ValueError('Positive alias evidence budget required')
    out = separate(out, [requests_path, Path(bench_root) / 'evidence', Path(bench_root) / 'core'])
    rows = read(requests_path)
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Alias requests must be a list of objects')
    from PIL import Image
    cache = {}; sections = []
    for row in rows:
        chapter = row['chapter_id']
        if chapter not in cache:
            gr, vr = (Path(bench_root) / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1'))
            g, v, _ = load_world(gr, vr, chapter)
            validate_reviews(rows, g, v, digest(gr / 'chapters' / (chapter + '.json')), digest(vr / 'chapters' / (chapter + '.json')))
            cache[chapter] = (g, v)
        g, v = cache[chapter]; nodes = {n['id']: n for n in g['nodes']}
        evidence = {e['evidence_id']: e for e in v['evidence']}
        identity = row['identity_id']; node = nodes[identity]; figures = []
        for eid in row['evidence_ids'][:max_evidence]:
            e = evidence[eid]
            if e['identity_id'] != identity or e['status'] != 'verified':
                raise ValueError('Alias packet evidence mismatch')
            page = nodes[e['page_id']]; path = Path(page['image_path'])
            if digest(path) != page['image_sha256'] or page['image_sha256'] != e['image_sha256']:
                raise ValueError('Alias review image hash mismatch')
            appearances = {f['args'][0] for f in g['facts'] if f['rel'] == 'is_char' and f['args'][1] == identity and f['answer_eligible'] and f['origin'] in ('H', 'V')}
            regions = [('name text', nodes[e['text_id']]['box'])] + [('human identity depiction', nodes[a]['box']) for a in sorted(appearances) if nodes[a]['page_id'] == e['page_id']]
            with Image.open(path) as source:
                for label, box in regions:
                    left, top, right, bottom = box
                    padded = (max(0, int(left) - 12), max(0, int(top) - 12), min(source.width, int(right) + 12), min(source.height, int(bottom) + 12))
                    crop = source.crop(padded).convert('RGB'); data = io.BytesIO(); crop.save(data, format='PNG')
                    encoded = base64.b64encode(data.getvalue()).decode('ascii')
                    figures.append('<figure><img src="data:image/png;base64,' + encoded + '"><figcaption>' + html.escape(label + ' | ' + e['page_id'] + ' | ' + eid) + '</figcaption></figure>')
            figures.append('<p>Paddle: ' + html.escape(e['paddle_text']) + '<br>MAGI: ' + html.escape(e['magi_text']) + '</p>')
        sections.append('<section><h2>' + html.escape(row['form'] + ' → ' + node['canonical_name']) + '</h2><p>' + html.escape(chapter + ' | recorded decision: ' + row['decision']) + '</p>' + ''.join(figures) + '</section>')
    text = '<!doctype html><meta charset="utf-8"><title>Private alias review</title><style>body{font:16px sans-serif;max-width:1100px;margin:auto}section{border-top:1px solid #bbb}figure{display:inline-block;vertical-align:top;max-width:45%}img{max-width:100%;max-height:600px}figcaption{font-size:12px;overflow-wrap:anywhere}</style><h1>Alias evidence — no automatic approval</h1><p>Inspect exact readable form, identity and use as a character name. Copy the review JSON outside its immutable source output before recording any decision. This packet grants no QA release or human-review status.</p>' + ''.join(sections)
    binary_publish(out, text.encode('utf-8'))
    return {'output': str(out), 'requests': len(rows), 'approval': 'none', 'source_sha256': digest(requests_path)}
