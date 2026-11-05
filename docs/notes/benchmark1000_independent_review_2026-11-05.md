# Independent review of story/event expansion — 2026-11-05

Reviewed the committed November 3 milestone, current uncommitted X1 additions, improvement/expansion plans, latest saved reports and the relevant producers/checkers. This was a review: no generator/checker changes, model calls, data transfers or production builds were performed.

## Assessment

The shift toward dialogue, identity relations, event ordering and quote-based anchors substantially improves alignment with comic reading. Keeping the original pool as reserve, maintaining separate independent checkers, and retaining human-required event flags are sound choices. X1 script errors, speaker tables and name traps add useful formats without claiming unaudited within-page reading order.

However, zero category shortfall is an inventory result. It does not establish simultaneous quota feasibility, necessary reasoning depth, long-relational supply, sentence-answer coverage or release readiness. Final selection should remain provisional until those conditions are checked.

## Evidence verified in this review

- `story_profile_v6`: 5,844 candidate representations under its current keys; exactly 3,774 previous candidates + 1,648 story items + 422 event items. Contrast membership is part of story keys; this is not a proof of global semantic independence.
- `story_v4`: 489 choice attribution, 117 open attribution, 581 quote order, 248 conversation partner, 126 next-speech partner, 87 shared-character items. 143 pairs are represented by 286 members within these counts.
- `story_events_v1`: 110 event-actor choices + 312 event-order questions. All 422 require human verification.
- Output manifests freshly verified: 1,699 story_v4 hashes, 473 story_events_v1 hashes, 3 story_profile_v6 hashes. Saved checker reports say 1,648/1,648 and 422/422; this review did not replay every graph proof or inspect every image.
- 28 focused tests passed: `test_story_families`, `test_story_expand`, `test_story_profile`, `test_story_events` using system Python 3.8. No claim that the full suite was rerun; this environment lacks Pillow.
- Current X1 files are still uncommitted; full `story_expand_v1` is absent from the inspected report directory.

## Findings and recommendations

### 1. Story complexity labels are not independently certified

`story_families.make` receives `hops` and `pages` from the generator and stores them as `story_hops` and `necessary_pages`. The story checker verifies answers but does not reconstruct/check these fields or perform necessity interventions. `story_profile` calls a numeric threshold over this field `multi_hop_with_certified_min_hops`.

Reproduction with the existing synthetic next-speech-partner fixture: set `story_hops=99` and `necessary_pages=[]`; `story_check.check` still returns `verified=True` with no errors. Thus the report's 243 “certified” ≥3-hop items should be treated as declared complexity until a separate certificate is checked.

In addition, both new multi-hop families cite two positive evidence pages. Three declared operations do not establish the separate ≥3-necessary-page long-relational requirement. Keep branch operation count, maximum depth, evidence span, necessary pages and long-relational eligibility separate. Add explicit independent complexity/necessity checking before using these labels for selection floors.

### 2. Event-actor independent checking omits coverage closure

`story_check._check_event` rejects a distractor present in `present` facts but does not require the event page's character/name coverage to be closed. The producer checks closure; the independent checker must recheck it as well.

Reproduction with the existing event fixture: generate a passing actor item, change every graph coverage certificate to `open`, then recheck. Result remains `verified=True` with no errors. This does not show that the saved 110 actor answers are wrong: the producer may have selected valid closed pages. It shows a missing independent proof obligation. Require closure and explicit appearance-to-page binding when certifying event absence/identity claims.

### 3. Event actor choices admit a presence-only shortcut

All three distractors are deliberately absent from the located page. Once the quoted page is found, choosing the only option drawn there can solve the item without interpreting the event action. This is valid identity/presence QA but weak evidence of event understanding. A useful next profile should identify these shortcuts. For a harder event-specific subset, use plausible same-page distractors with verified incompatible actions, or certify by ablation that the event description matters. Do not silently weaken answer uniqueness to get harder distractors.

### 4. The event audit is provisional AI review with material uncertainty

Actual audit artifact: 60 judgments by `claude_ai_visual`, 3 wrong, accepted under `max_errors=3`; all event questions retain human-required flags. This is consistent with deferring human review, but it is not a completed human audit.

Even if those 60 judgments were perfect independent reference labels, 3 errors/60 is a point estimate of 5%, not a 95% guarantee of <5%. The exact one-sided binomial 95% upper bound solves `P(X<=3; n=60,p)=0.05` and is approximately **12.42%**. AI judgments introduce additional unmeasured uncertainty. Keep the explicit provisional basis, final human review and any release-quality statistical claims separate. This review did not change the user-approved threshold or move human review earlier.

### 5. New story stores are not yet connected end to end to P11/selection

Generic store loading recognizes `story_store.1`, but `qwen_packs.task` still requires the old `proof_engine/program/execution/context` interface. Calling it on a generated valid story item raises `KeyError: 'proof_engine'`. The old unified pool also accepts only legacy/admitted-native/contrast-member records; existing selection assumptions include features absent from new story records.

Implement additive story-task adapters, canonical story programs/clauses, proof/claim hydration and blind wording validation for the new families before using the P11 commands on these stores. Integrate category caps, paired atomic selection, ranking features and independent complexity constraints in S9. Generic loader support alone does not establish these interfaces.

### 6. Final benchmark targets extend beyond category counts

Latest natural supply includes only 228 multi-hop items against 220 requested, and 213 are also page-number-free; it has little margin for dedup/review/shortcut rejection. Story-profile does not solve the intersection of split/chapter/identity/frequency/category/format/paired constraints. The new story/event sentence-answer path and free-generation pilot also remain planned. Existing 11 sentence plans are not 250–300 admitted sentence answers.

Preserve all successful builds. Next priority: checker/complexity corrections and a story-to-P11 bridge, then the planned X2/X3 evidence-pack and family work; produce a provisional feasibility selection before committing the final 1,000. Keep human review at the agreed final stage. Update the status wording to distinguish category supply from complete benchmark readiness.

## Local verification commands

```bash
PYTHONPATH=src:tests:tests/benchmark1000 PYTHONDONTWRITEBYTECODE=1 \
  python3 -m unittest test_story_families test_story_expand test_story_profile test_story_events -q
```

The two negative probes used copied synthetic fixtures only. All original source annotations, output stores and existing code paths remain unchanged.
