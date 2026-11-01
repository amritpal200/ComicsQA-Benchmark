# Semantic inventory v2: completed-run review

Date: 2026-10-30. Source: `reports/benchmark1000/semantic_v2/`.

## Integrity and execution

All parent/native-store output checksums and 32 proposal-to-query bindings pass. All **32 native answer proofs were independently rechecked** against their pinned CKG-1/2/3 evidence and accepted. A separate artifact records these checks at `reports/benchmark1000/semantic_v2_review/answer_checks.json`; the completed run remains unchanged.

The run covers all 50 chapters. Thirty-three chapters have executable pattern attempts; 13 contribute native proposals. Total: **250 executions, 34 proved answers, 34 measured multi-page dependencies, 32 native proposals, zero admitted candidates**. Zero admitted candidates is intentional: native question-level gates and wording certification are pending. It does not mean the 32 answer proofs failed.

## Pattern results

| Pattern | Executed | Proved | Native records | Interpretation |
|---|---:|---:|---:|---|
| Quote → next speaking page | 85 | 20 | 20 | Supported page answers; mostly short-range |
| Speaker relay | 85 | 2 | 2 | Both resolve to the same underlying path |
| Two-quote joint appearance | 58 | 6 | 6 | All six have redundant branches |
| Three-page clue | 22 | 6 | 4 | Three necessary clauses; two lack a readable answer name |
| Total | 250 | 34 | 32 | Proposals require further admission checks |

Other outcomes: 186 UNKNOWN, 11 AMBIGUOUS, 19 EMPTY. UNKNOWN reflects unmet coverage/reference prerequisites, not a proof that the depicted event never occurs.

Nineteen proved queries have two necessary pages; fifteen have three. These are fixed-program dependency measurements under the annotation/coverage model, not certified minimal question difficulty. `meaningful_hops` remains unassigned.

## Why 34 proved answers became 32 native proposals

Two three-page clue queries in `nisekoi-false-love__c002` resolve internally to Claude Ringheart, but the checked result has `display=null`: no verified readable answer-name form is available. The builder correctly does not print the annotation identity's name as an answer. A future validated visual-choice route could represent such an identity without weakening name visibility.

The four stored character-answer proposals name Nagisa (three different clue combinations in Assassination Classroom c002) and Naruto (one in Naruto c002). Their exact short forms still need the planned name-form eligibility review; stored readability and a proved identity are not automatic alias approval.

## Quality problems the next stage must handle

### Redundant joint branches

All six proved joint-appearance queries have zero necessary clauses under the branch-removal tests. Five use two quotes spoken by the same character; the sixth uses two different characters whose individual next-appearance answers coincide. These are executable answers, but they do not satisfy the intended branch-and-combine necessity requirement. Reject/hold them before admission; the immutable report is not edited to hide them.

### Duplicate relay paths

Both Blue Exorcist c001 relays resolve to the same path:

- initial page 12, speaker Shiro Fujimoto;
- next speaking page 13;
- only different character drawn there: Rin Okumura;
- Rin's next appearance: page 14.

The quote anchors differ, but the resolved identities, pages and target coincide. Native semantic-target hashing currently includes the raw program, so it does not catch this duplicate. Add resolved-path/target deduplication before admission; retain provenance for alternative anchors without counting them as independent hard questions.

### Page-offset concentration

Among the 26 proved scan answers, 25 are offset +1 and one is +2. The two relays are excluded from this scan statistic; they traverse two stages from their initial anchor. Relaxing selection rules alone will not create a broad page-answer distribution. The earlier small-denominator exception remains unresolved and must be dealt with explicitly before final selection.

### Budget-limited search

The clue search hit its 2,000-combination budget in 46 chapters and its proposal-count limit in four. Quote/relay sampling was truncated in 13 chapters and joint sampling in 11. This is a successful bounded pattern inventory, not an exhaustive search or proof that longer paths are absent. A chapter with zero executions may lack admitted quote anchors and/or produce no clue within the budget; it is not a failed job.

## Next implementation

Implement native question-level admission, preserving these 32 proposals:

1. Verify necessary conditions and visual/page support for the complete question; reject redundant joint branches.
2. Deduplicate resolved paths/targets across different quote anchors.
3. Check exact displayed name/alias eligibility, answer leakage and wording-to-program alignment. Keep unresolved items pending.
4. Publish a new admission/validation view or versioned store. Do not change `semantic_v2` records or old graph/generator policies.
5. Then expand successful pattern families and target-first searches based on the measured bottlenecks. Wider search should follow valid gates, rather than mass-producing the same shortcut.

No unchanged semantic rerun is needed. Qwen, claim/asset certification, human review and the final 1,000-item selection remain later work. No native proposal is declared release-approved by this review.
