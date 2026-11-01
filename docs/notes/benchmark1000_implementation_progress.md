# benchmark1000 implementation progress

Date: 2026-10-30. This records actual implementation and bounded checks, not completion of the full P00–P16 plan.

## Additive boundary

All implementation is under `src/comics_qa/benchmark1000/`, new `configs/benchmark1000/`, `scripts/benchmark1000*`, and `tests/benchmark1000/`. Only coordination/planning documentation was updated outside those new namespaces. Existing graph builders, CRL registry/interpreter/checker, GEN/VERB scripts, policies and outputs remain unchanged.

A baseline captured at the start is preserved in `configs/benchmark1000/legacy_baseline_v1.json`: all 142 legacy implementation files still match. The initial temporary snapshot accidentally included the newly added launcher; only that new file was excluded to obtain the actual legacy baseline. The original temporary snapshot is retained.

## Implemented and checked

- P00/P01 foundation: versioned policy template; source-relative code snapshot; safe read-only GEN-1/GEN-2 adapters; immutable candidate store with manifest/hash checks, importer code pins, exclusive writer lock, checkpoint resume and separate policy/review status.
- P02 selector: bounded exact reference search and optional scalable CP-SAT, independently checked constraints, semantic dedup with intentional pair preservation, per-split shortcut metrics, absolute small-pool limits, final complexity/claim/edit requirements and explicit infeasible/unknown statuses. Initial final split counts are derived only from a full inventory via a separate frozen policy; original policy files stay unchanged.
- P03 tooling: bounded structural graph inventory and retained-pool distributions with truncation and unknown meaningful-depth/yield fields. Semantic path/branch feasibility and full collection coverage are not established.
- Additional implemented primitives: four composed CRL family templates; target-first long-clue proposals with necessity/three-page certificates; new independently checked next-speaking/joint and last-presence scans; pure reviewed evidence overlays and positive-witness checks; exact crop/mask rendering; conservative mask dependency invalidation; name-free visual reference/predicate proofs; claim contracts and supplied-label scoring; task-specific hydrated packs; raw endpoint transport with dry-run/resume; private review HTML and snapshot-bound decisions; review sampling/bounds; exact/pair/evidence/composition metrics; judge calibration metrics; guarded export preparation.

These primitives are not all integrated or certified as complete question-generation/release tracks. In particular, the new store currently imports legacy-shaped records; native scan/sentence/asset admission and reviewed release views still need implementation. The README capability ledger identifies all remaining stage work.

## Verification evidence

- **59 new-layer CPU tests passed** in `/tmp/benchmark1000-dev-env`, with Pillow and OR-Tools installed only in that isolated uv environment. The suite exercises source corruption/overlap, immutable resume, solver/reference agreement, source/format/complexity policy failures, wrong/missing/reordered proofs, uncertain coverage, original/crop/mask pixels, source identity binding, AI-vs-human review, claim scoring, calibration and CLI integration. Later CLI summary/relocation changes were checked with direct commands and a model dry-run.
- **55 GEN-1 Dragon Ball c002** items imported and independently rechecked: 55 accepted, zero rejected. Artifacts: `/tmp/benchmark1000-gen1-dragon-ball-v2/`, `/tmp/benchmark1000-gen1-dragon-ball-proofs.json`.
- **21 GEN-2 v3 Blue Exorcist c002** retained candidates imported/resumed and independently rechecked: 21 accepted, zero rejected. Final bounded store: `/tmp/benchmark1000-final-verification-blue-c002/`; report: `/tmp/benchmark1000-final-proofs-blue-c002.json`.
- A new-policy chapter pilot selected **13 items** after deduplication. CP-SAT and exact enumeration agreed on optimum count in the pilot. This is a policy experiment, not a release-approved benchmark. The small-denominator absolute-cap policy applies, and the final 1,000/group/coverage floors are intentionally absent in pilot mode.
- New `next_speaks(Bulma, after=1)` scan on Dragon Ball c002 returned **page 2** and passed its separate checker (`/tmp/benchmark1000-scan-dragon-ball.json`).
- Chainsaw Man c001 first **8 composed proposals all returned UNKNOWN** under required coverage. A bounded 2,000-combination long-clue search found no proposal. Do not claim valid new long-question yield from these trials.
- A real hydrated pack was created at `/tmp/benchmark1000-final-pack.json`; the request at `/tmp/benchmark1000-final-request-dry-run.json` is explicitly **not inferred**. No endpoint was contacted. A private chapter viewer was created at `/tmp/benchmark1000-review-blue-c002-v2.html`.
- Shell syntax checks and `git diff --check` passed. The 142-file legacy baseline verifies unchanged.

Temporary development paths are evidence of this host's bounded checks, not assumed dependencies on other machines. No full candidate collection build, MN5 serving/inference, human benchmark approval or final export was run.

## What happens next

The next execution is the CPU foundation workflow, run by the user as agreed in STATUS.md:

```bash
# From ComicsQA_Benchmark/Code. Choose a new environment path.
bash scripts/benchmark1000_setup.sh /tmp/benchmark1000-env
BENCHMARK1000_PYTHON=/tmp/benchmark1000-env/bin/python \
  bash scripts/benchmark1000_foundation.sh v1
```

