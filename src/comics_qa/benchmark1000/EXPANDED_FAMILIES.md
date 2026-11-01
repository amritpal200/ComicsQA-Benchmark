# Bounded native family expansion and complexity

This is an additive P05–P07 implementation. Existing semantic_v2/admission_v1, all legacy graph/interpreter/checker files, policies and datasets remain unchanged. Qwen inference and final release are deferred.

## User-run workflow

From `Code/`, generate a resource-bounded candidate pool across the available chapters:

```bash
bash scripts/benchmark1000.sh family-pilot \
  --per-family 3 --max-executions 9 --search-budget 1000 --window 10 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1

bash scripts/benchmark1000.sh admit-native \
  --proposal-root /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1 \
  --max-ablation-pages 12 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1_admission
```

No GPU, Qwen or OR-Tools is needed. Both commands resume on identical inputs/code/configuration. Use a fresh output when any of those change. The source pilot checkpoints each chapter; admission checkpoints each proposal. Single-writer locks and create-only atomic publication protect outputs. Completed manifests are verified before reuse. `--chapter ID` may repeat to restrict a trial. Default scope is the full available collection, not a hardcoded sample.

Read `families_v1/report.json` for **per-family search targets, executions, proof yield and uncertainty reasons**, and `families_v1_admission/report.json` for actual admitted yield, duplicate/hold reasons and diversity. `family_yield` includes families yielding zero candidates. Search truncation is explicit; none of these counts is an exhaustive graph-path inventory.

The caps mean: at most `search-budget` source-anchor checks and reference tuples per family/chapter (walks test two step counts); at most `max-executions` complete recipe executions per family/chapter; at most `per-family` answer-proved proposals retained per family/chapter. Source anchors are checked before spending the recipe budget. Source-domain checks and counterfactual admission executions are additional, reported work. Every input window is bounded by actual chapter length. Do not raise budgets into a production generation sweep until bounded validity/yield/diversity reports are reviewed.

## Families and exact semantics

All references are unique scoped OCR quotes with human speaker links; named answer aliases are not needed for internal identity values. The search range starts immediately after the latest reference page and ends at the explicitly stated bound.

| Family | Answer | Meaning |
|---|---|---|
| `successive_speech` | Page | Follow the same character to their next speaking page two or three times, always strictly after the preceding result. |
| `speaker_walk` | Page | Follow a next-speaking link, switch to the only different drawn character, then continue; two or three navigations. |
| `speaking_gap` | Count | Independently find two speakers’ first speaking pages in the range; count strictly intervening pages (`max(0, abs(a-b)-1)`). Zero gaps/coincident endpoints are held. |
| `speaking_before` | Boolean | Compare those two independently resolved first speaking pages. Ties are held; Boolean items remain subject to the existing two-option quota. |
| `shared_speaking_pages` | Set of page numbers | All pages in the range on which both speakers speak. |
| `shared_presence_pages` | Set of page numbers | All pages in the range on which both speakers are drawn. |
| `next_speech_line_count` | Count | Find the reference speaker’s next speaking page in the range, then count their dialogue text regions on it. |
| `last_presence_window` | Page | Last page within the explicit range on which the reference speaker is drawn; full range coverage is required. |

Search uses trusted known-positive facts to propose targets; those facts never substitute for execution, coverage or proof. Output-value rarity and existing retained-output counts guide target choice. No missing fact becomes a negative assertion. Every answer-proved candidate is saved before global policy selection, including candidates later held by admission. Turns/order, caption claims, mentions, narrative causality and free synthesis are not inferred or admitted by this wave.

## Execution and independent proof checking

`proof_engine=recipe` stores a typed CRL let graph, source hashes and named checked stages. CRL operations/registries are unchanged. Source character lookup, other-character selection, arithmetic and complete set predicates use the original CRL interpreter/checker.

A bounded first-speaking operation uses a minimal-prefix scan with an explicit inclusive `end`. It proves every negative before the first positive and stops on an earlier UNKNOWN; uncertainty later in the stated window does not invalidate an already proved first witness. This is a new-layer proof refinement of the conservative full-collection CRL composition, not a claim that the legacy interpreter emits the new recipe document.

`RecipeChecker` does not call `RecipeEngine`. It reconstructs each closed expression from previously checked bindings, independently reconstructs scan bounds, checks every atomic proof and validates the final value. Reordered/missing/extra bindings, skipped probes, changed anchors/windows, wrong final values and stale source hashes fail. Bypasses replay the dependent suffix; they do not keep cached intermediate values from the original world.

