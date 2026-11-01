# benchmark1000: additive implementation

This namespace reads existing CKG/GEN artifacts without changing legacy code, commands, configurations, schemas or outputs. The design is [P00–P16](../../../docs/notes/benchmark_1000qa_implementation_plan.md). **The complete plan and the 1,000-item release are not finished.** See the capability ledger below; a helper/API is not an end-to-end certified question family.

## Environment

The importer, reference selector, proof bridge and inventory use the Python standard library plus existing repository modules. CP-SAT selection needs OR-Tools; exact crop/mask processing needs Pillow. Use a new uv environment:

```bash
bash scripts/benchmark1000_setup.sh /tmp/benchmark1000-env
export BENCHMARK1000_PYTHON=/tmp/benchmark1000-env/bin/python
```

Choose a new path if it exists. The setup command does not alter existing annotation environments. For persistent use choose a new environment on your host's scratch/cache filesystem. No model weights are downloaded by setup. Test dependencies were installed only into `/tmp/benchmark1000-dev-env` on the implementation host; that path is not assumed to exist elsewhere.

## Start with existing pools

From `ComicsQA_Benchmark/Code`, configure the data root for your host:

```bash
export BENCH_ROOT=/data/151-3/comics/ComicsQA_Benchmark
bash scripts/benchmark1000.sh snapshot \
  --out "$BENCH_ROOT/reports/benchmark1000/legacy_snapshot_v1.json"

bash scripts/benchmark1000.sh import \
  --source "$BENCH_ROOT/items/gen1/v1" \
  --source "$BENCH_ROOT/items/gen2/v3" \
  --out "$BENCH_ROOT/items/benchmark1000/candidates_v1"

bash scripts/benchmark1000.sh verify-store \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1"

bash scripts/benchmark1000.sh check-proofs \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1" \
  --bench-root "$BENCH_ROOT" \
  --out "$BENCH_ROOT/reports/benchmark1000/candidate_proofs_v1.json"

bash scripts/benchmark1000.sh preflight \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1" \
  --graphs "$BENCH_ROOT/evidence/ckg/v1" \
  --out "$BENCH_ROOT/reports/benchmark1000/preflight_v1.json"

bash scripts/benchmark1000.sh select \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1" \
  --policy configs/benchmark1000/v1.json \
  --pilot --backend cp-sat --seconds 20 \
  --out "$BENCH_ROOT/reports/benchmark1000/selection_pilot_v1.json"

bash scripts/benchmark1000.sh verify-legacy \
  --snapshot "$BENCH_ROOT/reports/benchmark1000/legacy_snapshot_v1.json"
```

These are user-run commands, not completed full jobs. `import --chapter CHAPTER` restricts ingestion; repeated `--chapter` arguments select several chapters and must exist in every source. Store import resumes by repeating the identical command; completed content is reused, no overwrite. A changed source manifest, importer code or scope requires a fresh store path. Interrupted candidates remain as atomic files; the final manifest publishes only after all imports succeed. An exclusive writer lock prevents concurrent ingestion into one store. Failed attempts never become approved records.

V3 imports all retained candidates; GEN-1/v1 and GEN-2/v1/v2 expose only their selected items. Previously discarded proofs cannot be recovered. Archived checks are not new revalidation and import is not release approval. `check-proofs` writes a separate validation report and does not mutate the store. Final selection remains blocked by archived statuses until a validated review/release-view integration is implemented. It also requires explicit final split counts; the initial policy leaves those `null` pending the full feasibility review.

CP-SAT reports optimal/feasible/infeasible/unknown separately. Reference enumeration is available with `--backend reference --max-search-nodes N`; it is for bounded cases, not a substitute for a scalable final solver. Pilot selection ignores final 1,000-size/group/coverage floors but applies configured baseline and small-denominator policy. It grants no release permission. Both report exact selected IDs and policy/store hashes. Small denominators use explicit absolute caps; inspect measured priors even when the cap is inactive. Top1/top2 shortcut ranks use trusted distinct-page frequency and deterministic identity-ID tie breaking; this differs from the historic frequent-name quota's cutoff-tie inclusion. Missing frequency features are unknown, not false.

