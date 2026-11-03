# Story families (improvement plan S3)

Questions about the story that do not name a page. Plan: [benchmark_improvements.md](../../../docs/notes/benchmark_improvements.md) §3.1c.
Additive: new store schema `story_store.1`, item schema `story_item.1`; no existing record, run or policy changes.

## Families (`story_families.4`; earlier items stay loadable)

| Family | Example (real, Blue Exorcist c002) | Answer | Evidence |
|---|---|---|---|
| `quote_speaker_choice` | Who says "class will now begin."? Choose one: A) Rin; B) Yukio; C) Mephisto; D) Fujimoto. | letter (`B`) | verified transcript (V), single human speaker link (H), readable names of all 4 options (CKG-2) |
| `quote_speaker_open` (v2) | Who says "he just needs someone to teach him."? | name (`Osamu`); accepted forms = verified forms | as above; used only where the chapter has fewer than 4 readable names |
| `conversation_partner` (v2) | Someone says "he was always satan's target.". Which other named character is drawn on the same page as this line? | name (`Rin`) | line page (H), presence facts (H), closed `char_boxes` + `names` coverage on that page; exactly one other non-generic identity drawn there |
| `next_speech_partner` (v3, multi-hop) | The character who says "magic is everything in this world, eh?" speaks again later in the chapter. On the next page where this character speaks, which other named character is drawn? | name (`Yuno`) | line → speaker (H) → next speaking page: closed `text_boxes` + `speaker_links` on every page in between, so no earlier unlinked line exists → only other identified character there (closed char/name coverage). 3 story hops |
| `shared_character` (v3, multi-hop) | Which named character is drawn both on the page where someone says "i'm a nun, so..." and on the page where someone says "how unfortunate that i happened to be here."? | name (`Asta`) | two lines ≥3 pages apart, closed char/name coverage on both pages, exactly one identified character on both, and that character speaks neither line. Two branches + intersection |
| contrast pair `choice` (v4) | Who says "...then it got weird!"? / Who says "don't worry, it's just a little explosion..."? — same options A) Kayano; B) Nagisa; C) Muramatsu; D) Terasaka | `B` / `D` | two `quote_speaker_choice` members with identical options and different gold; scored both-correct |
| contrast pair `partner` (v4) | two `conversation_partner` questions about lines of the same speaker on different pages | `Rin` / `Yukio` | members pass the partner checker; same speaker, different partners |
| `quote_order` | Put these lines in the order they appear in the chapter, first to last: A) "…"; B) "…"; C) "…"; D) "…". Answer with the four letters. | letter sequence | verified transcripts (V), text-on-page facts (H), chapter page order |

Rules:
- **Lines:** human dialogue text (`is_line`), verified OCR consensus, ≥4 words and ≥16 characters.
- **Distinctiveness certificate** (replaces the page number): every other text region of the chapter is compared through all its readings (consensus, MAGI, PaddleOCR), verified or not. A line is rejected if a reading equals it, contains it, is contained in it (≥ half its length), or has similarity ≥ 0.6 (`difflib` ratio on normalized text). The page-scoped CRL `quote` operation can't be used here: it needs every text on the page to have agreeing OCR, which holds for only ~2% of lines.
- **Distractors:** three other named characters of the chapter with readable names. They are ranked by being drawn on the same page as the line, then by speaking in the chapter, then by a seeded hash. Items are skipped if any option's name appears inside the quote. The gold letter rotates A–D within each chapter. At most 3 items share an answer identity per chapter; `features.is_frequent` marks the chapter's top-2 characters for the ≤30% rule at selection.
- **Names in quotes (v3):** the generator now checks every readable form (aliases too), as the checker already did. In v2 this caused the only 2 rejections (e.g. a nickname inside the quote).
- **Contrast pairs (v4):** each member keeps its family and passes that checker. `check_pair` also requires two members with roles 0/1, the same kind and chapter, different questions and different answers, plus identical options (`choice`) or the same speaker on different pages (`partner`). If one member fails, both are dropped. Members carry `contrast` (pair ID, role, kind), which is part of their item ID; `story-profile` counts them as `contrast`. At most 3 pairs per kind per chapter; partner pairs choose lines first.
- **Inner quotes (v4):** lines containing `"` are skipped (generator) and rejected (checker). Rechecking v1–v3 stores with the v4 checker flags their few such items.
- **Frequency (v2):** less frequent speakers are tried first. Where only 2–3 names are readable, frequent characters still dominate, and the ≤30% rule applies at selection. A frequent partner is used at most once per chapter.
- **Order:** four lines on four different pages, at least two different speakers, each line used once per chapter. The shown order is never already sorted. Within-page order is never used.
- **Checking:** `story_check.py` is a separate implementation (it does not import the generator). It rebuilds every claim from raw graph facts, visibility and transcripts, recomputes distinctiveness and the order, checks the exact wording, and rejects any page number outside quoted text. Generation keeps only items that pass. `check-story` repeats this against the current evidence files and also rejects stale snapshots.

