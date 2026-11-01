"""Native proposals alongside read-only legacy records; selection excludes proposals."""
import fcntl
from pathlib import Path
from .io import stable, digest, read, publish, separate, verify_manifest, member
from .contract import validate
from .native import SCHEMA as NATIVE

SCHEMA = 'comics_qa.benchmark1000.native_store.1'


def write(items, out, config, protected=()):
    out = separate(out, protected)
    ids = set()
    for item in items:
        validate(item)
        if item['item_id'] in ids:
            raise ValueError('Duplicate native/mixed store item ID')
        ids.add(item['item_id'])
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.native-writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        publish(out / 'config.json', config)
        outputs = {}; proposals = 0
        for item in sorted(items, key=lambda i: i['item_id']):
            is_proposal = item['schema'] == NATIVE
            proposals += is_proposal
            name = ('proposals/' if is_proposal else 'candidates/') + stable(item['item_id']) + '.json'
            publish(out / name, item); outputs[name] = digest(out / name)
        result = {'schema': SCHEMA, 'config': config, 'config_sha256': stable(config),
                  'outputs_sha256': outputs, 'counts': {'records': len(items), 'proposals': proposals,
                                                       'candidates': len(items) - proposals},
                  'release_status': 'pending'}
        publish(out / 'manifest.json', result)
        return result


def load(root, include_proposals=False):
    root = Path(root).resolve(); m = verify_manifest(root)
    if m['schema'] != SCHEMA or stable(m['config']) != m['config_sha256'] or read(root / 'config.json') != m['config']:
        raise ValueError('Invalid native store config/schema')
    records = []
    for name in sorted(m['outputs_sha256']):
        item = validate(read(member(root, name)))
        expected = 'proposals/' if item['schema'] == NATIVE else 'candidates/'
        if not name.startswith(expected):
            raise ValueError('Native proposal incorrectly admitted as a candidate')
        records.append(item)
    proposals = sum(i['schema'] == NATIVE for i in records)
    if len({i['item_id'] for i in records}) != len(records) or m['counts'] != {'records': len(records), 'proposals': proposals, 'candidates': len(records) - proposals}:
        raise ValueError('Native store totals mismatch')
    return records if include_proposals else [i for i in records if i['schema'] != NATIVE]