This imports preserved GEN-1/v1 and GEN-2/v3, independently checks proofs, inventories the collection, freezes source-chapter-proportional split counts in a new policy, runs a CP-SAT pilot and verifies old code hashes. Repeat an unchanged command to resume; choose a fresh output version if importer/config dependencies changed. A policy or generation change never overwrites old selections.

Review `reports/benchmark1000/v1/{preflight,proofs,pilot}.json`. Use the actual evidence/coverage results to complete semantic inventory, reviewed-order/spatial/mention consumers, native candidate contracts and new-family generation before another broad question build. Qwen, human decisions and final release remain later stages.

## References

- [Runnable commands and complete capability ledger](../../src/comics_qa/benchmark1000/README.md)
- [P00–P16 implementation plan](benchmark_1000qa_implementation_plan.md)
- [Revised design](benchmark_1000qa_design_discussion.md)
- [Shared status](../STATUS.md)


## Subsequent semantic/native implementation (2026-10-30)

The next two steps are now implemented and bounded-tested: [semantic inventory and native contracts](../../src/comics_qa/benchmark1000/NATIVE_SEMANTIC.md). The suite now has 82 passing tests. The final source pilot executes six queries, independently proves one answer, and measures a two-page dependency; native store/import/resume and legacy compatibility pass. Native records remain proposals until question-level gates are implemented. Run `semantic-preflight` for the next full inventory; do not rerun foundation v1. Historical counts above describe the earlier milestone, not the current total test count.

## Two-branch / long-relational extension — 2026-11-01

Implemented the separately versioned `branch-pilot` extension and native admission integration; [contract and full user-run commands](../../src/comics_qa/benchmark1000/BRANCH_RELATIONS.md). 171 tests pass. A bounded Blue Exorcist c002 run retained one exact sequence and one count question; both pass full native gates and measured long-relational eligibility, with 5/6 necessary visual pages and depth two measured separately from the four navigation clauses. The existing 3,762-item pool validates, and all 142 frozen files remain unchanged. The full collection run, remaining P06/P07 families, P09 pairs and P10 claims remain pending; human review/intake is deferred until after Qwen. See shared STATUS for final replay evidence.

## One-condition contrast pairs — 2026-11-01

Implemented P09 contrast pairs as a new versioned store above admitted branch tasks: one navigation-depth or search-start condition changes, with full independent native admission and distinct exact answers for both members. Added strict paired contracts/checkpoints, generic proof/store/pool integration, atomic pair selection and review sampling, single-member model-input allowlists and exact both-correct scoring. 187 tests pass, including positive synthetic member admission, 2/2 complete proof replay, CLI scoring and immutable resume. Two bounded real chapters retained zero pairs after endpoint/uncertainty gates; full run/yield review remains user-run. Existing 3,762-record pool and 142-file baseline verify. Masked-image/edited-world/unknowability P09 and paired final release remain pending. [Commands and limits](../../src/comics_qa/benchmark1000/CONTRAST_PAIRS.md). Human review remains deferred until after Qwen.

## Executable factual sentence plans — 2026-11-01

P10 now proves typed, source-question-bound factual claims before synthesis, with a producer-independent checker, required/optional/verified-false lists, separate page/claim order, immutable source-replayed plan stores and exact short-answer plus controlled-prose metrics. Unknown/unsupported clauses are held; source/code/response hashes prevent stale scoring. All 201 tests pass, covering actual graph proofs, sequence/count profiles, swaps/negation/omissions/paraphrases, extra false/unknown facts, independent checking, atomic resume and CLI scoring. Two real Blue Exorcist c001 plans contain 24 checked claims; separate check and canonical reference scoring both pass 2/2 and exact resume passes. No Qwen/model accuracy or newly admitted sentence candidate is claimed. Full preparation/check remains user-run; candidate count stays 3,774. Existing pool 3,762 and all 142 frozen files verify. [Commands and scope](../../src/comics_qa/benchmark1000/SENTENCE_CLAIMS.md). Human review remains post-Qwen.

## P11 CPU preparation and request lifecycle — 2026-11-01

Implemented separately versioned paraphrase/synthesis packs, pinned H/V/OCR hydration, ordered dependency views, exact full-page/proof-union crops and independent pack checking. Added actual local processor token/image preflight, explicit runtime profiles, two-request pilot defaults, stable sharding, bounded HTTP retries, append-only raw attempt recovery and independently parsed question/P10 claim validation. Existing source worlds and all original outputs remain unchanged. New source plan v2 adds branches and paired views above all older sources; full pool_v2/preparation remains user-run. User will fill MN5 settings later. No model server, actual processor or inference job has run; human review, candidate promotion and release remain pending. See [workflow and limits](../../src/comics_qa/benchmark1000/QWEN_PIPELINE.md) and STATUS for verified final test counts.

Final P11 checks: 218/218 benchmark1000 tests pass; independent real pack checks earlier GEN 1/1 and sentence synthesis 2/2 pass. Existing pool verifies 3,762 and all 142 frozen legacy files remain unchanged. Runtime processor/token transport tests use mocks; no actual model inference or MN5 deployment is claimed.
