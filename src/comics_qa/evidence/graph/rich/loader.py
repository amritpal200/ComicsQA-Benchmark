"""Explicit CKG-3 consumer boundary; never silently merge into a CKG-1 world."""
from pathlib import Path
from .model import build, require, SCHEMA
from .build import read, stable, digest, load_world, validate_graph, validate_companion


def load_rich(graphs, visibility, rich, chapter):
    """Verify snapshot bindings and recompute derivations/review gates before use.

    Raw-source freshness is a build option; loading verifies the pinned snapshots.
    Returns the companion, not a modified CKG-1 graph. CRL integration is separate.
    """
    graphs, visibility, rich = map(lambda p: Path(p).resolve(), (graphs, visibility, rich))
    graph, vis, _ = load_world(graphs, visibility, chapter)
    validate_graph(graph); validate_companion(vis, graph)
    manifest = read(rich / 'manifest.json')
    require(manifest['schema'] == SCHEMA and stable(manifest['config']) == manifest['fingerprint'], 'Invalid CKG-3 manifest')
    require(chapter in manifest['config']['chapters'], 'Chapter missing from CKG-3')
    name = 'chapters/' + chapter + '.json'
    raw = (rich / name).read_bytes()
    require(digest(raw) == manifest['outputs_sha256'][name], 'CKG-3 chapter checksum mismatch')
    saved = read(rich / name); companion = saved['payload']
    require(saved['fingerprint'] == manifest['fingerprint'] and saved['payload_sha256'] == stable(companion), 'CKG-3 payload checksum mismatch')
    sources = {'graph_sha256': digest((graphs / name).read_bytes()),
               'visibility_sha256': digest((visibility / name).read_bytes()),
               'graphs_manifest_sha256': digest((graphs / 'manifest.json').read_bytes()),
               'visibility_manifest_sha256': digest((visibility / 'manifest.json').read_bytes())}
    require(companion['sources'] == sources and all(manifest['config'][k] == sources[k] for k in ('graphs_manifest_sha256', 'visibility_manifest_sha256')), 'CKG-3 pins different evidence')
    require(companion == build(graph, vis, sources, companion['decisions']), 'CKG-3 derivation/review validation failed')
    return companion