`preflight` currently reports eligible directed positive **structural walks**, not meaningful hops or expected valid QA yield. State limits and truncation are explicit. It must not be used to claim that long-chain thresholds or the 150-identity target are feasible.

## New generation and reasoning trials

```bash
bash scripts/benchmark1000.sh trial --bench-root "$BENCH_ROOT" \
  --chapter chainsaw-man__c001 --budget 8 --families composed \
  --out /tmp/benchmark1000-composed-trial.json

bash scripts/benchmark1000.sh trial --bench-root "$BENCH_ROOT" \
  --chapter chainsaw-man__c001 --budget 3 --families long-clue \
  --out /tmp/benchmark1000-long-clue-trial.json
```

Four composition templates: next speaking page, last appearance, speaking-page gap, next joint appearance. They reuse unchanged CRL operators and independent checker through a class-local acceptance profile. Full later scopes can fail coverage conservatively. No legacy registry is changed.

`scan` adds separately checked minimal-prefix/suffix navigation in this namespace, accepting new JSON programs:

```json
{"op":"next_speaks","characters":[{"op":"char","args":["Bulma"]}],"after":1}
```

```bash
bash scripts/benchmark1000.sh scan --bench-root "$BENCH_ROOT" \
  --chapter dragon-ball__c002 --program /tmp/scan-program.json \
  --out /tmp/scan-result.json
```

Supported scan operations: `next_speaks` (one character), `next_joint` (two), `last_presence` (one; `after=0`). Character arguments are existing typed CRL expressions. A scan stops at the first positive witness or earlier UNKNOWN; an absent prefix is checked page by page. The checker verifies every atomic proof and rejects skipped/reordered/extra pages, wrong answers and changed sources. A scan proof is not a complete QA validity/wording certificate, and scan records are not yet native store candidates.

Long-clue proposals use three necessary presence/speech constraints on separated pages, target-first known-member filtering, then executable relaxation/page-ablations. Only measured >=3-clause, >=3-page, span>=5, >=81-word outputs receive the long-relational tag. Meaningful-hop count stays unknown. Other long forms remain pending.

## Review and ordered packs

```bash
bash scripts/benchmark1000.sh review-page \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1" \
  --out "$BENCH_ROOT/reviews/benchmark1000/queue_v1.html"

bash scripts/benchmark1000.sh sample-review \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1" \
  --size 60 --seed 42 \
  --out "$BENCH_ROOT/reviews/benchmark1000/sample_v1.json"

bash scripts/benchmark1000.sh pack \
  --store "$BENCH_ROOT/items/benchmark1000/candidates_v1" \
  --item-id 'b1000:ACTUAL_ID_FROM_THE_STORE' --bench-root "$BENCH_ROOT" \
  --out "$BENCH_ROOT/items/benchmark1000/qwen/pack_v1.json"
```

The item ID above is a placeholder: use an actual ID from a candidate JSON file. The viewer is private, includes answers/proofs, and references local images. Review records need item content hashes, reviewer identity/type, decision and reason. `check-reviews --store STORE --decisions LIST_JSON --out REPORT` checks bindings; AI decisions never count as human acceptance. Per-stratum zero-error bounds are binomial, not a claim of benchmark-wide quality. Release gating currently conservatively requires individual human review; statistical stratum acceptance is not yet wired to release.

Packs preserve page order separately from dependency order, resolve graph facts/coverage against validated pins, omit unreadable canonical names from character nodes, and retain raw provenance. They are private preparation artifacts. Paraphrase is text-only. Synthesis APIs require explicit verified claim records and crop metadata, but a synthesis generation/certification workflow is not complete.

```bash
bash scripts/benchmark1000.sh infer --pack /path/to/hydrated-pack.json \
  --model ACTUAL_SERVED_MODEL_ID \
  --endpoint http://ACTUAL_MN5_HOST:PORT/v1/chat/completions \
  --dry-run --out /tmp/benchmark1000-inference-request.json
```

