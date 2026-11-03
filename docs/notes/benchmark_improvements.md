# Benchmark improvements: from annotation questions to story questions

Created 2026-11-01. Agreed with the user: review points 2, 3, 5 and 6 from the 2026-11-01 review in
`docs/STATUS.md` ("Open questions"). Model evaluation (point 1) is deferred: it will use paid API
models later. Point 4 (early human check) was not adopted.

This file is the plan. Implement it step by step (section 6); record progress in `docs/STATUS.md`.
All existing rules still hold: ground truth is never changed, new work is additive (new namespaces,
configs and output roots), proofs are checked independently, long jobs are run by the user, and
trust tiers H > V > A > M apply (A only after a sample audit).

## 1. The problems

| # | Problem | Evidence (2026-11-01 inventory, 3,774 candidates) |
|---|---|---|
| P2 | Questions measure annotation conventions, not comic understanding. | 69% count answers, 17% "more/fewer/same text regions". A model cannot know how annotators split balloons, boxed sound effects or counted background figures. |
| P3 | Long questions are procedures, not comprehension. | "Search only the inclusive range from page 12 to 21. Start immediately before this range…" tests bookkeeping. Difficulty comes from the instructions, not the story. |
| P5 | Almost every question depends on page numbers. | Most anchors and 7% of answers are page positions. A model that miscounts images fails for reasons unrelated to understanding. |
| P6 | Effort goes into process, not content. | 3,640 of 3,774 candidates are legacy templates, 134 native. Many runs vary search mechanics (switch, branch, contrast); story-level families do not exist yet. |

## 2. Goal: what a world-class comics QA benchmark asks

A good item can only be answered by **reading the story across pages**: who says what, to what
effect, who is with whom, what happens and in which order. It must still be **exactly verifiable**
from our graph (proof-carrying), **natural** to read, and **robust** to annotation conventions.

Every item gets four new metadata fields (in addition to the existing axes `evidence_class`,
`generation_mode`, `reasoning_structure`, `answer_format`):

| Field | Values |
|---|---|
| `content_category` | `dialogue`, `character`, `event`, `story_order`, `multi_hop`, `contrast`, `perception` |
| `anchor_type` | `quote`, `character`, `event`, `relative` (e.g. "after X first speaks"), `page` |
| `wording_style` | `natural`, `procedural` |
| `unit_dependence` | `none`, `page_presence` (who is on a page), `box_count` (number of annotated boxes) |

## 3. Solutions

### 3.1 P2: ask about the story, and make counts convention-robust

**a) Hard caps in the final 1,000** (selection policy, not generation):

| Item kind | Max share |
|---|---:|
| `unit_dependence=box_count` (text regions, depictions per page) | 5% |
| all count answers | 15% |
| `content_category=perception` | 5% |

Box-count items that remain go into a separately reported `perception` category, never into the
headline story score.

**b) Convention-robust counts** replace box counts where a count is wanted:
- "On how many pages does X speak / appear?" (page presence, not box count)
- "How many different named characters speak in the scene where X says '…'?"
- "How many times does X appear with Y before Y first speaks?"

Exact counts still require closed coverage over the whole scope (existing CRL rule).

**c) New story families from data we already trust (H/V, CPU only).**

| Family | Example | Evidence | Format |
|---|---|---|---|
| Quote attribution with chapter distractors | "Who says 'I'll protect you no matter what'?" A–D: four named characters from this chapter | human speaker links + verified OCR | multiple choice / character |
| Quote order | "Put these four lines in story order: (A) '…' (B) '…' …" | quotes on **different pages** only, so page order (H) decides; within-page order only after the reading-order audit | sequence |
| Conversation partner | "Who else is drawn on the page where X answers '…'?" | speaker link + page presence | character / set |
| Mention before appearance | "Which character is named in dialogue before being drawn for the first time?" | CKG-3 lexical name occurrences + presence | character |
| Introduction | "Who is the first character to speak after Y first appears?" | presence + speaker links + coverage | character |
| Co-presence relations | "Who appears with both X and Y but never speaks to a page with Z on it?" | presence + coverage for "never" | character / set |
| Visual identity (existing P08 pilot) | "Which of these four pictured characters says '…'?" | crops of verified appearances | visual choice |

