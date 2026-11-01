# Implementation plan: 1,000 graph-grounded comics QA pairs

Date: 2026-10-30.
Source: [revised design discussion](benchmark_1000qa_design_discussion.md), including section 9A and D19.
Status: implementation plan prepared at the user's request. The stages below are planned, not implemented by this document. Existing stage completion is recorded in [STATUS.md](../STATUS.md).

Implementation started 2026-10-30: see [verified progress](benchmark1000_implementation_progress.md) and the [component capability ledger](../../src/comics_qa/benchmark1000/README.md#capability-ledger). Only the listed bounded results are complete; the full plan remains in progress.

## 1. Outcome and scope

Implement all components of the revised design, in stages, and produce one combined benchmark of **1,000 final QA items**, selected from preserved GEN-1, GEN-2 and newly generated candidates. All items remain chapter-scoped and graph-grounded. Preserve original seen/unseen membership. Include executable questions, graph-verified sentence claims, long relational questions, visual choices, counterfactual/contrast pairs, evaluation tools and diagnostic inputs. Interpretive questions are excluded from this first release, as specified in the revised design.

Implementation completeness and benchmark readiness are different: a family may be implemented but have no eligible examples until its evidence is reviewed. Neither the 1,000-item target nor any diversity floor is a claim of current feasibility. Report a shortfall and its evidence or policy cause rather than invent facts or silently weaken requirements.

The user runs full collection jobs and MN5 inference. Development includes synthetic tests and bounded real trials. Every implementation stage updates STATUS.md, documents exact runnable commands, and preserves earlier outputs. This plan does not start production work.

## 1A. Mandatory additive architecture (user clarification, 2026-10-30)

Build the 1,000-QA system **above the current implementation**. Existing code, scripts, configurations, schemas, policy behavior and generated artifacts remain unchanged. This constraint overrides any wording in the source discussion that suggests replacing the existing pipeline.

- Introduce a new namespace, provisionally `src/comics_qa/benchmark1000/`, with its own adapters, evidence overlays, reasoning engines, selection, generation, review and export components. New command names/configuration roots are separate from current commands/configs.
- Read existing CKG, GEN and VERB artifacts through read-only adapters. New metadata lives in new records referencing original IDs/hashes; never migrate or rewrite originals in place.
- Reuse existing engines by import/composition where their current contracts suffice. New operators and independent checker rules belong to the new layer; no edits or monkey-patches to existing CRL semantics or registries. New evidence is an overlay referencing a pinned base graph, not a modification of it.
- The new selection policy governs only new benchmark1000 selections. Existing quotas and generator results keep their original meaning. An old item excluded by new selection remains unchanged in its original collection.
- New crops, masks, annotation reviews, request packs and public exports go into separate roots. New decisions do not retroactively alter existing evidence companions.
- Pin legacy input/code hashes, check old command behavior and fingerprint compatibility on bounded fixtures, and verify the new layer does not write to legacy roots. Avoid imports that mutate shared registries or interpreter state.
- If a feature cannot be implemented through an adapter/composition or a new-layer implementation, report the boundary issue; do not modify the existing implementation to make it work.

This clarification authorizes updates to this plan and coordination documentation; it does not require retroactively editing the historical design discussion. Future implementation must follow this additive contract.

## 2. Implementation decisions and corrections

These are explicit defaults selected for this plan under the user's discretion; changes must be versioned.

1. **One final total:** 1,000 items across all pools. The 200 long relational items are an overlapping requirement, not 200 additional items. Sentence explanations can overlap long questions.
2. **Four-axis taxonomy:** adopt `evidence_class`, `generation_mode`, `reasoning_structure`, `answer_format`. Keep cross-page, long-relational, contrast and diagnostic tags separate. Compatibility adapters retain old labels without rewriting old artifacts.
3. **Validity is mandatory; distribution is selection policy.** Preserve graph/proof/coverage/readability/wording requirements. Implement alternative percentage/baseline rules only in the new layer’s selection policy; keep existing policy code and behavior unchanged. Measure achieved baselines and all exceptions.
4. **No invented evidence tier:** MAGI panels, OCR, grounding and captions do not become trusted tier-A facts merely because the new design calls them that. Define source-specific admission criteria. Current CKG-3 individual review rules remain until a tested, versioned alternative exists. Distinguish source, derivation and verification; a deterministic result can inherit model uncertainty.
5. **Coverage-aware anchors:** four-word normalized substrings are proposals, not automatically eligible. Prove uniqueness in the stated scope with appropriate transcript coverage. With incomplete chapter OCR, retain a page-scoped anchor or hold the item; no chapter-wide uniqueness claim from missing text.
6. **Identity boundaries:** a name-free visual option removes the requirement to print a readable name. It does not supply missing cross-page identity links. Unnamed page-local clusters cannot be assumed to be the same person across pages; require verified links or explicitly constrain the task to a valid local scope.
7. **Mask semantics:** distinguish “next visible annotated line in the edited input” from “next line in the original story.” Masking does not delete a story event. Determinability is about available evidence, not a human guarantee that the answer is unknowable from every possible clue.
8. **Sentence verification:** failure to map a claim is not proof of interpretation. Unsupported/unresolved items are rejected or held; they do not become verified by relabelling. Interpretive items stay out of v1.
9. **Long-question necessity:** required reasoning clauses must be necessary; optional, verified distractor clauses are explicitly tagged unnecessary. Noise-augmented questions cannot require every displayed clause to pass necessity. L/XL word counts are reporting buckets, not permission to pad text.
10. **Review is a release gate:** failed automatic meaning/proof checks are never rescued merely by adding an item to a random sample. Hold for repair or an explicit item-level decision followed by revalidation. AI review never counts as human review.
11. **Selection and review iterate:** choose a provisional set, review/calibrate it, then repair and reselect with the same published rules. “1,000 final” is reached after required checks; failed reviewed items are not left in place to meet a count.
12. **A proof is not a unique explanation:** retain alternative valid evidence sets when available. Necessary-page ablation and evidence-page scoring must not punish a valid alternative derivation just because it differs from the saved trace.

## 3. Target allocation and policy defaults

| Primary group (one per item) | Target |
|---|---:|
| Short precise | 120 |
| Long chains | 230 |
| Branch and combine across pages | 220 |
| Chapter aggregation/comparison | 80 |
| Masked evidence and contrast | 100 items, organised as 50 two-item pairs |
| Claim-verified sentence answers | 250 |
| **Total** | **1,000** |

Overlapping targets: at least 200 long relational questions, initially >=3 necessary described relations, >=3 necessary pages and page span >=5; aim for roughly half of these to have graded explanations. Report L (81–250 words) and XL (>250) buckets, while prioritising natural language and necessity. Aim for roughly 30% sentence/explanation outputs overall without double-counting. Define primary assignment precedence in configuration; for example, a paired sentence item can belong to the pair group while retaining claim verification.

Proposed coverage targets from the design: >=40 chapters, <=40 items/chapter, >=150 distinct target identities, source-proportional split counts, and visual choices >=15% of character-target answers. The identity floor concerns items with actual identity targets, not arbitrary characters mentioned in evidence. Count pairs as two items; keep pair members in the same split and review group. Diagnostic variants and sub-question probes are auxiliary records, not extra members of the 1,000.

Keep these as feasibility-tested targets initially. Publish which become release constraints after Stage P03. The existing pool cannot meet them.

## 4. Stage map

| Stage | Main result | Prerequisites |
|---|---|---|
| P00 | Frozen inputs, decisions and policy definitions | Existing artifacts |
| P01 | Shared item contract and permanent candidate store | P00 |
| P02 | Independent selection engine and baseline features | P01 |
| P03 | Feasibility inventory and pilot selection | P01–P02 |
| P04 | Evidence admission, review and richer adapters | P03; family-specific |
| P05 | CRL and independent checker extensions | P03–P04 |
| P06 | New answer-first graph families | P05 |
| P07 | Long relational questions and composition probes | P06 |
| P08 | Visual-choice assets and exact scoring | P04–P06 |
| P09 | Edited inputs, determinability and contrast pairs | P05–P08 as needed |
| P10 | Claim records and sentence-answer verification | P05–P07 |
| P11 | Ordered Qwen packs, MN5 runner and output validation | P07–P10 |
| P12 | Review tooling and statistical acceptance | P01; integrate P08–P11 |
| P13 | Evaluation and all diagnostic tracks | P08–P11 |
| P14 | Full candidate generation and provisional selection | Passed bounded trials |
| P15 | Human review, judge calibration, final selection | P12–P14 |
| P16 | Export, benchmark card and reproducible release | P15 |

User scheduling update (2026-11-01): actual human crop/distractor review and review-decision intake are deferred until the complete provisional benchmark and Qwen outputs have passed automated checks. Preserve pending flags during generation/preparation; bind final review decisions to final item/asset/source hashes, repair/recheck rejected items, then freeze/export. This supersedes an immediate P08 review-intake dependency; graph proof and automated quality checks continue throughout.

P12 tooling and CPU evaluation scaffolding can be developed before MN5 execution. The ordering is a dependency plan, not a requirement to wait for GPUs before doing independent CPU work.

## P00 — Freeze the starting point and define policy precisely

- Inventory input manifests, source paths/splits and current code versions. Preserve GEN-1, GEN-2 v1/v2/v3 and existing VERB packs.
- Read actual schemas; record which relations, coverage statuses and reviews are available. Check grounding-recovery completion before any caption-dependent use; old process status is not evidence of completion.
- Create a new versioned benchmark configuration with taxonomy, primary-group assignment, scoring rules, quotas and review policy. Do not change the historic generator defaults globally.
- Define page numbering as the displayed 1-based chapter order, retaining stable page IDs and filename mappings privately.
- Operationalise the design's baseline definitions. Distinguish a fixed chapter-top1 guess, the better of two globally fixed rank strategies, and a top2-set oracle upper bound; these are different metrics. No per-item answer-informed “better guess.”

**Done when:** configuration and baseline definitions are unambiguous; input inventory reproducible; legacy code/input hashes and bounded compatibility fixtures are pinned; old implementation and artifacts unchanged.

## P01 — Shared contract and versioned private candidate store

Define the new layer’s item contract and read-only adapters for existing graph-generation schemas; do not extend or mutate legacy schemas in place. Candidate admission stores validity results, policy features and review status separately. Keep answer/program/proof bindings, graph and source hashes, evidence subgraph, image/context references, factual claims, transformations and provenance.

Add the four axes, complexity dimensions, primary group/tags, pair/probe relationships, risk strata, model/prompt versions and release status. Use explicit unknown/not-applicable values where a metric cannot be computed. Allow separate statuses for answer proof, source admission, wording, claims and human review.

Import existing outputs read-only through adapters. A selected legacy item is not automatically certified under new rules. V3 retains all gate-passing proofs; v1/v2 cannot supply proofs they discarded. Track candidate-level hashes, stable IDs, dedup lineage and current validation versions. Store valid but policy-excluded items; keep failed attempts in a separate audit log.

**Done when:** imports preserve source bindings; stale inputs fail; interrupted writes/resume are safe; schema and compatibility tests pass.

## P02 — Selection independent of generation

Implement a separate selector over the candidate store. Compute features once per compatible snapshot, then version each selection independently. Prefer an exact integer solver if dependency installation is acceptable; otherwise implement deterministic repair with explicit limitations. Record feasible, infeasible, timeout and unknown distinctly; claim maximum yield only with solver evidence.

Encode pair/group assignment, split counts, chapter caps, target coverage, answer distribution and sentence budgets. Baseline constraints are linear count inequalities once each candidate's shortcut outcome is fixed; ratio denominators must be defined by answer opportunity, not merely display format. Evaluate character priors on visual-choice character targets too, and page+1 only for questions with a defined anchor/offset.

Design starting targets: chapter-top1 <=20%, defined top2 strategy <=30%, page+1 <=20%, modal count <=25%, identity concentration <=25%, two-option <=5%. Report answer-type priors. Four-choice label chance is 25%; binary/determinability items consume the two-option budget even when phrased as sentences. A mode-count ceiling of 25% needs at least four distinct values and sufficient balance: test feasibility, including old 2–12 count restrictions, before adopting it.

Remaining small-denominator caps use configured n_min (initially 20) and explicit absolute alternatives. A zero-opportunity metric is N/A. A minimum group floor and its corresponding cap cannot disappear silently because a denominator is small.

**Done when:** synthetic feasible/infeasible cases, binary budgets and pair closure work; no policy rejection is reported as a wrong proof; selection reports binding constraints and reproducible IDs.

## P03 — Preflight before another full generation

Run a bounded, typed path/branch inventory up to depth 5, with budgets to prevent graph-walk explosion. Enumerate supported relation patterns, not arbitrary raw edges; report truncation instead of calling capped counts exhaustive. Inventory by chapter/split: target identities, readable aliases, verified cross-page identity links, available orders/panels, coverage, target values, offsets, evidence positions and trust.

Distinguish structural path counts from actual candidates that pass execution, necessity and visual ablation. Estimate gated yield from representative bounded trials. Re-select the 153 retained v3 candidates experimentally, without rewriting their programs; record any old eligibility restrictions that cannot be recovered by reselection. A v3-only pilot need not satisfy the final 1,000-item floors.

Publish a feasibility report mapping every proposed family to prerequisites and likely shortfalls. Choose meaningful-hop thresholds from evidence. Confirm or explicitly revise target allocations/limits before production generation.

**Done when:** a documented next-family list and feasible pilot exist, or precise evidence/policy blockers are reported; no unchanged full v3 rebuild recommended.

## P04 — Evidence admission and review adapters

Implement review-aware consumers for panel memberships, reading order and semantic mentions; preserve immutable CKG companions and decision hashes. Exact speaking turns need supported order, not simply box coordinates. Literal name occurrence is not a semantic mention.

Build batch alias review with mention and character crops; verify source identity, exact readable form and reviewer type. For caption-dependent families, extract typed atomic claims linked to spans, boxes and verified identity groundings; keep proposal and admitted-fact stores separate. No motivation, addressee, cause or narrative chronology inferred from proximity. Captions cannot be sole unverified answer evidence.

Retain explicit `closed_assumed` dependencies for exact counts/first/last/next/never. Audit these in a dedicated review stratum; unsupported absence remains UNKNOWN. Source failures block only dependent families.

**Done when:** source/review pins, unknown coverage and ambiguous links fail correctly; bounded accepted/rejected examples demonstrate every newly admitted relation.

## P05 — CRL and independent proof checker

Audit existing operators before adding duplicates. Reuse compatible operators by composition; implement new typed operations/compositions exclusively in the new layer for next speaking page, joint presence, last/first occurrences, page gaps, turns, sets, comparisons and range aggregates where missing. Define ordering, ties, empty sets and coverage obligations precisely. Introduce substring lookup only with a checked scope/normalisation contract and collision tests.

Add independently implemented proof rules in the new layer alongside each extension, without changing the legacy interpreter/checker. The new layer’s two engines must agree on source eligibility, reviewed companions and derived-world semantics. Maintain resource budgets and bind proofs to the exact graph/image variant.

**Done when:** synthetic wrong-answer/wrong-proof, missing-coverage, ambiguous-order, redundant-clause, empty/tie and stale-review tests pass; bounded real executions verify independently.

## P06 — Answer-first family expansion

Choose underrepresented supported targets before searching for programs. First wave: speaking-page chains, joint/last appearance and page gaps, co-presence intersections, and turn-order questions where order is admitted. Then speaking comparisons, mention-vs-presence, proximity traps, panel spatial relations and admitted caption-fact chains. “Never” and first/last must satisfy coverage rules.

Use readable names, scoped unique quotes, verified relational descriptors and later visual choices. Record all candidates passing validity before selection. Generate the same task with multiple anchors only when useful; deduplicate by task semantics rather than only text. Do not force low-frequency characters or large offsets where evidence does not support them.

**Done when:** family-level bounded yields, answer diversity, proof correctness, text-only ablation and necessary-page reports pass before a full family run.

## P07 — Long relational generation and compositional probes

Implement target-first constraint accretion, supported path walks and relation-map construction. Include clue puzzles, relation walks/maps, two-chain comparisons, dependent multi-part questions, statement verification and verified noise variants. Bind each required natural-language clause to a program clause and evidence. Remove redundant required clauses; label true noise separately.

For the long-relational target, check >=3 necessary clauses/pages and span >=5 initially. Generate natural L/XL wording only when the relations warrant it. Exactly grade character/page/set/statement-number and multi-part answers; store short-answer plus claim-explanation components where used. A false statement needs a contradiction proof, not lack of support.

Record meaningful hops, independent branches, combines, clause eliminations, near-miss density, trust mix and evidence position. Generate sub-question probes with parent IDs and evidence, isolated at evaluation so earlier answers are not provided to the full task. Report both directions of compositional inconsistency without assuming either proves a shortcut.

**Done when:** clause alignment, necessity and multi-part scoring pass; bounded examples demonstrate genuinely distinct chains/branches and three-page dependencies.

## P08 — Visual choices and crop assets

Create immutable derived crops/option sheets with image hashes, transforms, provenance and accessible A–D labels. Include them in the model-facing input as an explicitly marked reference, not hidden annotation. Keep original pages intact. Randomise/balance correct option positions; save the seed and mapping privately.

Use a different page for the correct reference crop when a verified cross-page identity exists. Verify distractor identities are distinct and visually distinguishable; near-miss programs should explain distractor choice. Avoid same-crop matching, inconsistent crop quality and answer-revealing layout. “None of these” requires proving exclusion from the complete option set. Human-check distractor sets in the pilot.

**Done when:** option/text/image bindings and exact scoring pass; an identity-ambiguity pilot demonstrates that crops do not fabricate cross-page ground truth.

## P09 — Masked input, determinability and contrast

Implement deterministic local rendering of black masks into new images; originals stay untouched. This is an exact image-processing operation, not generative image editing. Store region coordinates, transform version, original/derived hashes and scope. Recompute all affected annotations and derived facts, including overlapping text/tails/geometry/caption dependencies; deleting a single convenient edge is insufficient.

Define answer-changed and evidence-insufficient variants. For determinability, show an alternative consistent interpretation or another explicit ambiguity certificate where possible; simply obtaining UNKNOWN from an incomplete graph is not a certificate of visual unknowability. Review residual clues in surrounding panels/pages.

Create paired unmasked/masked or one-clause-change items with verified answer differences. Keep pair members together during selection/review; evaluate separately to avoid cross-question disclosure. Explicit graph-only exclusions remain labelled `formal_hypothetical` with stated scope.

**Done when:** edited pixels and proof worlds match; residual-leakage tests, variant hash binding, pair scoring and bounded visual review pass.

## P10 — Atomic claims and sentence scoring contracts

Define required/optional claims with typed arguments and source facts or executable subprograms. Build claim lists before synthesis. Forbidden claims must be verified false under sufficient coverage; distinguish false from unsupported/unknown. Include near-miss contradictions without treating the finite list as exhaustive.

Require every factual clause in generated question/reference answer to be supported; citations alone do not establish entailment. Reject/hold extra or unresolved claims. A claim-verified answer must cover all required claims and answer the actual question. Support exact short answer plus separately scored explanation.

Specify required-claim recall, forbidden-claim assertions, independently detected unsupported assertions, and all-required-correct. Do not label “no forbidden claim found” as zero hallucinations. Keep subjective style outside factual scoring.

**Done when:** swapped entities/pages, negation, extra unsupported statements, omissions and paraphrases have adjudicated fixtures and correct scoring outcomes.

## P11 — Qwen preparation and MN5 execution

Version ordered task-specific packs: chapter/page order; target program/answer or fixed claim list; nodes/descriptors; directed facts with trust/coverage; dependency DAG; attached evidence; prohibited assertions. Preserve page order separately from traversal order. Existing VERB payloads use a narrower contract: new full-evidence packs need a new version, not silent reuse.

Paraphrase mode is text-only. Synthesis uses text plus necessary evidence crops. Verify the actual MN5 model/checkpoint, processor, context limits and deployment before implementation; use configured endpoints and Slurm resources. Apply token/image budgets with explicit failure or smaller valid tasks, never silent evidence truncation.

Implement resumable request/response IDs, retries, per-request statuses, raw responses, model/prompt/pack hashes and response ingestion. An independent back-parser must recover the intended program/clauses without seeing the expected program/answer as its oracle. Compare task semantics, execution and required/alternative evidence dependencies. Merely matching a coincidental answer is insufficient. Synthesis passes P10 checks; all sentence items proceed to human review.

**Done when:** CPU pack/resume/ingestion tests and bounded MN5 inference pass; unsupported additions, altered clauses and unfamiliar unverified wording cannot be auto-released.

## P12 — Review interface and acceptance sampling

Build a private per-item viewer with original/edited pages, crop options, question, answer, clause/proof trail, claim sources, coverage assumptions and accept/reject/flag reason codes. Bind decisions to exact versions. Record human and AI separately. All claim-verified sentence items receive individual human review; retain source-specific strata for models and assumed closure. Failed automatic checks remain quarantined.

Predefine random sampling, strata, tolerable error bounds and corrective actions. For zero errors use an exact one-sided binomial confidence bound (or appropriate finite-population calculation); report n and stratum size. The rule of three is an approximation, not a guarantee. Account for small strata, correlated generator failures and multiplicity if claiming a benchmark-wide bound. Do not repeatedly sample until a clean batch appears; fix/version causes and disclose earlier findings.

**Done when:** stale reviews invalidate; reviewer assignments and sampling manifests reproduce; release eligibility is separate from per-item vs stratum acceptance.

## P13 — Evaluation, baselines and all diagnostic tracks

Implement exact scorers for identities/accepted readable variants, page mapping, counts, booleans, sets, sequences, quotes, option labels and multi-part answers. Preserve label uncertainty and empty/unknown semantics. Implement claim scoring from P10, pair all-correct accuracy, component-vs-full composition results, and evidence-page precision/recall with alternative valid supports.

Build main images+question, images+ID-free facts, facts-only, OCR-text-only and blind inputs. Strip answers, proof traces, target highlighting and selected-evidence ordering that would reveal the result. Diagnostic facts must have a documented common scope: do not give only the minimal supporting facts and present that as pure reasoning difficulty. Include needed task assumptions consistently and label diagnostics as privileged settings. Sanitise filenames/IDs and private annotations from main inputs.

Report by source split, family, answer opportunity, meaningful hops, required pages/span, clause count, position, trust and coverage. Position controls select natural examples from start/middle/end; do not reorder chapter chronology just to move evidence. Question-only “chance” has no universal value for open-ended answers: use empirical prior baselines and random-option chance where defined.

**Done when:** score fixtures, answer-free exports and identical item alignment across tracks pass; no diagnostic record counts toward the 1,000-item total.

## P14 — Full generation and provisional selection

After bounded acceptance, generate roughly 3x surplus where feasible, with per-family yield reports rather than a blind 3,000 guarantee. Import eligible legacy items, run new graph families, create derived assets/probes and execute scheduled MN5 wording/synthesis. All full jobs are launched by the user with documented resume semantics.

Run frozen dedup and selection. Program+answer+page overlap is a duplicate signal, not a universal deletion rule: keep intentional contrasts and probes, and distinguish different reasoning on shared evidence. Keep all related items in their original source split; do not move chapters to repair quotas. Report actual split proportions, infeasible targets and solver status.

**Done when:** provisional IDs, group assignment and review reserve are pinned; dependencies and all validity bindings verify; unsatisfied targets are explicitly resolved before release.

## P15 — Human review, calibration and final freeze

Review sentence items individually and execute predeclared acceptance samples for remaining strata, including crops/masks and assumed-closure risks. Fix failures within the new layer, recording corrected evidence as new overlays when needed; invalidate only its dependent artifacts and reselect/review replacements. Report legacy-source issues without altering the original source or implementation. Publish achieved review coverage and bounds.

Calibrate claim-entailment judges on approximately 200 human-labelled claim–answer pairs stratified by errors; keep a held-out calibration assessment. Prefer a different model family from the generator and report judge versions. Use two judges/adjudication where configured, without assuming independence solely from family names. Report agreement, Cohen's kappa where meaningful, error types and class imbalance; humans settle unresolved cases.

Freeze final scoring weights before evaluating target models. Run shortcut baselines, all diagnostics and leakage/asset audits. Select exactly 1,000 only after release gates pass, or document the shortfall and required decision.

**Done when:** every final item has release permission under its review policy; no pending proof/wording/claim failures; final counts, pairs, baselines and source splits reconcile.

## P16 — Export and benchmark card

Export a model-facing schema (ordered images, explicit reference options/masks, question, format instructions) and separately controlled answer/evaluation metadata. Keep raw annotations, names/IDs revealing answers, graph/program/proof, Qwen packs and review UI assets out of answering-model inputs. Label modified/diagnostic tracks clearly.

Publish the benchmark card: actual allocation and overlap, split definition, model/source exposure limits, coverage assumptions, trust/admission rules, review statistics, baseline results, claim-judge reliability, position/composition/pair metrics, known limitations and reproducibility instructions. Keep source and licence/provenance metadata from the dataset; do not assume redistribution permissions for source images.

**Done when:** an independent export validation reproduces item/answer mappings, checks all assets/hashes and privacy boundaries, and confirms 1,000 main items with complete private provenance.

## 5. Implementation layout and artifact conventions

Create a separate `src/comics_qa/benchmark1000/` namespace with adapters importing compatible existing modules read-only. Place new configs under `configs/benchmark1000/`, new scripts under distinct `benchmark1000_*` names, and tests under a separate benchmark1000 test namespace. New reasoning/independent-checker operations, evidence overlays, claims, diagnostic and review code all live in the new layer. Existing `tasks/graph/`, evidence modules, scripts and configs retain their code and behavior. These paths are planned, not yet created.

Each stage specifies exact new files before edits. The roots below are dedicated to the new layer; they are planned artifact locations, not commands that already exist:

- `reports/benchmark1000/<version>/`: inventory, preflight, yields, baseline/solver/review reports.
- `items/benchmark1000/candidates/<version>/`: private append-only candidate shards and manifests.
- `items/benchmark1000/selections/<version>/`: selected IDs and policy snapshot, referencing candidates.
- `items/benchmark1000/qwen/<version>/`: private request packs, raw responses and validation records.
- `evidence/benchmark1000/<version>/`: new evidence overlays, crops, option sheets, edited images and transform manifests.
- `reviews/benchmark1000/<version>/`: snapshot-bound decisions and sampling manifests.
- `exports/benchmark1000/<version>/`: final main and explicitly labelled diagnostic exports.

All large artifacts live under configured BENCH_ROOT outside Git. Use atomic shards, a single manifest owner, checkpoint/retry rules and stage-local fingerprints. A selection-policy change should not invalidate an unchanged proof; an image transformation, source review or reasoning-semantics change must invalidate its affected dependencies. Record code versions at module/stage scope where possible, avoiding unrelated-code changes forcing complete rebuilds.

## 6. Coverage checklist against the revised design

| Design topic | Plan stages |
|---|---|
| S1/S2 shortcut constraints and small denominators | P00, P02–P03, P13–P15 |
| S3/S4 answer-first and varied page targets | P03, P05–P06 |
| S5/S6 visual references, aliases and safer quote anchors | P04–P05, P08 |
| S7/S8 permanent store and validity/policy separation | P01–P02 |
| Four-axis taxonomy and complexity inventory | P01, P03, P07 |
| All priority 1–3 families | P04–P10 |
| Ordered Qwen context, paraphrase/synthesis and parse-back | P10–P11 |
| Atomic claim evaluation and judge calibration | P10, P13, P15 |
| Section 9A long relational forms, including noise/multi-part | P07, P10–P11 |
| Visual choice, masks and contrast pairs | P08–P09 |
| Composition probes, evidence pages and position control | P07, P13 |
| All five diagnostic tracks | P13 |
| Risk review and acceptance sampling | P12, P15 |
| 1,000 allocation, >=200 long-relational overlap, release | P02–P03, P14–P16 |
| D1–D19 | P00 defaults; validated through the stages above |

## 7. First implementation task

Start with **P00 + P01**, then **P02/P03**, entirely within the additive architecture in section 1A. The first useful deliverable is a compatible candidate store and a feasibility/selection report over existing pools. It should expose the old policy conflict and the evidence needed for new families before another full build. Do not begin with a long GPU generation run.

When resuming, read this plan, the revised discussion brief and STATUS.md; state which stage is active and implement only that stage's bounded scope. Update STATUS.md after each stage and give the user exact full-run commands only after the implementation and bounded validation exist.
