# Full expanded-family run review — 2026-10-30

Inputs are the completed immutable `reports/benchmark1000/families_v1` and `families_v1_admission`. Generation covered all 50 chapters with per-family proposal cap 3, execution cap 9, reference search budget 1,000 and window length 10. This is a capped family pilot over the full collection, not exhaustive generation.

## Verified results

- Source parent manifest/output hashes and native proposal store verify: 358 recipe executions, 53 answer-proved proposals.
- Admitted store verifies: 39 admitted, 6 held, 8 duplicates; 159 auxiliary probes. Probes do not count as QA.
- Candidates cover 12 chapters: 25 seen / 14 unseen.
- All 39 have measured expanded-profile certificates; full fresh replay of all 39 has **not** been run in this review. Build/admission already checked their proofs; this review verified saved stores and re-executed one failed set case independently.
- Primary groups: 13 chain, 14 short, 12 aggregate/compare; no branch-combine candidates.
- Meaningful-hop distribution: 13 three-hop, 14 two-hop, 12 one-hop. The three-hop examples are successive speaking-page navigations, not character-switch walks.
- Answers: 27 page, 11 count, 1 Boolean; no sets or character-name answers. Page offsets from the declared search anchor are 2:12, 3:11, 4:2, 5:2. Counts cover 1, 2, 3, 4, 5, 6, 8.
- No final selection/release approval, 1,000-item feasibility, or new alias approval is established.

| Family | Executed | Answer proved | Admitted |
|---|---:|---:|---:|
| Successive speech | 51 | 28 | 27 |
| Dialogue count on next speaking page | 60 | 20 | 11 |
| Speaking-page comparison | 37 | 2 | 1 |
| Character-switch walk | 35 | 2 | 0 |
| Last appearance within a window | 68 | 1 | 0 |
| Shared presence pages | 44 | 0 | 0 |
| Shared speaking pages | 35 | 0 | 0 |
| Speaking-page gap | 28 | 0 | 0 |

## Held items and policy interpretation

Five candidates failed the operational dependency checks: two character-switch walks, two count questions and one Boolean comparison. Their recorded bypass leaves the final answer unchanged. Do not describe these as wrong answer proofs; admission requires the additional dependency condition.

One Oshi no Ko c002 last-appearance answer is 20, while the question states a search range of 20–26. The strict numeric-overlap gate holds it. This is a conservative policy filter: mentioning a range endpoint is not by itself proof that the answer is disclosed. Any refinement should be explicit and tested, preserving this baseline; recovering one item does not resolve the main yield limitation.

Eight passing proposals are resolved-path duplicates, retained privately with their representatives.

## Coverage diagnosis

Shared-page families failed 79 executions before admission, so loosening admission quotas would not fix them. Their main answer must be an exact complete set, not just a list of known-positive pages.

A bounded re-execution of one Blue Exorcist c001 shared-presence query (range 40–49) reproduced a valid execution proof but no supported complete answer: `status=OK`, `exact=false`, known-positive page positions `[40,41,42]`. The independent recipe checker reports `proof_valid=true, answer_supported=false`.

Unknown presence predicates point to stable page IDs `blue-exorcist__c001__p043` and `blue-exorcist__c001__p047`. Character-box, name and speaker-link coverage is `open` there. The reason is “Missing fact is not evidence of absence.” Nothing authorizes treating those pages as empty or silently closing their coverage. Other failed windows need similarly explicit predicate/page diagnostics; their current aggregate reasons are blank.

## Next implementation

Implement **coverage-aware, candidate-specific window search and uncertainty diagnostics** before another broad unchanged build:

1. Report the exact unresolved predicate, identity/page and required coverage or binding for each blocked family. Replace blank aggregate reasons with actionable categories.
2. Search bounded intervals where each required predicate can actually be proved. Use existing positive witnesses and admitted negative coverage; do not require blanket closure where positive facts already settle a predicate. Allow shorter/shifted explicitly worded ranges in a new run/profile as needed, with exact wording/program bindings and resource budgets.
3. Re-run small trials for shared sets, genuine character switches and two-branch gaps. Preserve all current checks; only scale when those families yield admitted examples.
4. For remaining blockers, prepare targeted source-evidence review rather than promoting model outputs or globally changing coverage.

Keep alias review for Nagisa/Naruto pending until actual decisions. Keep Qwen deferred. A separate policy decision on endpoint-number overlap and the existing small-denominator shortcut handling remains necessary before final selection.
