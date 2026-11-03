"""Immutable, content-addressed JSON and read-only legacy snapshot helpers."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def stable(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    def invalid(value):
        raise ValueError('Non-finite JSON: ' + value)
    return json.loads(Path(path).read_text(), parse_constant=invalid)


def member(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or path == root or root not in path.parents:
        raise ValueError('Path escapes artifact root: ' + str(relative))
    return path


def separate(output, inputs):
    output = Path(output).resolve()
    inputs = list(inputs)
    repo = Path(__file__).resolve().parents[3]
    if output == repo or repo in output.parents:
        raise ValueError('Generated artifacts must live outside the code repository')
    for name in ('src', 'scripts', 'configs', 'tests', 'slurm'):
        protected = repo / name
        if output == protected or protected in output.parents:
            raise ValueError('Generated artifacts cannot be written into implementation roots')
    # Infer data roots from conventional source paths, including a relocated host.
    for input_path in inputs:
        parts = Path(input_path).resolve().parts
        for marker in ('items', 'evidence', 'PopManga_Test', 'annotations', 'core'):
            if marker not in parts:
                continue
            bench = Path(*parts[:parts.index(marker)])
            if output == bench:
                raise ValueError('Output is benchmark input root')
            if bench in output.parents:
                rel = output.relative_to(bench).parts
                if rel[0] in ('PopManga_Test', 'annotations', 'core'):
                    raise ValueError('Output is within immutable source data')
                if rel[0] in ('items', 'evidence', 'reports', 'reviews', 'exports') and (len(rel) < 2 or rel[1] != 'benchmark1000'):
                    raise ValueError('Output requires a separate benchmark1000 namespace')
    for source in inputs:
        source = Path(source).resolve()
        if output == source or output in source.parents or source in output.parents:
            raise ValueError('Output overlaps protected input: ' + str(source))
    return output


def publish(path, value):
    """Atomic create-only publication. Matching content is safe to resume."""
    path = Path(path)
    raw = (encoded(value) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Refusing symlink output')
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Existing output differs; choose a new version: ' + str(path))
        return
    fd, temp = tempfile.mkstemp(prefix='.b1000-', dir=path.parent)
    os.fchmod(fd, 0o644)  # shared outputs are world-readable, like the annotation runs
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != raw:
                raise ValueError('Concurrent output differs')
    finally:
        os.unlink(temp)


def verify_manifest(root):
    root = Path(root).resolve()
    m = read(root / 'manifest.json')
    outputs = m.get('outputs_sha256')
    if not isinstance(outputs, dict):
        raise ValueError('Missing output manifest')
    for name, expected in outputs.items():
        if digest(member(root, name)) != expected:
            raise ValueError('Artifact checksum mismatch: ' + name)
    return m


def legacy_snapshot(repo):
    """Exclude only this new layer and documentation; pin all legacy implementation."""
    repo = Path(repo).resolve()
    roots = ('src', 'scripts', 'configs', 'tests', 'slurm')
    result = {}
    for name in roots:
        root = repo / name
        if not root.exists():
            continue
        for p in sorted(root.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts:
                continue
            rel = p.relative_to(repo)
            if 'benchmark1000' in rel.parts or p.name == 'benchmark1000.sh' or p.name.startswith('benchmark1000_'):
                continue
            result[str(rel)] = digest(p)
    return result


def verify_snapshot(repo, snapshot):
    if legacy_snapshot(repo) != snapshot:
        raise ValueError('Legacy implementation changed since snapshot')
