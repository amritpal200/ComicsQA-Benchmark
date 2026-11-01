"""Sub-question and contrast manifests; probes are auxiliary, never extra main items."""
from .io import stable


def composition_probes(item):
    old = item['legacy']; proof = old['execution']['proof']
    probes = []
    # Clause-removal checks are useful diagnostic tasks, not human question paraphrases.
    for step in proof['steps']:
        if step['op'] in ('literal', 'var', 'let', 'page', 'ctx'):
            continue
        probes.append({'probe_id': 'probe:' + stable([item['item_id'], step['nid']]),
                       'parent_id': item['item_id'], 'expression': step['expression'],
                       'expected_value': step['value'], 'expected_status': step['status'],
                       'wording': None, 'standalone_program_verified': False,
                       'main_item': False})
    return probes


def composition_metrics(full_scores, probe_scores):
    if set(full_scores) != set(probe_scores):
        raise ValueError('Composition parent sets differ')
    eligible = []
    for parent, full in full_scores.items():
        scores = probe_scores[parent]
        if type(full) is not bool or not scores or any(type(s) is not bool for s in scores):
            raise ValueError('Need Boolean full and nonempty probe outcomes')
        eligible.append((full, all(scores)))
    n = len(eligible)
    return {'items': n,
            'all_steps_correct_full_wrong': sum(not f and p for f, p in eligible) / n if n else None,
            'full_correct_steps_not_all_correct': sum(f and not p for f, p in eligible) / n if n else None,
            'limitation': 'Associations do not by themselves prove a shortcut or causal perception bottleneck.'}


def contrast(first, second, change):
    if first['item_id'] == second['item_id'] or first['split'] != second['split'] or first['chapter_id'] != second['chapter_id']:
        raise ValueError('Contrast needs distinct items in one chapter/split')
    if stable(first['answer']) == stable(second['answer']):
        raise ValueError('Contrast answers must differ')
    if change not in ('one_clause', 'one_page', 'one_mask'):
        raise ValueError('Unsupported contrast change')
    # A label alone does not prove the specified edit; retain as a proposal.
    return {'pair_id': 'pair:' + stable([first['item_id'], second['item_id'], change]),
            'members': [first['item_id'], second['item_id']], 'change': change,
            'edit_verification': 'pending', 'release_status': 'pending'}


def recipe_probes(item, graph, visibility, rich):
    """Private oracle-context diagnostics; not additional benchmark QA items."""
    from comics_qa.tasks.graph.crl.proof_checker import ProofChecker
    from .scan import ScanChecker
    from .admission_store import validate
    validate(item)
    if item.get('proof_engine') not in ('recipe', 'coverage_recipe'):
        return []
    probes = []
    for stage in item['execution']['stages']:
        doc = stage['execution']
        from .membership import MembershipChecker
        check = (MembershipChecker(graph, visibility, rich).check(doc, doc['program']) if stage['engine'] == 'membership' else ProofChecker(graph, visibility, rich=rich).check(doc, doc['program']) if stage['engine'] == 'crl'
                 else ScanChecker(graph, visibility, rich).check(doc))
        if not check['proof_valid']:
            raise ValueError('Invalid standalone recipe probe')
        probes.append({'probe_id': 'probe:' + stable([item['item_id'], stage['name'], stable(doc)]),
                       'parent_id': item['item_id'], 'binding': stage['name'], 'engine': stage['engine'],
                       'program': doc['program'], 'execution_sha256': stable(doc), 'expected_result': doc['result'],
                       'source_snapshots': item['source']['snapshots'], 'proof_check': check,
                       'standalone_program_verified': True, 'wording': None,
                       'input_mode': 'privileged_subproblem', 'oracle_intermediate_bindings': True,
                       'main_item': False, 'release_status': 'pending_wording_and_review',
                       'limitation': 'Literal intermediate pages are oracle inputs to this isolated probe; never provide probes or their answers to the parent task.'})
    return probes
