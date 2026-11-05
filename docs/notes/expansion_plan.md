# Expansion plan: free generation, creative types, long relational questions

Created 2026-11-03. Source idea: [Free_QA_generation.md](Free_QA_generation.md) (8B, 8C, 9A). Decided by Claude as
supervisor with the user. **Additive only:** new families, new stores and new commands; no existing code path, store,
policy or result changes, and all existing tests keep passing.

## Decisions (2026-11-03, revised 2026-11-05 with the user)

| # | Question | Decision |
|---|---|---|
| E1 | Trust tiers | **Two tracks.** *Official* track unchanged: answers rest on H/V facts or audited facts (flagged). New **experimental** track: unaudited model facts (MAGI reading order and panels, unconfirmed caption facts, single-model OCR) **may decide answers**, with `track=experimental`, `uses_model_facts=[…]` and `needs_human_verification`. Experimental items live in their own stores; they join the official benchmark only if an audit shows they are right (wrong ones are removed). |
| E2 | Within-page reading order | **Used, in the experimental track.** Source: core v1 `reading_order` per human text box (MAGI-3 ordering rules on human boxes; the port matched MAGI on 2,022/2,022 pages). Enables "who speaks right after", same-page line order and, later, script reconstruction. Promotion to official after a reading-order audit (AI now, human at the end). |
| E3 | Long relational (9A) | A **tag** (`long_relational`) across the content targets, ≥200 in the final 1,000. Natural wording (≤5% procedural cap still applies). |
| E4 | Human checks | AI checks now, flagged `needs_human_verification`; humans at the end. |
| E5 | Share of free generation | At most **300 of the final 1,000** (30%) may come from free generation until its quality is measured (pilot pass rate + audit). Raise the cap if it measures well. |
| E6 | Compute | **Everything local; no MN5.** Free generation and wording: Qwen3-VL-32B-Instruct-FP8 (cached; default) or Qwen3-VL-32B-Thinking (local) via the existing vLLM server on a local Blackwell GPU. Solver/verifier: InternVL3-14B (local). Harden loop and image edits after the free-generation pilot. |

New metadata on new items: `question_form` (clue_puzzle, relation_check, script_error, speaker_table, name_trap,
line_of_character, proximity_trap, …), `generation_mode=free_generation` for 8B, `pack_level`/`pack_pages` for 8B,
reasoning tag `long_relational` where it applies.

## Phases

| Phase | What | Where | Status |
|---|---|---|---|
| X1 | Creative types from human annotations (8C.2/8C.3), as story families with independent checks: **script error spotting**, **speaker table**, **name-in-bubble trap**, **line of character** (incl. the "says nothing on that page" answer = false-premise/absent-entity) | CPU | implemented 2026-11-03 (`expand-pilot`, `story_expand.1`); bounded 4 chapters 89/89; full run user-run |
| X2 | More types: proximity trap (tails + boxes), who-is-missing, distant co-reference, true/false relation check (with verified-false near misses), natural clue puzzles (constraint accretion + necessity) → `long_relational` tag | CPU | planned |
| X3 | 8B preparation: pack serializer at four levels (page/window/selection/chapter) with fact IDs + provenance; proposal schema; validator; claim checking (reuse P10); uniqueness via the distinctiveness certificate | CPU | planned |
| X1b | Experimental within-page order families: **next line speaker** ("right after someone says …, who speaks next?") and **same-page line order**; `track=experimental` | CPU | implemented 2026-11-05 (`experimental-pilot`, `story_experimental.1`); bounded 4 chapters 51/51; full run user-run |
| X4 | 8B pilot: local Qwen3-VL-32B (Instruct-FP8 or Thinking), 3–5 chapters, ~50 items/chapter; pass rates and rejection reasons per level; AI hand check of 50 accepted | local GPU (user-run) | after X3 |
| X5 | Harden loop (2–3 rounds, local solver models, e.g. InternVL3-14B) and image edits (masking, page shuffling) | local GPU + CPU | after X4 |
| → | S9 final selection over all stores, S1 evaluation protocol, S10 Qwen wording | | after X1–X3 at least |

## Rules every new family follows
- Story-family framework: `story_item.1` records, `story_store.1` stores, a new version string per family set,
  generator and `story_check` kept separate, `check-story` re-runs the check.
