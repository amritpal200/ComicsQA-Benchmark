"""Optional CKG-3 proof transport. Query semantics live separately in each engine."""
import hashlib
import json


def fingerprint(rich):
    return hashlib.sha256(json.dumps(rich, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest() if rich is not None else None


def prepare(graph, visibility, rich):
    if rich is None:
        return [], []
    from comics_qa.evidence.graph.rich.model import build
    if rich != build(graph, visibility, rich['sources'], rich['decisions']):
        raise ValueError('CKG-3 companion fails derivation validation')
    facts = []
    for f in rich['facts']:
        if f['rel'] not in ('transcript', 'name_occurs') or not f['answer_eligible'] or f['origin'] != 'V':
            continue
        # The immutable rich artifact carries the underlying alignment/review
        # premises; these virtual source facts retain its original stable IDs.
        facts.append({'fact_id': f['id'], 'rel': f['rel'], 'args': f['args'], 'origin': 'V',
                      'derivation': 'S', 'premises': [], 'page_ids': [f['page_id']],
                      'answer_eligible': True, 'rich_premises': f['premises']})
    certs = [{**c, 'coverage_id': c['id'], 'family': 'rich_ocr'} for c in rich['coverage'] if c['family'] == 'ocr']
    return facts, certs


def load_optional(graphs, visibility, root, chapter, sources):
    if root is None:
        return None
    from pathlib import Path
    from comics_qa.evidence.graph.rich.loader import load_rich
    rich = load_rich(graphs, visibility, root, chapter)
    for name in ('manifest.json', 'chapters/' + chapter + '.json'):
        p = Path(root).resolve() / name
        sources[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return rich
