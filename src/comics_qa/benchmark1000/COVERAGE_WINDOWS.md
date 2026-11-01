# Coverage-aware windows and uncertainty diagnostics

The new `coverage_windows.1` profile searches shorter or later explicitly stated ranges. It preserves the completed `families_v1` and `families_v1_admission` runs, legacy interpreters/checkers and all evidence. It neither closes coverage nor approves names or QA release. Qwen stays deferred.

## Run

From `Code/`, use fresh output roots:

```bash
bash scripts/benchmark1000.sh coverage-pilot \
  --per-family 3 --max-executions 9 --search-budget 1000 \
  --window 10 --min-window 4 --max-shift 20 \
  --probe-budget 192 --max-windows 4 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/coverage_v1

bash scripts/benchmark1000.sh admit-native \
  --proposal-root /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/coverage_v1 \
  --max-ablation-pages 12 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/coverage_v1_admission
```

Both are CPU-only and resumable on identical inputs/code/configuration. Scope defaults to all available chapters; repeat `--chapter ID` for bounded trials. Changed code/budgets/reviews require fresh outputs. Generation checkpoints each chapter; admission checkpoints each proposal. Manifests, source snapshots, checksums and writer locks follow the existing immutable workflow. Do not rerun old outputs in place.

Inspect:

- `coverage_v1/report.json`: per-family yield, probe budgets and discovery-rejection counts.
- `coverage_v1/diagnostics.json`: per-chapter unresolved predicates, source-bound evidence requirements and resource limits.
- `coverage_v1/chapters/*.json`: bounded search details, executed recipes, proposals and failed-execution diagnostics.
- `coverage_v1_admission/report.json`: actual admitted yield, held/duplicate reasons and diversity. Discovery success is not admission.
- `coverage_v1_admission/probes.json`: private oracle-context diagnostics, excluded from the main QA count and parent model input.

## Search semantics and budgets

The question says **“Search only the inclusive range from page S to page E.”** A range can start later than the latest reference page. It makes a claim only about that stated range; it does not claim to find the first event after the reference across an ignored gap. The old “Use only pages…” grammar retains its original immediate-start rule.

Search uses known-positive human/derived facts to find possible targets, then independently checked CRL probes to determine whether the required predicates can be answered. Every retained recipe is fully re-executed and independently checked before native publication, then assessed again by admission. Cached discovery decisions are never answer-proof receipts.

- `--search-budget`: maximum source-anchor checks, raw reference tuples and window trials per family/chapter; truncation is explicit.
- `--window`, `--min-window`: maximum and minimum interval length. Enumeration is lazy and clamped to actual chapter size.
- `--max-shift`: maximum later-start offset from the earliest allowed search start, also clamped to chapter size.
- `--probe-budget`: maximum **new checked discovery queries per family/chapter**, in addition to bounded source-anchor checks. Identical resolved-identity/page predicates can reuse checked truth within the same immutable world. Cache hits and new queries are reported separately. Full recipe/admission executions are additional work.
- `--max-windows`: maximum eligible windows retained per reference tuple before the family proposal cap.
- `--per-family`, `--max-executions`: existing answer-proved proposal and full recipe execution caps.

Windows are sampled fairly across references and range sizes/shifts. Search remains capped, not exhaustive. A budget failure is not an annotation gap or a negative fact. No known target and no known branch distinction are discovery outcomes, not proofs that no QA exists anywhere in the collection.

The shared-set prefilter seeks known positives distinguishing both branches as well as common members; it does not treat missing positives as negatives. Numeric-overlap candidates and count windows with an unproved/unchanged control count are avoided during discovery under the **existing** admission rules. All other name, wording, redundancy, page/OCR ablation, set-cardinality and global policy rules remain intact.

## New proof refinement, isolated from old evaluators

New recipes use `proof_engine=coverage_recipe`, a mode-bound extension of the checked recipe executor. Old `recipe` records keep the old behavior and receipts; they cannot silently opt into this refinement.

A verified Bool3 predicate can have a settled `True` value while carrying `exact=false` because broader annotation coverage is open. That flag does not negate its positive witness. The new membership checker uses the same three-valued **known truth** contract as the existing independent prefix scanner: independently valid Boolean proofs with `status=OK` and a Boolean value settle that page’s predicate. UNKNOWN settles nothing.