Use actual model/host values verified on MN5. Omit `--dry-run` only when you intend to call that endpoint. Authentication, if needed, is read from `BENCHMARK1000_API_KEY` and never saved. Responses remain raw and pending validation. No MN5 serving configuration or GPU fit is assumed. The client reuses a matching published response; a timeout may have reached the server, so server-level exactly-once execution is not guaranteed. Retry/failure orchestration, Slurm deployment and independent model back-parsing remain unfinished. Matching a proposed program does not itself verify that a question expresses it; model output cannot self-declare human review.

## Image, evaluation and review APIs

- `render --image PATH --sha256 ACTUAL_SHA --boxes '[[x0,y0,x1,y1]]' --mode crop|mask --out PNG`: exact RGB/PNG transformations; half-open pixel boxes; originals untouched; image and transform manifest published create-only.
- `assets.choice_manifest`: verifies four distinct stable identity options on reference pages different from evidence pages. Generic page-local clusters are rejected. Crop rendering/option-layout release still needs integration and pilot review.
- `visual.bind_reference` / `predicate` / `check_predicate`: verify actual crop pixels and an admitted identity link, then use separate producer/checker predicate implementations without needing readable names. These are proof primitives, not automatically released visual-choice questions.
- `assets.masked_overlay`: invalidates overlapping nodes and dependent facts and opens affected coverage; explicitly invalidates external companions on the edited page. It produces neither a determinability certificate nor a rebuilt, approved edited-input QA world.
- `overlays.build_review_overlay`: pure new companion construction, explicit human/AI decisions and pinned source-specific review rules. `positive_fact` and its checker prove positive witnesses only; missing facts stay UNKNOWN.
- `claims`: validates required/optional/contradicted-forbidden claim contracts and scores supplied entailment labels. It does not establish factual support by accepting a model's verification flag. Claim extraction, factual certification and calibrated inference must be implemented before release.
- `evaluation`: typed exact scores, pair all-correct, alternative evidence-set precision/recall; allowlisted main/blind/privileged diagnostic input helpers. All-input diagnostic construction still needs scope-controlled fact/OCR adapters.
- `probes`: auxiliary expression probes and both composition-gap directions; standalone probe programs/wording are not yet certified. Contrast proposals remain pending edit verification.
- `calibrate --labels JSON --out REPORT`: human/judge Boolean claim agreement, confusion counts and Cohen's kappa; degenerate kappa is N/A. It does not generate calibration labels.
- `export.prepare`: fails closed on policy/review gaps and unsupported derived assets; verifies original image hashes and produces opaque public image names plus separate private metadata. Copying assets and final exporter/benchmark-card CLI remain pending. Do not publish its combined in-memory return value as public inputs.

## Capability ledger

| Plan stage | Implemented now | Still required |
|---|---|---|
| P00 | Versioned initial policy, legacy snapshot and isolation checks | Full source/decision freeze after preflight; configure split counts |
| P01 | Immutable legacy imports, native proposals/mixed stores and [admission for four closed templates](NATIVE_ADMISSION.md) | Sentence/visual asset/claim certification and release integration |
| P02 | Exact reference and scalable CP-SAT selectors; separate policy reports | Full-pool feasibility, complete feature families and final policy calibration |
| P03 | Structural + [typed semantic inventory](NATIVE_SEMANTIC.md), clause/page tests; semantic_v2 complete (250 executed, 32 proposals) | Wider patterns and meaningful-hop certification |
| P04 | Pure review overlays, positive witness proof API | Review-aware ablation/consumers; caption claims and grounded evidence admission |
| P05 | Typed compositions, four independently checked scans and source-bound relay stages | Reviewed order/spatial/mention and complete native question validation |
| P06 | [Eight bounded native families](EXPANDED_FAMILIES.md), [two-branch speaking chains](BRANCH_RELATIONS.md), answer-first search and proof/admission diagnostics | Full-collection yield/feasibility, reviewed order and caption-dependent families |
| P07 | Long-clue generator, [measured parallel-chain and long-relational certificates](BRANCH_RELATIONS.md), necessary-step certificates and private native probes | Relation walks/maps, comparison stories, multi-part/statements/noise and certified probes |
| P08 | [Visual feasibility and checked four-image pilot](VISUAL_PILOT.md), exact cross-page crops, A–D sheets, independent graph/pixel/ablation checker and review packets | Actual human distractor/crop review; reviewed native admission/selection and release integration |
| P09 | [Independently admitted one-condition contrast pairs](CONTRAST_PAIRS.md), pair-aware stores/selection/review sampling/exact scoring; pixel masking primitives | Edited-world rebuilding, residual-clue/ambiguity certificates, masked paired generation and final pair review/release |
| P10 | [Executable typed claims, independent checker, ordered sentence plans and controlled response scoring](SENTENCE_CLAIMS.md) | Broader factual predicates, unrestricted-prose extraction and generated sentence admission; Qwen/human integration |
| P11 | [Ordered private packs, exact crops, local processor/runtime preflight, resumable bounded transport and independent question/P10 response validation](QWEN_PIPELINE.md) | Full preparation, actual processor/MN5 pilot and inference; broader prose contracts and reviewed candidate promotion |
| P12 | Private review queue, decision checking, sampling/bounds | Strata construction, adjudication and audited acceptance-to-release integration |
| P13 | Exact/pair/evidence metrics, diagnostic/probe helpers | Native formats, complete diagnostic adapters and model evaluation runner |
| P14 | Import/trial tools | Full new-family build and provisional 1,000 selection |
| P15 | Calibration metrics and conservative human release gate | Human labels/review, actual judge calibration, replacements and final freeze |
| P16 | Guarded export preparation | Complete image/asset export, benchmark card and independently audited release |