**d) New story families from model evidence (need verification first; see step S5).**
Captions (Qwen3-VL-32B, per panel) are grounded to human-labelled characters by the MAGI-3
recovery run (2,022 pages; 19 partial). From them we extract **event facts**:
`(character, action, object/other character, panel, page)`, e.g. `(Rin, draws, sword, p032)`.

Event facts start at tier M. They become usable (tier A) only after:
1. a second, independent pass confirms each fact on its panel crop (another model call, yes/no);
2. a sample audit (risk-based review, design brief §11) measures the error rate;
3. every item whose answer depends on an event fact is reviewed before release.

Families this enables:

| Family | Example | Format |
|---|---|---|
| Who did it | "Who draws a sword right after Mephisto says '…'?" | character |
| What happened | "What does the speaker of '…' do when they are next drawn?" | multiple choice (distractors are other verified events from the same chapter) |
| Event order | "Which happens first: X falls, Y opens the door, or Z laughs?" | sequence / choice |
| Cause in dialogue | "After Y says '…', which character reacts by attacking?" | character |

Interpretive questions (motivation, emotion, tone) stay excluded from v1, as already decided.

**e) Paraphrased quote attribution (real reading comprehension).**
Qwen rewrites a quote's **meaning** without its words: "Who promises to protect his younger
brother?" → answer from the human speaker link. Validity check: an independent model must pick the
source quote from **all** quotes in the chapter given the paraphrase (unique match required), and
the item is reviewed before release. This removes exact-string matching as a shortcut.

### 3.2 P3: natural multi-hop questions

**a) Anchors from the story replace search ranges.** Every procedural element has a story-level
equivalent that the existing CRL programs can still execute:

| Procedural (now) | Natural (target) |
|---|---|
| "Search only pages 12–21" | "In the scene after Rin says 'welcome to True Cross Academy'…" (start = that quote's page) |
| "Start immediately before this range and follow the current person to their next speaking page two times" | "the second time this character speaks after that" |
| "switch to the only different character drawn on the page just found" | "…and the person with them then" |
| "Give the two distinct final page positions in increasing order" | ask for a character, quote or event instead of page positions |

Example. Procedural: "Identify the speaker of 'welcome to true cross academy.' on page 6. Search
only pages 17–26 … two times … switch …" Natural: "After the boy who says 'welcome to True Cross
Academy' speaks again later, who is the other character with him, and what does that character say
next?" Same program, three story hops, no page arithmetic.

**b) Measure difficulty in story hops**, not words or clauses. A hop is one of:
quote → speaker, speaker → their next speech / appearance, page → co-present character,
character → event, event → order. Long-chain items need ≥3 necessary story hops (existing
necessity checks reused).

**c) Wording pipeline.** CPU: a closed natural-anchor template grammar with parse-back (the
existing VERB-1 parser approach). MN5: Qwen paraphrases the natural template, and the paraphrase is
parsed back to the same program and answer (existing G10 contract).

**d) Cap:** `wording_style=procedural` ≤5% of the final 1,000. Existing procedural candidates stay
in the pool as reserve or are re-worded through (a).

### 3.3 P5: fewer page numbers, and a clear page protocol

**a) Evaluation input protocol** (write it now, use it when API evaluation starts):
- Images are given in chapter order, each preceded by the text label `Page N` (1-based, the same
  index as in questions and answers; a spread counts once, as in CRL).
- The prompt states: "Pages are numbered by their position in this input, not by printed numbers."
- Page labels are the only text added to images; no OCR, names or boxes.
- Spec location: `docs/specs/09_validation_export.md` (new section) + exporter.

**b) Anchor mix in the final 1,000:**

| Anchor / answer | Target |
|---|---:|
| questions anchored by a page number | ≤35% |
| answers that are page numbers / page sets | ≤15% |
| quote, character, event or relative anchors | ≥65% |

**c) Prefer non-page answers:** characters, quotes, events, multiple choice and sentences. When
a page answer is necessary, also accept "the page where …" in sentence answers.

### 3.4 P6: content first; target composition of the final 1,000

