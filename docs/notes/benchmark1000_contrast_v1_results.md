# Contrast v1 results — 2026-11-01

The user completed contrast generation and standalone proof validation. The run succeeded: **two admitted pairs, four QA members, all four full admission certificates replayed successfully**. This is the one-condition contrast substep of P09; masked-image/edited-world/determinability work and final paired review/release remain pending.

## Verification

All 57 output hashes verify. Store loading reproduces checkpoint/decision/count/summary bindings and validates both complete pair certificates and all four member views. Current new-layer code fingerprints, source-admission manifest and graph/visibility/rich manifest fingerprints match the saved configuration. Each saved proof-report row binds to its exact member hash and the report binds to the current store manifest. No conflicting/reused member path occurs between the two pairs.

The user-run saved report supplies the full expensive proof replays; this review checked their integrity rather than rerunning them. Existing `pool_v1` still validates at 3,762 candidates; all 142 frozen legacy files remain unchanged. No source data, completed output or merged pool was changed.

Artifacts under `/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/`:

- `contrast_v1/`
- `contrast_v1.check.json`

## Results

| Measurement | Result |
|---|---:|
| Configured chapter scope | 50 |
| Source admitted branch seeds | 11, from four chapters |
| Edited variants attempted | 28 |
| Retained pairs / QA members | 2 / 4 |
| Proof replay verified / rejected | 4 / 0 |
| Degenerate endpoints / unproved answers | 20 / 6 |
| Seen / unseen members | 0 / 4 |

The original source questions are preserved inside each pair. Thus four paired views consist of **two existing source questions plus two new variants**, not four newly distinct tasks. Selection prevents choosing a paired member again as its standalone source.

Both successful edits change only the explicit search-start boundary. Branch depths, references, range end, images and proof world remain fixed.

| Chapter | Start change | Original answer | Variant answer | Necessary visual pages | Long-relational tags |
|---|---|---|---|---|---|
| Food Wars c002 | 19 → 20 | `[20, 21]` | `[21, 22]` | 4 / 4 | Neither member |
| Blue Exorcist c001 | 40 → 41 | `[41, 42]` | `[42, 43]` | 5 / 5 | Both members |

All members have measured maximum branch depth three. The two tagged Blue Exorcist members are one existing long-relational source task and one new variant. Neither long tags nor parallel branch lengths are added together to inflate task depth or novelty.

Defaults were two retained pairs/eight attempted variants per chapter, with 16 maximum admission-ablation pages. Blue Exorcist c002 and Jujutsu Kaisen c001 reached their variant budgets; neither exhausted search establishes absence of valid pairs. No chapter reached the retained-pair cap. Endpoint collisions and unproved answers remain rejected, without relaxing eligibility or coverage.

## Interpretation and next step

The CPU contrast pipeline now has real positive examples as well as positive synthetic tests and negative real fixtures. It adds a small verified paired supply, not the final paired quota. Both pairs are unseen; seen coverage and broader source families remain gaps. The current seed pool/default caps cannot support the full paired target, so a later expansion or explicit design decision is still needed.

Recommended next implementation is **P10 atomic claims and sentence-answer preparation**: execute required/optional factual claims before Qwen synthesis, distinguish verified-false from unsupported claims, and define factual coverage/contradiction scoring. Qwen generation/independent validation follows later under P11. Do not label unrestricted generated prose claim-verified merely because it cites graph nodes.

All human/release statuses remain pending. Human crop/distractor/question review and intake stay deferred until after generation, Qwen and automated validation, before final freeze/export. Masked P09 variants and pair-wide adjudication/release remain separate unfinished work.

## Combined count correction — 2026-11-01

A later explicit key union unwraps each contrast member to its original admitted task and compares it with both `pool_v1` and `branch_v1_admission`. One generated variant matches an already admitted branch path. Thus the two variant records add **one** distinct path beyond those stores. The combined inventory is **3,774** candidate paths: 3,762 + 11 + 1, comprising 3,640 archived legacy and 134 native-admitted candidates. Four paired views remain valid as two complete pairs; they are not four additional distinct questions. This is current proof-path deduplication, not a stronger language-level equivalence claim. The 45 visual-pilot questions remain separate and pending admission, and no merged pool/final selection was written.