## Verified bounded results (2026-10-30)

- GEN-2 v3 Blue Exorcist c002: 21 imported candidates, all 21 independently rechecked proofs accepted. New-policy pilot: 13 selected after semantic deduplication; no release approval.
- GEN-1 Dragon Ball c002: 55 imported, all 55 proofs accepted in bounded revalidation.
- Dragon Ball c002 new `next_speaks(Bulma, after=1)` scan: page 2, separate checker accepts.
- Chainsaw Man c001: first 8 composed proposals all UNKNOWN under required coverage; bounded long-clue search found no proposal. No valid new long question or 1,000-item feasibility is claimed from these trials.
- All 142 actual legacy implementation files match the start snapshot. The first snapshot accidentally included the newly created launcher; a preserved corrected comparison excludes only that new file.
- Full tests and latest details are in STATUS.md. No full collection build, MN5 inference, human approval or final export was run.

## Tests

```bash
PYTHONPATH=src:tests:tests/benchmark1000 PYTHONDONTWRITEBYTECODE=1 \
  "$BENCHMARK1000_PYTHON" -m unittest discover -s tests/benchmark1000 -v
```

Optional image/solver tests skip if those libraries are absent. Run the complete suite in the dedicated environment. Tests cover corruption/overlap, immutable resume, policy feasibility/search budgets, reference/solver agreement, wrong proofs, missing coverage, crop pixels, masks, AI-vs-human decisions, raw-response resumption and claim/scoring edge cases.

## Single foundation command

After environment setup, the CPU preparation above is also available as:

```bash
BENCHMARK1000_PYTHON=/path/to/new/environment/bin/python \
  bash scripts/benchmark1000_foundation.sh v1
```

`v1` names a new output version; repeat unchanged to resume, or choose a new version after importer/config changes. This runs legacy import, independent proof revalidation, structural inventory, source-chapter-proportional split-policy freezing and a 30-second CP-SAT pilot. It does not run annotation models, Qwen, full new-family generation or final release. The automatic split policy uses largest-remainder allocation from source chapter counts and records its lineage; structural inventory does not certify final feasibility. Expected outputs are under `reports/benchmark1000/v1/` and `items/benchmark1000/v1/`.


## Foundation v1 completed; derived validation views

The full user-run foundation is now reviewed in [results](../../../docs/notes/benchmark1000_foundation_v1_results.md). Its 3,630 proofs passed; 2,000 pilot items are expected under 50 × 40 chapter capacity. This is not a final 1,000-item release. All original reports and stores are preserved.

