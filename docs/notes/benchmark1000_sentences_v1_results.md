# Sentence plans v1 results — 2026-11-01

The user completed `prepare-sentences` and `check-sentences`. P10 preparation succeeded: **11 private plans, all 11 independently verified, zero rejected**. These remain `prepared_not_inferred`, with sentence admission and human/release approval pending.

## Verified artifacts

Under `/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/`:

- `sentences_v1/`
- `sentences_v1.check.json`

All 62 output hashes verify. The store loader validates all chapter checkpoints, source-admission replay rows, seed/content/snapshot bindings, plan requirements, canonical reference answers, ordering and regenerated counts/report. Current code fingerprints and source-admission/CKG manifest fingerprints match the saved configuration. Each of the 11 saved checker rows binds to the exact plan hash and source snapshot, and the check report binds to the store manifest.

This review checked the integrity of the user's saved complete proof check; it did not repeat the full expensive job. All 142 frozen legacy files remain unchanged.

## Counts

| Measurement | Result |
|---|---:|
| Configured chapter scope | 50 |
| Chapters containing supported seeds/plans | 4 |
| Plans prepared / verified / rejected | 11 / 11 / 0 |
| Required supported claims | 33 |
| Optional supported claims | 44 |
| Proved-false near misses | 55 |
| Total proposition checks | 132 |
| Distinct query programs across plans | 77 |
| Seen / unseen plans | 3 / 8 |

The 55 counterclaims are **false propositions with verified contradictions**, not additional true facts or questions. Their queries reuse known values where appropriate; 132 proposition checks do not mean 132 different query programs.

Plan distribution: Blue Exorcist c001: 2; Blue Exorcist c002: 3; Food Wars c002: 3; Jujutsu Kaisen c001: 3. All 11 admitted branch seeds were prepared. Empty checkpoints elsewhere do not imply chapter-wide impossibility of sentence QA; this profile only consumes the existing supported branch seeds.

A canonical reference answer is:

> The first speaker's final speaking page is page 20. The second speaker's final speaking page is page 21. The final pages in chronological order are pages 20 and 21.

Each statement is scoped to the question's declared searches. Optional claims supply verified intermediate results and the complementary sequence/gap summary for later explanations.

## Interpretation and next step

These are private factual plans before synthesis, not 11 newly generated/admitted sentence questions. **The current candidate total stays 3,774**, and the final balanced 1,000-item benchmark remains unfinished. No Qwen run, model accuracy, unrestricted prose verification, LLM judging or human approval is claimed.

Next recommended implementation is **P11 CPU task-specific Qwen pack preparation and response validation**: bind target programs/answers or fixed claim lists, order pages separately from graph dependencies, hydrate only relevant evidence, record prompt/model/input fingerprints and preserve raw responses/resumability. Independently validate recovered question semantics and every factual answer clause. Do not reuse narrow legacy VERB packs as full-evidence packs or accept a coincidentally correct answer as semantic equivalence.

MN5 inference follows after verifying the actual checkpoint, processor, deployment and token/image limits. Unsupported prose remains held. Human crop/distractor/question review and intake stay deferred until after generation, Qwen and automated validation, before final freeze/export. Masked P09, broader fact profiles, generated sentence admission and final release remain separate pending work.
