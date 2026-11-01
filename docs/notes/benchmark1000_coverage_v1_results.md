# Coverage-aware full-collection pilot review — 2026-10-31

Inputs: immutable `reports/benchmark1000/coverage_v1` and `coverage_v1_admission`. The user executed generation and admission over all 50 chapters. Caps: three proposals/nine executions per family/chapter, search budget 1,000, maximum window 10/minimum 4, maximum shift 20, 192 new discovery queries per family and four retained windows per reference. This remains a bounded pilot, not exhaustive generation or final release.

## Integrity and outcome

- Generation parent manifest: all 53 output hashes verify; config binding matches. The native store validates all 141 answer-proved proposals. The job's Python code hashes match the current implementation.
- Admission parent manifest: all 237 output hashes verify; config binding matches. All 93 admitted candidates validate, including saved independent proof/admission receipts. No full fresh replay of all 93 was run during this review.
- Counts reconcile: 141 executions/proved proposals → 93 admitted, 23 held, 25 resolved-path duplicates.
- There are 317 auxiliary probes; they are private diagnostics and do not count as QA pairs.
- Contributions come from 16 chapters, 51 seen/42 unseen. The full 50-chapter scope was inspected; chapters without proposals are not silently skipped.
- All 142 frozen legacy files still match. Completed family/coverage outputs and source annotations remain untouched.

| Family | Proposals | Admitted | Held | Duplicate |
|---|---:|---:|---:|---:|
| Successive speech | 45 | 36 | 0 | 9 |
| Next-speaking-page line count | 39 | 23 | 0 | 16 |
| Last appearance in range | 27 | 27 | 0 | 0 |
| Speaking-page comparison | 6 | 4 | 2 | 0 |
| Speaking-page gap | 3 | 3 | 0 | 0 |
| Character-switch walk | 18 | 0 | 18 | 0 |
| Shared presence pages | 3 | 0 | 3 | 0 |
| Shared speaking pages | 0 | 0 | 0 | 0 |

Compared with the earlier full family pilot, admitted yield rises from 39 to 93. Those are overlapping pools, not 132 different QA pairs: 30 stored resolved-path hashes occur in both; their union contains 102 distinct stored hashes. That is a provisional two-store hash comparison, not a selected or semantically deduplicated final benchmark.

## Answer and graph diversity

- Answers: 63 page, 26 count, 4 Boolean; still no admitted sets or character answers in this saved run.
- Count values cover 1–8. Page offsets from the explicit range predecessor cover 2–9. Shift distance is not counted as extra reasoning.
- Primary groups: 15 chain, 48 short, 30 aggregate/compare; no admitted branch-combine group yet.
- Certified meaningful-hop distribution: 0:27, 1:30, 2:21, 3:15. Thus 93 candidates does not mean 93 hard multi-hop questions. Last-in-range items contribute the zero-navigation category.
- 37 questions contain at least 60 whitespace-delimited words. Length alone does not establish long relational complexity.
- The diagnostic report lists no current pool-policy violations. Admission does not apply final global selection quotas; this does not establish 1,000-item feasibility, target allocations or release approval.

A recovered gap example asks for the first speaking pages in range 52–57 of the speakers of “what was father fujimoto like...” (page 46) and “i don't want to become an exorcist to get revenge.” (page 47), then asks how many pages lie strictly between them. Answer: 2. Its two branches and visual-page necessity pass admission.

## Shared sets: a verification budget, not an unproved answer

All three answer-proved sets are in `hell-s-paradise-jigokuraku__c001`. Both branch-removal checks demonstrate necessity: removing a person admits extra pages. The saved holds list `page_ablation_budget_exceeded`, `insufficient_necessary_visual_pages` and `complexity_uncertified`.

The full proof-support page counts are 13, 14 and 14, exceeding the chosen admission limit of 12. Therefore page ablations were skipped, and the latter two hold labels are consequences of incomplete verification, not established failures of visual dependence. Context contains all 67 chapter pages; ablation budget applies to proof-support pages, not the full context or just the explicit window length.

