# GEN-2 v3 completed-run review (2026-10-29)

Output: `/data/151-3/comics/ComicsQA_Benchmark/items/gen2/v3`.

## Verified artifacts

All 103 manifest output SHA256 values match. The 50 retained pools contain 153 candidates: 100 seen and 53 unseen; 93 count, 50 character and 10 page answers. Report: 960 attempted, 153 gate-passed, zero selected, 960 rejected. Here rejected includes both 807 gate failures and 153 selection exclusions, not 960 invalid proofs. All four AI visual alias approvals were loaded. Compared with v2, gate-passed yield increased from 140 to 153. This review checked saved artifacts and selection logic; it did not re-execute all candidate proofs or rescan images.

## Why selection is empty

The complete name pool has only one non-frequent identity per split:

- Seen: Zombie Devil, 2 candidates; remaining 34 name answers are frequent in their respective chapters.
- Unseen: Mephisto, 3 candidates; remaining 11 name answers are frequent in their respective chapters (Rin 5, Yukio 4, Erina Nakiri 2).

Every selected chapter must have frequent names <=30% of its name answers. Summing these inequalities across chapters requires non-frequent names >=70% of each split's name answers. Because each split has only one non-frequent identity available, that identity would necessarily exceed the separate 50% identity cap. Thus no nonempty name subset of this pool satisfies both rules, independent of the greedy selector.

All 10 page-answer candidates have offset +1, so no nonempty page subset satisfies the 50% offset cap. Only integer answers remain, but a count-only subset is 100% counts and violates the 70% count-type cap. Consequently no nonempty subset of this specific pool meets all current rules. This conclusion follows from the actual candidate inventory, not merely the selector's generic empty-result status.

Selection exclusions: 65 semantic/program duplicates, 44 chapter frequent-name quota, 20 count-value cap, 13 count-type cap, 6 page-offset cap, 5 name-identity cap. Sequential removal labels are not independent estimates of constraint effects.

## Next step

Preserve v3 pools and earlier baselines. Do not rerun unchanged or prepare an empty v3 VERB pack. Before another production generation run, perform a feasibility preflight and identify supported additional non-frequent identities in each split, or expand supported families to provide other answer types/varied page offsets. Extra aliases of already-frequent characters alone cannot fix the quota conflict. Broader generation needs new proofs; a different selector alone cannot fix this pool. Any quota-scope or numeric-policy change must be explicit, not silently applied. No code or quota changes were made in this review; future implementation needs authorization under AGENTS.md. Final human review and Qwen remain pending.
