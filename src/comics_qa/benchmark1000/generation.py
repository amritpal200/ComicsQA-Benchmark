"""Additive generation using subclass-local profiles and unchanged independent engines."""
from pathlib import Path
from comics_qa.tasks.graph.gen2.gates import RichGates
from comics_qa.tasks.graph.gen2.quality import configure
from comics_qa.tasks.graph.generation.policy import stable as legacy_stable
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.rich_contract import load_optional
from .adapters import adapt, enrich_frequencies, frequencies
from .families import propose
from .io import publish, stable, digest, separate


class ComposedGates(RichGates):
    # A class-local extension. Neither SPECS nor legacy PROFILE_OPS is modified.
    profile_ops = RichGates.profile_ops | {'first', 'last_app', 'pages_speaking', 'span_after', 'gap', 'chars_on', 'co_present', 'diff'}


def trial(bench_root, chapter, out, budget=20, family_set="composed"):
    root = Path(bench_root).resolve()
    out = separate(out, [root / p for p in ('evidence/ckg', 'evidence/name_visibility', 'evidence/ckg3', 'items/gen1', 'items/gen2')])
    graphs, visibility, rich_root = (root / p for p in ('evidence/ckg/v1', 'evidence/name_visibility/v1', 'evidence/ckg3/v1'))
    g, v, pins = load_world(graphs, visibility, chapter)
    rich = load_optional(graphs, visibility, rich_root, chapter, pins)
    if rich['decisions']:
        raise ValueError('Reviewed rich consumers need explicit new-layer review-aware ablation; not enabled')
    # These are new-layer generation settings; legacy defaults are untouched.
    p = configure({'count_targets': list(range(1, 101)), 'max_candidates_per_chapter': budget})
    gate = ComposedGates(g, v, rich, p, pins)
    candidates, rejected = [], []
    if family_set == 'long-clue':
        from .long_relational import propose as long_propose
        proposals = long_propose(g, budget)
    elif family_set == 'composed':
        proposals = propose(g, v, rich, budget)
    else:
        raise ValueError('Unknown family set')
    for q in proposals:
        old, rejection = gate.assess(q)
        if rejection:
            rejected.append(rejection); continue
        old['item_id'] = 'benchmark1000-composed:' + stable([old['item_id'], q.family])
        old['versions']['generator'] = 'benchmark1000.compositions.1'
        old['verbalization'] = {'mode': 'template', 'version': 'benchmark1000.compositions.1'}
        source = {'record_kind': 'new_composition', 'graph_inputs': pins,
                  'generator': 'benchmark1000.compositions.1'}
        item = enrich_frequencies(adapt(old, source), frequencies(g))
        item['reasoning_structure'] = 'chain'
        item['primary_group'] = 'chain'
        item['verification']['proof'] = 'verified'
        item['reasoning_tags'] = ['cross_page', 'new_composition']
        # Number of operations is not asserted to be meaningful chain depth.
        if family_set == 'long-clue':
            from .long_relational import certify
            certificate = certify(old)
            if not certificate['eligible']:
                rejected.append({'family': q.family, 'gate': 'long_relational', 'reason': 'measured_thresholds_not_met', 'certificate': certificate})
                continue
            item['long_relational_certificate'] = certificate
            item['reasoning_structure'] = 'branch_combine'
            item['primary_group'] = 'branch_combine'
            item['reasoning_tags'].append('long_relational')
            item['complexity'].update({k: certificate[k] for k in ('meaningful_hops', 'branch_count', 'necessary_pages', 'page_span')})
        candidates.append(item)
    report = {'schema': 'comics_qa.benchmark1000.trial.1', 'chapter_id': chapter,
              'pins': pins, 'budget': budget, 'family_set': family_set, 'candidates': candidates,
              'rejections': rejected, 'counts': {'attempted': len(candidates) + len(rejected),
                                               'valid': len(candidates), 'rejected': len(rejected)},
              'release_status': 'pending_wording_and_human_review',
              'limitations': ['Four composition families only', 'No long-relational threshold certification',
                              'No unreviewed panel/order/semantic-mention promotion']}
    publish(out, report)
    return report
