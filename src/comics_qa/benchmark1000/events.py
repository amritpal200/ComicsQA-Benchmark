"""Event facts from grounded captions, confirmed by an independent model (improvement plan S5).

prepare  (CPU): caption sentences about exactly one grounded, human-matched character and containing an action
                verb become statements about "the outlined character". Each gets two images of the panel: the human
                annotation box of that character outlined (positive) and another identified character outlined (control).
verify   (GPU server, user-run): yes/no answers from an OpenAI-compatible endpoint; one create-only file per request.
ingest   (CPU): a fact is accepted only with positive=yes and control=no. Accepted facts are tier-A candidates;
                promotion needs the audit sample (audit.html) to be reviewed.

The outline comes from the human box (H) and the identity from human is_char facts, so a grounding error (caption
phrase linked to the wrong character) makes the verifier see another character and answer no. Caption text is model
output (M) and is never shown to the evaluated model.
"""
import base64
import html
import json
import os
import re
import tempfile
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .io import digest, member, publish, read, separate, stable

VERSION = 'events.1'
REQUESTS = 'comics_qa.benchmark1000.event_requests.1'
FACTS = 'comics_qa.benchmark1000.event_facts.1'
SUBJECT = 'the outlined character'
PROMPT = ('This image is a manga panel. One character is outlined with a red box. Is the following statement true '
          'for the outlined character?\nStatement: {statement}\nAnswer with only "yes" or "no".')
VERBS = {'point', 'raise', 'hold', 'grip', 'clutch', 'lunge', 'run', 'leap', 'jump', 'fall', 'kneel', 'sit', 'stand',
         'shout', 'yell', 'scream', 'cry', 'smile', 'laugh', 'grin', 'frown', 'glare', 'stare', 'look', 'turn', 'reach',
         'swing', 'wield', 'punch', 'kick', 'attack', 'hug', 'carry', 'eat', 'drink', 'read', 'write', 'walk', 'rush',
         'flinch', 'recoil', 'cover', 'bow', 'wave', 'clench', 'crouch', 'lie', 'sleep', 'bleed', 'grab', 'throw',
         'push', 'pull', 'strike', 'slash', 'block', 'dodge', 'charge', 'fly', 'float', 'lean', 'kiss', 'weep', 'sob',
         'gasp', 'sweat', 'blush', 'tremble', 'shake', 'nod', 'gesture', 'extend', 'brandish', 'aim', 'fire', 'hide',
         'peek', 'climb', 'collapse', 'embrace', 'touch', 'lift', 'drag', 'catch', 'bite', 'scowl', 'pout', 'wink'}
TEXTY = re.compile(r'speech bubble|text|caption|letter(ing)?|sound effect|onomatopoeia', re.I)
SENTENCE = re.compile(r'[^.!?]+[.!?]+')
NOUN_PHRASE = re.compile(r"^(a|an|the|another|one|this|that)\b[\w\s'’-]*$", re.I)
MAX_PHRASE_WORDS, MAX_STATEMENT_WORDS = 5, 40


def verb_forms():
    forms = set()
    for v in VERBS:
        stem = v[:-1] if v.endswith('e') and v not in ('see',) else v
        forms |= {v, v + 's', v + 'es', stem + 'ing', v + 'ing', v[:-1] + 'ies' if v.endswith('y') else v}
    return forms


FORMS = verb_forms()


def has_action(sentence):
    return any(w in FORMS for w in re.findall(r"[a-z]+", sentence.lower()))


def statements(panel):
    """(statement, phrase) for caption sentences with exactly one grounded phrase naming one human-matched entity."""
    caption = panel['caption']; out = []
    entities = {e['entity_id']: e for e in panel.get('entities', [])}
    for m in SENTENCE.finditer(caption):
        start, end = m.span()
        inside = [p for p in panel.get('phrases', []) if start <= p['span_in_caption'][0] and p['span_in_caption'][1] <= end]
        if len(inside) != 1 or len(inside[0]['entity_ids']) != 1: continue
        p = inside[0]; e = entities.get(p['entity_ids'][0], {})
        phrase = p.get('text_in_caption') or ''
        # Only a short noun phrase may become the subject; long reconstructed spans break the sentence.
        if not NOUN_PHRASE.match(phrase) or len(phrase.split()) > MAX_PHRASE_WORDS or has_action(phrase): continue
        human = e.get('human_character', {})
        if human.get('status') != 'matched' or not human.get('named'): continue
        sentence = caption[start:end].strip()
        if TEXTY.search(sentence) or not has_action(sentence): continue
        a, b = p['span_in_caption'][0] - start, p['span_in_caption'][1] - start
        raw = caption[start:end]
        lead = len(raw) - len(raw.lstrip())
        text = raw[:a] + SUBJECT + raw[b:]
        text = text.strip()
        if a - lead == 0: text = text[0].upper() + text[1:]
        if SUBJECT not in text.lower() or len(text.split()) > MAX_STATEMENT_WORDS or not has_action(text.lower().replace(SUBJECT, '')): continue
        out.append((text, p, human['ref']))
    return out


