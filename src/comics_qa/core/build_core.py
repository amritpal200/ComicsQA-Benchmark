"""Build the benchmark foundation: chapters, pages and series-level character identities (spec 01).

Joins, per page, the human ground truth (annotations/human) with MAGI v3 structure (panels and their
reading order), following the source-precedence rule in docs/specs/00_architecture.md: human facts
wherever they exist, MAGI v3 only for what the ground truth lacks (panels, reading order) and for
pages without ground truth (kept separately as `model_only`). All inputs are read-only; the output is
a new versioned folder that is never overwritten.

IDs are derived from file names and ground-truth indices, so they are stable across rebuilds:
  chapter  <series-slug>__c001             page   <chapter>__p004 (spread: __p001-002)
  panel    <page>__panel03 (MAGI v3 index)   human  <page>__hchar05 / __htext07 / __htail02
  identity <series-slug>__<name-slug> for named characters (same exact name within a series; the
           names are consistent per series, and subset names such as "L" / "Lind L. Tailor" are
           different people, so nothing is merged); unnamed ("none") characters get page-local
           identities <page>__unnamed<cluster>.

Output (--out/<version>/): chapters.jsonl, pages.jsonl, characters.jsonl, manifest.json, report.json
Standard library only.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geometry  # noqa: E402

SCHEMA = 'comics_qa.core.v1'
FILENAME = re.compile(r'^(?P<series>.+) - (?P<chapter>\d{3}) - p(?P<start>\d{3})(?:-(?P<end>\d{3}))? - '
                      r'(?P<title>.+)\.(?:jpe?g|png|webp)$', re.IGNORECASE)
MIN_ALIAS_LEN = 3


def log(message):
    print(message, file=sys.stderr, flush=True)


def slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.casefold()).strip('-')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while block := handle.read(1 << 22):
            digest.update(block)
    return digest.hexdigest()


def write_jsonl(path, rows):
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.',
                                     suffix='.tmp', delete=False) as handle:
        temp = Path(handle.name)
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def write_json(path, obj):
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix=f'.{path.name}.',
                                     suffix='.tmp', delete=False) as handle:
        temp = Path(handle.name)
        handle.write(json.dumps(obj, ensure_ascii=False, indent=1) + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o644)
    os.replace(temp, path)


def parse_page_path(relative):
    """'Series/Series - 001 - Title/Series - 001 - p004 - Title.jpg' -> parts, or None."""
    parts = Path(relative).parts
    m = FILENAME.match(parts[-1])
    if len(parts) != 3 or not m or parts[0] != m['series'] \
            or not parts[1].startswith(f"{m['series']} - {m['chapter']} - "):
        return None
    start = int(m['start'])
    end = int(m['end']) if m['end'] else start
    return {'series': m['series'], 'chapter_number': int(m['chapter']), 'page_start': start,
            'page_end': end, 'chapter_dir': parts[1], 'chapter_title': parts[1].split(' - ', 2)[2]}


def list_images(root):
    images = []
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if path.is_file() and not any(p.startswith('.') for p in rel.parts) \
                and path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
            images.append(rel.as_posix())
    return sorted(images)


def name_aliases(name):
    """Alias candidates for later visibility checks: the full name plus name parts (>= 3 letters)."""
    tokens = [t for t in re.split(r"[^\w']+", name) if len(t) >= MIN_ALIAS_LEN]
    aliases = [name] + [t for t in tokens if t.casefold() != name.casefold()]
    return list(dict.fromkeys(aliases))


def build_page(rel, parsed, chapter_id, human_doc, magi_doc, report):
    page_label = f"p{parsed['page_start']:03d}" + (f"-{parsed['page_end']:03d}"
                                                   if parsed['page_end'] != parsed['page_start'] else '')
    page_id = f'{chapter_id}__{page_label}'
    magi = magi_doc['magi3']
    width, height = magi['_meta']['image_size']
    panels_raw = magi['panels']
    order = magi['reading_order']['panels'] if magi['reading_order'].get('status') == 'complete' \
        else list(range(len(panels_raw)))
    rank = {idx: r for r, idx in enumerate(order)}
    panels = [{'panel_id': f'{page_id}__panel{i:02d}', 'magi3_index': i, 'box': box,
               'reading_order': rank.get(i), 'source': 'model:magi3'} for i, box in enumerate(panels_raw)]
    sorted_panel_boxes = [panels_raw[i] for i in order]

    def panel_of(box):
        k = geometry.box_to_panel(box, sorted_panel_boxes)
        return panels[order[k]]['panel_id'] if k >= 0 else None

    record = {
        'schema': SCHEMA, 'page_id': page_id, 'chapter_id': chapter_id,
        'page_start': parsed['page_start'], 'page_end': parsed['page_end'],
        'is_spread': parsed['page_end'] != parsed['page_start'],
        'relative_path': rel, 'image_sha256': magi_doc['page']['image_sha256'],
        'width': width, 'height': height, 'has_ground_truth': human_doc is not None,
        'panels': panels,
    }
    if human_doc is None:
        report['pages_without_ground_truth'].append(page_id)
        record['characters'], record['texts'], record['tails'] = [], [], []
        record['model_only'] = {
            'note': 'no human annotation for this page; MAGI v3 predictions for context only',
            'characters': [{'box': b, 'panel_id': panel_of(b), 'page_cluster': c, 'source': 'model:magi3'}
                           for b, c in zip(magi['characters'], magi['character_cluster_labels'])],
            'texts': [{'box': b, 'panel_id': panel_of(b), 'source': 'model:magi3'} for b in magi['texts']],
        }
        record['reading_order'] = {'panels': [panels[i]['panel_id'] for i in order], 'texts': [],
                                   'method': 'MAGI v3 panel order'}
        return record
    human = human_doc['human']
    if [human_doc['page']['width'], human_doc['page']['height']] != [width, height]:
        raise ValueError(f'{rel}: human and MAGI v3 image sizes differ')
    if human_doc['page']['image_sha256'] != record['image_sha256']:
        raise ValueError(f'{rel}: human and MAGI v3 annotations refer to different images')
    record['split'] = human_doc['page']['split']
    speakers, tails_of = defaultdict(list), defaultdict(list)
    for t, c in human['text_character']:
        speakers[t].append(c)
    for t, tl in human['text_tail']:
        tails_of[t].append(tl)
    record['characters'] = [{
        'char_id': f"{page_id}__hchar{c['index']:02d}", 'human_index': c['index'], 'box': c['box'],
        'name': c['name'], 'named': c['named'], 'page_cluster': c['cluster'],
        'identity_id': None, 'panel_id': panel_of(c['box']), 'source': 'human'} for c in human['characters']]
    text_order = geometry.sort_boxes_in_reading_order([t['box'] for t in human['texts']], sorted_panel_boxes)
    text_rank = {idx: r for r, idx in enumerate(text_order)}
    record['texts'] = [{
        'text_id': f"{page_id}__htext{t['index']:02d}", 'human_index': t['index'], 'box': t['box'],
        'text_classification': t['text_classification'], 'panel_id': panel_of(t['box']),
        'reading_order': text_rank[t['index']],
        'speaker_char_ids': [f'{page_id}__hchar{c:02d}' for c in speakers[t['index']]],
        'tail_ids': [f'{page_id}__htail{tl:02d}' for tl in tails_of[t['index']]],
        'source': 'human (box, links); panel and order: MAGI v3 geometry'} for t in human['texts']]
    record['tails'] = [{'tail_id': f"{page_id}__htail{tl['index']:02d}", 'human_index': tl['index'],
                        'box': tl['box'], 'source': 'human'} for tl in human['tails']]
    record['reading_order'] = {
        'panels': [panels[i]['panel_id'] for i in order],
        'texts': [record['texts'][i]['text_id'] for i in text_order],
        'method': 'MAGI v3 panel order; human text boxes ordered with the MAGI v3 geometry rules (ported)'}
    if not panels:
        report['ground_truth_pages_without_panels'].append(page_id)
    return record


def build(args):
    report = defaultdict(list)
    images = list_images(args.images)
    chapters = defaultdict(list)
    for rel in images:
        parsed = parse_page_path(rel)
        if parsed is None:
            raise SystemExit(f'Unrecognized page file name: {rel}')
        chapters[(parsed['series'], parsed['chapter_number'])].append((rel, parsed))
    sources = {}
    pages, chapter_rows = [], []
    for (series, number), items in sorted(chapters.items()):
        items.sort(key=lambda x: (x[1]['page_start'], x[1]['page_end']))
        chapter_id = f'{slug(series)}__c{number:03d}'
        chapter_pages = []
        for order_index, (rel, parsed) in enumerate(items):
            magi_path = args.magi3 / (rel + '.json')
            human_path = args.human / (rel + '.json')
            if not magi_path.exists():
                raise SystemExit(f'Missing MAGI v3 annotation: {magi_path}')
            human_doc = json.loads(human_path.read_text()) if human_path.exists() else None
            page = build_page(rel, parsed, chapter_id, human_doc, json.loads(magi_path.read_text()), report)
            page['order_in_chapter'] = order_index
            page['sources'] = {'magi3': {'path': str(magi_path.relative_to(args.magi3)),
                                         'sha256': sha256_file(magi_path)}}
            if human_doc is not None:
                page['sources']['human'] = {'path': str(human_path.relative_to(args.human)),
                                            'sha256': sha256_file(human_path)}
            sources[rel] = page['sources']
            chapter_pages.append(page)
        splits = {p['split'] for p in chapter_pages if p['has_ground_truth']}
        if len(splits) != 1:
            raise SystemExit(f'{chapter_id}: expected one split, found {splits}')
        split = splits.pop()
        for p in chapter_pages:
            if not p['has_ground_truth']:
                p['split'], p['split_source'] = split, 'chapter'
            else:
                p['split_source'] = 'human'
        numbers = sorted({n for p in chapter_pages for n in range(p['page_start'], p['page_end'] + 1)})
        missing = sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
        chapter_rows.append({
            'schema': SCHEMA, 'chapter_id': chapter_id, 'series': series, 'series_slug': slug(series),
            'chapter_number': number, 'chapter_title': items[0][1]['chapter_title'],
            'chapter_dir': f"{series}/{items[0][1]['chapter_dir']}", 'split': split,
            'reading_direction': 'rtl', 'page_ids': [p['page_id'] for p in chapter_pages],
            'pages_with_ground_truth': [p['page_id'] for p in chapter_pages if p['has_ground_truth']],
            'pages_without_ground_truth': [p['page_id'] for p in chapter_pages if not p['has_ground_truth']],
            'missing_page_numbers': missing,
            'counts': {'pages': len(chapter_pages),
                       'ground_truth_pages': sum(p['has_ground_truth'] for p in chapter_pages),
                       'panels': sum(len(p['panels']) for p in chapter_pages),
                       'characters': sum(len(p['characters']) for p in chapter_pages),
                       'texts': sum(len(p['texts']) for p in chapter_pages)}})
        pages += chapter_pages

    # series-level identities (named) and page-level groups (unnamed)
    identities = {}
    series_of_chapter = {c['chapter_id']: c['series'] for c in chapter_rows}
    for page in pages:
        series = series_of_chapter[page['chapter_id']]
        for c in page['characters']:
            if c['named']:
                ident = f"{slug(series)}__{slug(c['name'])}"
                entry = identities.setdefault(ident, {
                    'schema': SCHEMA, 'identity_id': ident, 'kind': 'named', 'scope': 'series',
                    'series': series, 'name': c['name'],
                    'display_name': c['name'].title() if c['name'].isupper() else c['name'],
                    'appearances': defaultdict(list), 'source': 'derived from human names (exact match)'})
                if entry['name'] != c['name']:
                    raise SystemExit(f'identity slug collision: {entry["name"]!r} vs {c["name"]!r}')
            else:
                ident = f"{page['page_id']}__unnamed{c['page_cluster']}"
                entry = identities.setdefault(ident, {
                    'schema': SCHEMA, 'identity_id': ident, 'kind': 'unnamed', 'scope': 'page',
                    'series': series, 'name': None, 'display_name': None,
                    'appearances': defaultdict(list), 'source': 'human page-local cluster (name "none")'})
            c['identity_id'] = ident
            entry['appearances'][page['chapter_id']].append({'page_id': page['page_id'], 'char_id': c['char_id'],
                                                             'panel_id': c['panel_id']})
    alias_owners = defaultdict(set)
    for ident in identities.values():
        if ident['kind'] == 'named':
            ident['aliases'] = name_aliases(ident['name'])
            for alias in ident['aliases']:
                alias_owners[(ident['series'], alias.casefold())].add(ident['identity_id'])
    character_rows = []
    for ident in sorted(identities.values(), key=lambda x: x['identity_id']):
        if ident['kind'] == 'named':
            ident['aliases'] = [{'text': a, 'kind': 'full_name' if a == ident['name'] else 'name_part',
                                 'ambiguous': len(alias_owners[(ident['series'], a.casefold())]) > 1,
                                 'shared_with': sorted(alias_owners[(ident['series'], a.casefold())]
                                                       - {ident['identity_id']})} for a in ident['aliases']]
        apps = dict(ident['appearances'])
        ident['appearances'] = apps
        all_pages = [a['page_id'] for chapter in apps.values() for a in chapter]
        ident['counts'] = {'boxes': len(all_pages), 'pages': len(set(all_pages)), 'chapters': len(apps),
                           'pages_per_chapter': {k: len({a['page_id'] for a in v}) for k, v in apps.items()}}
        character_rows.append(ident)

    for page in pages:
        for c in page['characters']:
            if c['panel_id'] is None:
                report['characters_without_panel'].append(c['char_id'])
        for t in page['texts']:
            if t['panel_id'] is None:
                report['texts_without_panel'].append(t['text_id'])
    named = [r for r in character_rows if r['kind'] == 'named']
    summary = {
        'chapters': len(chapter_rows), 'pages': len(pages),
        'pages_with_ground_truth': sum(p['has_ground_truth'] for p in pages),
        'spreads': [p['page_id'] for p in pages if p['is_spread']],
        'panels': sum(len(p['panels']) for p in pages),
        'human_characters': sum(len(p['characters']) for p in pages),
        'human_texts': sum(len(p['texts']) for p in pages),
        'named_identities': len(named), 'unnamed_page_groups': len(character_rows) - len(named),
        'named_identities_in_both_chapters': sum(r['counts']['chapters'] > 1 for r in named),
        'ambiguous_name_parts': sorted({(r['series'], a['text']) for r in named for a in r['aliases']
                                        if a['ambiguous']}),
        'splits': dict(Counter(c['split'] for c in chapter_rows)),
    }
    return chapter_rows, pages, character_rows, summary, dict(report), sources


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--images', type=Path, required=True)
    p.add_argument('--human', type=Path, required=True)
    p.add_argument('--magi3', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True, help='parent folder; output goes to <out>/<version>')
    p.add_argument('--version', default='v1')
    args = p.parse_args(argv)
    for name in ('images', 'human', 'magi3', 'out'):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    target = args.out / args.version
    for name in ('images', 'human', 'magi3'):
        source = getattr(args, name)
        if target == source or source in target.parents or target in source.parents:
            p.error(f'output must be separate from --{name} (inputs are read-only)')
    if target.exists():
        log(f'{target} already exists; choose a new --version (outputs are never overwritten)')
        return 1
    chapters, pages, characters, summary, report, sources = build(args)
    partial = target.with_name(target.name + '.partial')
    partial.mkdir(parents=True, exist_ok=False)
    write_jsonl(partial / 'chapters.jsonl', chapters)
    write_jsonl(partial / 'pages.jsonl', pages)
    write_jsonl(partial / 'characters.jsonl', characters)
    write_json(partial / 'report.json', {'summary': summary, 'issues': report})
    write_json(partial / 'manifest.json', {
        'schema': SCHEMA, 'version': args.version, 'created_at': datetime.now(timezone.utc).isoformat(),
        'inputs': {'images': str(args.images), 'human': str(args.human), 'magi3': str(args.magi3)},
        'input_files_sha256': sources, 'summary': summary})
    partial.rename(target)
    log(json.dumps(summary, ensure_ascii=False, indent=1))
    log(f'Done: {target}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