## Commands (from `Code/`)

```bash
export BENCHMARK1000_PYTHON=/tmp/benchmark1000-dev-env/bin/python   # or any Python 3.12 with the repo deps
B=/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000

bash scripts/benchmark1000.sh story-pilot --out $B/story_v4            # all 50 chapters, ~15 min CPU; resumable
bash scripts/benchmark1000.sh check-story --store $B/story_v4 --out $B/story_v4.check.json
bash scripts/benchmark1000.sh story-profile --store $B/pool_v1 --store $B/branch_v1_admission \
  --store $B/contrast_v1 --store $B/story_v4 --out $B/story_profile_v5
```

`--per-family N` (default 12) caps items per family per chapter; `--chapter ID` (repeatable) restricts scope.
Outputs are create-only; a changed code/config needs a new `--out`.

## Bounded verification (2026-11-01)

Blue Exorcist c002 + Chainsaw Man c001: 45 items (21 attribution, 24 order), 0 rejected; identical resume;
fresh `check-story` 45/45. 7 synthetic tests (tampered answers/order/wording, unreadable names, similar or
contained quotes, names inside quotes) plus 232 benchmark1000 and 276 graph tests pass.

## Full run v1 (user-run, reviewed 2026-11-02)

`story_v1`: 890 items (308 attribution, 582 order) from 50 chapters, 0 rejected; fresh `check-story` 890/890.
19 chapters had no attribution item (<4 readable names) → v2 open-answer fallback. Attribution answers were
56% frequent characters → v2 ordering. Keep `story_v1`; `story_v2` supersedes it for selection (same lines can recur).

## Bounded verification v2 (2026-11-02)

Blue Exorcist c002, One Piece c001, Dragon Ball c002, World Trigger c002: 84 items (22 choice, 9 open, 44 order,
9 partner), 0 rejected; fresh check 84/84. 234 benchmark1000 + 276 graph tests pass.

## Full run v2 (user-run, reviewed 2026-11-02)

`story_v2`: 1,153 items (308 choice, 116 open, 582 order, 147 partner), every chapter has attribution items;
2 generation-time rejections (`name_in_quote` via an alias; fixed in v3); fresh check 1,153/1,153.
`story_profile_v3`: dialogue, character and story-order targets met; remaining shortfall 435 (multi-hop 205, event 160, contrast 70).

## Bounded verification v3 (2026-11-02)

Blue Exorcist c002, Assassination Classroom c001, Black Clover c001, JoJo c001: 118 items (14 next-speech partner,
8 shared character), 0 rejected; fresh check 118/118. Estimated full yield ~250 multi-hop items (67 in 13 sampled chapters).
236 benchmark1000 + 276 graph tests pass.

## Full run v3 (user-run, reviewed 2026-11-02)

`story_v3`: 1,364 items (126 next-speech partner, 87 shared character), 0 rejected, fresh check 1,364/1,364.
`story_profile_v4`: multi-hop target met (228 natural; 243 with ≥3 certified hops, was 30). Remaining shortfall 230 (event 160, contrast 70).

## Bounded verification v4 (2026-11-02)

Blue Exorcist c002, Assassination Classroom c001, Black Clover c001, One Piece c001: 157 items incl. 19 pairs (12 choice,
7 partner), 0 rejected, fresh check 157/157. After the inner-quote fix: Blue Exorcist c002 + One Piece c001, 95 items, check 95/95.
237 benchmark1000 + 276 graph tests pass.

## Limits
- The quote is shown as the normalized OCR consensus (lowercase). Qwen wording later (S10) may restore casing.
- Distinctiveness relies on the text boxes being complete. Pages with open text-box coverage can hide an unboxed duplicate. This uses the same `closed_assumed` acceptance as the rest of the graph.
- Human review is still pending for all items (agreed post-Qwen stage).