`audit-features --store STORE --out REPORT` recovers next-appearance page offsets from typed proof children. `select` now accepts `--proof-report` and `--feature-report`: each report must bind to every original item and its store manifest. Derived views change neither source content nor legacy code. Feature application independently checks the recovered values. The original store's archived status remains intact.

Important: below `minimum_denominator`, current percentage constraints use absolute-cap fallbacks. The view pilot selects 19 page answers per split with 17 answers at +1, so compliance does not imply low shortcut accuracy. Resolve this policy explicitly before final release. Structural inventory was truncated in every chapter; no semantic path/branch or 1,000-item feasibility claim follows.


## Semantic inventory and native integration implemented

See [NATIVE_SEMANTIC.md](NATIVE_SEMANTIC.md) for the next full CPU command, actual typed patterns, native records, pending proposal/admission rules, mixed stores and bounded validation. Existing foundation v1 remains unchanged and readable; do not rebuild it. Native answer proof is separate from question certification.

Native admission now consumes saved semantic proposals without a new generation run. See [commands, gates and limitations](NATIVE_ADMISSION.md).

## Expanded family pilot

[Run the bounded native family expansion](EXPANDED_FAMILIES.md): eight recipe families, an independent typed recipe checker, necessary-step complexity certificates, separate admission/diversity diagnostics, private compositional probes and visual alias review. This extends the new layer; completed semantic/admission artifacts remain unchanged.

## Coverage-aware windows

[Coverage-aware pilot and uncertainty replay](COVERAGE_WINDOWS.md) search explicitly stated shorter/shifted intervals with checked predicates and a separate positive-membership proof refinement. Existing family/admission artifacts stay immutable; no coverage or policy is automatically relaxed.

## Necessary switch preselection

[Switch-only discovery](SWITCH_SEARCH.md) adds bounded independently checked navigation/switch bypasses before retained-window and proposal caps. It preserves the current question profiles and admission gates; run into fresh outputs.

## Unified saved pools

[Unified candidate inventory](POOL_INVENTORY.md) merges admitted native records and explicitly adapted legacy pools with source-bound deduplication, unchanged status/receipts, provenance ledgers and necessary quota-gap reports. Use `pool-inventory` then `verify-store`; no release approval or selection feasibility is inferred.

## P08 visual feasibility and pilot

[Visual identity preflight and four-image QA](VISUAL_PILOT.md) provide graph-bound quote-speaker questions, exact source crops, A–D option sheets, an independent checker and private review packets. Human distractor fairness and reviewed admission/release integration remain pending; existing pools stay unchanged.

## Two-branch relational generation

[Two-branch and long-relational graph QA](BRANCH_RELATIONS.md) adds explicit two/three-step searches for two different speakers with exact final-page sequences or gap answers. Every branch/navigation must affect the answer before retention. Admission measures visual dependencies, maximum branch depth and long-relational eligibility. Human review/intake remains deferred until after Qwen. Use fresh output paths; completed pools remain immutable.

## P09 one-condition contrast pairs

[Contrast pair commands and contract](CONTRAST_PAIRS.md) build immutable paired views above admitted branch questions. One chain-depth condition changes; both versions must pass their full native gates and have different exact answers. Selection/review sampling preserve pair closure, and model inputs expose one member at a time. Masked-image variants remain separate pending work; human review stays deferred until after Qwen.

## P10 executable sentence plans

[Sentence claims and run commands](SENTENCE_CLAIMS.md) prepare source-replayed, independently proved factual claims before Qwen synthesis. Required/optional/verified-false lists, separate page/dependency order, exact short answers and controlled-prose diagnostics remain private plans. Unsupported text stays held; plans cannot enter candidate counts or gain human/release approval.

## P11 Qwen preparation and response validation

[Commands and contract](QWEN_PIPELINE.md): immutable legacy/native paraphrase and P10 synthesis packs, ordered evidence hydration, exact page crops, configurable local processor/runtime preflight, bounded resumable HTTP jobs and independent question/factual validation. New pool source plan v2 includes older questions, branches and contrast views without changing pool_v1. CPU implementation is tested; full preparation, actual processor preflight, MN5 server/inference and final reviewed admission remain pending. Runtime settings will be filled by the user later.