- Quotes are located by the distinctiveness certificate; no page numbers unless the question states a range.
- Exact or set answers only, or letters for options; sentence answers only through claim checking.
- Readable names only (CKG-2); ≤30% frequent-name answers and ~5% two-option answers enforced at selection.
- Coverage: any "nothing / never / all / exactly" claim needs closed coverage of the relevant families on the pages it covers.

## X1 details (`story_expand.1`, command `expand-pilot`)

| Family | Real example (Blue Exorcist c002 / One Piece c001) | Answer | Rule |
|---|---|---|---|
| `script_error` | Here are six lines from this chapter, each shown with a speaker name. Exactly two of the names are wrong (they were swapped with each other). Which two lines have the wrong speaker? (1) Mephisto: "this is actually a lot." (2) Fujimoto: "now return to your seat." … | `[2, 6]` | 6 lines, ≥3 readable speakers; one swap of two different names; no shown name inside any quote |
| `speaker_table` | Who says each of these lines? Options: A) Mephisto; B) Rin; C) Fujimoto; D) Yukio. Lines: (1) "…" (2) "…" (3) "…" (4) "…" | `['A','B','A','D']` | 4 lines on 4 pages, ≥3 speakers, options = speakers + readable distractors |
| `name_trap` | Who says "yukio, will you join my fight?"? Choose one: A) Fujimoto; B) Rin; C) Yukio; D) Mephisto. | `A` (Fujimoto) | quote names exactly one other readable character, who is an option; speaker not named |
| `line_of_character` | On the page where someone says "hey! we gotta go help luffy!", which of these does Roger say? A) "…"; B) Roger says nothing on that page; C) "…"; D) "…" | `B` | page with closed text boxes + speaker links; alternate "says one shown line" / "says nothing" (false premise); drawn-but-silent characters preferred |

All lines carry the distinctiveness certificate; X1 never claims within-page order (official track). Checker:
`story_expand_check.py` (separate), reached through `story_check.check`. Existing families take the same path as before.
`story-profile` counts all four as `dialogue` and reports `question_form`.

```bash
B=/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000
bash scripts/benchmark1000.sh expand-pilot --out $B/story_expand_v1          # ~20 min CPU, resumable
bash scripts/benchmark1000.sh check-story --store $B/story_expand_v1 --out $B/story_expand_v1.check.json
```

Bounded run 2026-11-03 (Blue Exorcist c002, One Piece c001, Naruto c001, Spy x Family c001): 89 items (32 script error,
24 speaker table, 19 name trap, 14 line of character: 6 "says nothing", 8 "says this line"), 0 rejected, check 89/89.
4 new tests; all story tests and 276 graph tests pass.

## X1b details (`story_experimental.1`, command `experimental-pilot`; experimental track)

| Family | Real example | Answer |
|---|---|---|
| `next_line_speaker` | Right after someone says "maybe in 10 years i'll give you a chance.", who says the next line on the same page? Choose one: A) Shanks; B) Roger; C) Makino; D) Luffy. | `D` |
| `page_line_order` | These four lines are on the same page. Put them in reading order, first to last: A) "once word of this spreads …"; B) "we have to find him!"; C) "i'll try the forest first!"; D) "if it's discovered …". | `['B','C','A','D']` |

Reading order = core v1 `reading_order` (MAGI-3 rules on human boxes; unaudited model fact). Next-line items need closed
text boxes + speaker links on the page; the next text must be a dialogue line with a single readable speaker different from
the anchor's speaker. Every item: `track=experimental`, `uses_model_facts=['magi_reading_order']`,
`verification.human=required`, flags `needs_human_verification`, `experimental_track`, `uses_magi_reading_order`.
The checker re-reads core v1 order itself and rejects unflagged items.

```bash
bash scripts/benchmark1000.sh experimental-pilot --out $B/story_experimental_v1     # ~15 min CPU, resumable
bash scripts/benchmark1000.sh check-story --store $B/story_experimental_v1 --out $B/story_experimental_v1.check.json
```

Bounded run 2026-11-05 (same 4 chapters): 51 items (21 next-line speaker, 30 page line order), 0 rejected, check 51/51.
