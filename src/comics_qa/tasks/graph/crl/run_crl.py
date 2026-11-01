"""Run one CRL program against a pinned CKG-1/2 chapter and optional CKG-3 companion, without rebuilding evidence."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

try:
    from .interpreter import Interpreter, GRAPH
    from .artifacts import digest, load_world, write_new
except ImportError:
    from interpreter import Interpreter, GRAPH
    from artifacts import digest, load_world, write_new


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graphs', type=Path, required=True)
    parser.add_argument('--visibility', type=Path, required=True)
    parser.add_argument('--rich', type=Path, help='Optional pinned CKG-3 companion root')
    parser.add_argument('--chapter', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--program')
    group.add_argument('--program-file', type=Path)
    parser.add_argument('--format', choices=['auto', 'surface', 'sexpr', 'json'], default='auto')
    parser.add_argument('--out', type=Path, help='New JSON file; existing outputs are never overwritten')
    parser.add_argument('--max-steps', type=int, default=50000)
    parser.add_argument('--require-verified-coverage', action='store_true',
                        help='Exclude closed_assumed coverage (including supplied page order)')
    args = parser.parse_args(argv)
    try:
        if args.max_steps < 1:
            raise ValueError('--max-steps must be positive')
        if args.out:
            dest = args.out.resolve()
            for root in (args.graphs.resolve(), args.visibility.resolve(), *([args.rich.resolve()] if args.rich else [])):
                if dest == root or root in dest.parents:
                    raise ValueError('--out must be outside evidence input directories')
        graph, visibility, sources = load_world(args.graphs, args.visibility, args.chapter)
        from comics_qa.tasks.graph.crl.rich_contract import load_optional
        rich = load_optional(args.graphs,args.visibility,args.rich,args.chapter,sources)
        program = args.program_file.read_text(encoding='utf-8') if args.program_file else args.program
        runner = Interpreter(graph, visibility, max_steps=args.max_steps,
                             allow_closed_assumed=not args.require_verified_coverage, rich=rich)
        result = runner.execute(program, args.format)
        result['inputs_sha256'] = sources
        code = list(Path(__file__).parent.glob('*.py')) + [GRAPH / name for name in
                ('ckg_schema.py', 'name_visibility.py', 'build_ckg2.py')]
        if args.rich: code += list((GRAPH / 'rich').glob('*.py'))
        result['code_sha256'] = {str(p.resolve()): digest(p.read_bytes()) for p in sorted(code)}
        payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.out:
            write_new(args.out, payload)
            print(json.dumps({'output': str(args.out), 'result': result['result'],
                              'eligible_for_generation': result['eligible_for_generation']}))
        else:
            print(payload, end='')
        return 2 if result['result']['status'] == 'ERROR' else 0
    except (OSError, ValueError, KeyError) as exc:
        print(f'CRL input/output error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