A bounded fresh read-only assessment of proposal `b1000n:e79d74ee48b0a738a19eaebdfee36039fc345e1f06b6dec4b22ac5cfe696a775` with its required budget of 13 passes all gates. Answer pages: [51, 53, 57, 58, 59]. It has 11 necessary pages and 7 necessary visual pages. The local receipt is `/tmp/comicsqa-coverage-shared-set-review-20261031.json`. This is verification evidence, not a newly published admitted candidate; the other two were not freshly assessed in this review.

Next, run targeted admission into a fresh output root, without regenerating proposals or relaxing any gate:

```bash
bash scripts/benchmark1000.sh admit-native \
  --proposal-root /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/coverage_v1 \
  --chapter hell-s-paradise-jigokuraku__c001 \
  --max-ablation-pages 16 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/coverage_v1_sets_admission
```

This rechecks all proposals in the one chapter, including previously admitted items. Do not add its entire candidate count to 93; merge/deduplicate future pools using validated provenance/paths. Existing outputs remain baselines.

## Character-switch walks: dependency remains unresolved

All 18 switch walks have valid answer proofs but fail complexity certification. Seventeen have a redundant-clause witness and ten have an unresolved bypass (labels overlap). In a Spy x Family c001 example, keeping the original person instead of switching still reaches page 62. That question cannot justify claiming the switch is necessary.

Two speaking-before comparisons are likewise held for redundant clauses. Increasing the page-ablation limit will not repair those dependency failures. Do not relabel them as difficult questions merely because their programs or wording are long.

The next implementation after targeted set admission should seek **necessary character-switch paths before spending proposal slots**, retaining bypass evidence and reporting whether no such path is found within the budget. This is a separate code change, not performed during this results review. It should precede another broad unchanged generation run.

## Remaining evidence/search limits

Discovery made 1,449 new checked queries and reports 464 open-coverage/79 unresolved-selection diagnostic occurrences; these are trace categories, not unique pages or QA counts. No chapter exhausted its per-family predicate probe budget. Some reference/window trial searches were truncated, so lack of candidates is not a universal impossibility claim.

Shared presence rejected 1,097 windows for no known branch distinction and 252 for unproved required probes. Shared speaking rejected 727 for no known branch distinction and 153 for unproved required probes. These remain separate from resource exhaustion and supported absence. Targeted source review is appropriate where diagnostics identify an actual evidence gap; no blanket closure or model assertion is authorized.

Keep Qwen wording/synthesis on MN5 deferred, alias approvals pending, and the final selector/human review/export separate. First recover the verified branch-combine sets with complete admission checks, then improve truly necessary switch paths and review actual pool feasibility.


## Targeted readmission completed — 2026-10-31

The user ran the command above into `reports/benchmark1000/coverage_v1_sets_admission`. All 26 manifest output hashes verify, the configuration binding and both source-manifest pins match, and the job code matches the current implementation. All 11 admitted candidate records validate. This review validates saved proof/admission receipts; it does not claim a new full execution replay.

- 12 proposals checked → **11 admitted, 0 held, 1 duplicate**; 33 private auxiliary probes.
- **All three shared-presence sets now pass**, including both necessary branches and visual-page checks, under unchanged policies.

| Answer page positions | Necessary pages | Necessary visual pages | Group |
|---|---:|---:|---|
| [51, 53, 57, 58, 59] | 11 | 7 | branch_combine |
| [53, 57, 58, 59, 60, 61, 62] | 12 | 9 | branch_combine |
| [51, 53, 57, 58, 59, 60] | 12 | 8 | branch_combine |

The other eight admitted paths overlap `coverage_v1_admission`. Thus this run adds three admitted path hashes, giving **96** distinct stored paths across the two coverage admission stores; including the older `families_v1_admission` gives **105**. These are cross-store inventory counts, not a published merged store, selected 1,000-item benchmark or final semantic-deduplication guarantee. All 142 frozen legacy files still match; source evidence and previous outputs remain unchanged.

The next implementation is **dependency-aware character-switch candidate search**: test whether removing a navigation or keeping the earlier character changes the final answer before spending the limited proposal slots, and retain separate counts for unproved bypasses versus proved redundant paths. Then run bounded trials before full generation. Do not relax the existing necessity/visual/name checks to admit the 18 held switch walks. No unchanged generation rerun is needed now. Qwen and final selection/review/export remain deferred.