def inside_share(box, crop):
    x0, y0, x1, y1 = max(box[0], crop[0]), max(box[1], crop[1]), min(box[2], crop[2]), min(box[3], crop[3])
    area = max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    return 0.0 if area <= 0 else max(0, x1 - x0) * max(0, y1 - y0) / area


def render(image_path, crop, box, path):
    """Panel crop with one red outline; create-only PNG."""
    from PIL import Image, ImageDraw
    path = Path(path)
    if path.exists(): return
    with Image.open(image_path) as im:
        panel = im.convert('RGB').crop(tuple(int(round(c)) for c in crop))
    draw = ImageDraw.Draw(panel); w = max(3, round(min(panel.size) / 150))
    draw.rectangle([box[0] - crop[0], box[1] - crop[1], box[2] - crop[0], box[3] - crop[1]], outline=(255, 0, 0), width=w)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.ev-', suffix='.png', dir=path.parent); os.close(fd)
    try:
        panel.save(temp, format='PNG')
        try: os.link(temp, path)
        except FileExistsError: pass
    finally:
        os.unlink(temp)


def chapter_candidates(g, grounding_root, out, min_inside=0.8):
    pages = {n['relative_path']: n for n in g['nodes'] if n['type'] == 'Page'}
    apps = {n['id']: n for n in g['nodes'] if n['type'] == 'Appearance'}
    is_char = {f['args'][0]: f for f in g['facts'] if f['rel'] == 'is_char' and f['origin'] == 'H' and f['answer_eligible']}
    generic = {n['id'] for n in g['nodes'] if n['type'] == 'Character' and n.get('generic')}
    rows, stats = [], Counter()
    for rel, page in sorted(pages.items()):
        path = Path(grounding_root) / (rel + '.json')
        if not path.exists(): stats['no_grounding_file'] += 1; continue
        doc = read(path)
        if doc['page'].get('image_sha256') != page['image_sha256']: stats['image_mismatch'] += 1; continue
        for panel in doc['grounding']['panels']:
            if panel.get('status') != 'complete' or not panel.get('caption_exact'): stats['panel_not_exact'] += 1; continue
            crop = panel['crop_bbox']
            # Identified characters of this panel (human-matched entities, human box mostly inside the crop).
            present = {}
            for e in panel.get('entities', []):
                h = e.get('human_character', {})
                if h.get('status') != 'matched': continue
                aid = f"{page['id']}__hchar{h['ref']:02d}"
                if aid in apps and aid in is_char and inside_share(apps[aid]['box'], crop) >= min_inside:
                    present[aid] = is_char[aid]['args'][1]
            for statement, phrase, ref in statements(panel):
                stats['statements'] += 1
                aid = f"{page['id']}__hchar{ref:02d}"
                if aid not in present: stats['subject_not_identified'] += 1; continue
                identity = present[aid]
                if identity in generic: stats['generic_subject'] += 1; continue
                controls = sorted((a for a, c in present.items() if c != identity), key=lambda a: (-area(apps[a]['box']), a))
                if not controls: stats['no_control'] += 1; continue
                control = controls[0]
                fact_id = 'event:' + stable([page['id'], panel['panel_index'], panel['caption_sha256'], statement, aid])
                images = {}
                for role, a in (('positive', aid), ('control', control)):
                    name = f"images/{stable([fact_id, role])}.png"
                    render(page['image_path'], crop, apps[a]['box'], out / name); images[role] = name
                rows.append({'fact_id': fact_id, 'chapter_id': g['chapter_id'], 'page_id': page['id'], 'panel_index': panel['panel_index'],
                             'crop_bbox': crop, 'caption_sha256': panel['caption_sha256'], 'statement': statement,
                             'caption_phrase': phrase['text_in_caption'], 'appearance_id': aid, 'identity_id': identity,
                             'is_char_fact': is_char[aid]['fact_id'], 'control_appearance_id': control, 'control_identity_id': present[control],
                             'images': images, 'prompt': PROMPT.format(statement=statement)})
                stats['candidates'] += 1
    return rows, stats


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def prepare(bench_root, grounding_root, out, chapters=None):
    from comics_qa.tasks.graph.crl.artifacts import load_world
    root = Path(bench_root).resolve(); roots = [root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1']
    out = separate(out, roots + [root / 'core', Path(grounding_root)])
    available = read(roots[0] / 'manifest.json')['config']['chapters']; chosen = sorted(chapters or available)
    if not set(chosen) <= set(available): raise ValueError('Unknown chapter scope')
    config = {'schema': REQUESTS, 'version': VERSION, 'chapters': chosen, 'grounding_root': str(Path(grounding_root).resolve()),
              'graph_manifest_sha256': digest(roots[0] / 'manifest.json'), 'prompt': PROMPT,
              'code_sha256': digest(Path(__file__))}
    out.mkdir(parents=True, exist_ok=True); publish(out / 'config.json', config)
    rows, stats = [], Counter()
    for cid in chosen:
        path = out / 'chapters' / (cid + '.json')
        if path.exists():
            saved = read(path)
            if saved['config_sha256'] != stable(config): raise ValueError('Stale event checkpoint')
        else:
            g, _, _ = load_world(roots[0], roots[1], cid)
            r, s = chapter_candidates(g, grounding_root, out)
            saved = {'config_sha256': stable(config), 'rows': r, 'stats': dict(s)}
            publish(path, saved)
        rows += saved['rows']; stats.update(saved['stats'])
    publish(out / 'requests.json', {'schema': REQUESTS, 'config_sha256': stable(config), 'requests': rows})
    report = {'candidates': len(rows), 'stats': dict(stats), 'chapters': len(chosen), 'images': 2 * len(rows)}
    publish(out / 'report.json', report)
    return report


def ask(endpoint, model, prompt, image, timeout=120):
    data = base64.b64encode(Path(image).read_bytes()).decode()
    body = {'model': model, 'temperature': 0, 'max_tokens': 4, 'messages': [{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}}, {'type': 'text', 'text': prompt}]}]}
    req = urllib.request.Request(endpoint.rstrip('/') + '/chat/completions', data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())['choices'][0]['message']['content']


