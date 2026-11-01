"""Immutable checkpointed candidate ingestion; imports never grant release approval."""
import fcntl
from pathlib import Path
from . import VERSION
from .adapters import records
from .contract import validate
from .io import digest, publish, read, stable, separate, verify_manifest


def ingest(sources, out, chapters=None):
    sources = [Path(p).resolve() for p in sources]
    if len(set(sources)) != len(sources):
        raise ValueError('Duplicate source')
    out = separate(out, sources)
    module_pins = {name: digest(Path(__file__).with_name(name)) for name in ('__init__.py', 'io.py', 'contract.py', 'adapters.py', 'store.py')}
    config = {'version': VERSION, 'importer_code_sha256': module_pins, 'sources': [
        {'root': str(p), 'manifest_sha256': digest(p / 'manifest.json')} for p in sources],
        'chapters': sorted(chapters) if chapters else None}
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        outputs, ids = {}, set()
        for source in sources:
            for item in records(source, chapters):
                name = 'candidates/' + item['item_id'].split(':')[1] + '.json'
                if item['item_id'] in ids:
                    raise ValueError('Duplicate candidate ID across imports')
                ids.add(item['item_id'])
                publish(out / name, item)
                outputs[name] = digest(out / name)
        report = {'schema': 'comics_qa.benchmark1000.store.1', 'config': config,
                  'config_sha256': stable(config), 'counts': {'candidates': len(ids)},
                  'outputs_sha256': outputs, 'release_status': 'pending_validation_review'}
        publish(out / 'manifest.json', report)
    return report


def load(root, include_proposals=False):
    root = Path(root).resolve()
    manifest = verify_manifest(root)
    if manifest.get('schema') == 'comics_qa.benchmark1000.contrast_store.1':
        from .contrast_pilot import load as load_contrast
        return load_contrast(root)
    if manifest.get('schema') == 'comics_qa.benchmark1000.pool.1':
        from .pool import load as load_pool
        return load_pool(root)
    if manifest.get('schema') == 'comics_qa.benchmark1000.admission_store.1':
        from .admission_store import load as load_admitted
        return load_admitted(root)
    if manifest.get('schema') == 'comics_qa.benchmark1000.native_store.1':
        from .native_store import load as load_native
        return load_native(root, include_proposals)
    if manifest.get('schema') != 'comics_qa.benchmark1000.store.1':
        raise ValueError('Not a benchmark1000 store')
    if stable(manifest['config']) != manifest['config_sha256']:
        raise ValueError('Store config mismatch')
    if read(root / 'config.json') != manifest['config']:
        raise ValueError('Store configuration changed')
    items = [validate(read(root / name)) for name in sorted(manifest['outputs_sha256'])]
    if len(items) != manifest['counts']['candidates'] or len({i['item_id'] for i in items}) != len(items):
        raise ValueError('Store totals mismatch')
    return items