For complete shared-page sets, the new rule checks **every supplied page in the stated finite range**. Only if every membership is settled is the main set exact. Known positives alone, an omitted page, or a forged exact flag do not establish completeness. Negative outcomes still need their original supported absence evidence or a logically decisive false branch. Character identity inputs must already be uniquely proved; positive evidence is not used to guess identities.

For last appearance, a separately checked descending suffix stops at the first positive witness, proving every later negative. An earlier unknown cannot change that last witness; an unknown encountered before reaching it blocks the claim. This is not a claim of full-range absence.

`MembershipChecker` verifies source hashes, page order/domain, every atomic predicate proof, probe completeness/order and the final result without invoking the producer. It does not edit graph facts, coverage, source images or legacy operation registries. The recipe checker binds the membership result back to the exact parsed program and previously checked variables.

Partial membership sets are not treated as unchanged exact answers during page ablation, even when their currently known positives equal the original set. Thus a necessary negative page cannot disappear from the certificate merely because deleting it did not remove a positive member.

## Diagnostics

Records identify the unresolved operator/binding, known identity IDs, stable page IDs and 1-based indices, reason, declared evidence families and actual coverage IDs/statuses. The requirements are candidate families for that operation, not authority to approve a fact. Diagnostics retain program/execution hashes, source snapshots, independent-check status and explicit truncation.

Successful Boolean probes are not reported as blocked just because their trace contains a short-circuited unknown. Discovery records distinguish open coverage, ambiguous/unresolved selection, inexact results, resource exhaustion and structural lack of known branch distinction. Blank aggregate reasons now have a reason-code fallback. Diagnostic record limits are reported.

Replay failures from an existing immutable run without generating a new pool:

```bash
bash scripts/benchmark1000.sh diagnose-families \
  --source /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1 \
  --family shared_presence_pages --family shared_speaking_pages \
  --max-queries 12 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1_uncertainty.json
```

The command verifies the input manifest, checkpoint/source bindings and exact reproduction of the saved result before explaining it. It reports eligible/replayed counts and truncation. It grants no review or closure. The report is create-only; an interrupted bounded batch can be restarted.

## Complexity, offsets and release

The existing bypass/dependency and visual-necessity requirements still decide admission. Merely moving a window farther away does not add meaningful hops. For this profile, `page_offset` is measured from the range predecessor (S−1), with `offset_basis=expanded_search_range_predecessor`; distance from the latest reference page is recorded separately. This avoids presenting a distant range as a harder next-page problem. Profiles with equivalent commutative shared/gap paths deduplicate regardless of reference ordering.

Pool quota diagnostics are unchanged. Full collection yield, 1,000-item feasibility, paired/sentence families, actual alias approvals, human review and release remain pending. Some data may still need targeted source review; no relaxed condition or model assertion is substituted for missing evidence.

## Bounded verification

Tests prove that a shorter interval can recover an exact two-branch set before an unknown tail, and that an explicitly shifted range can recover a three-navigation chain after an unknown earlier page. They cover positive witnesses under open coverage, later-vs-earlier last-witness uncertainty, forged completeness, skipped probes, source immutability, exact-answer ablation, new/old grammar distinction, resource bounds and checkpoint resume.

A bounded baseline diagnosis reproduces one original Blue Exorcist shared-presence failure and points to unresolved presence evidence on page indices 44 and 48 (stable IDs p043/p047). A final two-chapter real trial produces five proposals and admits all five: two successive-speech chains, two next-speech line counts and one last-presence result. All five independently replay with zero rejections. Three archived page/count/Boolean candidates also freshly replay; all 39 old candidates load. All 125 tests pass and all 142 frozen legacy files match. These checks do not establish real shared-set/walk/gap yield; no full collection scan was launched.

## Necessary switch preselection

[Switch-only discovery](SWITCH_SEARCH.md) adds bounded independently checked navigation/switch bypasses before retained-window and proposal caps. It preserves the current question profiles and admission gates; run into fresh outputs.
