"""Build CKG-3 companions and visual review queues without changing CKG-1/2."""
import argparse
from collections import Counter
import fcntl
import html
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comics_qa.evidence.graph.rich.model import build, require, SCHEMA, VERSION, POLICY
from comics_qa.tasks.graph.crl.artifacts import load_world, digest
from comics_qa.tasks.graph.generation.build_gen1 import read, write
from comics_qa.tasks.graph.generation.policy import stable
from ckg_schema import validate_graph
from build_ckg2 import validate_companion


def source_records(value):
    if isinstance(value, dict):
        if isinstance(value.get('file'), str) and isinstance(value.get('sha256'), str):
            yield value['file'], value['sha256']
        for child in value.values():
            yield from source_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from source_records(child)


def raw_sources(graph, visibility, cache):
    records = {}
    for path, sha in source_records([graph, visibility]):
        require(path not in records or records[path] == sha, 'Conflicting source hashes: ' + path)
        records[path] = sha
    for path, sha in records.items():
        if path not in cache:
            cache[path] = digest(Path(path).read_bytes())
        require(cache[path] == sha, 'Raw source changed: ' + path)
    return records


def code_hashes():
    root = Path(__file__).resolve().parents[3]
    paths = list(Path(__file__).parent.glob('*.py'))
    paths += list(Path(__file__).resolve().parents[1].glob('*.py'))
    paths += [root / name for name in ('tasks/graph/crl/artifacts.py', 'tasks/graph/crl/check_crl.py',
              'tasks/graph/generation/build_gen1.py', 'tasks/graph/generation/policy.py', 'core/geometry.py', 'core/build_core.py')]
    return {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(set(paths))}


def safe_file(root, name):
    require(isinstance(name, str), 'Invalid manifest filename')
    path = (root / name).resolve()
    require(not Path(name).is_absolute() and root in path.parents, 'Unsafe manifest filename')
    return path


def verify_outputs(root, manifest):
    for name, sha in manifest['outputs_sha256'].items():
        require(digest(safe_file(root, name).read_bytes()) == sha, 'Output checksum mismatch: ' + name)


def review_html(graph, companion):
    esc = lambda x: html.escape(str(x), quote=True)
    nodes = {n['id']: n for n in graph['nodes']}
    chunks = ['<!doctype html><meta charset="utf-8"><title>CKG-3 private review</title>',
              '<style>body{font:16px sans-serif;max-width:1500px;margin:auto}svg{width:75%;height:auto}pre{white-space:pre-wrap}details{border:1px solid #aaa;padding:8px}text{paint-order:stroke;stroke:white;stroke-width:2px}</style>',
              '<h1>CKG-3 private visual review</h1><p>Blue: model panel boxes; red: human text boxes; green: human appearances. '
              'Labels show region ID suffixes, not reading positions; the queue contains full IDs. Review the original image. '
              'No automatic approval occurs. The JSON queue supplies snapshot-bound decision templates.</p>']
    for pid in graph['page_ids']:
        page = nodes[pid]
        chunks.append(f'<h2>{esc(pid)}</h2><svg viewBox="0 0 {page["width"]} {page["height"]}" xmlns="http://www.w3.org/2000/svg">')
        chunks.append(f'<image href="{esc(Path(page["image_path"]).as_uri())}" width="{page["width"]}" height="{page["height"]}"/>')
        for n in graph['nodes']:
            if n.get('page_id') != pid or n['type'] not in ('Panel', 'Text', 'Appearance'):
                continue
            x, y, x2, y2 = n['box']; color = {'Panel': 'blue', 'Text': 'red', 'Appearance': 'green'}[n['type']]
            chunks.append(f'<rect x="{x}" y="{y}" width="{max(0,x2-x)}" height="{max(0,y2-y)}" fill="none" stroke="{color}" stroke-width="3"/>')
            chunks.append(f'<text x="{x}" y="{max(15,y)}" font-size="14" fill="{color}">{esc(n["id"].split("__")[-1])}</text>')
        chunks.append('</svg>')
        for row in companion['review_queue']:
            if row['page_id'] == pid:
                chunks.append(f'<details><summary>{esc(row["kind"])}: {esc(row["target_id"])}</summary><pre>{esc(json.dumps(row,ensure_ascii=False,indent=2))}</pre></details>')
    return '\n'.join(chunks)


