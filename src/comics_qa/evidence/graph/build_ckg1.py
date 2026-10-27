"""Build chapter-scoped CKG-1 graphs from pinned core/audit/review snapshots (stdlib)."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import itertools
import json
from pathlib import Path
import sys

import audit_ckg0 as audit
import review_ckg0 as review
from ckg_schema import BUILDER_VERSION, REGISTRY, SCHEMA, TRUST, stable_id, validate_graph


def checksum(path):
    return audit.sha256(path.read_bytes())


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify_outputs(root, manifest):
    for filename, digest in manifest['outputs_sha256'].items():
        check(checksum(audit.safe_path(root, filename)) == digest, f'Checksum mismatch: {root / filename}')


class Inputs:
    def __init__(self, args):
        self.args = args
        am, deps, self.pages, ap, ac, issues = review.load_snapshot(args.audit, args.core)
        rm = review.read_json(args.review / 'manifest.json')
        check(rm['schema'] == review.SCHEMA, 'Unsupported review schema')
        verify_outputs(args.review, rm)
        # Check the review's dependency declarations against the explicitly supplied snapshots.
        expected = {str(Path(rm['arguments']['audit']) / 'manifest.json'): checksum(args.audit / 'manifest.json')}
        expected.update({str(Path(rm['arguments']['core']) / name): checksum(args.core / name)
                         for name in ('pages.jsonl', 'chapters.jsonl', 'characters.jsonl', 'manifest.json')})
        check(rm['inputs_sha256'] == expected, 'Review does not pin the supplied core/audit')
        summary, rows = review.make_review(self.pages, ap, ac, issues)
        check(summary['unresolved_errors'] == 0, 'Review has unresolved integrity errors')
        # v1 is the automated disposition contract; changes need a new explicit review policy/schema.
        for name, values in rows.items():
            check(review.read_rows(args.review / (name + '.jsonl')) == values, f'Review decisions differ: {name}')
        check(review.read_json(args.review / 'report.json') == summary, 'Review summary differs')
        self.coverage = review.unique(rows['coverage'], 'page_id')
        self.overrides = review.unique(rows['identity_overrides'], 'char_id')
        self.chapters = review.unique(review.read_rows(args.core / 'chapters.jsonl'), 'chapter_id')
        self.identities = review.unique(review.read_rows(args.core / 'characters.jsonl'), 'identity_id')
        self.audit_chapters = review.unique(ac, 'chapter_id')
        self.audit_manifest = am
        self.audit_inputs = {r['path']: r for r in review.read_rows(args.audit / 'inputs.jsonl')}
        self.dependencies = {**deps, str(args.review / 'manifest.json'): checksum(args.review / 'manifest.json')}
        self.file_hashes = dict(self.dependencies)
        for root in (args.core, args.review):
            for path in root.glob('*.jsonl'):
                self.file_hashes[str(path)] = checksum(path)
        self.issues = rows['unresolved_issues']

    def pointer(self, path, pointer='', **selector):
        return {'file': str(path), 'sha256': self.file_hashes[str(path)], 'pointer': pointer, **selector}

    def core_pointer(self, kind, key, value, pointer=''):
        return self.pointer(self.args.core / (kind + '.jsonl'), pointer, record_key={key: value})

    def review_pointer(self, kind, key, value):
        return self.pointer(self.args.review / (kind + '.jsonl'), record_key={key: value})

    def chapter_sources(self, chapter):
        """Hash every consumed source and image; missing optional artifacts must remain missing."""
        records, documents = [], {}
        check(self.audit_chapters[chapter['chapter_id']]['structure_ok'], 'Chapter structure audit failed')
        # Recheck inventory so new images cannot silently fall outside the pinned scope.
        folder = audit.safe_path(self.args.images, chapter['chapter_dir'])
        actual = {p.relative_to(self.args.images).as_posix() for p in folder.rglob('*')
                  if p.is_file() and p.suffix.lower() in audit.IMAGE_EXTENSIONS
                  and not any(x.startswith('.') for x in p.relative_to(folder).parts)}
        expected = {self.pages[p]['relative_path'] for p in chapter['page_ids']}
        check(actual == expected, f'Image inventory changed: {chapter["chapter_id"]}; rerun audit')
        for pid in chapter['page_ids']:
            page = self.pages[pid]
            image = audit.safe_path(self.args.images, page['relative_path'])
            digest = checksum(image)
            check(digest == page['image_sha256'], f'Image bytes changed: {pid}; rerun audit')
            records.append({'path': str(image), 'sha256': digest, 'status': 'read'})
            self.file_hashes[str(image)] = digest
            documents[pid] = {}
            for kind in ('human', 'magi3', 'ocr'):
                rel = page['relative_path'] + '.json'
                source = audit.safe_path(getattr(self.args, kind), rel)
                old = str(Path(self.audit_manifest['arguments'][kind]) / rel)
                pinned = self.audit_inputs.get(old)
                check(pinned is not None, f'Input not recorded by audit: {old}')
                if pinned['status'] == 'missing':
                    check(not source.exists(), f'Previously missing input now exists: {source}; rerun audit')
                    records.append({'path': str(source), 'sha256': None, 'status': 'missing'})
                    documents[pid][kind] = None
                    continue
                check(pinned['status'] == 'read', f'Unauditable source status: {source}')
                data = source.read_bytes()
                digest = audit.sha256(data)
                check(digest == pinned['sha256'], f'Source changed: {source}; rerun audit')
                records.append({'path': str(source), 'sha256': digest, 'status': 'read'})
                self.file_hashes[str(source)] = digest
                documents[pid][kind] = json.loads(data, parse_constant=audit.reject_constant)
        return records, documents


class ChapterGraph:
    def __init__(self, inputs, chapter):
        self.inputs, self.chapter = inputs, chapter
        self.cid = chapter['chapter_id']
        self.nodes, self.facts, self.certificates = {}, {}, {}
        self.fact_keys = {}
        self.certificate_ids = {}
        for pid in chapter['page_ids']:
            row = inputs.coverage[pid]
            for family, status in {**row['candidate_coverage'], 'page_sequence': 'closed_assumed'}.items():
                source = inputs.review_pointer('coverage', 'page_id', pid)
                cert = {'page_id': pid, 'family': family, 'status': status,
                    'basis': 'supplied_chapter_image_inventory' if family == 'page_sequence' else row['coverage_basis'],
                    'scope': 'supplied_chapter_images', 'sources': [source],
                    'unresolved_issue_lines': [] if family == 'page_sequence' else row['unresolved_issue_lines'],
                    'policy_version': BUILDER_VERSION}
                if family == 'page_sequence':
                    cert['sources'].append(inputs.core_pointer('chapters', 'chapter_id', self.cid, '/page_ids'))
                cert['coverage_id'] = stable_id('cov:', cert)
                self.certificates[cert['coverage_id']] = cert
                self.certificate_ids[pid, family] = cert['coverage_id']

    def node(self, nid, kind, sources, origin='H', **attrs):
        value = {'id': nid, 'type': kind, 'origin': origin, 'sources': sources, **attrs}
        check(nid not in self.nodes, f'Duplicate node: {nid}')
        self.nodes[nid] = value

    def fact(self, rel, args, page_ids, sources=None, premises=(), families=None):
        key = (rel, tuple(args))
        if key in self.fact_keys:
            return self.fact_keys[key]
        reg = REGISTRY[rel]
        premise_records = [self.facts[p] for p in premises]
        sources = list(sources or [])
        if not sources:
            sources = [s for p in premise_records for s in p['sources']]
        sources = list({json.dumps(s, sort_keys=True): s for s in sources}.values())
        sources.sort(key=lambda s: json.dumps(s, sort_keys=True))
        origins = [self.nodes[v]['origin'] for v, t in zip(args, reg['signature']) if t != 'Str']
        origins += [p['origin'] for p in premise_records]
        origin = min(origins, key=TRUST.get)
        families = reg['coverage_families'] if families is None else families
        cert_ids = sorted({self.certificate_ids[p, f] for p in page_ids for f in families})
        record = {'rel': rel, 'args': args, 'origin': origin, 'derivation': reg['derivation'],
            'rule_id': rel + ':' + BUILDER_VERSION if reg['derivation'] == 'R' else None,
            'premises': sorted(set(premises)), 'sources': sources, 'page_ids': sorted(set(page_ids)),
            'coverage_refs': cert_ids, 'answer_eligible': origin in ('H', 'V'),
            'confidence': 1.0 if origin == 'H' else None,
            'confidence_basis': 'accepted_annotation/identity_policy; not a measured probability' if origin == 'H' else 'unverified_model',
            'graph_version': BUILDER_VERSION}
        record['fact_id'] = stable_id('f:', record)
        self.facts[record['fact_id']] = record
        self.fact_keys[key] = record['fact_id']
        return record['fact_id']

    def region(self, page, record, kind, id_key, source):
        box = record['box']
        check(audit.valid_box(box), f'Invalid {kind} box: {record[id_key]}')
        w, h = page['width'], page['height']
        check(w > 0 and h > 0 and min(box[2], w) > max(box[0], 0)
              and min(box[3], h) > max(box[1], 0), f'Region does not intersect image: {record[id_key]}')
        norm = [box[0]/w*1000, box[1]/h*1000, box[2]/w*1000, box[3]/h*1000]
        overflow = box[0] < 0 or box[1] < 0 or box[2] > w or box[3] > h
        attrs = {'page_id': page['page_id'], 'box': box, 'box_normalized_1000': norm,
            'normalization': 'x / original_width * 1000; y / original_height * 1000; no clipping',
            'outside_image': overflow, 'touches_image_edge': box[0] <= 0 or box[1] <= 0 or box[2] >= w or box[3] >= h,
            'geometry_review_required': overflow, 'area': (box[2]-box[0])*(box[3]-box[1])}
        if kind == 'Appearance':
            attrs.update(source_name=record['name'], page_cluster=record['page_cluster'],
                         source_identity_id=record['identity_id'])
        elif kind == 'Text':
            attrs.update(raw_text_class=record['text_classification'], class_semantics='unverified')
        elif kind == 'Panel':
            attrs.update(source='model:magi3', estimated_reading_rank=record['reading_order'])
        origin = 'M' if kind == 'Panel' else 'H'
        self.node(record[id_key], kind, [source], origin=origin, **attrs)
        families = {'Appearance': ['char_boxes'], 'Text': ['text_boxes'], 'Tail': ['speaker_links'], 'Panel': ['panels']}[kind]
        return self.fact('on_page', [record[id_key], page['page_id']], [page['page_id']], sources=[source], families=families)

    def build(self, documents):
        inp = self.inputs
        csource = inp.core_pointer('chapters', 'chapter_id', self.cid)
        self.node(self.cid, 'Chapter', [csource], series=self.chapter['series'], split=self.chapter['split'],
                  reading_direction=self.chapter['reading_direction'], page_ids=self.chapter['page_ids'])
        character_apps, char_sources = defaultdict(list), defaultdict(list)
        app_identity, app_facts, text_facts, speaker_facts = {}, {}, {}, defaultdict(list)
        for order, pid in enumerate(self.chapter['page_ids']):
            page = inp.pages[pid]
            check(page['order_in_chapter'] == order and page['chapter_id'] == self.cid, 'Invalid chapter order/membership')
            psource = inp.core_pointer('pages', 'page_id', pid)
            image = audit.safe_path(inp.args.images, page['relative_path'])
            self.node(pid, 'Page', [psource, inp.pointer(image)], chapter_id=self.cid, index_in_chapter=order,
                image_path=str(image), relative_path=page['relative_path'], image_sha256=page['image_sha256'],
                width=page['width'], height=page['height'], annotated=page['has_ground_truth'],
                split=page['split'], page_start=page['page_start'], page_end=page['page_end'], is_spread=page['is_spread'])
            self.fact('page_in', [pid, self.cid], [pid], sources=[psource, csource])
            if order:
                prev = self.chapter['page_ids'][order-1]
                self.fact('next_page', [prev, pid], [prev, pid], sources=[csource])
            mpath = audit.safe_path(inp.args.magi3, page['relative_path'] + '.json')
            for panel in page['panels']:
                self.region(page, panel, 'Panel', 'panel_id', inp.pointer(mpath, f"/magi3/panels/{panel['magi3_index']}"))
            if not page['has_ground_truth']:
                check(not page['characters'] and not page['texts'] and not page['tails'], 'Non-GT page contains human nodes')
                continue
            human = documents[pid]['human']['human']
            hpath = audit.safe_path(inp.args.human, page['relative_path'] + '.json')
            for plural, kind, id_key in [('characters','Appearance','char_id'), ('texts','Text','text_id'), ('tails','Tail','tail_id')]:
                for record in page[plural]:
                    index = record['human_index']
                    check(human[plural][index]['box'] == record['box'], 'Core/source region mismatch')
                    source = inp.pointer(hpath, f'/human/{plural}/{index}')
                    fid = self.region(page, record, kind, id_key, source)
                    if kind == 'Text':
                        text_facts[record[id_key]] = fid
                    if kind != 'Appearance':
                        continue
                    aid = record['char_id']
                    override = inp.overrides.get(aid)
                    identity = override['identity_id'] if override else record['identity_id']
                    if override:
                        check(override['source_identity_id'] == record['identity_id'], 'Override source identity mismatch')
                    generic = audit.name_kind(record['name']) == 'generic'
                    check(audit.name_kind(record['name']) != 'missing', 'Missing identity name')
                    if generic:
                        check(identity == f"{pid}__unnamed{record['page_cluster']}", 'Generic identity is not page-local')
                    else:
                        check(identity == f"{audit.slug(self.chapter['series'])}__{audit.slug(record['name'])}", 'Exact-name identity mismatch')
                    self.nodes[aid].update(identity_id=identity, generic_name=generic)
                    character_apps[identity].append(aid)
                    char_sources[identity].append(source)
                    app_identity[aid] = identity
                    app_facts[aid] = fid
            for key, rel, target_kind in [('text_character','spoken_by','characters'), ('text_tail','has_tail','tails')]:
                id_key = 'char_id' if target_kind == 'characters' else 'tail_id'
                for index, pair in enumerate(human[key]):
                    check(len(pair) == 2 and all(type(x) is int for x in pair), 'Malformed human association')
                    ti, ri = pair
                    check(0 <= ti < len(page['texts']) and 0 <= ri < len(page[target_kind]), 'Human link out of range')
                    text, target = page['texts'][ti]['text_id'], page[target_kind][ri][id_key]
                    fid = self.fact(rel, [text, target], [pid], sources=[inp.pointer(hpath, f'/human/{key}/{index}')])
                    if rel == 'spoken_by':
                        speaker_facts[text].append(fid)
        # Integrate the existing exact-name identities; keep appearance lists chapter-local.
        for identity, apps in sorted(character_apps.items()):
            first = self.nodes[apps[0]]
            generic = first['generic_name']
            stored = inp.identities.get(identity)
            check(generic or stored is not None, f'Missing core identity: {identity}')
            aliases = [] if generic else [a['text'] for a in stored.get('aliases', []) if not a['ambiguous']]
            sources = list(char_sources[identity])
            if stored:
                sources.append(inp.core_pointer('characters', 'identity_id', identity))
            for aid in apps:
                if aid in inp.overrides:
                    sources.append(inp.review_pointer('identity_overrides', 'char_id', aid))
            self.node(identity, 'Character', sources, canonical_name=None if generic else first['source_name'],
                aliases=aliases, generic=generic, scope='page' if generic else 'series',
                chapter_id=self.cid, appearance_ids=apps, visibility_status='not_checked')
        links = {}
        presence = defaultdict(dict)
        for aid, identity in sorted(app_identity.items()):
            pid = self.nodes[aid]['page_id']
            source = list(self.nodes[aid]['sources'])
            if aid in inp.overrides:
                source.append(inp.review_pointer('identity_overrides', 'char_id', aid))
            else:
                source.append(inp.core_pointer('characters', 'identity_id', identity))
            links[aid] = self.fact('is_char', [aid, identity], [pid], sources=source, premises=[app_facts[aid]])
            presence[pid][identity] = self.fact('present', [identity, pid], [pid], premises=[links[aid], app_facts[aid]])
            char = self.nodes[identity]
            if not char['generic']:
                named = self.fact('named', [identity, char['canonical_name']], [pid], sources=self.nodes[aid]['sources'])
                for alias in char['aliases']:
                    self.fact('alias', [identity, alias], [pid], sources=char['sources'], premises=[named])
        for text, speakers in sorted(speaker_facts.items()):
            pid = self.nodes[text]['page_id']
            self.fact('is_line', [text], [pid], premises=[speakers[0]])
            for speaker in speakers:
                aid = self.facts[speaker]['args'][1]
                self.fact('speaks_on', [app_identity[aid], pid], [pid], premises=[speaker, links[aid], text_facts[text], app_facts[aid]])
        for pid, characters in sorted(presence.items()):
            for a, b in itertools.combinations(sorted(characters), 2):
                self.fact('co_present', [a, b, pid], [pid], premises=[characters[a], characters[b]])
        graph = {'schema': SCHEMA, 'builder_version': BUILDER_VERSION, 'chapter_id': self.cid,
            'split': self.chapter['split'], 'page_ids': self.chapter['page_ids'],
            'nodes': sorted(self.nodes.values(), key=lambda n: n['id']),
            'facts': sorted(self.facts.values(), key=lambda f: f['fact_id']),
            'coverage': sorted(self.certificates.values(), key=lambda c: (c['page_id'], c['family'])),
            'metadata': {'dependencies': inp.dependencies, 'registry_sha256': stable_id('', REGISTRY),
                'context': 'full_supplied_chapter', 'identity_policy': 'exact_name_plus_ckg0_review_overrides',
                'name_visibility': 'not_checked; CKG-2 required before GEN-1', 'depth': 'excluded',
                'human_completeness': 'assumed except unresolved family flags',
                'geometry': 'original boxes retained; no spatial predicates in CKG-1'}}
        validate_graph(graph)
        return graph


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('core', 'audit', 'review', 'images', 'human', 'magi3', 'ocr', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--chapter', action='append', default=[], help='Exact chapter ID, repeatable; always includes all chapter pages')
    p.add_argument('--resume', action='store_true', help='Validate/reuse matching complete chapter shards from .partial or completed output')
    args = p.parse_args(argv)
    for key in ('core', 'audit', 'review', 'images', 'human', 'magi3', 'ocr', 'out'):
        setattr(args, key, getattr(args, key).expanduser().resolve())
    for target in (args.out, args.out.with_name(args.out.name + '.partial')):
        for key in ('core', 'audit', 'review', 'images', 'human', 'magi3', 'ocr'):
            source = getattr(args, key)
            check(target != source and source not in target.parents and target not in source.parents,
                  f'Output overlaps --{key}')
    return args


def main(argv=None):
    args = parse_args(argv)
    inp = Inputs(args)
    selected = sorted(set(args.chapter) or inp.chapters.keys())
    check(set(selected) <= inp.chapters.keys(), 'Unknown --chapter ID')
    for cid in selected:
        check(cid and all(c.isalnum() or c in '_-' for c in cid), 'Unsafe chapter ID')
    module = Path(__file__).resolve().parent
    code = [module / n for n in ('build_ckg1.py', 'ckg_schema.py', 'review_ckg0.py', 'audit_ckg0.py')]
    code += [audit.CORE / 'build_core.py', audit.CORE / 'geometry.py']
    config = {'schema': SCHEMA, 'builder_version': BUILDER_VERSION, 'chapters': selected,
        'scope': 'selected_chapters' if args.chapter else 'full_collection',
        'arguments': {k: str(v) for k,v in vars(args).items() if k not in ('resume', 'out', 'chapter')},
        'dependencies': inp.dependencies, 'code_sha256': {str(p): checksum(p) for p in code}}
    fingerprint = stable_id('', config)
    partial = args.out.with_name(args.out.name + '.partial')
    check(not partial.is_symlink(), 'Partial output must not be a symlink')
    complete = args.out.exists()
    check(args.resume or not complete and not partial.exists(), 'Output/.partial exists; use --resume or a new --out')
    check(not (complete and partial.exists()), 'Both output and .partial exist; inspect before resuming')
    root = args.out if complete else partial
    if complete:
        manifest = review.read_json(root / 'manifest.json')
        check(manifest['fingerprint'] == fingerprint, 'Completed graph configuration/dependencies changed')
        verify_outputs(root, manifest)
    else:
        root.mkdir(parents=True, exist_ok=args.resume)
    for name in ('.build.lock', 'chapters', 'checkpoints', 'build_config.json'):
        check(not (root / name).is_symlink(), f'Output entry must not be a symlink: {name}')
    # Kernel lock is automatically released on interruption; the marker may safely remain on disk.
    with (root / '.build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = root / 'build_config.json'
        if state.exists():
            check(review.read_json(state) == config, 'Partial build configuration/dependencies changed; use a new --out')
        else:
            check(not complete, 'Missing completed build configuration')
            audit.write_json(state, config)
        (root / 'chapters').mkdir(exist_ok=True)
        (root / 'checkpoints').mkdir(exist_ok=True)
        totals = Counter()
        all_inputs = {}
        for index, cid in enumerate(selected, 1):
            chapter = inp.chapters[cid]
            sources, docs = inp.chapter_sources(chapter)
            all_inputs.update({s['path']: s for s in sources})
            target = root / 'chapters' / (cid + '.json')
            marker = root / 'checkpoints' / (cid + '.json')
            if marker.exists():
                checkpoint = review.read_json(marker)
                check(checkpoint['fingerprint'] == fingerprint and checkpoint['sources'] == sources,
                      f'Checkpoint dependencies changed: {cid}')
                check(checksum(target) == checkpoint['sha256'], f'Corrupt chapter shard: {cid}')
                graph = review.read_json(target)
                validate_graph(graph)
                action = 'Verified/reused'
            else:
                check(not complete, f'Completed output missing checkpoint: {cid}')
                graph = ChapterGraph(inp, chapter).build(docs)
                audit.write_json(target, graph)
                audit.write_json(marker, {'fingerprint': fingerprint, 'sources': sources, 'sha256': checksum(target)})
                action = 'Built'
            totals.update(chapters=1, pages=len(graph['page_ids']), nodes=len(graph['nodes']), facts=len(graph['facts']),
                          human_pages=sum(n['type']=='Page' and n['annotated'] for n in graph['nodes']),
                          coverage_records=len(graph['coverage']))
            print(f'{action} {cid} ({index}/{len(selected)})', file=sys.stderr, flush=True)
        if not complete:
            audit.write_json(root / 'relations.json', {'schema': SCHEMA, 'relations': REGISTRY})
            audit.write_jsonl(root / 'inputs.jsonl', [all_inputs[k] for k in sorted(all_inputs)])
            report = {'schema': SCHEMA, 'scope': config['scope'], 'counts': dict(totals), 'chapters': selected,
                      'name_visibility': 'pending CKG-2', 'source_freshness': 'image bytes and audited source states/hashes verified',
                      'coverage_policy': 'reviewed candidates carried as assumption-based certificates; open/absent preserved'}
            audit.write_json(root / 'report.json', report)
            audit.write_json(root / 'manifest.json', {'schema': SCHEMA, 'created_at': datetime.now(timezone.utc).isoformat(),
                'fingerprint': fingerprint, 'config': config, 'counts': dict(totals),
                'outputs_sha256': {p.relative_to(root).as_posix(): checksum(p) for p in sorted(root.rglob('*'))
                                  if p.is_file() and p.name not in ('.build.lock', 'manifest.json') and not p.name.startswith('.') }})
            check(not args.out.exists(), 'Output appeared during build; refusing replacement')
            root.rename(args.out)
    print(f'Graphs: {args.out}; {dict(totals)}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, IndexError) as exc:
        print(f'CKG-1 could not complete: {exc}', file=sys.stderr)
        sys.exit(1)
