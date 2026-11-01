# Native proposal admission (2026-10-30)

This additive CPU stage reads a **completed semantic run**. It neither regenerates questions nor edits its input proposals, legacy code, evidence or selection policy. Output candidates have fresh question-gate certificates; human review, complexity-group assignment and final release remain pending.

Run from `Code/`:

```bash
bash scripts/benchmark1000.sh admit-native \
  --semantic-root /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/semantic_v2 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1
```

No GPU/Qwen/OR-Tools needed. Repeat the exact command to resume. Each proposal check is published atomically under a single-writer lock; the completed manifest is published last. Changed code, inputs, chapter scope, budget or reviews require a **fresh output directory**. A completed output is checksum-verified before reuse. Optional `--chapter CHAPTER` may repeat for bounded tests. `--max-ablation-pages` defaults to 8; exceeding it holds an item, never assumes success.

## Checks

- Independently check the stored answer proof and its graph/visibility/rich snapshots, exact question/answer/program binding, context and evidence.
- Parse the four current **closed templates** independently: quote → next speech, speaker relay, two-quote joint appearance, three-page clue intersection. Compare the parsed program with the proved program; canonical CRL hashes account for commutative operands. Changed negation, page references or constraints cannot inherit a proof. Unsupported free-form/Qwen wording remains held.
- For clue intersections, independently prove that removing the hidden `is_named` domain restriction still gives the same unique character. The template does not state that restriction.
- Names must be exact readable canonical forms or explicitly reviewed readable aliases, resolving to one registered identity. Apply the existing canonical/reviewed embedded-name policy to quoted text too. A readable short form is not automatically an approved alias. Check exact answer leakage and the used transcripts’ full normalized Paddle/MAGI consensus.
- Re-execute each represented clue/branch removal and the relay’s other-person exclusion. UNKNOWN cannot certify clause necessity; known ambiguity, emptiness or a different answer can. For relays, additionally follow the **original speaker** after the intermediate page: the identity switch must affect the final page, not merely disambiguate an intermediate `the()` operation. A same-page result is held; an unknown alternative is held.
- Rebuild rich evidence after each supported-page removal, also removing hidden-page OCR alignments. Require at least two necessary visual support pages for a quote scan, three for joint/relay/clue templates. An ablation that makes the fixed program UNKNOWN is recorded as breaking that program, not as a new exact answer.
- Rebuild the OCR-only world with text locations, OCR and lexical mappings retained, and character/speaker visual facts removed. Hold questions it still answers.
- Deduplicate **only passing** proposals using resolved identities, anchor/intermediate/target pages and relation conditions. Different quotes for the same next-speaker/relay path merge. Distinct necessary clue-page combinations remain separate even when their answer identity agrees. A held proposal cannot suppress a passing alternative. The representative is the shortest question, then stable ID; duplicate provenance remains in the report.

These are operational program/constraint and visual-dependency checks. They do not certify universal semantic minimality, meaningful-hop counts, arbitrary OCR-noise robustness, narrative quality, final pool quotas or blind-model difficulty. Primary group stays `unassigned`, meaningful hops stay null. Later complexity certification/selection must enforce the agreed allocations and shortcut limits. Sentence, visual-option, synthesis and reviewed-rich counterfactual profiles are not admitted by this initial implementation.

## Output and review

- `report.json`: admitted/held/duplicate decisions and reasons; duplicate → passing representative.
- `checks/*.json`: per-proposal receipts, complete independently checked counterfactual executions, necessary pages, exact-name results and resolved-character proofs.
- `candidates/*.json`: new `admitted_native.1` records embedding the untouched original proposal and admission receipt. Original proposal IDs/statuses remain unchanged.
- `pending_alias_reviews.json`: exact snapshot/evidence-bound requests; **all pending**, no automatic approval.
- `config.json`, `manifest.json`: inputs, code fingerprints, counts and immutable output checksums.

```bash
bash scripts/benchmark1000.sh verify-store \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1

bash scripts/benchmark1000.sh review-page \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1_review.html

# Recompute admission and compare the full saved receipt, including counterfactuals.
bash scripts/benchmark1000.sh check-proofs \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/admission_v1_recheck.json
```

`verify-store` checks stored integrity/receipt bindings; `check-proofs` freshly re-executes admission against pinned evidence. Selection and review can consume the candidate store. Native MN5 packing/export remains explicitly unsupported; no production release is implied.

If an alias is legitimate, **copy** the pending review list outside the immutable output, e.g. into `configs/benchmark1000/reviews/`, inspect its page/text evidence, and record `decision: approved`, `name_use: character_name`, a reviewer and justification. Preserve snapshot pins/evidence IDs. Leave uncertain rows pending or reject them. Pass the reviewed copy via `--alias-reviews FILE` to a new `admission_v2` output. Passing an unchanged pending file grants no eligibility. Alias review does not approve final human QA review.

## Bounded verification

**99 CPU tests pass; all 142 frozen legacy files unchanged.** Three real chapters / 15 saved proposals: Blue Exorcist c001, Assassination Classroom c002 and Hunter x Hunter c001. The relay switch was found to leave the final answer at page 14 and is therefore held, even though intermediate selection became ambiguous. The long clue answers remain held for unreviewed “Nagisa”; the four joint queries have redundant branches. Result: **4 admitted, 9 held, 2 duplicates**; all four admitted certificates were freshly reproduced with `check-proofs` (0 rejected). One pending alias request for Nagisa was emitted without approval. Temporary verification output: `/tmp/comicsqa-native-admission-final`. The full 32-proposal admission run is left for the user. Unit tests cover wording/program changes, exact-name approval, necessary-clue recomputation, OCR-only worlds, relay shortcuts, deduplication, provenance tampering, atomic resume and changed-config refusal.

## Expanded native profiles

The [expanded family wave](EXPANDED_FAMILIES.md) adds typed `recipe` execution, Page/Count/Boolean/Page-set admission and measured primary-group certificates for those new profiles. `--proposal-root` aliases `--semantic-root` for complete family outputs. Older records retain their original receipts and pending complexity; no archived artifact is upgraded in place. New admission reports include diversity diagnostics and private, non-main compositional probes.

## Coverage-aware recipes

[Coverage-aware windows](COVERAGE_WINDOWS.md) use a separate `coverage_recipe` proof engine for explicitly shifted/shorter ranges and independently checked membership completeness. Admission also treats loss of exactness as a broken answer in ablations. Current name, wording, dependency, numeric-overlap and diversity gates remain in force; old recipe receipts remain valid.
