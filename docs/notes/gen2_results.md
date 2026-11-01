# GEN-2 v1 full collection review — 2026-10-29

Output: `/data/151-3/comics/ComicsQA_Benchmark/items/gen2/v1/`.
The user completed the production run. `bash scripts/build_gen2.sh --resume` verified
current code/config/input fingerprints, all 53 output hashes and all chapter companions.
All 120 selected executions were independently rechecked against pinned CKG-1/2/3 inputs:
zero proof errors; all accepted for generation. This is formal evidence validation, not
manual image review or final benchmark approval. No source or generated artifacts were edited.

## Yield

- 50 chapters; 960 attempted, 214 gate-passed, 120 selected, 840 rejected.
- 16 chapters contribute selected items; 34 contribute none; 21 had no proposals.
- Acceptance: 12.5% of attempted proposals. No chapter reaches the configured 180-proposal cap
  (maximum observed 135), so increasing that cap alone cannot increase this run's yield.
- 633 proposals return UNKNOWN; other execution rejections: 9 ambiguous, 8 empty,
  44 ineligible answers. Remaining gate rejections: 48 count-distribution and 4 answer-number
  leakage. Selection excludes another 94 under quota/capacity/dedup rules.
- Per-chapter frequent-name (<=30%) and two-option (<=5%) limits rechecked; none relaxed.
  Selected frequent-name answers: 2/12; no two-option answers.

| Family | Selected |
|---|---:|
| quote_speaker_depictions | 89 |
| name_speaker_depictions | 9 |
| quote_speaker | 11 |
| name_speaker | 1 |
| quote_speaker_next_page | 10 |
| name_speaker_next_page | 0 |

98 integer answers (81.7%), 12 character answers (10%), 10 page answers (8.3%).
110 single-page and 10 multi-page items. Count answers: 2 (39), 3 (18), 4 (28), 5 (13).
Always answering 2 on the count subset would score 39/98 (39.8%); the existing name/two-option
quotas do not control this count skew. All 10 next-page answers are the immediately following
page, creating another shortcut to address in final selection/baselines. Proof dependence on
multiple pages alone does not establish difficulty. This is a small evidence-limited supplement
to GEN-1, not the broader diverse GEN-2 target.

## Quality findings before verbalization/export

1. Alias quality needs a separate generation eligibility rule. Jujutsu Kaisen c001 has an item
   describing `The` as a name form. The inherited identity is `The student council president`,
   whose aliases include separate words `The`, `student`, `council`, `president`.
   Chainsaw Man c001 has the answer `DEBT`, inherited from `DEBT COLLECTOR` with aliases
   `DEBT` and `COLLECTOR`. Lexical readability and formal alias mapping do not establish that
   these fragments are appropriate character names. Preserve raw aliases/provenance; filter
   usable question/answer forms or require reviewed name forms. Inspect role labels such as
   `Boss` and `Lord` individually rather than assuming every title is invalid.
2. Similar quotes can ask for the same speaker's depiction count on the same page. Audit
   semantic target duplication, not only identical programs/full proof-support hashes.
3. Current questions still use page-scoped anchors, and answers remain exact typed scalars.
   The planned approximately 30% sentence-answer track and answer-conditioned Qwen class
   are still separate, unimplemented work. No chapter-wide OCR uniqueness can be inferred
   from this output.

Recommended next CPU work: tighten name-form eligibility and selection diversity/shortcut
checks, with regression tests and a fresh immutable output version. Keep this completed v1
as a baseline. Then extend the VERB-1 grammar and evidence packs to supported GEN-2 templates;
run Qwen later on MN5. Human review, final dedup/baselines and export remain pending.
