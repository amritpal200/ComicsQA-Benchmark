"""Independently check a saved CRL result against its pinned chapter artifacts."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

try:
    from .artifacts import digest, load_world, write_new
    from .proof_checker import ProofChecker
except ImportError:
    from artifacts import digest, load_world, write_new
    from proof_checker import ProofChecker


def strict_json(raw):
    def pairs(items):
        output = {}
        for name, value in items:
            if name in output: raise ValueError('Duplicate JSON key: ' + name)
            output[name] = value
        return output
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def verify_input_pins(document, sources):
    pins = document.get('inputs_sha256')
    if not isinstance(pins, dict) or len(pins) != len(sources):
        raise ValueError('Saved result must pin all supplied manifests and chapter shards')
    if not all(isinstance(k, str) and isinstance(v, str) and re.fullmatch(r'[0-9a-f]{64}', v) for k, v in pins.items()):
        raise ValueError('Malformed input checksum map')
    # Never follow paths supplied by an untrusted proof. Content pins survive relocation.
    if Counter(pins.values()) != Counter(sources.values()):
        raise ValueError('Saved result input hashes differ from supplied artifacts')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graphs', type=Path, required=True)
    parser.add_argument('--visibility', type=Path, required=True)
    parser.add_argument('--rich', type=Path, help='Optional pinned CKG-3 companion root')
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--out', type=Path, help='New check report; never overwrites result or existing files')
    parser.add_argument('--expected-program', help='Optionally bind the result to this query')
    parser.add_argument('--max-steps', type=int, default=50000)
    parser.add_argument('--require-verified-coverage', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.result.stat().st_size > 128 * 1024 * 1024:
            raise ValueError('Result file exceeds 128 MiB checker limit')
        raw = args.result.read_bytes()
        document = strict_json(raw)
        if not isinstance(document, dict): raise ValueError('Expected result JSON object')
        if args.out:
            dest = args.out.resolve()
            for root in (args.graphs.resolve(), args.visibility.resolve(), *([args.rich.resolve()] if args.rich else [])):
                if dest == root or root in dest.parents:
                    raise ValueError('--out must be outside evidence inputs')
            if dest == args.result.resolve(): raise ValueError('--out must differ from --result')
        graph, visibility, sources = load_world(args.graphs, args.visibility, document['chapter_id'])
        from comics_qa.tasks.graph.crl.rich_contract import load_optional
        rich = load_optional(args.graphs,args.visibility,args.rich,document['chapter_id'],sources)
        verify_input_pins(document, sources)
        checker = ProofChecker(graph, visibility, args.max_steps, not args.require_verified_coverage, rich=rich)
        report = checker.check(document, args.expected_program)
        report['result_source'] = {'file': str(args.result.resolve()), 'sha256': digest(raw)}
        report['inputs_sha256'] = sources
        report['policy'] = {'closed_statuses': sorted(checker.closed), 'max_steps': args.max_steps}
        directory = Path(__file__).parent
        graph_code = directory.parents[2] / 'evidence/graph'
        files = [directory / n for n in ('check_crl.py', 'proof_checker.py', 'proof_rules.py', 'language.py', 'artifacts.py', 'rich_contract.py')]
        files += [graph_code / n for n in ('ckg_schema.py', 'build_ckg2.py', 'name_visibility.py')]
        if args.rich: files += list((graph_code / 'rich').glob('*.py'))
        report['checker_code_sha256'] = {str(p.resolve()): digest(p.read_bytes()) for p in files}
        payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.out:
            write_new(args.out, payload)
            print(json.dumps({'output': str(args.out), 'status': report['status'],
                              'proof_valid': report['proof_valid'],
                              'accepted_for_generation': report['accepted_for_generation'],
                              'checked_steps': report['checked_steps'], 'errors': report['errors']}))
        else:
            print(payload, end='')
        return 0 if report['proof_valid'] else 1
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        print('CRL checker input/output error: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
