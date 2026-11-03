"""New commands only; all publication is create-only or identical-content resume."""
import argparse
import json
from pathlib import Path
from .io import legacy_snapshot, publish, read, verify_snapshot
from .store import ingest, load


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    snap = sub.add_parser('snapshot')
    snap.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    snap.add_argument('--out', type=Path, required=True)
    check = sub.add_parser('verify-legacy')
    check.add_argument('--snapshot', type=Path, required=True)
    check.add_argument('--repo', type=Path, help='Override snapshot repo location after relocation')
    add = sub.add_parser('import')
    add.add_argument('--source', type=Path, action='append', required=True)
    add.add_argument('--chapter', action='append')
    add.add_argument('--out', type=Path, required=True)
    pool = sub.add_parser('pool-inventory', help='Unify immutable candidates; preserve archived and admitted status')
    pool.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    pool.add_argument('--source', type=Path, action='append')
    pool.add_argument('--source-plan', type=Path)
    pool.add_argument('--policy', type=Path, required=True)
    pool.add_argument('--chapter', action='append')
    pool.add_argument('--out', type=Path, required=True)
    visual_pre = sub.add_parser('visual-preflight', help='Graph-grounded visual identity/crop feasibility')
    visual_pre.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    visual_pre.add_argument('--chapter', action='append')
    visual_pre.add_argument('--min-edge', type=int, default=48)
    visual_pre.add_argument('--quote-budget', type=int, default=128)
    visual_pre.add_argument('--out', type=Path, required=True)
    visual_run = sub.add_parser('visual-pilot', help='Checked four-image options; human fairness review pending')
    visual_run.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    visual_run.add_argument('--preflight', type=Path, required=True)
    visual_run.add_argument('--chapter', action='append')
    visual_run.add_argument('--per-chapter', type=int, default=4)
    visual_run.add_argument('--max-attempts', type=int, default=32)
    visual_run.add_argument('--seed', type=int, default=42)
    visual_run.add_argument('--out', type=Path, required=True)
    visual_check = sub.add_parser('check-visual', help='Independent graph/label/pixel/ablation replay')
    visual_check.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    visual_check.add_argument('--store', type=Path, required=True)
    visual_check.add_argument('--out', type=Path, required=True)
    verify = sub.add_parser('verify-store')
    verify.add_argument('--store', type=Path, required=True)
    verify.add_argument('--include-proposals', action='store_true')
    select_cmd = sub.add_parser('select')
    select_cmd.add_argument('--store', type=Path, required=True)
    select_cmd.add_argument('--policy', type=Path, required=True)
    select_cmd.add_argument('--proof-report', type=Path)
    select_cmd.add_argument('--feature-report', type=Path)
    select_cmd.add_argument('--pilot', action='store_true')
    select_cmd.add_argument('--backend', choices=['reference', 'cp-sat'], default='reference')
    select_cmd.add_argument('--seconds', type=float, default=20)
    select_cmd.add_argument('--max-search-nodes', type=int, default=100000)
    select_cmd.add_argument('--out', type=Path, required=True)
    pre = sub.add_parser('preflight')
    pre.add_argument('--store', type=Path)
    pre.add_argument('--graphs', type=Path)
    pre.add_argument('--chapter', action='append')
    pre.add_argument('--max-states', type=int, default=10000)
    pre.add_argument('--out', type=Path, required=True)
    proofs = sub.add_parser('check-proofs')
    proofs.add_argument('--store', type=Path, required=True)
    proofs.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    proofs.add_argument('--out', type=Path, required=True)
    trial = sub.add_parser('trial')
    trial.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    trial.add_argument('--chapter', required=True)
    trial.add_argument('--budget', type=int, default=20)
    trial.add_argument('--families', choices=['composed', 'long-clue'], default='composed')
    trial.add_argument('--out', type=Path, required=True)
    review = sub.add_parser('review-page')
    review.add_argument('--store', type=Path, required=True)
    review.add_argument('--include-proposals', action='store_true')
    review.add_argument('--out', type=Path, required=True)
    pack = sub.add_parser('pack')
    pack.add_argument('--store', type=Path, required=True)
    pack.add_argument('--item-id', required=True)
    pack.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    pack.add_argument('--out', type=Path, required=True)
    render = sub.add_parser('render')
    render.add_argument('--image', type=Path, required=True)
    render.add_argument('--sha256', required=True)
    render.add_argument('--boxes', required=True, help='JSON list of pixel boxes')
    render.add_argument('--mode', choices=['crop', 'mask'], required=True)
    render.add_argument('--out', type=Path, required=True)
    sample = sub.add_parser('sample-review')
    sample.add_argument('--store', type=Path, required=True)
    sample.add_argument('--size', type=int, required=True)
    sample.add_argument('--seed', type=int, default=42)
    sample.add_argument('--out', type=Path, required=True)
    decisions = sub.add_parser('check-reviews')
    decisions.add_argument('--store', type=Path, required=True)
    decisions.add_argument('--include-proposals', action='store_true')
    decisions.add_argument('--decisions', type=Path, required=True)
    decisions.add_argument('--out', type=Path, required=True)
    infer_cmd = sub.add_parser('infer')
    infer_cmd.add_argument('--pack', type=Path, required=True)
    infer_cmd.add_argument('--model', required=True)
    infer_cmd.add_argument('--endpoint', required=True, help='Full chat/completions URL')
    infer_cmd.add_argument('--max-tokens', type=int, default=2048)
    infer_cmd.add_argument('--dry-run', action='store_true')
    infer_cmd.add_argument('--out', type=Path, required=True)
    scan = sub.add_parser('scan')
    scan.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    scan.add_argument('--chapter', required=True)
    scan.add_argument('--program', type=Path, required=True, help='New-layer scan JSON program file')
    scan.add_argument('--out', type=Path, required=True)
    calibration = sub.add_parser('calibrate')
    calibration.add_argument('--labels', type=Path, required=True)
    calibration.add_argument('--out', type=Path, required=True)
    freeze = sub.add_parser('freeze-policy')
    freeze.add_argument('--policy', type=Path, required=True)
    freeze.add_argument('--preflight', type=Path, required=True)
    freeze.add_argument('--out', type=Path, required=True)
    feature_audit = sub.add_parser('audit-features')
    feature_audit.add_argument('--store', type=Path, required=True)
    feature_audit.add_argument('--out', type=Path, required=True)
    semantic = sub.add_parser('semantic-preflight')
    semantic.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    semantic.add_argument('--chapter', action='append')
    semantic.add_argument('--reuse-from', type=Path, help='Revalidate completed semantic checkpoints into a fresh output')
    semantic.add_argument('--per-pattern', type=int, default=4)
    semantic.add_argument('--max-ablation-pages', type=int, default=8)
    semantic.add_argument('--clue-search', type=int, default=2000)
    semantic.add_argument('--out', type=Path, required=True)
    native = sub.add_parser('import-native')
    native.add_argument('--records', type=Path, required=True, help='JSON list of native proposal records')
    native.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    native.add_argument('--base-store', type=Path)
    native.add_argument('--out', type=Path, required=True)
    admit = sub.add_parser('admit-native', help='Validate saved native proposals without regenerating them')
    admit.add_argument('--semantic-root', '--proposal-root', dest='semantic_root', type=Path, required=True)
    admit.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    admit.add_argument('--alias-reviews', type=Path)
    admit.add_argument('--chapter', action='append')
    admit.add_argument('--max-ablation-pages', type=int, default=8)
    admit.add_argument('--out', type=Path, required=True)
    score_contrast = sub.add_parser('score-contrast', help='Exact member and both-correct contrast scores')
    score_contrast.add_argument('--store', type=Path, required=True)
    score_contrast.add_argument('--predictions', type=Path, required=True)
    score_contrast.add_argument('--out', type=Path, required=True)
    qcheck = sub.add_parser('check-qwen-packs', help='Independently verify task packs and exact source pixels')
    qcheck.add_argument('--store', type=Path, required=True)
    qcheck.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    qcheck.add_argument('--out', type=Path, required=True)
    qp = sub.add_parser('prepare-qwen-packs', help='Task-specific native/legacy paraphrase or sentence synthesis packs')
    qp.add_argument('--source', type=Path, required=True)
    qp.add_argument('--mode', choices=['paraphrase','synthesis'], default='paraphrase')
    qp.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    qp.add_argument('--chapter', action='append')
    qp.add_argument('--max-pack-bytes', type=int, default=1000000)
    qp.add_argument('--max-images', type=int, default=16)
    qp.add_argument('--crop-scope', choices=['full-page','proof-union'], default='full-page')
    qp.add_argument('--out', type=Path, required=True)
    qm = sub.add_parser('qwen-model-info', help='Inspect local checkpoint/processor metadata without weights or inference')
    qm.add_argument('--model-path', type=Path, required=True)
    qm.add_argument('--out', type=Path, required=True)
    qr = sub.add_parser('prepare-qwen-requests', help='Exact offline processor token/image preflight; no HTTP')
    qr.add_argument('--packs', type=Path, required=True)
    qr.add_argument('--runtime', type=Path, required=True)
    qr.add_argument('--limit', type=int, default=2)
    qr.add_argument('--out', type=Path, required=True)
    qrun = sub.add_parser('run-qwen', help='Bounded resumable endpoint client; only explicit runtime settings')
    qrun.add_argument('--requests', type=Path, required=True)
    qrun.add_argument('--max-requests', type=int, default=2)
    qrun.add_argument('--shard-index', type=int, default=0)
    qrun.add_argument('--shards', type=int, default=1)
    qrun.add_argument('--dry-run', action='store_true')
    qrun.add_argument('--retry-ambiguous', action='store_true')
    qrun.add_argument('--out', type=Path, required=True)
    qi = sub.add_parser('ingest-qwen', help='Independently check raw generated question semantics and sentence facts')
    qi.add_argument('--requests', type=Path, required=True)
    qi.add_argument('--responses', type=Path, required=True)
    qi.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    qi.add_argument('--out', type=Path, required=True)
    sentences = sub.add_parser('prepare-sentences', help='Prove private atomic claims before sentence synthesis')
    sentences.add_argument('--source', type=Path, required=True)
    sentences.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    sentences.add_argument('--chapter', action='append')
    sentences.add_argument('--out', type=Path, required=True)
    sentence_check = sub.add_parser('check-sentences', help='Independently verify all executable sentence-plan claims')
    sentence_check.add_argument('--store', type=Path, required=True)
    sentence_check.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    sentence_check.add_argument('--out', type=Path, required=True)
    sentence_score = sub.add_parser('score-sentences', help='Proof-backed controlled-claim response scoring; no LLM judge')
    sentence_score.add_argument('--store', type=Path, required=True)
    sentence_score.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    sentence_score.add_argument('--responses', type=Path, required=True)
    sentence_score.add_argument('--out', type=Path, required=True)
    contrast = sub.add_parser('contrast-pilot', help='Independently admitted one-clause contrast pairs')
    contrast.add_argument('--source', type=Path, required=True)
    contrast.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    contrast.add_argument('--chapter', action='append')
    contrast.add_argument('--per-chapter', type=int, default=2)
    contrast.add_argument('--max-variants', type=int, default=8)
    contrast.add_argument('--max-ablation-pages', type=int, default=16)
    contrast.add_argument('--out', type=Path, required=True)
    branch = sub.add_parser('branch-pilot', help='Necessary parallel chains and long-relational graph questions')
    branch.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    branch.add_argument('--chapter', action='append')
    branch.add_argument('--per-family', type=int, default=3)
    branch.add_argument('--search-budget', type=int, default=1000)
    branch.add_argument('--window', type=int, default=10)
    branch.add_argument('--min-window', type=int, default=4)
    branch.add_argument('--max-shift', type=int, default=20)
    branch.add_argument('--probe-budget', type=int, default=192)
    branch.add_argument('--dependency-budget', type=int, default=128)
    branch.add_argument('--max-steps', type=int, choices=[2,3], default=3)
    branch.add_argument('--out', type=Path, required=True)
    family = sub.add_parser('family-pilot', help='Bounded target-first expanded-family proposal pilot')
    family.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    family.add_argument('--chapter', action='append')
    family.add_argument('--per-family', type=int, default=3)
    family.add_argument('--max-executions', type=int, default=9)
    family.add_argument('--search-budget', type=int, default=1000)
    family.add_argument('--window', type=int, default=10)
    family.add_argument('--out', type=Path, required=True)
    alias_packet = sub.add_parser('alias-review-page', help='Private visual packet; no alias approval')
    alias_packet.add_argument('--requests', type=Path, required=True)
    alias_packet.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    alias_packet.add_argument('--max-evidence', type=int, default=3)
    alias_packet.add_argument('--out', type=Path, required=True)
    for name in ('coverage-pilot', 'switch-pilot'):
        coverage = sub.add_parser(name, help='Bounded candidate-specific provable-window search')
        coverage.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
        coverage.add_argument('--chapter', action='append')
        coverage.add_argument('--per-family', type=int, default=3)
        coverage.add_argument('--max-executions', type=int, default=9)
        coverage.add_argument('--search-budget', type=int, default=1000)
        coverage.add_argument('--window', type=int, default=10)
        coverage.add_argument('--min-window', type=int, default=4)
        coverage.add_argument('--max-shift', type=int, default=20)
        coverage.add_argument('--probe-budget', type=int, default=192)
        coverage.add_argument('--max-windows', type=int, default=4)
        coverage.add_argument('--out', type=Path, required=True)
        if name == 'switch-pilot':
            coverage.add_argument('--dependency-budget', type=int, default=128)
    diagnosis = sub.add_parser('diagnose-families', help='Replay bounded failed recipes without generating questions')
    diagnosis.add_argument('--source', type=Path, required=True)
    diagnosis.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    diagnosis.add_argument('--chapter', action='append')
    diagnosis.add_argument('--family', action='append')
    diagnosis.add_argument('--max-queries', type=int, default=12)
    diagnosis.add_argument('--out', type=Path, required=True)
    story_pilot = sub.add_parser('story-pilot', help='Story families without page numbers (quote attribution, quote order)')
    story_pilot.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    story_pilot.add_argument('--chapter', action='append')
    story_pilot.add_argument('--per-family', type=int, default=12)
    story_pilot.add_argument('--out', type=Path, required=True)
    story_check = sub.add_parser('check-story', help='Independent re-check of every story item against the evidence')
    story_check.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    story_check.add_argument('--store', type=Path, required=True)
    story_check.add_argument('--out', type=Path, required=True)
    ev_prep = sub.add_parser('prepare-events', help='Event statements + outlined/control panel images from grounded captions')
    ev_prep.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    ev_prep.add_argument('--grounding', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark/annotations/magi3_grounding_recovery_v1'))
    ev_prep.add_argument('--chapter', action='append')
    ev_prep.add_argument('--out', type=Path, required=True)
    ev_run = sub.add_parser('verify-events', help='Resumable yes/no answers from an independent VLM endpoint')
    ev_run.add_argument('--requests', type=Path, required=True)
    ev_run.add_argument('--endpoint', default='http://localhost:18101/v1')
    ev_run.add_argument('--model', default='internvl3-14b')
    ev_run.add_argument('--workers', type=int, default=16)
    ev_run.add_argument('--limit', type=int)
    ev_run.add_argument('--out', type=Path, required=True)
    ev_in = sub.add_parser('ingest-events', help='Accept positive=yes and control=no; write facts and audit sample')
    ev_in.add_argument('--requests', type=Path, required=True)
    ev_in.add_argument('--responses', type=Path, required=True)
    ev_in.add_argument('--out', type=Path, required=True)
    ev_audit = sub.add_parser('record-event-audit', help='Record correct/wrong for the event audit sample; pass/fail')
    ev_audit.add_argument('--facts', type=Path, required=True)
    ev_audit.add_argument('--decisions', type=Path, required=True)
    ev_audit.add_argument('--max-errors', type=int, default=3)
    ev_audit.add_argument('--out', type=Path, required=True)
    ev_pilot = sub.add_parser('event-pilot', help='Event question families from audited event facts')
    ev_pilot.add_argument('--bench-root', type=Path, default=Path('/data/151-3/comics/ComicsQA_Benchmark'))
    ev_pilot.add_argument('--facts', type=Path, required=True)
    ev_pilot.add_argument('--audit', type=Path, required=True)
    ev_pilot.add_argument('--chapter', action='append')
    ev_pilot.add_argument('--per-family', type=int, default=8)
    ev_pilot.add_argument('--out', type=Path, required=True)
    story = sub.add_parser('story-profile', help='Content category/anchor/wording profile and gap to story targets (read-only)')
    story.add_argument('--store', type=Path, action='append', required=True)
    story.add_argument('--targets', type=Path, default=Path(__file__).resolve().parents[3] / 'configs/benchmark1000/story_targets_v1.json')
    story.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if hasattr(args, 'out'):
            from .io import separate
            protected = [value for name, value in vars(args).items() if name not in ('out', 'bench_root', 'repo') and isinstance(value, Path)]
            import os
            protected.append(getattr(args, 'bench_root', Path(os.environ.get('BENCH_ROOT', '/data/151-3/comics/ComicsQA_Benchmark'))) / 'core')
            separate(args.out, protected)
        if args.command == 'visual-preflight':
            from .visual_jobs import preflight
            report = preflight(args.bench_root,args.out,args.chapter,args.min_edge,args.quote_budget)
            result = {'output':str(args.out),'chapters':report['chapters'],'unique_verified_target_ids':report['unique_verified_target_ids'],'release_status':'not_approved'}
        elif args.command == 'visual-pilot':
            from .visual_jobs import pilot
            report = pilot(args.bench_root,args.preflight,args.out,args.chapter,args.per_chapter,args.max_attempts,args.seed)
            result = {'output':str(args.out),**report}
        elif args.command == 'check-visual':
            from .visual_jobs import verify_pilot
            result = verify_pilot(args.bench_root,args.store)
            publish(args.out,result)
            result = {'output':str(args.out),'verified':result['verified'],'rejected':result['rejected'],'human_review':'pending'}
        elif args.command == 'pool-inventory':
            from .pool import run
            from .io import member
            sources = args.source
            if sources is not None and args.source_plan is not None:raise ValueError('Choose explicit sources or a source plan')
            if sources is None:
                plan = read(args.source_plan or Path(__file__).resolve().parents[3] / 'configs/benchmark1000/pool_sources_v1.json')
                if plan['version'] != 'benchmark1000.pool_sources.1': raise ValueError('Unknown source plan')
                sources = [member(args.bench_root, p) for p in plan['sources']]
            report = run(sources, args.out, read(args.policy), args.chapter)
            result = {'output': str(args.out), **report['counts'], 'release_status': 'not_approved'}
        elif args.command == 'admit-native':
            from .admission_store import run
            report = run(args.semantic_root, args.bench_root, args.out, args.alias_reviews, args.chapter, args.max_ablation_pages)
            result = {'output': str(args.out), **report['counts'], 'release_status': report['release_status']}
        elif args.command == 'alias-review-page':
            from .alias_packet import create
            result = create(args.requests, args.bench_root, args.out, args.max_evidence)
        elif args.command == 'story-pilot':
            from .story_families import run as story_run
            report = story_run(args.bench_root, args.out, args.chapter, {'per_family': args.per_family})
            result = {'output': str(args.out), 'candidates': report['candidates'], 'families': report['families'],
                      'rejected': report['rejected'], 'release_status': 'not_approved'}
        elif args.command == 'check-story':
            from .story_families import recheck
            report = recheck(args.bench_root, args.store)
            publish(args.out, report)
            result = {'output': str(args.out), 'verified': report['verified'], 'rejected': report['rejected']}
        elif args.command == 'prepare-events':
            from .events import prepare as prepare_events
            result = {'output': str(args.out), **prepare_events(args.bench_root, args.grounding, args.out, args.chapter)}
        elif args.command == 'verify-events':
            from .events import verify as verify_events
            result = {'output': str(args.out), **verify_events(args.requests, args.endpoint, args.model, args.out, args.workers, args.limit)}
        elif args.command == 'ingest-events':
            from .events import ingest as ingest_events
            report = ingest_events(args.requests, args.responses, args.out)
            result = {'output': str(args.out), 'requests': report['requests'], 'accepted': report['accepted'], 'outcomes': report['outcomes']}
        elif args.command == 'record-event-audit':
            from .story_events import record_audit
            result = {'output': str(args.out), **record_audit(args.facts, args.decisions, args.out, args.max_errors)}
        elif args.command == 'event-pilot':
            from .story_events import run as event_run
            report = event_run(args.bench_root, args.facts, args.audit, args.out, args.chapter, {'per_family': args.per_family})
            result = {'output': str(args.out), 'candidates': report['candidates'], 'families': report['families'], 'rejected': report['rejected']}
        elif args.command == 'story-profile':
            from .story_profile import run as profile_run
            report = profile_run(args.store, args.targets, args.out)
            result = {'output': str(args.out), 'candidates': report['summary']['candidates'],
                      'total_shortfall_natural': report['summary']['total_shortfall_natural'], 'release_status': 'not_approved'}
        elif args.command == 'diagnose-families':
            from .diagnose_families import run
            report = run(args.source, args.bench_root, args.out, args.chapter, args.max_queries, args.family)
            result = {k: report[k] for k in ('eligible_queries', 'replayed_queries', 'truncated', 'coverage_changes')}
            result['output'] = str(args.out)
        elif args.command in ('coverage-pilot', 'switch-pilot'):
            from .family_pilot import run
            report = run(args.bench_root, args.out, args.chapter, args.per_family, args.max_executions, args.search_budget, args.window, True, args.min_window, args.max_shift, args.probe_budget, args.max_windows, getattr(args, 'dependency_budget', None))
            result = {'output': str(args.out), **report['counts'], 'families': report['families'], 'release_status': 'not_approved'}
        elif args.command == 'score-contrast':
            from .contrast import score
            from .io import separate
            separate(args.out,[args.store,args.predictions])
            result = score(load(args.store),read(args.predictions))
            publish(args.out,result)
            result = {'output':str(args.out),**{k:v for k,v in result.items() if k != 'scores'}}
        elif args.command == 'check-qwen-packs':
            from .qwen_packs import verify
            from .io import separate
            separate(args.out,[args.store,args.bench_root / 'core',args.bench_root / 'evidence'])
            report = verify(args.store,args.bench_root)
            publish(args.out,report)
            result = {'output':str(args.out),**{k:v for k,v in report.items() if k != 'items'}}
        elif args.command == 'prepare-qwen-packs':
            from .qwen_packs import run
            result = {'output':str(args.out),**run(args.source,args.bench_root,args.out,args.mode,args.chapter,args.max_pack_bytes,args.max_images,args.crop_scope)}
        elif args.command == 'qwen-model-info':
            from .qwen_runtime import metadata
            from .io import separate
            separate(args.out,[args.model_path])
            report = metadata(args.model_path)
            publish(args.out,report)
            result = {'output':str(args.out),'status':report['status']}
        elif args.command == 'prepare-qwen-requests':
            from .qwen_jobs import prepare
            result = {'output':str(args.out),**prepare(args.packs,args.runtime,args.out,args.limit)}
        elif args.command == 'run-qwen':
            from .qwen_jobs import run
            result = {'output':str(args.out),**run(args.requests,args.out,args.max_requests,args.shard_index,args.shards,args.dry_run,args.retry_ambiguous)}
        elif args.command == 'ingest-qwen':
            from .qwen_validation import ingest as ingest_qwen
            result = {'output':str(args.out),**ingest_qwen(args.requests,args.responses,args.bench_root,args.out)}
        elif args.command == 'prepare-sentences':
            from .sentence_plans import run
            report = run(args.source,args.bench_root,args.out,args.chapter)
            result = {'output':str(args.out),**report}
        elif args.command == 'check-sentences':
            from .sentence_plans import verify
            from .io import separate
            separate(args.out,[args.store])
            report = verify(args.store,args.bench_root)
            publish(args.out,report)
            result = {'output':str(args.out),**{k:v for k,v in report.items() if k != 'items'}}
        elif args.command == 'score-sentences':
            from .sentence_scoring import batch
            from .io import separate
            separate(args.out,[args.store,args.responses])
            report = batch(args.store,args.bench_root,args.responses)
            publish(args.out,report)
            result = {'output':str(args.out),**{k:v for k,v in report.items() if k != 'items'}}
        elif args.command == 'contrast-pilot':
            from .contrast_pilot import run
            report = run(args.source,args.bench_root,args.out,args.chapter,args.per_chapter,args.max_variants,args.max_ablation_pages)
            result = {'output':str(args.out),**report}
        elif args.command == 'branch-pilot':
            from .branch_pilot import run
            report = run(args.bench_root,args.out,args.chapter,args.per_family,args.search_budget,args.window,args.min_window,args.max_shift,args.probe_budget,args.dependency_budget,args.max_steps)
            result = {'output':str(args.out),**report}
        elif args.command == 'family-pilot':
            from .family_pilot import run
            report = run(args.bench_root, args.out, args.chapter, args.per_family, args.max_executions, args.search_budget, args.window)
            result = {'output': str(args.out), **report['counts'], 'families': report['families'], 'release_status': 'not_approved'}
        elif args.command == 'snapshot':
            result = {'repo': str(args.repo.resolve()), 'files': legacy_snapshot(args.repo)}
            publish(args.out, result)
            result = {'snapshot': str(args.out), 'files': len(result['files'])}
        elif args.command == 'verify-legacy':
            saved = read(args.snapshot)
            verify_snapshot(args.repo or saved['repo'], saved['files'])
            result = {'legacy': 'unchanged', 'files': len(saved['files'])}
        elif args.command == 'import':
            report = ingest(args.source, args.out, args.chapter)
            result = {'store': str(args.out), **report['counts'], 'release': report['release_status']}
        elif args.command == 'verify-store':
            result = {'store': 'verified', ('records' if args.include_proposals else 'candidates'): len(load(args.store, include_proposals=args.include_proposals))}
        elif args.command == 'select':
            from .selection import select
            from .io import separate, digest
            separate(args.out, [args.store, args.policy])
            from .views import apply
            items = apply(load(args.store), digest(args.store / 'manifest.json'),
                          read(args.proof_report) if args.proof_report else None,
                          read(args.feature_report) if args.feature_report else None)
            if args.backend == 'cp-sat':
                from .solver import select_cp
                _, result = select_cp(items, read(args.policy), args.pilot, args.seconds)
            else:
                _, result = select(items, read(args.policy), args.pilot, args.max_search_nodes)
            result['store_manifest_sha256'] = digest(args.store / 'manifest.json')
            result['proof_report_sha256'] = digest(args.proof_report) if args.proof_report else None
            result['feature_report_sha256'] = digest(args.feature_report) if args.feature_report else None
            publish(args.out, result)
        elif args.command == 'preflight':
            from .preflight import pool_report, inspect_graphs
            from .io import separate
            if not args.store and not args.graphs:
                raise ValueError('Supply --store and/or --graphs')
            separate(args.out, [p for p in (args.store, args.graphs) if p])
            result = {}
            if args.store:
                result['pool'] = pool_report(load(args.store))
            if args.graphs:
                result['graphs'] = inspect_graphs(args.graphs, args.chapter, args.max_states)
            publish(args.out, result)
        elif args.command == 'check-proofs':
            from .verification import revalidate
            from .io import separate, digest
            separate(args.out, [args.store, args.bench_root / 'evidence/ckg', args.bench_root / 'evidence/name_visibility', args.bench_root / 'evidence/ckg3'])
            result = revalidate(load(args.store), args.bench_root)
            result['store_manifest_sha256'] = digest(args.store / 'manifest.json')
            publish(args.out, result)
        elif args.command == 'trial':
            from .generation import trial
            report = trial(args.bench_root, args.chapter, args.out, args.budget, args.families)
            result = {'output': str(args.out), **report['counts'], 'release': report['release_status']}
        elif args.command == 'review-page':
            from .review_ui import page
            from .assets import binary_publish
            from .io import separate
            separate(args.out, [args.store])
            items = load(args.store, include_proposals=args.include_proposals)
            binary_publish(args.out, page(items).encode())
            result = {'output': str(args.out), 'items': len(items), 'approval': 'none'}
        elif args.command == 'pack':
            from .packs import prepare, hydrate
            from .io import separate
            from comics_qa.tasks.graph.crl.artifacts import load_world
            from comics_qa.tasks.graph.crl.rich_contract import load_optional
            separate(args.out, [args.store, args.bench_root / 'evidence/ckg', args.bench_root / 'evidence/name_visibility', args.bench_root / 'evidence/ckg3'])
            matches = [i for i in load(args.store) if i['item_id'] == args.item_id]
            if len(matches) != 1:
                raise ValueError('Unknown or ambiguous item ID')
            item = matches[0]; r = args.bench_root
            if item.get('schema') in ('comics_qa.benchmark1000.admitted_native.1','comics_qa.benchmark1000.contrast_member.1'):
                raise ValueError('Native MN5 pack/export integration is pending; use review-page for admitted candidates')
            g, v, pins = load_world(r / 'evidence/ckg/v1', r / 'evidence/name_visibility/v1', item['chapter_id'])
            rich = load_optional(r / 'evidence/ckg/v1', r / 'evidence/name_visibility/v1', r / 'evidence/ckg3/v1', item['chapter_id'], pins) if item['legacy']['execution'].get('rich_evidence_sha256') is not None else None
            pack = hydrate(prepare(item), g, rich, v, pins)
            publish(args.out, pack)
            result = {'output': str(args.out), 'pack_id': pack['pack_id'], 'status': pack['validation_status']}
        elif args.command == 'render':
            from .assets import render
            result = render(args.image, args.sha256, json.loads(args.boxes), args.out, args.mode)
        elif args.command == 'sample-review':
            from .review import sample
            from .io import separate
            separate(args.out, [args.store])
            result = sample(load(args.store), args.size, args.seed)
            publish(args.out, result)
        elif args.command == 'check-reviews':
            from .review import validate_decision
            from .io import separate
            separate(args.out, [args.store, args.decisions])
            items = {i['item_id']: i for i in load(args.store, include_proposals=args.include_proposals)}
            rows = read(args.decisions)
            if not isinstance(rows, list):
                raise ValueError('Review file must be a list')
            validated = [validate_decision(items[d['item_id']], d) for d in rows]
            result = {'records': validated, 'valid_records': len(validated),
                      'human_records': sum(d['reviewer_type'] == 'human' for d in validated),
                      'release_status': 'not_approved_by_ingestion'}
            publish(args.out, result)
        elif args.command == 'infer':
            import os
            from .transport import request, infer
            from .io import separate
            separate(args.out, [args.pack])
            payload = request(read(args.pack), args.model, args.max_tokens)
            if args.dry_run:
                result = {'endpoint': args.endpoint, 'payload': payload, 'status': 'not_inferred'}
                publish(args.out, result)
                result = {'output': str(args.out), 'status': 'not_inferred', 'model': args.model}
            else:
                result = infer(payload, args.endpoint, args.out, api_key=os.environ.get('BENCHMARK1000_API_KEY'))
                result = {'output': str(args.out), 'request_sha256': result['request_sha256'], 'validation_status': 'pending'}
        elif args.command == 'scan':
            from .scan import ScanEngine, ScanChecker
            from comics_qa.tasks.graph.crl.artifacts import load_world
            from comics_qa.tasks.graph.crl.rich_contract import load_optional
            from .io import separate
            root = args.bench_root
            separate(args.out, [args.program, root / 'evidence/ckg', root / 'evidence/name_visibility', root / 'evidence/ckg3'])
            g, v, pins = load_world(root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1', args.chapter)
            rich = load_optional(root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1', root / 'evidence/ckg3/v1', args.chapter, pins)
            document = ScanEngine(g, v, rich).execute(read(args.program))
            check = ScanChecker(g, v, rich).check(document)
            if not check['proof_valid']:
                raise ValueError('Scan producer/checker mismatch: ' + str(check))
            publish(args.out, {'execution': document, 'check': check, 'pins': pins})
            result = {'output': str(args.out), 'result': document['result'], 'check': check}
        elif args.command == 'calibrate':
            from .calibration import agreement
            result = agreement(read(args.labels))
            publish(args.out, result)
        elif args.command == 'freeze-policy':
            from .freeze import freeze
            from .io import digest
            p, lineage = freeze(read(args.policy), read(args.preflight))
            lineage['preflight_sha256'] = digest(args.preflight)
            publish(args.out, p)
            publish(args.out.with_suffix(args.out.suffix + '.provenance.json'), lineage)
            result = {'output': str(args.out), 'split_counts': p['split_counts'], 'feasibility': lineage['feasibility']}
        elif args.command == 'audit-features':
            from .views import feature_audit
            from .io import digest
            report = feature_audit(load(args.store), digest(args.store / 'manifest.json'))
            publish(args.out, report)
            result = {'output': str(args.out), **report['counts'], 'offset_distribution': report['offset_distribution']}
        elif args.command == 'semantic-preflight':
            from .semantic import run
            report = run(args.bench_root, args.out, args.chapter, args.per_pattern, args.max_ablation_pages, args.clue_search, args.reuse_from)
            result = {'output': str(args.out), **report['counts'], 'native_store': report['native_store']['counts'], 'release_status': report['release_status']}
        elif args.command == 'import-native':
            from .native import validate as validate_native, check_answer
            from .native_store import write as write_native
            from .io import separate, digest, stable
            from comics_qa.tasks.graph.crl.artifacts import load_world
            from comics_qa.tasks.graph.crl.rich_contract import load_optional
            root = args.bench_root
            protected = [args.records, root / 'evidence/ckg', root / 'evidence/name_visibility', root / 'evidence/ckg3'] + ([args.base_store] if args.base_store else [])
            separate(args.out, protected)
            records = read(args.records)
            if not isinstance(records, list):
                raise ValueError('Native import needs a JSON list')
            worlds = {}
            for item in records:
                validate_native(item)
                cid = item['chapter_id']; needs_rich = item['source']['snapshots']['rich'] != stable(None)
                key = (cid, needs_rich)
                if key not in worlds:
                    g, v, pins = load_world(root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1', cid)
                    r = load_optional(root / 'evidence/ckg/v1', root / 'evidence/name_visibility/v1', root / 'evidence/ckg3/v1', cid, pins) if needs_rich else None
                    worlds[key] = g, v, r, pins
                g, v, r, pins = worlds[key]
                def roles(mapping):
                    return {str(p).split('/evidence/', 1)[1]: sha for p, sha in mapping.items() if '/evidence/' in str(p)}
                if roles(pins) != roles(item['source']['pins']):
                    raise ValueError('Native imported source pins differ')
                checked = check_answer(item, g, v, r)
                if item['verification']['proof'] == 'verified' and not checked['answer_supported']:
                    raise ValueError('Native claimed proof fails independent rechecking')
            config = {'source_records_sha256': digest(args.records), 'base_store_sha256': digest(args.base_store / 'manifest.json') if args.base_store else None}
            combined = (load(args.base_store) if args.base_store else []) + records
            manifest = write_native(combined, args.out, config, protected)
            result = {'output': str(args.out), **manifest['counts'], 'release_status': 'pending'}
        # Verbose evidence stays in the artifact; terminal output is a summary.
        if args.command == 'select':
            result = {'output': str(args.out), 'status': result['status'], 'backend': result.get('backend', 'reference'), 'mode': result['mode'], 'selected': len(result.get('selected_ids', [])), 'release_status': result['release_status']}
        if args.command == 'check-proofs':
            result = {k: v for k, v in result.items() if k != 'items'}
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
        parser.exit(2, 'benchmark1000: ' + str(exc) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
