"""Name-free visual identity references with separately checked predicate proofs."""
import io
from pathlib import Path
from .assets import box_pixels, image_library
from .io import digest, read, stable


def bind_reference(graph, appearance_id, crop_path):
    """Verify actual pixels, original image pin and admitted identity link."""
    nodes = {n['id']: n for n in graph['nodes']}
    app = nodes[appearance_id]; page = nodes[app['page_id']]
    if app['type'] != 'Appearance':
        raise ValueError('Reference must be a character appearance')
    identity = nodes[app['identity_id']]
    if identity['generic']:
        raise ValueError('Page-local unnamed clusters do not establish cross-page identity')
    links = [f for f in graph['facts'] if f['rel'] == 'is_char' and f['args'] == [appearance_id, identity['id']]
             and f['origin'] in ('H', 'V') and f['answer_eligible']]
    if len(links) != 1:
        raise ValueError('Reference identity link not uniquely admitted')
    crop_path = Path(crop_path)
    transform = read(crop_path.with_suffix(crop_path.suffix + '.json'))
    pixels = box_pixels(app['box'], page['width'], page['height'])
    if transform['mode'] != 'crop' or transform['boxes_pixels_half_open'] != [list(pixels)] or transform['source_image_sha256'] != page['image_sha256'] or transform['image_sha256'] != digest(crop_path):
        raise ValueError('Crop manifest differs from identity reference')
    if digest(page['image_path']) != page['image_sha256']:
        raise ValueError('Original reference page changed')
    Image, _ = image_library()
    with Image.open(page['image_path']) as image:
        expected = image.convert('RGB').crop(pixels)
    with Image.open(crop_path) as image:
        actual = image.convert('RGB')
    if actual.size != expected.size or actual.tobytes() != expected.tobytes():
        raise ValueError('Reference crop pixels do not match the annotated depiction')
    return {'appearance_id': appearance_id, 'identity_id': identity['id'],
            'identity_fact_id': links[0]['fact_id'], 'reference_page': app['page_id'],
            'crop_sha256': digest(crop_path), 'crop_path': str(crop_path.resolve()),
            'graph_sha256': stable(graph)}


def predicate(graph, visibility, reference, relation, page_id):
    """Producer uses only legacy interpreter predicate primitives, no new registry."""
    from comics_qa.tasks.graph.crl import Interpreter
    if relation not in ('present', 'speaks_on') or page_id not in graph['page_ids']:
        raise ValueError('Unsupported reference predicate')
    checked_ref = bind_reference(graph, reference['appearance_id'], reference['crop_path'])
    if checked_ref != reference:
        raise ValueError('Visual reference changed')
    engine = Interpreter(graph, visibility)
    r = engine.predicate(relation, reference['identity_id'], page_id)
    return {'schema': 'comics_qa.benchmark1000.visual_predicate.1', 'reference': reference,
            'relation': relation, 'page_id': page_id, 'graph_sha256': stable(graph),
            'visibility_sha256': stable(visibility),
            'result': {'value': r.value, 'status': r.status, 'exact': r.exact},
            'facts': sorted(r.facts | {reference['identity_fact_id']}),
            'certificates': sorted(r.certificates), 'release_status': 'pending_question_gates'}


def check_predicate(graph, visibility, document):
    from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
    try:
        if document['schema'] != 'comics_qa.benchmark1000.visual_predicate.1' or document['graph_sha256'] != stable(graph) or document['visibility_sha256'] != stable(visibility):
            raise ValueError('Visual proof source mismatch')
        ref = document['reference']
        if bind_reference(graph, ref['appearance_id'], ref['crop_path']) != ref:
            raise ValueError('Stale reference')
        if document['relation'] not in ('present', 'speaks_on') or document['page_id'] not in graph['page_ids']:
            raise ValueError('Unknown visual predicate')
        checker = ProofChecker(graph, visibility)
        # Independent checker-owned semantics; never calls producer predicate().
        r = checker.world.predicate(document['relation'], ref['identity_id'], document['page_id'])
        expected = {'value': r.value, 'status': r.status, 'exact': r.exact}
        facts = sorted(r.support['facts'] | {ref['identity_fact_id']})
        if stable(expected) != stable(document['result']) or facts != document['facts'] or sorted(r.support['certificates']) != document['certificates']:
            raise ValueError('Visual predicate claim/support mismatch')
        checker.check_derivations(facts)
        return {'proof_valid': True, 'known': r.status == 'OK'}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {'proof_valid': False, 'error': str(exc)}