Proposal by content category (structure and format remain separate axes; this refines the
design brief §13, which grouped by structure). Sentence answers (~25–30%, user decision) are an
answer format across categories, not a category.

| `content_category` | Target | Main sources |
|---|---:|---|
| `dialogue` (attribution, paraphrased quotes, conversation) | 200 | 3.1c, 3.1e |
| `character` (appearances, introductions, relations, visual identity) | 180 | 3.1c, P08 |
| `event` (who did it, what happened, cause in dialogue) | 160 | 3.1d |
| `story_order` (quote order, event order, summary verification) | 120 | 3.1c, 3.1d |
| `multi_hop` (≥3 story hops, natural wording) | 220 | 3.2 |
| `contrast` (pairs, "cannot be determined") | 70 | existing P09, reworded |
| `perception` (box counts etc., reported separately) | ≤50 | legacy pool |
| **Total** | **1,000** | |

Rules:
- **Stop** adding search-mechanic variants (switch/branch/contrast versions) unless they come out
  in natural wording (3.2).
- The 3,640 legacy candidates become a **reserve**: used only where a category is short and the item
  passes the new caps.
- Every new family follows the existing contract: CRL operation (if new), independent checker rule,
  synthetic tests incl. wrong/redundant proofs, bounded real trial, then a user-run full build.
- Floors from the design brief stay: ≥40 chapters, seen/unseen in source proportion, ≥150 distinct
  target identities.

## 4. What does not change
Ground truth; trust tiers; completeness/coverage rules; name-readability rule (names in questions
and answers must be readable in the chapter); ≤30% frequent-name answers; ~5% two-option answers;
full-chapter context; existing outputs (preserved, never rewritten).

## 5. Risks
- **Event facts may be noisy.** Caption errors become question errors. Mitigation: two-pass
  confirmation + audit + per-item review; drop the event category share if the audited error rate is
  high (decision after S5).
- **Paraphrase ambiguity.** Mitigation: unique-match check against all chapter quotes.
- **Lower yield** under natural anchors and caps. Mitigation: generate ~3× surplus per category and
  report shortfalls instead of relaxing rules.

## 6. Implementation steps (in order)
Each step ends with tests passing and a STATUS.md row. CPU steps are implemented and tested on small
samples; full builds and GPU/MN5 jobs are user-run.

| Step | What | Needs | Done when |
|---|---|---|---|
| S1 | Evaluation input protocol (3.3a): spec section + exporter producing labelled page lists | CPU | spec written; exporter test checks labels/order |
| S2 | New metadata fields (section 2) + composition/anchor caps config (3.1a, 3.2d, 3.3b, 3.4) + inventory report of the current 3,774 against the targets | CPU | report shows per-category gap |
| S3 | Story families from H/V data (3.1c) + convention-robust counts (3.1b) | CPU | bounded trial + independent proof replay; full build user-run |
| S4 | Natural-anchor grammar and rewording of chain/branch/contrast items (3.2a–c) | CPU | every reworded item parses back to its original program and answer |
| S5 | Event facts: extraction from grounded captions, second-pass confirmation, audit sample (3.1d) | GPU (user-run) + audit | audited error rate recorded; facts promoted to A or rejected |
| S6 | Event families (3.1d) | S5 | bounded trial + proofs; full build user-run |
| S7 | Paraphrased quote attribution (3.1e) | MN5 Qwen (user-run) | unique-match check passes; review queue prepared |
| S8 | Sentence answers from dialogue + event facts (claim-verified, existing P10 contract) | S5, S6 | claims verified; scoring fixtures |
| S9 | Selection of the final 1,000 with the new caps; legacy as reserve | S2–S8 | selection report meets all caps and floors or lists shortfalls |
| S10 | Qwen wording of selected items (existing P11 pipeline) + review + export | MN5 | parse-back passes; review/export per existing plan |

## 7. Decisions for the user
- D-A: accept the content-category targets in 3.4 (or adjust numbers).
- D-B: accept the caps (box counts ≤5%, all counts ≤15%, procedural ≤5%, page anchors ≤35%,
  page answers ≤15%).
- D-C: which model does the event-fact second pass in S5 (e.g. Qwen3-VL-32B in a different prompt,
  or a different open model for independence).
