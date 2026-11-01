# benchmark1000 foundation v1: results and next work

Date: 2026-10-30. Outputs: `/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/` and `items/benchmark1000/v1/candidates/`.

## Verified run

- Store: **3,630 candidates**, comprising the preserved GEN-1 selection and GEN-2 v3 retained pool.
- Proof report: **3,630 verified, zero rejected**. All item IDs/hashes and saved program bindings were checked against the immutable store. This review validated saved reports; it did not rerun 3,630 programs again.
- All candidate manifest output checksums and the report-to-store manifest bindings pass.
- Policy: **600 seen / 400 unseen** final targets, derived from **30 seen / 20 unseen source chapters**. This freezes proportions, not feasibility.
- Original CP-SAT pilot: **2,000 selected, optimal**, 40 per chapter across all 50 chapters. That equals the chapter capacity upper bound (50 × 40). Its objective value/bound is 102,050 = 2,000 × 51 + 50.
- The pilot intentionally omits final size/group/identity/long-question floors. The 2,000 result is expected; it is neither the final selection nor an instruction to release 2,000 questions.
- All 142 legacy implementation files still match the durable start baseline.

## What the original pilot contains

| Dimension | Result |
|---|---:|
| Seen/unseen items | 1,200 / 800 |
| Chapters | 50, each with 40 items |
| Count answers | 1,418 |
| Character answers | 145 |
| Comparison/multiple-choice-format answers | 338 |
| Page answers | 99 |
| Primary groups | All 2,000 are legacy `short` imports |
| Distinct answer identities | 51 selected; 59 in the entire store |

The comparison format includes inherited comparative answers, not newly generated crop choices. It does not demonstrate that visual-choice generation is integrated.

## Gaps that still prevent the intended final benchmark

1. The store has only **59 distinct character-answer identities**, below the proposed 150 target. The graph inventory has **266 distinct named identities depicted on at least two pages**. Those are possible targets, not verified question yield: readable references, visual identity bridges, query uniqueness, coverage and necessary reasoning still need checking.
2. Imported items are conservatively classified as `short`. Operation count is not certified meaningful-hop count. New long, branching, sentence and edited-input groups have not been filled by this run.
3. All 50 structural inventories hit their 10,000-state budget. These are truncated directed raw walks, not an exhaustive semantic path/branch inventory. They establish neither long-question yield nor impossibility.
4. The original preflight says `proofs_archived=3630` / `proofs_revalidated=0` because the store itself is immutable. The separate proof report is successful; the counter does not mean proof checking failed. A new read-only view can now apply that report without rewriting the store.
5. Original next-page features were incomplete for GEN-1. Only two of the pilot's 99 page answers had measured offsets. No conclusion about all page answers' shortcut rate was justified from that report.

## Implemented follow-up: read-only proof and feature views

New code: `benchmark1000/views.py`, `audit-features`, and optional `select --proof-report ... --feature-report ...`.

- Recover next-appearance anchors from typed `next_app` proof children, not arbitrary page numbers in question text.
- Bind each overlay row to the store manifest and original candidate content hash.
- Recompute recovered offset features on application; forged/stale rows fail.
- Apply saved verified proof status in a derived in-memory view; original store files stay unchanged.
- Preserve source report hashes and original candidate hashes in the view.

The new audit found **191 page answers in the full store**, all recoverable next-appearance offsets:

| Offset | Candidates |
|---|---:|
| +1 | 157 |
| +2 | 21 |
| +3 | 10 |
| +4 | 1 |
| +6 | 1 |
| +9 | 1 |

Files added alongside the original reports:

- `feature_audit.json`
- `pilot_validated_view.json`

The latter is a separate 10-second CP-SAT experiment: **optimal, 2,000 items**, preserving the original store, original pilot and original policy. Test suite: **64 CPU tests pass** after these additions.

## Important selection-policy issue exposed by the audit

The view pilot selects **19 anchored page answers in each split**, with **17 of 19 answering +1**: approximately **89.5% page+1 accuracy**.

This complies with the current configured small-denominator rule: below 20 page answers, the percentage baseline is inactive and an absolute per-chapter cap applies. Maximising yield can therefore settle just below the denominator threshold. “Optimal” means optimal under that policy, not low shortcut bias or final benchmark readiness.

Before final selection, explicitly resolve this: enforce global shortcut limits even for small nonempty answer groups, require minimum opportunity-group sizes, or retain an audited small-group exception with a clear label. Do not silently change the completed v1 policy. New offsets and richer families are still needed; an optimiser cannot invent diversity. No numeric caps were changed in this review.

## Next implementation

Continue P03 semantic/typed path and branch inventory, plus native candidate/validation-view integration. Use executable supported compositions and necessity tests, not capped raw graph-walk counts, to choose the next family targets. Extend new families and visual identity references before another large question-generation build. Broader Qwen sentence/wording validation, human review and final release remain pending. Do not rerun the unchanged original foundation to obtain 1,000 or send this pilot to Qwen as a final benchmark.

## Reproduce the overlay experiment

```bash
bash scripts/benchmark1000.sh audit-features \
  --store /data/151-3/comics/ComicsQA_Benchmark/items/benchmark1000/v1/candidates \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/feature_audit.json

BENCHMARK1000_PYTHON=/path/to/benchmark1000/env/bin/python \
  bash scripts/benchmark1000.sh select \
  --store /data/151-3/comics/ComicsQA_Benchmark/items/benchmark1000/v1/candidates \
  --policy /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/policy.json \
  --proof-report /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/proofs.json \
  --feature-report /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/feature_audit.json \
  --pilot --backend cp-sat --seconds 10 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/pilot_validated_view_NEW.json
```

Use the actual environment path. Choose a fresh output for a new solver experiment; original result files are create-only. The already-created view report need not be regenerated.
