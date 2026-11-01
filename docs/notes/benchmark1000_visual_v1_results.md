# Full P08 visual run review — 2026-11-01

Inputs: `reports/benchmark1000/visual_preflight_v1`, `visual_pilot_v1` and `visual_pilot_v1.check.json`. The user completed all three commands. This review performs integrity checks and two fresh item spot checks; it does not regenerate the pilot or repeat the entire 45-item execution batch.

## Integrity and verification

- All 51 preflight and 272 pilot output hashes verify; configurations/checkpoint payload hashes are bound and job code matches the current implementation.
- The pilot pins the exact completed preflight. All three source-manifest pins still match their current source files.
- Every one of the 45 content-addressed item IDs, public-input mapping, scoring mapping and review-request hash binding checks out.
- The saved independent-check report covers exactly those 45 IDs: **45 verified, 0 rejected**. This establishes the implemented graph/pixel/label/ablation profile, not human visual fairness.
- Fresh independent spot checks on a seen item (Chainsaw Man c001) and an unseen item (Assassination Classroom c001) both pass against current source images and graph worlds. Spot-check report: `/tmp/comicsqa-visual-fullrun-spotcheck-20261101.json`.
- All 142 frozen legacy files still match. Existing native/legacy data and `pool_v1` were not changed by this review.

## Preflight results

The preflight covers all 50 chapters with minimum reference crop edge 48 and quote-anchor consideration cap 128 per chapter.

| Quantity | Result |
|---|---:|
| Distinct usable reference identities across chapters | 244 |
| Eligible raw quote anchors | 201 |
| Quote anchors considered | 201 |
| Independently checked quote programs | 169 |
| Verified quote anchors | 105 |
| Distinct verified quote-speaker target identities | 27 |
| Contributing chapters with verified targets | 17 |
| Quote-budget-hit chapters | 0 |

The report's `trusted_identity_ids=425`, `trusted_cross_page_ids=347`, `usable_reference_ids=323` and `verified_target_ids=32` are **sums of chapter-scoped counts**. They must not be presented as distinct corpus totals. Use the top-level `unique_*` values for that purpose.

Of the 201 anchors, 32 lack four eligible cross-page options; of the 169 checked programs, 64 do not prove an exact speaker under current evidence rules. Missing evidence remains UNKNOWN; none was automatically closed or promoted.

Reference exclusions are 6,568 generic/page-local identity appearances, 6,143 known text-overlap crops, 1,419 large other-character-overlap crops, 1,066 geometry-review cases and 292 size/aspect cases. These are crop/appearance exclusions, not distinct identity counts, and do not establish visual absence.

**No quote budget was exhausted.** Increasing that budget alone will not produce more target identities under this same family/anchor eligibility. Metadata suggests a wider usable reference pool than this dialogue-only family can address; it does not certify 244 eligible answer targets.

## Pilot results

The pilot uses up to four items per chapter, at most 32 attempts, seed 42 and Pillow 13.0.0.

- **45 questions**, **27 target identities**, **17 contributing chapters**.
- Split: **27 seen / 18 unseen**.
- Correct labels: A=11, B=11, C=12, D=11, as expected for the seeded balanced schedule.
- Zero rejected pilot attempts. Preflight already filtered unsupported anchors; zero pilot rejection does not mean all raw annotations are usable.
- There are 105 verified anchors available; the per-chapter item cap limits how many are rendered. Raising that cap may add more questions about existing targets, but cannot exceed the preflight's 27 target identities for this family.
- All records remain `visual_pilot_not_native_admitted`; human and distractor review are pending, with no release approval.

The earlier candidate-answer inventory has 59 identities. The pilot overlaps 17 and adds **10 new identities**, so the candidate-plus-pilot union is **69**, leaving 81 against the design target of 150. This is potential inventory coverage, not reviewed/released coverage, and is not written back into the immutable `pool_v1` report.

The pilot therefore demonstrates that name-free image answers can add targets, but this first quote-speaker family does not solve identity coverage or the chain/branch/long-relational quotas by itself. Qwen paraphrasing would not create the missing identities or graph dependencies.

## Human-review status and next implementation

`visual_pilot_v1/review.html` is the private source-page/option-sheet/gold packet. Open it in a browser. It is self-contained and approximately 45 MB. `review_requests.json` contains 45 initially flagged templates with blank reviewers: these are **pending placeholders, not 45 human rejections**.

Inspect source/reference identity agreement, crop visibility/quality, similar faces/poses, whether all options are visually distinguishable, and whether composition or layout reveals an answer. Copy the JSON outside the immutable pilot directory before recording actual decisions. Do not label AI-only triage as human acceptance.

**Next implementation: P08 review-decision intake and reviewed visual admission/pool integration.** It should validate explicit human/AI reviewer type, exact item/asset/source bindings, accept/reject/flag decisions and stale/conflicting reviews. Only records satisfying the agreed human visual pilot checks should become a new reviewed admission view. Keep the original pilot untouched; do not automatically add all 45 to the native pool or overwrite pending statuses.

After the intake/admission mechanism exists and actual reviews are available, rebuild the unified inventory in a fresh version and measure real gains. For further identity expansion, investigate non-OCR visual-appearance/marked-reference anchors using trusted cross-page graph links rather than relaxing generic identity or visual-fairness rules. Continue broader branching/long-relational families separately; keep the current 1,000-QA policy unchanged until an explicit design decision.


## User scheduling update — 2026-11-01

This supersedes the immediate review-intake priority above. The user chose to perform human crop/distractor review and review-decision intake at the final stage, after all benchmark candidate families and Qwen work are prepared.

Agreed execution order:

1. Finish remaining graph-grounded families and required automated proof, dependency, pixel and source checks. Preserve review-pending visual items as explicitly provisional candidates.
2. Prepare the provisional benchmark/reserve pool and supported ordered Qwen inputs; run Qwen on MN5.
3. Independently validate final wording/program/answer correspondence and other automated quality checks.
4. Review the complete final provisional questions, answers, images and evidence together. Generate review requests bound to these final item/asset/source hashes; keep human and AI decisions distinct.
5. Reject or repair flagged items, recheck replacements, then complete reviewed admission, selection freeze and export.

Pending human review does not block family development or Qwen preparation. It does not grant reviewed admission/release status either. A future working-view adapter may carry the visual pilots into preparation with their pending flags; the existing immutable pool/admission code and outputs are unchanged by this decision. Next implementation should return to broader branching/long-relational graph families rather than making human review the immediate dependency.
