"""Shared immutable artifact IO; no CRL execution or proof semantics."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_world(graphs, visibility, chapter):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', chapter):
        raise ValueError('Invalid chapter ID')
    roots = [Path(graphs).resolve(), Path(visibility).resolve()]
    loaded = []
    sources = {}
    manifests = []
    for root, schema in zip(roots, ('comics_qa.ckg.v1', 'comics_qa.name_visibility.v1')):
        manifest_path = root / 'manifest.json'
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw)
        if manifest['schema'] != schema or chapter not in manifest['config']['chapters']:
            raise ValueError('Manifest schema/chapter mismatch: ' + str(root))
        sources[str(manifest_path)] = digest(raw)
        relative = f'chapters/{chapter}.json'
        path = root / relative
        raw = path.read_bytes()
        if manifest['outputs_sha256'].get(relative) != digest(raw):
            raise ValueError('Chapter checksum mismatch: ' + str(path))
        sources[str(path)] = digest(raw)
        loaded.append(json.loads(raw))
        manifests.append(manifest)
    graph, companion = loaded
    if graph['chapter_id'] != chapter or companion['chapter_id'] != chapter:
        raise ValueError('Chapter identity mismatch')
    if companion['graph_source']['sha256'] != sources[str(roots[0] / f'chapters/{chapter}.json')]:
        raise ValueError('Visibility companion pins a different graph')
    # Original absolute paths can differ on another host; content hashes must agree.
    original_root = manifests[1]['config']['arguments']['graphs']
    expected = manifests[1]['config']['dependencies'].get(str(Path(original_root) / 'manifest.json'))
    if expected != sources[str(roots[0] / 'manifest.json')]:
        raise ValueError('Visibility manifest pins a different graph build')
    return graph, companion, sources


def write_new(path, payload):
    """Publish complete JSON atomically, never replace an existing file or symlink."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.crl-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(name, path)
    finally:
        os.unlink(name)