def markdown(report):
    lines = ['# CKG-3 richer evidence', '', f'Scope: {report["scope"]}.', '', '| Measurement | Count |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in sorted(report['counts'].items())]
    lines += ['', '## Interpretation', '',
        '- Panel inventories/order become V only through snapshot-bound individual visual review. No sample audit is presumed.',
        '- OCR verifies complete normalized transcripts; punctuation is retained. Raw model strings remain available.',
        '- Name occurrence is lexical; semantic mentions require individual review and a verified full transcript.',
        '- Spatial positives require valid human boxes and unique same-panel assignments; reviewed panels are required for answer eligibility.',
        '- Original human coverage is inherited, never silently closed. Missing facts are UNKNOWN, not false.',
        '- Review queue counts are work remaining, not proof of a failed build. No model inference was run.',
        '- These companions are not merged into CKG-1. Existing CRL/GEN-1 do not consume richer operations yet; GEN-2 must extend the interpreter and independent checker together.', '']
    return '\n'.join(lines)


def run(args):
    graphs, visibility, out = args.graphs.resolve(), args.visibility.resolve(), args.out.resolve()
    partial = out.with_name(out.name + '.partial')
    require(not partial.is_symlink(), 'Partial output must not be a symlink')
    for target in (out, partial):
        for source in (graphs, visibility):
            require(target != source and source not in target.parents and target not in source.parents, 'Output overlaps source')
        if args.decisions:
            require(target != args.decisions.resolve() and target not in args.decisions.resolve().parents, 'Output overlaps review decisions')
    gm, vm = read(graphs / 'manifest.json'), read(visibility / 'manifest.json')
    upstream_roots = []
    for manifest in (gm, vm):
        for key, value in manifest['config'].get('arguments', {}).items():
            if key in ('graphs', 'core', 'audit', 'review', 'images', 'human', 'magi3', 'ocr') and isinstance(value, str):
                upstream_roots.append(Path(value).resolve())
    for target in (out, partial):
        for source in upstream_roots:
            require(target != source and source not in target.parents and target not in source.parents, 'Output overlaps upstream source')
    available = gm['config']['chapters']
    chapters = sorted(set(args.chapter or available))
    require(chapters and set(chapters) <= set(available) and set(chapters) <= set(vm['config']['chapters']), 'Missing/unknown chapter')
    decisions = []
    if args.decisions:
        decisions = [json.loads(line) for line in args.decisions.read_text().splitlines() if line.strip()]
    require(all(d.get('chapter_id') in chapters for d in decisions), 'Decision outside selected chapters')
    decisions.sort(key=lambda d: (d['chapter_id'], d['kind'], d['target_id']))
    config = {'schema': SCHEMA, 'version': VERSION, 'policy': POLICY, 'chapters': chapters,
              'scope': 'full_collection' if chapters == sorted(available) and gm['config']['scope'] == 'full_collection' else 'selected_chapters',
              'graphs_manifest_sha256': digest((graphs / 'manifest.json').read_bytes()),
              'visibility_manifest_sha256': digest((visibility / 'manifest.json').read_bytes()),
              'decisions_sha256': stable(decisions), 'snapshot_only': args.snapshot_only, 'code_sha256': code_hashes()}
    fingerprint = stable(config)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.with_name(out.name + '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another CKG-3 writer holds the output lock')
        complete = out.exists()
        require(not (complete and partial.exists()), 'Both completed and partial outputs exist')
        root = out if complete else partial
        require(args.resume or not root.exists(), 'Output exists; use --resume or a fresh --out')
        if complete:
            manifest = read(root / 'manifest.json')
            require(manifest['fingerprint'] == fingerprint, 'Completed dependencies/code changed; use a fresh output')
            verify_outputs(root, manifest)
        for name in ('chapters', 'review', 'build_config.json'):
            require(not (root / name).is_symlink(), 'Output entry must not be a symlink')
        if root.exists():
            require(read(root / 'build_config.json') == config, 'Partial dependencies/code changed; use a fresh output')
        else:
            root.mkdir(); write(root / 'build_config.json', config)
        totals = Counter(); relations = Counter(); cache = {}
        for cid in chapters:
            graph, vis, _ = load_world(graphs, visibility, cid)
            validate_graph(graph); validate_companion(vis, graph)
            sources = {'graph_sha256': digest((graphs / 'chapters' / (cid + '.json')).read_bytes()),
                       'visibility_sha256': digest((visibility / 'chapters' / (cid + '.json')).read_bytes()),
                       'graphs_manifest_sha256': config['graphs_manifest_sha256'],
                       'visibility_manifest_sha256': config['visibility_manifest_sha256']}
            raw = {} if args.snapshot_only else raw_sources(graph, vis, cache)
            # Recompute pure derivations on resume: catches stale review targets and altered checkpoints.
            companion = build(graph, vis, sources, [d for d in decisions if d['chapter_id'] == cid])
            wrapper = {'fingerprint': fingerprint, 'payload_sha256': stable(companion), 'raw_sources_sha256': raw, 'payload': companion}
            target = root / 'chapters' / (cid + '.json')
            if target.exists():
                require(read(target) == wrapper, 'Checkpoint content/dependency mismatch: ' + cid)
            else:
                require(not complete, 'Missing completed chapter')
                write(target, wrapper)
            if not complete:
                write(root / 'review' / (cid + '.json'), companion['review_queue'])
                (root / 'review' / (cid + '.html')).write_text(review_html(graph, companion), encoding='utf-8')
            totals.update(companion['counts']); totals['chapters'] += 1
            relations.update(f['rel'] for f in companion['facts'] if f['answer_eligible'])
            print(f'{cid}: {companion["counts"]}', file=sys.stderr, flush=True)
        if not complete:
            report = {'schema': SCHEMA, 'scope': config['scope'], 'counts': dict(totals),
                      'eligible_relations': dict(relations), 'raw_sources_verified': not args.snapshot_only}
            write(root / 'report.json', report)
            (root / 'report.md').write_text(markdown(report), encoding='utf-8')
            outputs = {p.relative_to(root).as_posix(): digest(p.read_bytes()) for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
            write(root / 'manifest.json', {'schema': SCHEMA, 'fingerprint': fingerprint, 'config': config,
                                         'counts': dict(totals), 'outputs_sha256': outputs})
            root.rename(out)
    print(json.dumps({'output': str(out), 'status': 'verified_completed' if complete else 'complete', 'counts': dict(totals)}))
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('graphs', 'visibility', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--chapter', action='append', default=[])
    p.add_argument('--decisions', type=Path, help='Individual visual review decisions JSONL; no pending rows')
    p.add_argument('--snapshot-only', action='store_true', help='Check pinned CKG snapshots, without reading original annotations/images')
    p.add_argument('--resume', action='store_true')
    try:
        return run(p.parse_args(argv))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print('CKG-3 build error: ' + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; completed chapter checkpoints retained. Rerun with --resume.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