Shared-page sets use pointwise conjunction, retaining three-valued semantics. The complete main answer must be exact. Removing a branch must prove an extra member outside the original answer; a verified known-positive extra member can witness necessity even when the relaxed set has unknown additional members. An UNKNOWN result or mere missing members cannot establish that witness.

## Admission and measured complexity

Closed wording must round-trip to the exact typed recipe. Existing name eligibility, used-transcript agreement, exact answer leakage, OCR-only ablation and source/image-context bindings still apply. All represented navigation/switch/branch bypasses and required page removals are rechecked. Gap/Boolean branch sensitivity tests both endpoints of the stated range when needed, retaining the counterfactual trials; an unchanged low-end substitute alone is not evidence that a Boolean branch is unnecessary. These are typed input-dependency interventions, not newly asserted story facts. Set answers must have at least two members and be smaller than the full stated domain. Identical source identities and trivial branch targets are held.

A complexity certificate records the semantic steps whose bypasses change the final result, necessary visual pages, page span, independent branches and combines. UNKNOWN or ambiguous intermediate bypasses do not certify a chain. For chains, meaningful hops count necessary navigations and identity switches; quote lookup, AST primitives and prose length are excluded. Parallel branch depths are not summed. This is an operational dependency measure, not universal semantic minimality or a narrative-difficulty claim.

Only expanded profiles with passing certificates receive groups: `chain` requires at least three meaningful hops; shorter temporal chains use `short`; shared-page sets use `branch_combine`; gaps/comparisons/counts use `aggregate_compare`. Existing admitted records retain their original pending complexity status. Global quotas are diagnosed rather than silently relaxed or applied as validity filters. Neither a successful pilot nor empty `pool_policy_violations` establishes 1,000-item feasibility; the known small-denominator policy question still needs resolution before final selection.

Admitted native records include `reasoning_tags`, `answer_format`, `evidence_class`, `generation_mode`, proof/certificate provenance and pending human/release status. Long narrative forms, pair certification, the sentence allocation and final selection remain separate work.

## Review and compositional probes

```bash
bash scripts/benchmark1000.sh check-proofs \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1_admission \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1_recheck.json

bash scripts/benchmark1000.sh review-page \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1_admission \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/families_v1_review.html
```

Admission also writes `probes.json`: independently checked standalone stage programs linked to parent IDs. These are **private privileged subproblems**, with oracle intermediate page bindings and no generated natural wording. They are not additional QA items and must never be shown, with their answers, to the parent task. Natural probe wording/model evaluation remains pending.

Prepare visual evidence for the two existing pending aliases (optional command requires Pillow):

```bash
bash scripts/benchmark1000.sh alias-review-page \
  --requests /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1/pending_alias_reviews.json \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/native_alias_review.html
```

The portable private HTML embeds source-hash-verified name-text and same-page human-identity crops, alongside Paddle/MAGI text. It never changes an image, alias decision or QA approval. Copy review JSON outside the immutable source output before recording actual decisions; use `configs/benchmark1000/reviews/` for new review files. Uncertain aliases stay pending. A reviewed file can be passed via `--alias-reviews` to a **fresh** admission output; final human QA release remains separate.

## Verification scope

**112 CPU tests pass; all 142 frozen legacy files unchanged.** Original admission_v1 still verifies with 15 candidates. The bounded pilot/admission artifacts are `/tmp/comicsqa-expanded-verified` and `/tmp/comicsqa-expanded-release-admission`; optional private alias evidence is `/tmp/comicsqa-native-alias-review.html`.

The bounded real pilot uses Blue Exorcist c001 and Hunter x Hunter c001: 33 recipe executions, six answer-proved proposals; admission retains five distinct candidates and one duplicate; fresh `check-proofs` reproduces all five certificates (zero rejected). It includes a certified three-navigation chain and dialogue counts. Character-switch walks and shared/last-page collections still encounter open coverage in these sampled chapters; no closure is manufactured to improve yield. Other families have explicit zero-yield/blocker entries. This does not predict full-collection yield.

Synthetic fixtures independently prove necessary three-navigation and character-switch chains, two-branch gaps and shared-page sets; test stale sources, scope/step/answer changes, prefix uncertainty, exactness, same-count shortcuts, re-labelling, private probe isolation, zero-eligible-OCR outputs and checkpoint resume. All legacy files and completed source artifacts remain immutable. Full collection execution and feasibility review are user-run.

## Follow-up: coverage-aware windows

The full first run yielded 39 admitted candidates but no shared sets. The separate [coverage-aware profile](COVERAGE_WINDOWS.md) adds bounded shifted/shorter ranges, a versioned positive-membership refinement and predicate/page diagnostics. Continue in fresh output roots; the original profiles, results and policies remain preserved.
