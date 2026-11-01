# Full necessary-switch pilot review — 2026-10-31

The user completed `reports/benchmark1000/switch_v1` and `switch_v1_admission`. Generation covers all 50 chapters in the opt-in `necessary_switches.1` mode, with dependency budget 128 full checked recipe executions per chapter, atomic probe budget 192, window/reference budget 1,000, maximum interval 10/minimum 4, maximum shift 20 and proposal cap 3. Admission uses page-ablation budget 16. This is bounded collection-wide search, not exhaustive enumeration or final benchmark selection.

## Verified outcomes

- All 53 generation output hashes and 9 admission output hashes verify. Configuration bindings and current Python code hashes match.
- Four answer-proved proposals validate; admission yields **2 admitted, 0 held, 2 resolved-path duplicates**. Both saved candidate/admission receipts validate.
- There are 10 private auxiliary probes. They do not count as main QA pairs.
- The two candidates are one seen/one unseen, in Blue Exorcist c002 and Spy x Family c001. Both have a certified three-operation chain: two necessary navigations and one necessary character switch, with three necessary pages and three necessary visual pages.
- No three-navigation/two-switch, five-operation walk is admitted by this run. Program length or a distant search range is not counted as additional complexity.

| Chapter | Quote anchor page | Search interval | First speaking page | Final answer after switch | Answer if the switch is bypassed |
|---|---:|---|---:|---:|---:|
| blue-exorcist__c002 | 6 | 17–26 | 17 | 18 | 19 |
| spy-x-family__c001 | 55 | 68–71 | 68 | 69 | 70 |

For Blue Exorcist, the anchor is “welcome to true cross academy.” The speaker first speaks on page 17 in the declared range; following the only different character drawn there leads to page 18. Keeping the original person instead leads to 19. Thus the identity change affects the answer, rather than merely lengthening the question. Every navigation-removal intervention also changes the answer. The Spy x Family anchor is “...i became a spy in the first place.”; its switch similarly changes 70 to 69.

A fresh independent replay of both admitted certificates succeeds: **2 verified, 0 rejected**, reproducing the full admission receipts. Local replay report: `/tmp/comicsqa-switch-v1-recheck-20261031.json`. All 142 frozen legacy files still match.

## What search rejected

There were 580 newly checked dependency executions (original recipes plus bypasses). Candidate-level first-blocker outcomes:

| Outcome | Recipes |
|---|---:|
| Passed every dependency check | 4 |
| Redundant switch | 226 |
| Redundant navigation | 16 |
| Unproved navigation bypass | 13 |
| Unproved switch bypass | 8 |
| Dependency budget exhausted during a recipe | 4 |

These are first-blocker counts, not a count of every bad operation or all possible paths. The predicate-discovery phase additionally skipped windows without known topology or provable required predicates. No atomic predicate budget was exhausted.

Four chapters reached the independent dependency-execution cap of 128:

- `assassination-classroom__c001`: 64 redundant switches before the incomplete next recipe.
- `blue-exorcist__c001`: 64 redundant switches before the incomplete next recipe.
- `blue-exorcist__c002`: three passing windows plus redundant/unproved alternatives; these three passing proposals collapse to one admitted path.
- `chainsaw-man__c001`: 40 redundant switches and 16 redundant navigations before the incomplete next recipe.

Two chapters also hit the window/reference trial cap. Therefore no conclusion that other necessary paths do not exist is justified. Any later budget expansion must use a fresh output, preferably targeted to recorded limiting chapters. It is optional pool expansion, not a requirement to trust these two candidates. Do not relax necessity requirements to accept the rejected paths.

## Pool overlap and next stage

The two admitted switch paths are new relative to the saved earlier admission stores. Distinct stored resolved-path hashes total:

- 96 across `coverage_v1_admission` plus `coverage_v1_sets_admission`.
- **98** when adding `switch_v1_admission`.
- **107** when also including `families_v1_admission`.

These are read-only cross-store inventory counts, not a newly published merged store or a final semantic-deduplication guarantee. Previous candidate counts overlap, and private probes are excluded. Legacy GEN-1/GEN-2 pools are not included in these native admission totals.

Next implementation: **a unified proof-bearing candidate-pool inventory with cross-run deduplication and a feasibility/gap report against the 1,000-QA design**. Include existing legacy pools through their explicit adapters and preserve their actual validation/review status. Preserve all parent hashes, receipts and rejected/duplicate provenance; distinguish candidate availability from final release eligibility. Report shortages by split, group, meaningful hops, answer format, chapter, visual dependence and long/sentence status before deciding which family to expand. Do not silently promote archived items or relax quotas to produce a nominal count of 1,000.

This stage should precede another broad unchanged build. Qwen wording/synthesis on MN5, alias decisions, human review and final export stay separate and pending. Existing scripts/results and source annotations are unchanged by this review.
