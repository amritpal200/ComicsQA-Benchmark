# GEN-2 v2 full collection review — 2026-10-29

Output: `/data/151-3/comics/ComicsQA_Benchmark/items/gen2/v2/`.
Completed resume verified current code/config/input fingerprints and all 53 output hashes.
All five production executions independently pass CRL-2 against the pinned CKG-1/2/3
artifacts, with matching input pins. No source/generated artifacts were edited.

## Outcome

50 chapters; 960 attempted → 140 gate-passed → 5 selected; 955 rejected.
All selected items come from Chainsaw Man c001: three depiction counts (2, 4, 5)
and two speaker questions, both answered ZOMBIE DEVIL. No page-answer family survives.
The run is technically correct under the configured policy, but it is not a sufficiently
diverse GEN-2 collection. Formal proof validity does not establish dataset usefulness.

Before selection, rejections were 603 UNKNOWN, 8 EMPTY, 41 ineligible answers,
46 count-target failures, 3 numeric-answer leakage, 62 ineligible answer name forms,
and 57 ineligible question name forms (820 total).
Of the 140 gate-passed candidates, selection removed 63 semantic duplicates,
36 under existing quota/capacity rules, 29 for count-value concentration,
6 for page-offset concentration and 1 for count-type concentration (135 total).
These are recorded sequential rejection reasons, not independent causal effects.

## Policy problem

The new per-chapter concentration caps over-prune sparse evidence. A chapter with only
two count values cannot retain any counts under a 35% maximum share per value. Eleven
chapters had count candidates but fewer than three count values before selection.
The canonical-only name rule is deliberately conservative and can also exclude legitimate
shortened names. The selector is a greedy trimming method, not a maximum-yield optimizer.

The retained answers expose an additional gap: the frequent-character quota measures
character prevalence on chapter pages, not repetition in the answer distribution. Both
name answers are ZOMBIE DEVIL while the original quota still passes. The implementation
therefore meets its stated constraints but does not yet meet the broader diversity aim.

## Recommended next revision (not implemented by this review)

1. Preserve all proof-passing candidates and their evidence in private artifacts before
   final balancing, so selection can be audited without rerunning proof generation.
2. Keep semantic deduplication, unreadable-name rejection and fragment exclusion. Add a
   reviewed, provenance-bound alias allowlist for legitimate shortened names; do not restore
   automatic acceptance of fragments such as The or DEBT.
3. Apply the new distribution/offset constraints at collection or split level, with chapter
   coverage represented in selection. Preserve the previously agreed name/two-option limits;
   clearly version any policy-scope change. Add actual repeated-answer checks, not only
   character-prevalence checks. Validate feasibility and report shortfalls explicitly.
4. Keep both v1 and v2 immutable; implement a fresh version and validate it before the next
   full run. Broader supported families/evidence remain necessary; selection cannot invent
   difficult questions or remove all shortcuts by wording alone.

The VERB-1 GEN-2 adapter is implemented and tested, but full request preparation should
wait for this selection review/revision. No Qwen inference or final approval has occurred.