def verify(requests_root, endpoint, model, out, workers=16, limit=None, retries=3):
    requests_root = Path(requests_root).resolve(); out = separate(out, [requests_root])
    doc = read(requests_root / 'requests.json'); rows = doc['requests'][:limit] if limit else doc['requests']
    publish(out / 'config.json', {'schema': 'comics_qa.benchmark1000.event_responses.1', 'requests_sha256': digest(requests_root / 'requests.json'),
                                  'endpoint': endpoint, 'model': model})
    jobs = [(r, role) for r in rows for role in ('positive', 'control')]
    def one(job):
        r, role = job; path = out / 'responses' / f"{stable([r['fact_id'], role])}.json"
        if path.exists(): return 'reused'
        for attempt in range(retries):
            try:
                answer = ask(endpoint, model, r['prompt'], requests_root / r['images'][role]); break
            except Exception as e:  # network/server errors: retry, then record nothing (rerun resumes)
                if attempt == retries - 1: return 'failed'
                time.sleep(2 ** attempt)
        publish(path, {'fact_id': r['fact_id'], 'role': role, 'model': model, 'answer': answer})
        return 'answered'
    with ThreadPoolExecutor(workers) as pool:
        counts = Counter(pool.map(one, jobs))
    return {'jobs': len(jobs), **counts}


def parse(answer):
    a = re.sub(r'[^a-z]', ' ', answer.lower()).split()
    return a[0] if a and a[0] in ('yes', 'no') else 'unparsed'


def ingest(requests_root, responses_root, out, audit_size=60, seed=0):
    requests_root, responses_root = Path(requests_root).resolve(), Path(responses_root).resolve()
    out = separate(out, [requests_root, responses_root])
    rows = read(requests_root / 'requests.json')['requests']; model = read(responses_root / 'config.json')['model']
    facts, outcome = [], Counter()
    for r in rows:
        got = {}
        for role in ('positive', 'control'):
            p = responses_root / 'responses' / f"{stable([r['fact_id'], role])}.json"
            got[role] = parse(read(p)['answer']) if p.exists() else 'missing'
        key = got['positive'] + '/' + got['control']; outcome[key] += 1
        if key == 'yes/no':
            facts.append({**{k: r[k] for k in ('fact_id', 'chapter_id', 'page_id', 'panel_index', 'statement', 'appearance_id',
                                               'identity_id', 'is_char_fact', 'control_appearance_id', 'caption_sha256', 'images')},
                          'origin': 'M', 'confirmation': {'model': model, 'positive': 'yes', 'control': 'no'},
                          'tier': 'A_candidate', 'audit': 'pending'})
    audit = sorted(facts, key=lambda f: stable([seed, f['fact_id']]))[:audit_size]
    report = {'schema': FACTS, 'version': VERSION, 'requests': len(rows), 'accepted': len(facts), 'outcomes': dict(outcome),
              'model': model, 'audit_ids': [f['fact_id'] for f in audit],
              'inputs_sha256': {'requests': digest(requests_root / 'requests.json'), 'responses_config': digest(responses_root / 'config.json')}}
    publish(out / 'facts.json', {'schema': FACTS, 'facts': facts})
    publish(out / 'report.json', report)
    page = ['<!doctype html><meta charset="utf-8"><title>Event audit</title>',
            '<style>body{font:14px sans-serif;margin:16px}figure{display:inline-block;margin:8px;vertical-align:top;width:300px}'
            'img{max-width:300px;max-height:300px}</style>',
            f'<h1>Event fact audit sample ({len(audit)} of {len(facts)})</h1><p>For each: is the statement true for the red-outlined '
            'character in the first image? Record correct / wrong per fact ID.</p>']
    for f in audit:
        img = os.path.relpath(requests_root / f['images']['positive'], out)
        page.append(f'<figure><img src="{html.escape(img)}"><figcaption><b>{html.escape(f["fact_id"][6:18])}</b> '
                    f'{html.escape(f["statement"])}</figcaption></figure>')
    target = out / 'audit.html'
    text = '\n'.join(page) + '\n'
    if target.exists() and target.read_text() != text: raise ValueError('Existing audit differs; choose a new output')
    target.write_text(text)
    return report
