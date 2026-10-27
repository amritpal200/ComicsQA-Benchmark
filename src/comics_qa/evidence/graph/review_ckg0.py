"""Review an existing CKG-0 snapshot; emit explicit identity and coverage decisions.

No annotation scan or inference is performed. CKG-1 must consume this companion
alongside the original core/audit, check hashes, and apply identity overrides.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

from audit_ckg0 import FAMILIES, HUMAN_FAMILIES, name_kind, safe_path, sha256, write_json, write_jsonl

SCHEMA = 'comics_qa.ckg0_review.v1'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def unique(rows, key):
    result = {r[key]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError(f'Duplicate {key}; resolve core/audit integrity before review')
    return result


def load_snapshot(root, core):
    manifest = read_json(root / 'manifest.json')
    required = {'report.json', 'pages.jsonl', 'chapters.jsonl', 'issues.jsonl', 'inputs.jsonl'}
    hashes = manifest['outputs_sha256']
    if manifest.get('schema') != 'comics_qa.ckg0.v1' or not required <= hashes.keys():
        raise ValueError('Expected a complete CKG-0 v1 manifest')
    for name, digest in hashes.items():
        if sha256(safe_path(root, name).read_bytes()) != digest:
            raise ValueError(f'Audit checksum mismatch: {name}')
    inputs = {r['path']: r for r in read_rows(root / 'inputs.jsonl')}
    original_core = Path(manifest['arguments']['core'])
    dependencies = {str(root / 'manifest.json'): sha256((root / 'manifest.json').read_bytes())}
    for name in ('pages.jsonl', 'chapters.jsonl', 'characters.jsonl', 'manifest.json'):
        digest = sha256((core / name).read_bytes())
        if inputs.get(str(original_core / name), {}).get('sha256') != digest:
            raise ValueError(f'Core differs from audited snapshot: {name}')
        dependencies[str(core / name)] = digest
    report = read_json(root / 'report.json')
    if report['scope'] != 'full_collection':
        raise ValueError('Review requires the full collection audit, not a smoke test')
    pages = unique(read_rows(core / 'pages.jsonl'), 'page_id')
    audit_pages = unique(read_rows(root / 'pages.jsonl'), 'page_id')
    if pages.keys() != audit_pages.keys():
        raise ValueError('Audit/core page sets differ')
    return manifest, dependencies, pages, audit_pages, read_rows(root / 'chapters.jsonl'), read_rows(root / 'issues.jsonl')


def make_review(pages, audit_pages, chapters, issues):
    overrides, resolutions, pending, geometry = [], [], [], []
    by_override = {}
    all_chars = {c['char_id']: c for p in pages.values() for c in p['characters']}
    identity_groups = defaultdict(list)
    for char in all_chars.values():
        identity_groups[char['identity_id']].append(char)
    # Derive from stable core fields, never from parsing a free-text error message.
    for page in pages.values():
        for char in page['characters']:
            if name_kind(char['name']) != 'generic' or type(char['page_cluster']) is not int:
                continue
            target = f"{page['page_id']}__unnamed{char['page_cluster']}"
            if char['identity_id'] == target:
                continue
            cluster = [c for c in page['characters'] if c['page_cluster'] == char['page_cluster']]
            # Don't merge a generic cluster into a conflicting named identity.
            if any(name_kind(c['name']) != 'generic' for c in cluster):
                continue
            if any(c not in cluster for c in identity_groups.get(target, [])):
                continue
            override = {'page_id': page['page_id'], 'char_id': char['char_id'],
                'source_identity_id': char['identity_id'], 'identity_id': target,
                'source_name': char['name'], 'named': False, 'scope': 'page', 'kind': 'unnamed',
                'aliases': [], 'reason': 'generic_name_policy',
                'core_pointer': f"/characters/{char['human_index']}",
                'policy': 'none/Unnamed names are generic; identity uses the existing page-local cluster'}
            overrides.append(override)
            by_override[char['char_id']] = override
    for number, issue in enumerate(issues, 1):
        key = {'audit_issue_line': number, 'issue_sha256': sha256(
            json.dumps(issue, sort_keys=True, ensure_ascii=False).encode()), **issue}
        match = re.fullmatch(r'/human/characters/(\d+)(?:/named)?', issue['pointer'])
        char_id = f"{issue['page_id']}__hchar{int(match[1]):02d}" if match else None
        if issue['code'] in ('identity_reference', 'generic_policy_mismatch') and char_id in by_override:
            resolutions.append({**key, 'resolution': 'apply_identity_override', 'char_id': char_id})
            continue
        pending.append(key)
        if issue['code'] == 'box_outside_image':
            m = re.fullmatch(r'/human/(characters|texts|tails)/(\d+)/box', issue['pointer'])
            if m and issue['page_id'] in pages:
                page = pages[issue['page_id']]
                box = page[m[1]][int(m[2])]['box']
                w, h = page['width'], page['height']
                overflow = [max(0, -box[0]), max(0, -box[1]), max(0, box[2] - w), max(0, box[3] - h)]
                geometry.append({'page_id': page['page_id'], 'relative_path': page['relative_path'],
                    'category': m[1], 'source_file': issue['file'], 'source_pointer': issue['pointer'],
                    'box': box, 'image_size': [w, h], 'max_overflow_px': max(overflow),
                    'max_overflow_fraction': max(overflow[0]/w, overflow[1]/h, overflow[2]/w, overflow[3]/h),
                    'decision': 'retain_open_for_affected_families', 'families': issue['families']})
    # Only overrides supported by matching audit findings are actionable.
    resolved_ids = {r['char_id'] for r in resolutions}
    overrides = [o for o in overrides if o['char_id'] in resolved_ids]
    pending_by_page = defaultdict(list)
    resolved_by_page = defaultdict(list)
    for i in pending:
        pending_by_page[i['page_id']].append(i)
    for i in resolutions:
        resolved_by_page[i['page_id']].append(i)
    coverage = []
    for pid, original in audit_pages.items():
        states = dict(original['candidate_coverage'])
        flags = pending_by_page[pid]
        for family in HUMAN_FAMILIES:
            removed = any(family in i['families'] for i in resolved_by_page[pid])
            remaining = any(family in i['families'] or (i['severity'] == 'error' and not i['families']) for i in flags)
            if removed and not remaining and original['has_ground_truth'] and states[family] == 'open':
                states[family] = 'closed_assumed'
        coverage.append({'page_id': pid, 'chapter_id': original['chapter_id'],
            'has_ground_truth': original['has_ground_truth'], 'candidate_coverage': states,
            'previous_candidate_coverage': original['candidate_coverage'],
            'unresolved_issue_lines': [i['audit_issue_line'] for i in flags],
            'resolved_issue_lines': [i['audit_issue_line'] for i in resolved_by_page[pid]],
            'coverage_basis': 'human_completeness_assumption_with_unresolved_flags',
            'allow_positive_facts': bool(original['has_ground_truth'])})
    unresolved_errors = sum(i['severity'] == 'error' for i in pending)
    by_id = {p['page_id']: p for p in coverage}
    chapter_rows = []
    for chapter in chapters:
        members = [by_id[pid] for pid in chapter['page_ids']]
        chapter_rows.append({'chapter_id': chapter['chapter_id'], 'page_ids': chapter['page_ids'],
            'full_chapter_candidate_closed': {f: not unresolved_errors and chapter['structure_ok']
                and bool(members) and all(p['candidate_coverage'][f] == 'closed_assumed' for p in members)
                for f in HUMAN_FAMILIES}})
    geometry.sort(key=lambda x: (-x['max_overflow_fraction'], -x['max_overflow_px'], x['page_id'], x['source_pointer']))
    summary = {'schema': SCHEMA, 'pages': len(coverage), 'chapters': len(chapter_rows),
        'identity_overrides': len(overrides), 'corrected_generic_identities': len({o['identity_id'] for o in overrides}),
        'resolved_errors': sum(i['severity'] == 'error' for i in resolutions),
        'resolved_warnings': sum(i['severity'] == 'warning' for i in resolutions),
        'unresolved_errors': unresolved_errors, 'unresolved_warnings': sum(i['severity'] == 'warning' for i in pending),
        'ready_for_ckg1_with_restrictions': unresolved_errors == 0,
        'coverage': {f: dict(Counter(p['candidate_coverage'][f] for p in coverage)) for f in FAMILIES},
        'full_chapters_candidate_closed': {f: sum(c['full_chapter_candidate_closed'][f] for c in chapter_rows) for f in HUMAN_FAMILIES},
        'geometry_review_records': len(geometry), 'geometry_visual_review': 'pending',
        'limitations': ['Resolutions apply only when CKG-1 consumes the identity overrides.',
            'Positive facts still need valid individual evidence; allow_positive_facts is not blanket approval.',
            'No coverage upgraded from boundary tolerance or inferred text-class semantics.',
            'Original source/core/audit IDs are retained as provenance; generic graph identities are explicit overrides.',
            'This review checks the saved audit and core checksums, not current source images/annotations.',
            'Name visibility must be verified before GEN-1; raw OCR matches alone do not establish it.']}
    return summary, {'identity_overrides': overrides, 'resolutions': resolutions, 'unresolved_issues': pending,
                     'coverage': coverage, 'chapters': chapter_rows, 'geometry_review': geometry}


def markdown(summary, outputs):
    lines = ['# CKG-0 review decisions', '',
        f"Reviewed {summary['pages']} pages / {summary['chapters']} chapters from the existing audit.", '',
        f"Resolved {summary['resolved_errors']} errors and {summary['resolved_warnings']} warnings through "
        f"{summary['identity_overrides']} explicit appearance-to-identity overrides.",
        f"Remaining: {summary['unresolved_errors']} errors, {summary['unresolved_warnings']} review warnings.", '',
        'CKG-1 must apply identity_overrides.jsonl and consume coverage.jsonl alongside the pinned core/audit.',
        'Generic identities lose name aliases; raw source names and identity IDs remain in provenance.', '',
        '## Coverage decisions', '', '| Family | closed_assumed | open | absent |', '|---|---:|---:|---:|']
    lines += [f"| {f} | {c.get('closed_assumed', 0)} | {c.get('open', 0)} | {c.get('absent', 0)} |" for f,c in summary['coverage'].items()]
    lines += ['', 'All unresolved geometry/speaker flags remain open for their affected families.',
        'All pages, including those without GT, must remain in chapter context.',
        'Exact counts, absence, only and first require coverage of every relevant page/relation in scope.',
        'No source was corrected by clipping boxes. Model panels, order and OCR remain open.', '',
        '## Highest-priority human geometry flags (visual review pending)', '',
        '| Page | Category | Maximum overflow (pixels) |', '|---|---|---:|']
    lines += [f"| {g['page_id']} | {g['category']} | {g['max_overflow_px']:.2f} |" for g in outputs['geometry_review'][:10]]
    lines += ['', 'The full geometry_review.jsonl queue contains human character/text/tail boxes.',
        'Model panel proxies remain in unresolved_issues.jsonl, separately from human geometry.', '',
        '## Next stages', '',
        '1. CKG-1: build supported positive facts, apply identity overrides, keep explicit coverage and source pointers.',
        '2. CKG-2: verify chapter name visibility using aligned OCR agreement or individual visual verification before GEN-1.',
        '3. CRL: require coverage for non-monotone operations; return UNKNOWN for unsupported scopes.',
        '4. GEN-1: enforce chapter name readability, at most ~30% frequent-character name answers and ~5% two-option answers.',
        '5. EXP-1: recheck quotas and run baselines. Page-order generation may be an independent side task.', '',
        '## Limits', ''] + ['- ' + s for s in summary['limitations']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for key in ('audit', 'core', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args(argv)
    args.audit, args.core, args.out = (p.expanduser().resolve() for p in (args.audit, args.core, args.out))
    manifest, dependencies, pages, audit_pages, chapters, issues = load_snapshot(args.audit, args.core)
    partial = args.out.with_name(args.out.name + '.partial')
    protected = [args.audit, args.core] + [Path(manifest['arguments'][k]).resolve() for k in ('images','human','magi3','ocr')]
    for target in (args.out, partial):
        if target.exists() or target.is_symlink():
            raise ValueError('Output/.partial exists; choose a new --out')
        if any(target == p or p in target.parents or target in p.parents for p in protected):
            raise ValueError('Output must be separate from audit, core and source inputs')
    summary, outputs = make_review(pages, audit_pages, chapters, issues)
    partial.mkdir(parents=True)
    for name, rows in outputs.items():
        write_jsonl(partial / (name + '.jsonl'), rows)
    write_json(partial / 'report.json', summary)
    (partial / 'report.md').write_text(markdown(summary, outputs), encoding='utf-8')
    write_json(partial / 'manifest.json', {'schema': SCHEMA, 'created_at': datetime.now(timezone.utc).isoformat(),
        'arguments': {k: str(v) for k,v in vars(args).items()}, 'inputs_sha256': dependencies,
        'code_sha256': {str(p): sha256(p.read_bytes()) for p in (Path(__file__), Path(__file__).with_name('audit_ckg0.py'))},
        'outputs_sha256': {p.name: sha256(p.read_bytes()) for p in sorted(partial.iterdir())},
        'policy': 'generic identities page-local; retain unresolved coverage flags; no visual completeness claim'})
    partial.rename(args.out)
    print(f"Review: {args.out / 'report.md'}")
    print(f"Resolved errors: {summary['resolved_errors']}; unresolved: {summary['unresolved_errors']}")
    return 2 if summary['unresolved_errors'] else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'CKG-0 review could not complete: {exc}', file=sys.stderr)
        sys.exit(1)
