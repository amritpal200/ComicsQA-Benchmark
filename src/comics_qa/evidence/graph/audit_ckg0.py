"""CKG-0: read-only audit of core v1 and its human, MAGI and OCR sources (stdlib only).

Writes a new report directory, never graph facts or coverage certificates. All coverage
states are candidates under the explicit human-completeness assumption, not measured recall.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

CORE = Path(__file__).resolve().parents[2] / 'core'
sys.path.insert(0, str(CORE))
from build_core import parse_page_path, slug, write_json, write_jsonl  # noqa: E402
from geometry import area, intersection_area  # noqa: E402

SCHEMA = 'comics_qa.ckg0.v1'
HUMAN_FAMILIES = ('char_boxes', 'names', 'text_boxes', 'speaker_links')
FAMILIES = (*HUMAN_FAMILIES, 'panels', 'reading_order', 'ocr')
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def reject_constant(value):
    raise ValueError(f'Non-finite JSON constant: {value}')


def name_kind(name):
    if not isinstance(name, str) or not name.strip():
        return 'missing'
    value = name.strip().casefold()
    return 'generic' if value == 'none' or re.match(r'^unnamed(?:\s|$)', value) else 'named'


def valid_box(box):
    return (isinstance(box, list) and len(box) == 4
            and all(type(x) in (int, float) and math.isfinite(x) for x in box)
            and box[2] > box[0] and box[3] > box[1])


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError(f'Invalid relative path: {relative!r}')
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError(f'Path escapes input root: {relative!r}')
    return path


class Audit:
    def __init__(self, args):
        self.args = args
        self.issues = []
        self.inputs = {}
        self.names = {}
        self.classes = {}

    def issue(self, code, message, *, page=None, chapter=None, file=None, pointer='',
              families=(), severity='warning'):
        record = {'code': code, 'severity': severity, 'message': message,
                  'page_id': page, 'chapter_id': chapter, 'file': str(file) if file else None,
                  'pointer': pointer, 'families': list(families)}
        self.issues.append(record)

    def read(self, path, *, page=None, chapter=None, optional=False, jsonl=False):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.inputs[str(path)] = {'path': str(path), 'status': 'missing', 'sha256': None}
            if not optional:
                self.issue('missing_file', 'Expected input file is absent', page=page,
                           chapter=chapter, file=path, severity='error')
            return None
        except OSError as exc:
            self.inputs[str(path)] = {'path': str(path), 'status': 'unreadable', 'sha256': None}
            self.issue('unreadable_file', str(exc), page=page, chapter=chapter,
                       file=path, severity='error')
            return None
        self.inputs[str(path)] = {'path': str(path), 'status': 'read',
                                  'sha256': sha256(data), 'bytes': len(data)}
        try:
            if jsonl:
                rows = []
                for line_no, line in enumerate(data.decode('utf-8').splitlines(), 1):
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line, parse_constant=reject_constant)
                        if not isinstance(row, dict):
                            raise ValueError('Expected object')
                        rows.append(row)
                    except ValueError as exc:
                        self.issue('invalid_jsonl_row', str(exc), file=path,
                                   pointer=f'line:{line_no}', severity='error')
                return rows
            obj = json.loads(data, parse_constant=reject_constant)
            if not isinstance(obj, dict):
                raise ValueError('Expected JSON object')
            return obj
        except (ValueError, UnicodeError) as exc:
            self.inputs[str(path)]['status'] = 'invalid'
            self.issue('invalid_json', str(exc), page=page, chapter=chapter,
                       file=path, severity='error')
            return None

    def index(self, rows, key, path):
        result = {}
        for i, row in enumerate(rows or []):
            value = row.get(key)
            if not isinstance(value, str) or not value:
                self.issue('missing_id', f'Missing {key}', file=path, pointer=f'row:{i}', severity='error')
                continue
            if value in result:
                self.issue('duplicate_id', f'Duplicate {key}: {value}', file=path,
                           page=value if key == 'page_id' else None,
                           chapter=value if key == 'chapter_id' else None, severity='error')
            else:
                result[value] = row
            if row.get('schema') != 'comics_qa.core.v1':
                self.issue('core_schema', f'Unexpected core schema for {value}', file=path,
                           page=value if key == 'page_id' else None, severity='error')
        return result

    def source(self, kind, page):
        root = getattr(self.args, kind)
        pid, cid = page['page_id'], page['chapter_id']
        try:
            path = safe_path(root, page['relative_path'] + '.json')
        except (ValueError, KeyError, TypeError) as exc:
            self.issue('invalid_source_path', str(exc), page=pid, chapter=cid, severity='error')
            return None, None
        doc = self.read(path, page=pid, chapter=cid,
                        optional=(kind == 'human' and not page.get('has_ground_truth')) or kind == 'ocr')
        if doc is None:
            return None, path
        expected = {'human': 'comics_qa.human.v1', 'magi3': 'comics_qa.magi3.v1',
                    'ocr': 'comics_qa.ocr.v1'}[kind]
        if doc.get('schema') != expected:
            self.issue('source_schema', f'{kind}: expected {expected}', page=pid, chapter=cid,
                       file=path, pointer='/schema', severity='error')
            return None, path
        metadata = doc.get('page')
        if not isinstance(metadata, dict):
            self.issue('source_page_metadata', 'Missing page object', page=pid, chapter=cid,
                       file=path, pointer='/page', severity='error')
            return None, path
        if metadata.get('relative_path') != page.get('relative_path'):
            self.issue('source_relative_path', 'Source relative_path differs from core', page=pid,
                       chapter=cid, file=path, pointer='/page/relative_path', severity='error')
        if not page.get('image_sha256') or metadata.get('image_sha256') != page['image_sha256']:
            self.issue('source_image_hash', 'Source and core refer to different/missing image hashes',
                       page=pid, chapter=cid, file=path, pointer='/page/image_sha256', severity='error')
        if kind in ('human', 'magi3'):
            if kind == 'human' and any(metadata.get(k) != page.get(k) for k in ('width', 'height')):
                self.issue('human_dimensions', 'Human/core image dimensions differ', page=pid,
                           chapter=cid, file=path, severity='error')
            expected_source = page.get('sources', {}).get(kind, {})
            if expected_source.get('sha256') != self.inputs[str(path)]['sha256']:
                self.issue('stale_core_source', f'Core {kind} checksum differs from current source',
                           page=pid, chapter=cid, file=path, severity='error')
            if expected_source.get('path') != page['relative_path'] + '.json':
                self.issue('core_source_path', f'Unexpected core {kind} source pointer', page=pid,
                           chapter=cid, file=path, severity='error')
        return doc, path

    def check_page(self, page, identities, series):
        pid, cid = page['page_id'], page['chapter_id']
        start = len(self.issues)
        row = {'page_id': pid, 'chapter_id': cid, 'relative_path': page.get('relative_path'),
               'has_ground_truth': page.get('has_ground_truth'), 'counts': {}, 'sources': {},
               'candidate_coverage': {}, 'text_classes': {}, 'ocr_statuses': {}}
        try:
            image = safe_path(self.args.images, page['relative_path'])
            if not image.is_file():
                self.issue('missing_image', 'Image is absent', page=pid, chapter=cid,
                           file=image, families=FAMILIES, severity='error')
            elif self.args.verify_images:
                actual = sha256(image.read_bytes())
                self.inputs[str(image)] = {'path': str(image), 'status': 'read', 'sha256': actual}
                if actual != page.get('image_sha256'):
                    self.issue('image_checksum', 'Image bytes differ from core hash', page=pid,
                               chapter=cid, file=image, families=FAMILIES, severity='error')
        except (KeyError, ValueError, TypeError, OSError) as exc:
            self.issue('image_path', str(exc), page=pid, chapter=cid, families=FAMILIES, severity='error')
        docs, paths = {}, {}
        for kind in ('human', 'magi3', 'ocr'):
            docs[kind], paths[kind] = self.source(kind, page)
            record = self.inputs.get(str(paths[kind]), {})
            row['sources'][kind] = {'path': str(paths[kind]) if paths[kind] else None,
                                    'status': record.get('status', 'invalid'),
                                    'sha256': record.get('sha256')}
        human_present = docs['human'] is not None
        if human_present != bool(page.get('has_ground_truth')):
            self.issue('human_presence_mismatch', 'Human source availability differs from core GT flag',
                       page=pid, chapter=cid, file=paths['human'], families=HUMAN_FAMILIES,
                       severity='error')
        for family in HUMAN_FAMILIES:
            truly_absent = (not page.get('has_ground_truth')
                            and row['sources']['human']['status'] == 'missing')
            row['candidate_coverage'][family] = 'absent' if truly_absent else (
                'closed_assumed' if human_present else 'open')
        for family, kind in (('panels', 'magi3'), ('reading_order', 'magi3'), ('ocr', 'ocr')):
            row['candidate_coverage'][family] = 'absent' if row['sources'][kind]['status'] == 'missing' else 'open'
        # An artifact can be well-formed while its source provenance is invalid.
        for issue in self.issues[start:]:
            if issue['severity'] == 'error' and not issue['families']:
                kind = next((k for k, p in paths.items() if str(p) == issue['file']), None)
                issue['families'] = list(HUMAN_FAMILIES if kind == 'human' else
                                         ('panels', 'reading_order') if kind == 'magi3' else
                                         ('ocr',) if kind == 'ocr' else FAMILIES)
        try:
            human = docs['human']['human'] if human_present else None
            magi = docs['magi3']['magi3'] if docs['magi3'] else None
            if human is not None:
                self.check_human(page, human, paths['human'], identities, series, row)
            if magi is not None:
                self.check_magi(page, magi, paths['magi3'], human, row)
            self.check_ocr(page, docs['ocr'], paths['ocr'], human, magi, row)
        except (KeyError, TypeError, ValueError, IndexError, AttributeError) as exc:
            # Malformed source pages must appear in the report, never disappear from denominators.
            self.issue('malformed_page', f'{type(exc).__name__}: {exc}', page=pid, chapter=cid,
                       families=FAMILIES, severity='error')
        row['issue_codes'] = []
        for issue in self.issues[start:]:
            row['issue_codes'].append(issue['code'])
            for family in issue['families']:
                if row['candidate_coverage'].get(family) != 'absent':
                    row['candidate_coverage'][family] = 'open'
        row['issue_codes'] = sorted(set(row['issue_codes']))
        return row

    def check_human(self, page, human, path, identities, series, row):
        pid, cid = page['page_id'], page['chapter_id']

        def flag(code, message, pointer='', families=HUMAN_FAMILIES, severity='warning'):
            self.issue(code, message, page=pid, chapter=cid, file=path, pointer=pointer,
                       families=families, severity=severity)

        lists = {}
        for key, families in [('characters', ('char_boxes', 'names', 'speaker_links')),
                              ('texts', ('text_boxes', 'speaker_links')),
                              ('tails', ('speaker_links',)), ('panels_proxy', ())]:
            records = human[key]
            if not isinstance(records, list):
                raise ValueError(f'human.{key} must be an array')
            lists[key] = records
            row['counts']['human_' + key] = len(records)
            for i, record in enumerate(records):
                pointer = f'/human/{key}/{i}'
                if record['index'] != i or type(record['index']) is not int:
                    flag('human_index', 'Index must equal category-array position', pointer, families, 'error')
                self.check_box(record['box'], page, path, pointer + '/box', families)
        chars, texts, tails = lists['characters'], lists['texts'], lists['tails']
        text_ids = [f'{pid}__htext{i:02d}' for i in range(len(texts))]
        declared_order = page.get('reading_order', {}).get('texts', [])
        if sorted(declared_order) != sorted(text_ids):
            flag('invalid_core_text_order', 'Text reading order must contain each human text once',
                 families=('reading_order',), severity='error')
        for i, tail in enumerate(tails):
            core_tail = page['tails'][i] if i < len(page['tails']) else {}
            if core_tail.get('tail_id') != f'{pid}__htail{i:02d}' or core_tail.get('box') != tail['box']:
                flag('core_tail_mismatch', 'Core tail differs from human source',
                     f'/human/tails/{i}', ('speaker_links',), 'error')
        if not chars:
            flag('no_human_characters', 'No character boxes; inspect whether the page is truly character-free',
                 '/human/characters', ('char_boxes', 'names', 'speaker_links'))
        speakers = self.links(human['text_character'], len(texts), len(chars), flag, 'text_character')
        tail_links = self.links(human['text_tail'], len(texts), len(tails), flag, 'text_tail')
        row['counts'].update(texts_with_speaker=sum(bool(speakers[i]) for i in range(len(texts))),
                             texts_without_speaker=sum(not speakers[i] for i in range(len(texts))),
                             texts_with_multiple_speakers=sum(len(speakers[i]) > 1 for i in range(len(texts))),
                             texts_with_tail=sum(bool(tail_links[i]) for i in range(len(texts))))
        if texts and not any(speakers.values()):
            flag('text_without_any_speaker_links',
                 'Text exists but no speaker links; may be narration/title, requires review',
                 '/human/text_character', ('speaker_links',))
        clusters = defaultdict(set)
        core_chars = page['characters']
        if len(core_chars) != len(chars) or len(page['texts']) != len(texts) or len(page['tails']) != len(tails):
            flag('core_human_counts', 'Core and human category lengths differ', severity='error')
        for i, char in enumerate(chars):
            name, cluster = char['name'], char['cluster']
            kind = name_kind(name)
            if type(cluster) is not int:
                flag('invalid_cluster', 'Page-local cluster must be an integer', f'/human/characters/{i}',
                     ('names', 'speaker_links'), 'error')
            else:
                clusters[cluster].add(name if isinstance(name, str) else '')
            if kind == 'missing':
                flag('empty_character_name', 'Missing/empty name', f'/human/characters/{i}/name',
                     ('names', 'speaker_links'))
                name = ''
            if char.get('named') != (kind == 'named'):
                flag('generic_policy_mismatch', 'Stored named flag differs from none/Unnamed policy',
                     f'/human/characters/{i}/named', ('names', 'speaker_links'))
            cid_expected = f'{pid}__hchar{i:02d}'
            core_char = core_chars[i] if i < len(core_chars) else {}
            expected_identity = f'{slug(series)}__{slug(name)}' if kind == 'named' else f'{pid}__unnamed{cluster}'
            if (core_char.get('char_id') != cid_expected or core_char.get('name') != char['name']
                    or core_char.get('box') != char['box'] or core_char.get('page_cluster') != cluster):
                flag('core_character_mismatch', 'Core appearance differs from human source',
                     f'/human/characters/{i}', ('char_boxes', 'names', 'speaker_links'), 'error')
            identity_id = core_char.get('identity_id')
            ident = identities.get(identity_id)
            if identity_id != expected_identity or ident is None:
                flag('identity_reference', f'Expected identity {expected_identity}; got {identity_id}',
                     f'/human/characters/{i}', ('names', 'speaker_links'), 'error')
            elif ((kind == 'named' and (ident.get('name') != name or ident.get('series') != series
                                       or ident.get('scope') != 'series' or ident.get('kind') != 'named'))
                  or (kind != 'named' and (ident.get('scope') != 'page' or ident.get('kind') != 'unnamed'))):
                flag('identity_metadata', 'Identity metadata violates exact-name/page-local policy',
                     f'/human/characters/{i}', ('names', 'speaker_links'), 'error')
            if ident is not None:
                matches = [a for a in ident.get('appearances', {}).get(cid, [])
                           if a.get('char_id') == cid_expected and a.get('page_id') == pid]
                if len(matches) != 1:
                    flag('identity_appearance', 'Identity must contain this appearance exactly once',
                         f'/human/characters/{i}', ('names', 'speaker_links'), 'error')
            key = (series, name)
            entry = self.names.setdefault(key, {'series': series, 'name': name, 'kind': kind,
                'boxes': 0, 'pages': set(), 'chapters': set(), 'identity_ids': set(),
                'examples': [], 'aliases': ident.get('aliases', []) if ident else []})
            entry['boxes'] += 1
            entry['pages'].add(pid)
            entry['chapters'].add(cid)
            if identity_id:
                entry['identity_ids'].add(identity_id)
            if len(entry['examples']) < self.args.examples:
                entry['examples'].append({'page_id': pid, 'char_id': cid_expected,
                                          'file': str(path), 'pointer': f'/human/characters/{i}'})
        for cluster, names in clusters.items():
            if len(names) > 1:
                flag('cluster_name_conflict', f'Cluster {cluster} has names {sorted(names)}',
                     '/human/characters', ('names', 'speaker_links'))
        per_class = defaultdict(Counter)
        for i, text in enumerate(texts):
            pointer = f'/human/texts/{i}'
            cls = text['text_classification']
            if type(cls) is not int or cls not in (0, 1):
                flag('unexpected_text_class', f'Raw text class {cls!r}; semantics unverified', pointer,
                     ('text_boxes', 'speaker_links'))
            if tail_links[i] and not speakers[i]:
                flag('tail_without_speaker', 'Text has a human tail link but no speaker', pointer,
                     ('speaker_links',))
            if len(speakers[i]) > 1:
                flag('multiple_speakers', 'Text links to multiple character appearances', pointer,
                     ('speaker_links',))
            if i < len(page['texts']):
                ct = page['texts'][i]
                if (ct.get('text_id') != f'{pid}__htext{i:02d}' or ct.get('box') != text['box']
                        or ct.get('text_classification') != cls
                        or sorted(ct.get('speaker_char_ids', [])) != sorted(f'{pid}__hchar{c:02d}' for c in speakers[i])
                        or sorted(ct.get('tail_ids', [])) != sorted(f'{pid}__htail{t:02d}' for t in tail_links[i])):
                    flag('core_text_mismatch', 'Core text/links differ from human source', pointer,
                         ('text_boxes', 'speaker_links'), 'error')
            stats = per_class[str(cls)]
            stats['texts'] += 1
            stats['with_speaker'] += bool(speakers[i])
            stats['with_tail'] += bool(tail_links[i])
        row['text_classes'] = {k: dict(v) for k, v in sorted(per_class.items())}

    def links(self, pairs, left_count, right_count, flag, key):
        if not isinstance(pairs, list):
            raise ValueError(f'human.{key} must be an array')
        result = defaultdict(set)
        for i, pair in enumerate(pairs):
            if (not isinstance(pair, list) or len(pair) != 2 or any(type(x) is not int for x in pair)
                    or not 0 <= pair[0] < left_count or not 0 <= pair[1] < right_count):
                flag('invalid_human_link', f'Invalid [text, target] pair {pair!r}',
                     f'/human/{key}/{i}', ('speaker_links',), 'error')
                continue
            if pair[1] in result[pair[0]]:
                flag('duplicate_human_link', f'Duplicate link {pair}', f'/human/{key}/{i}',
                     ('speaker_links',))
            result[pair[0]].add(pair[1])
        return result

    def check_box(self, box, page, path, pointer, families):
        if not valid_box(box):
            self.issue('invalid_box', f'Non-finite, reversed or empty box: {box!r}', page=page['page_id'],
                       chapter=page['chapter_id'], file=path, pointer=pointer, families=families, severity='error')
            return
        tol = self.args.box_tolerance
        if box[0] < -tol or box[1] < -tol or box[2] > page['width'] + tol or box[3] > page['height'] + tol:
            self.issue('box_outside_image', 'Box extends beyond original raster (including tolerance)',
                       page=page['page_id'], chapter=page['chapter_id'], file=path,
                       pointer=pointer, families=families)

    def check_magi(self, page, magi, path, human, row):
        panels = magi['panels']
        if not isinstance(panels, list):
            raise ValueError('magi3.panels must be an array')
        pid, cid = page['page_id'], page['chapter_id']
        row['counts']['magi_panels'] = len(panels)
        if magi['_meta'].get('status') != 'complete':
            self.issue('magi_incomplete', 'MAGI status is not complete', page=pid, chapter=cid,
                       file=path, pointer='/magi3/_meta/status', families=('panels', 'reading_order'))
        if magi['_meta'].get('image_size') != [page['width'], page['height']]:
            self.issue('magi_dimensions', 'MAGI/core image dimensions differ', page=pid, chapter=cid,
                       file=path, families=('panels', 'reading_order'), severity='error')
        if not panels:
            self.issue('no_magi_panels', 'No MAGI panels detected', page=pid, chapter=cid,
                       file=path, families=('panels', 'reading_order'))
        for i, box in enumerate(panels):
            self.check_box(box, page, path, f'/magi3/panels/{i}', ('panels', 'reading_order'))
        order = magi['reading_order']
        indices = order.get('panels')
        if (order.get('status') != 'complete' or not isinstance(indices, list)
                or any(type(i) is not int for i in indices) or sorted(indices) != list(range(len(panels)))):
            self.issue('invalid_panel_order', 'Panel order is not a complete permutation', page=pid,
                       chapter=cid, file=path, families=('reading_order',), severity='error')
        if [p['box'] for p in page['panels']] != panels:
            self.issue('core_panel_mismatch', 'Core panel boxes differ from MAGI', page=pid,
                       chapter=cid, file=path, families=('panels', 'reading_order'), severity='error')
        if isinstance(indices, list) and all(type(i) is int for i in indices):
            expected = [f'{pid}__panel{i:02d}' for i in indices]
            if page['reading_order']['panels'] != expected:
                self.issue('core_panel_order', 'Core panel order differs from MAGI', page=pid,
                           chapter=cid, file=path, families=('reading_order',), severity='error')
        valid = [b for b in panels if valid_box(b)]
        if human:
            for key in ('characters', 'texts'):
                unsupported, ambiguous = [], []
                for i, rec in enumerate(human[key]):
                    box = rec['box']
                    if not valid_box(box):
                        continue
                    fractions = sorted((intersection_area(box, b) / area(box) for b in valid), reverse=True)
                    if not fractions or fractions[0] < self.args.panel_min_fraction:
                        unsupported.append(i)
                    if len(fractions) > 1 and fractions[1] >= self.args.panel_ambiguous_fraction:
                        ambiguous.append(i)
                row['counts'][key + '_weak_panel_membership'] = len(unsupported)
                row['counts'][key + '_ambiguous_panel_membership'] = len(ambiguous)
                if unsupported or ambiguous:
                    self.issue('panel_membership_review',
                               f'{key}: weak overlap indices={unsupported}, ambiguous indices={ambiguous}',
                               page=pid, chapter=cid, file=path, families=('panels',), severity='warning')

    def check_ocr(self, page, doc, path, human, magi, row):
        pid, cid = page['page_id'], page['chapter_id']
        if doc is None:
            self.issue('ocr_unavailable', 'OCR artifact unavailable; no transcript reliability claim',
                       page=pid, chapter=cid, file=path, families=('ocr',))
            return
        ocr = doc['ocr']
        expected = [t['box'] for t in human['texts']] if human is not None else (magi['texts'] if magi else None)
        expected_source = 'human' if human is not None else 'model:magi3'
        if ocr.get('boxes_source') != expected_source:
            self.issue('ocr_boxes_source', f'Expected boxes_source={expected_source}', page=pid,
                       chapter=cid, file=path, families=('ocr',), severity='error')
        if ocr['_meta'].get('status') != 'complete':
            self.issue('ocr_incomplete', 'OCR page not marked complete', page=pid, chapter=cid,
                       file=path, families=('ocr',))
        entries = ocr['texts']
        if not isinstance(entries, list):
            raise ValueError('ocr.texts must be an array')
        by_index, statuses = {}, Counter()
        for i, text in enumerate(entries):
            index = text.get('index')
            if type(index) is not int or index in by_index:
                self.issue('ocr_index', f'Invalid/duplicate text index {index!r}', page=pid,
                           chapter=cid, file=path, pointer=f'/ocr/texts/{i}', families=('ocr',), severity='error')
                continue
            by_index[index] = text
            status = text.get('status', 'missing_status')
            statuses[str(status)] += 1
            if (status != 'ok' or text.get('truncated')
                    or not isinstance(text.get('text_normalized'), str) or not text['text_normalized'].strip()):
                self.issue('ocr_text_review', f'OCR status={status}, truncated={text.get("truncated")}',
                           page=pid, chapter=cid, file=path, pointer=f'/ocr/texts/{i}', families=('ocr',))
        if expected is None or set(by_index) != set(range(len(expected))):
            self.issue('ocr_text_coverage', 'OCR indices do not cover the source text boxes exactly',
                       page=pid, chapter=cid, file=path, families=('ocr',), severity='error')
        if expected is not None:
            for index, text in by_index.items():
                if not 0 <= index < len(expected) or text.get('box') != expected[index]:
                    self.issue('ocr_box_mismatch', f'OCR box {index} differs from source', page=pid,
                               chapter=cid, file=path, families=('ocr',), severity='error')
        row['ocr_statuses'] = dict(sorted(statuses.items()))
        row['counts']['ocr_texts'] = len(entries)
        if human:
            for i, text in enumerate(human['texts']):
                cls = str(text['text_classification'])
                entry = self.classes.setdefault(cls, {'raw_class': cls, 'semantics': 'unverified',
                                                      'examples': []})
                if len(entry['examples']) < self.args.examples:
                    transcript = by_index.get(i, {})
                    entry['examples'].append({'page_id': pid, 'text_id': f'{pid}__htext{i:02d}',
                        'human_file': str(self.args.human / (page['relative_path'] + '.json')),
                        'pointer': f'/human/texts/{i}', 'ocr_status': transcript.get('status'),
                        'ocr_excerpt': str(transcript.get('text_normalized', ''))[:240]})


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ('core', 'images', 'human', 'magi3', 'ocr', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--chapter', action='append', default=[], help='Exact core chapter ID; repeatable')
    parser.add_argument('--limit-pages', type=int, help='Smoke test only; report explicitly marked partial')
    parser.add_argument('--verify-images', action='store_true', help='Also hash image bytes (slower)')
    parser.add_argument('--examples', type=int, default=5, help='Maximum examples per name/text class')
    parser.add_argument('--box-tolerance', type=float, default=1.0, help='Raster boundary tolerance in pixels')
    parser.add_argument('--panel-min-fraction', type=float, default=0.6)
    parser.add_argument('--panel-ambiguous-fraction', type=float, default=0.3)
    args = parser.parse_args(argv)
    for name in ('core', 'images', 'human', 'magi3', 'ocr', 'out'):
        setattr(args, name, getattr(args, name).expanduser().resolve())
    if args.limit_pages is not None and args.limit_pages < 1 or args.examples < 1:
        parser.error('--limit-pages and --examples must be positive')
    if not math.isfinite(args.box_tolerance) or args.box_tolerance < 0:
        parser.error('--box-tolerance must be finite and nonnegative')
    if not 0 < args.panel_ambiguous_fraction <= args.panel_min_fraction <= 1:
        parser.error('panel fractions must satisfy 0 < ambiguous <= min <= 1')
    for name in ('core', 'images', 'human', 'magi3', 'ocr'):
        source = getattr(args, name)
        for target in (args.out, args.out.with_name(args.out.name + '.partial')):
            if target == source or source in target.parents or target in source.parents:
                parser.error(f'Output must be separate from --{name} (sources are read-only)')
    for name in ('core', 'images', 'human', 'magi3'):
        if not getattr(args, name).is_dir():
            parser.error(f'--{name} directory is missing')
    if args.out.exists() or args.out.with_name(args.out.name + '.partial').exists():
        parser.error('Output or .partial already exists; inspect it and choose a new --out')
    return args


def audit(args):
    a = Audit(args)
    chapters = a.index(a.read(args.core / 'chapters.jsonl', jsonl=True), 'chapter_id', args.core / 'chapters.jsonl')
    pages = a.index(a.read(args.core / 'pages.jsonl', jsonl=True), 'page_id', args.core / 'pages.jsonl')
    identities = a.index(a.read(args.core / 'characters.jsonl', jsonl=True), 'identity_id', args.core / 'characters.jsonl')
    manifest = a.read(args.core / 'manifest.json')
    if not chapters or not pages or manifest is None:
        raise ValueError('Core indexes/manifest are missing or empty; a core v1 export is required')
    if manifest.get('schema') != 'comics_qa.core.v1':
        a.issue('manifest_schema', 'Unexpected core manifest schema', severity='error')
    for p in pages.values():
        if p.get('chapter_id') not in chapters:
            a.issue('orphan_page', 'Page refers to an absent chapter', page=p['page_id'], severity='error')
        if manifest.get('input_files_sha256', {}).get(p.get('relative_path')) != p.get('sources'):
            a.issue('manifest_source_mismatch', 'Core manifest and page source records differ',
                    page=p['page_id'], chapter=p.get('chapter_id'), severity='error')
    unknown = set(args.chapter) - chapters.keys()
    if unknown:
        raise ValueError(f'Unknown --chapter IDs: {sorted(unknown)}')
    selected_chapters = [c for k, c in sorted(chapters.items()) if not args.chapter or k in args.chapter]
    selected_ids = {c['chapter_id'] for c in selected_chapters}
    selected = [p for p in pages.values() if p.get('chapter_id') in selected_ids]
    selected.sort(key=lambda p: (p['chapter_id'], p.get('order_in_chapter', -1), p['page_id']))
    if args.limit_pages:
        selected = selected[:args.limit_pages]
    visited = {p['page_id'] for p in selected}
    # Audit ordering and membership against the full core chapter, even for a limited source smoke test.
    chapter_reports = []
    for chapter in selected_chapters:
        cid = chapter['chapter_id']
        cp = [p for p in pages.values() if p.get('chapter_id') == cid]
        ids = chapter['page_ids']
        local_issues = len(a.issues)

        def flag(code, message, pointer=''):
            a.issue(code, message, chapter=cid, file=args.core / 'chapters.jsonl', pointer=pointer, severity='error')

        if len(set(ids)) != len(ids) or set(ids) != {p['page_id'] for p in cp}:
            flag('chapter_membership', 'Chapter page_ids and page records differ or repeat')
        ordered = sorted(cp, key=lambda p: (p['page_start'], p['page_end'], p['page_id']))
        if ids != [p['page_id'] for p in ordered]:
            flag('chapter_page_order', 'Declared order differs from numeric page/spread order')
        covered = Counter()
        expected_paths = set()
        for i, p in enumerate(ordered):
            expected_paths.add(p.get('relative_path'))
            parsed = parse_page_path(p['relative_path'])
            label = f"p{p['page_start']:03d}" + (f"-{p['page_end']:03d}" if p['page_start'] != p['page_end'] else '')
            if (parsed is None or p['page_id'] != f'{cid}__{label}'
                    or parsed['page_start'] != p['page_start'] or parsed['page_end'] != p['page_end']
                    or f"{slug(parsed['series'])}__c{parsed['chapter_number']:03d}" != cid):
                flag('filename_identity', f'Filename/core ID mismatch: {p["page_id"]}')
            if p.get('order_in_chapter') != i or p.get('split') != chapter['split']:
                flag('page_rank_or_split', f'Incorrect rank/split: {p["page_id"]}')
            if p['page_end'] < p['page_start']:
                flag('invalid_page_span', p['page_id'])
            covered.update(range(p['page_start'], p['page_end'] + 1))
        gaps = sorted(set(range(min(covered), max(covered) + 1)) - covered.keys()) if covered else []
        overlaps = sorted(n for n, count in covered.items() if count > 1)
        if gaps:
            flag('missing_page_numbers', f'Internal page-number gaps: {gaps}')
        if overlaps:
            flag('overlapping_page_spans', f'Page spans overlap: {overlaps}')
        if chapter.get('missing_page_numbers') != gaps:
            flag('stale_gap_report', 'Stored missing-page list differs from computed gaps')
        for field, gt in [('pages_with_ground_truth', True), ('pages_without_ground_truth', False)]:
            if chapter.get(field) != [p['page_id'] for p in ordered if p.get('has_ground_truth') == gt]:
                flag('chapter_gt_lists', f'{field} differs from page records')
        try:
            folder = safe_path(args.images, chapter['chapter_dir'])
            actual = {p.relative_to(args.images).as_posix() for p in folder.rglob('*')
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
                      and not any(part.startswith('.') for part in p.relative_to(folder).parts)}
            extra = sorted(actual - expected_paths)
            missing = sorted(expected_paths - actual)
            if extra or missing:
                flag('image_inventory', f'Extra images={extra}; missing images={missing}')
        except (ValueError, KeyError, OSError) as exc:
            extra, missing = [], []
            flag('chapter_image_directory', str(exc))
        chapter_reports.append({'chapter_id': cid, 'series': chapter['series'], 'split': chapter['split'],
            'page_ids': ids, 'pages_total': len(cp), 'pages_audited': sum(p['page_id'] in visited for p in cp),
            'pages_with_ground_truth': sum(bool(p.get('has_ground_truth')) for p in cp),
            'missing_page_numbers': gaps, 'overlapping_page_numbers': overlaps,
            'extra_images': extra, 'missing_images': missing,
            'structure_ok': len(a.issues) == local_issues})
    series = {c['chapter_id']: c['series'] for c in selected_chapters}
    page_reports = []
    for i, p in enumerate(selected, 1):
        page_reports.append(a.check_page(p, identities, series[p['chapter_id']]))
        if i % 100 == 0 or i == len(selected):
            print(f'Audited {i}/{len(selected)} pages', file=sys.stderr, flush=True)
    # Neighbor count drops are review flags, not proof of missed detections.
    by_id = {p['page_id']: p for p in page_reports}
    for chapter in chapter_reports:
        ids = chapter['page_ids']
        for i in range(1, len(ids) - 1):
            triplet = [by_id.get(k) for k in ids[i - 1:i + 2]]
            if any(p is None or not p['has_ground_truth'] for p in triplet):
                continue
            counts = [p['counts'].get('human_characters', 0) for p in triplet]
            if min(counts[0], counts[2]) >= 4 and counts[1] < min(counts[0], counts[2]) / 4:
                middle = triplet[1]
                a.issue('neighbor_character_drop', f'Character counts on adjacent pages: {counts}',
                        page=middle['page_id'], chapter=chapter['chapter_id'],
                        file=args.core / 'pages.jsonl', families=('char_boxes', 'names', 'speaker_links'))
                middle['issue_codes'] = sorted(set(middle['issue_codes']) | {'neighbor_character_drop'})
                for family in ('char_boxes', 'names', 'speaker_links'):
                    middle['candidate_coverage'][family] = 'open'
        audited = [by_id[k] for k in ids if k in by_id]
        chapter['coverage'] = {family: dict(Counter(p['candidate_coverage'][family] for p in audited))
                               for family in FAMILIES}
        chapter['full_chapter_candidate_closed'] = {
            family: chapter['structure_ok'] and len(audited) == chapter['pages_total']
            and bool(audited) and all(p['candidate_coverage'][family] == 'closed_assumed' for p in audited)
            for family in HUMAN_FAMILIES}
    names = []
    for entry in sorted(a.names.values(), key=lambda x: (x['series'], x['name'])):
        names.append({**entry, **{k: sorted(entry[k]) for k in ('pages', 'chapters', 'identity_ids')}})
    # Detect distinct exact names that normalize to the same core slug; never merge them.
    slug_groups = defaultdict(list)
    for entry in names:
        if entry['kind'] == 'named':
            slug_groups[(entry['series'], slug(entry['name']))].append(entry['name'])
    for (s, key), values in slug_groups.items():
        if len(values) > 1:
            a.issue('name_slug_collision', f'{s}/{key}: {values}', families=('names',), severity='error')
    # Global integrity failures must never produce apparently usable chapter certificates.
    # Conservative: any integrity error blocks all selected chapters until reviewed.
    integrity_ok = not any(issue['severity'] == 'error' for issue in a.issues)
    if not integrity_ok:
        for chapter in chapter_reports:
            chapter['full_chapter_candidate_closed'] = dict.fromkeys(HUMAN_FAMILIES, False)
    classes = defaultdict(Counter)
    totals, ocr_statuses = Counter(), Counter()
    for p in page_reports:
        totals.update(p['counts'])
        ocr_statuses.update(p['ocr_statuses'])
        for key, values in p['text_classes'].items():
            classes[key].update(values)
    class_rows = [{**a.classes.get(key, {'raw_class': key, 'semantics': 'unverified', 'examples': []}),
                   'counts': dict(stats)} for key, stats in sorted(classes.items())]
    report = {'schema': SCHEMA, 'scope': 'sample' if args.chapter or args.limit_pages else 'full_collection',
        'chapters_selected': len(chapter_reports), 'pages_audited': len(page_reports),
        'integrity_ok': integrity_ok,
        'pages_with_ground_truth': sum(bool(p['has_ground_truth']) for p in page_reports),
        'pages_without_ground_truth': sum(not p['has_ground_truth'] for p in page_reports),
        'pages_in_core': len(pages), 'counts': dict(totals), 'ocr_statuses': dict(ocr_statuses),
        'coverage': {f: dict(Counter(p['candidate_coverage'][f] for p in page_reports)) for f in FAMILIES},
        'name_counts': dict(Counter(n['kind'] for n in names)),
        'issues_by_code': dict(sorted(Counter(x['code'] for x in a.issues).items())),
        'issues_by_severity': dict(Counter(x['severity'] for x in a.issues)),
        'full_chapters_candidate_closed': {f: sum(c['full_chapter_candidate_closed'][f] for c in chapter_reports)
                                            for f in HUMAN_FAMILIES},
        'policy': {'human_coverage': 'closed_assumed unless flagged; absent on unannotated pages',
                   'model_coverage': 'open; no automatic trust promotion or recall estimate',
                   'text_class_semantics': 'unverified; correlations are evidence for review only',
                   'unlinked_text': 'not automatically dialogue; tails/no-link pages trigger review',
                   'identity': 'exact name within series; none/Unnamed are generic; core IDs preserved',
                   'depth': 'excluded', 'image_check': 'sha256' if args.verify_images else 'existence only'},
        'limitations': ['Candidate coverage is not a graph certificate or measured visual completeness.',
                       'OCR agreement/name visibility and panel visual precision are not established by this audit.',
                       'No graph, interpreter or questions are generated.']}
    return a, report, page_reports, chapter_reports, names, class_rows


def markdown(report, chapters, classes):
    lines = ['# CKG-0 audit', '', f"Scope: **{report['scope']}**. Audited {report['pages_audited']} pages "
             f"in {report['chapters_selected']} selected chapters.", '',
             'Human completeness is assumed, not measured. Flags require review; model sources stay open.',
             'Depth is excluded. Raw text-class semantics remain unverified.', '', '## Counts', '',
             '| Measurement | Count |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in sorted(report['counts'].items())]
    lines += ['', '## Candidate coverage', '', '| Family | closed_assumed | open | absent |', '|---|---:|---:|---:|']
    lines += [f"| {f} | {c.get('closed_assumed', 0)} | {c.get('open', 0)} | {c.get('absent', 0)} |"
              for f, c in report['coverage'].items()]
    lines += ['', '## Whole-chapter exact-query prerequisites', '',
              'A chapter qualifies only when all its pages were audited, structure checks pass, every page is closed_assumed for the family, and the audit has no integrity errors.',
              '', '| Chapter | Audited/total | Character boxes | Speaker links |', '|---|---:|---|---|']
    lines += [f"| {c['chapter_id']} | {c['pages_audited']}/{c['pages_total']} | "
              f"{c['full_chapter_candidate_closed']['char_boxes']} | {c['full_chapter_candidate_closed']['speaker_links']} |"
              for c in chapters]
    lines += ['', '## Raw text-class evidence (no semantic mapping)', '',
              '| Raw class | Texts | With speaker | With tail |', '|---|---:|---:|---:|']
    lines += [f"| {c['raw_class']} | {c['counts'].get('texts', 0)} | "
              f"{c['counts'].get('with_speaker', 0)} | {c['counts'].get('with_tail', 0)} |" for c in classes]
    lines += ['', 'OCR status counts: ' + json.dumps(report['ocr_statuses'], sort_keys=True), '',
              '## Findings', '', '| Code | Count |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in report['issues_by_code'].items()]
    lines += ['', 'See issues.jsonl for page IDs and source pointers, names.jsonl for identities and aliases,',
              'text_classes.jsonl for review examples, and inputs.jsonl for every consumed file checksum.', '',
              '## Before CKG-1', '',
              '- Resolve integrity errors and inspect coverage flags; preserve absent pages in chapter context.',
              '- Verify text-class meaning from source documentation or manual examples.',
              '- Review OCR truncation/empty results before quote or name-visibility tasks.',
              '- Model panel/order/OCR outputs still require their own reliability checks.', '']
    return '\n'.join(lines)


def main(argv=None):
    args = parse_args(argv)
    a, report, pages, chapters, names, classes = audit(args)
    partial = args.out.with_name(args.out.name + '.partial')
    partial.mkdir(parents=True, exist_ok=False)
    for name, rows in [('pages', pages), ('chapters', chapters), ('names', names),
                       ('text_classes', classes), ('issues', a.issues), ('inputs', list(a.inputs.values()))]:
        write_jsonl(partial / f'{name}.jsonl', rows)
    write_json(partial / 'report.json', report)
    (partial / 'report.md').write_text(markdown(report, chapters, classes), encoding='utf-8')
    write_json(partial / 'manifest.json', {'schema': SCHEMA,
        'created_at': datetime.now(timezone.utc).isoformat(), 'arguments': {k: str(v) if isinstance(v, Path) else v
                                                                       for k, v in vars(args).items()},
        'code_sha256': {str(p): sha256(p.read_bytes()) for p in
                        (Path(__file__), CORE / 'build_core.py', CORE / 'geometry.py')},
        'outputs_sha256': {p.name: sha256(p.read_bytes()) for p in sorted(partial.iterdir()) if p.is_file()},
        'scope': report['scope'], 'source_mutation': False})
    partial.rename(args.out)
    print(f"Report: {args.out / 'report.md'}")
    print(f"Findings: {report['issues_by_severity']}")
    # Review warnings are expected; integrity errors produce a nonzero exit after saving the report.
    return 2 if report['issues_by_severity'].get('error') else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'CKG-0 could not complete: {exc}', file=sys.stderr)
        sys.exit(1)
