# Addendum to Discussion brief v2: free generation, creative strategies, long relational questions

Date: 2026-11-03. Status: **proposal only. Nothing here is implemented.**

## Instructions for the agent

- Read this together with "Discussion brief v2: 1,000 graph-grounded comics QA pairs". Section
  numbers referred to here (4, 6.3, 8.3, 9, 9.2, 10.2, 10.4, 11, 13, 14) are in that brief.
- This addendum adds sections 8B, 8C and 9A, a new allocation row and decisions D19–D22.
- Do not implement or run anything yet. First review it against the current repository, data and
  existing CRL/checker, report conflicts and missing prerequisites, and propose a plan. Wait for
  approval.
- Character names in examples (Rin, Yukio, Shiemi, Mephisto) and page numbers are **illustrative,
  not facts from our data**.
- Trust tiers agreed earlier: H = PopManga human annotations; A = MAGI-3 outputs, PaddleOCR-VL
  transcripts and caption facts, accepted without audit but labelled by source. Every fact keeps its
  provenance label.

---

## 8B. Free QA generation from chapter evidence packs [proposal]

### 8B.1 Idea

Build an **evidence pack** from the graph: annotations and derived facts, in reading order. Give it to
the model (Qwen3-VL-32B on MN5) and let it **freely propose QA pairs**: any question type and any answer
format (one word, a name, a number, a page, a list, one sentence, a short paragraph).

The model proposes; the graph decides. Every proposed item must cite the facts it uses and is then
verified automatically. Unverifiable items are rejected, or kept only as `interpretive` (excluded from
v1). This adds variety and natural, interesting questions that template generators would never
produce, while keeping traceability.

### 8B.2 Pack levels

The same pipeline works at four levels. Only the pack contents change; the output format,
verification and review stay the same.

| Level | Pack contains | Good for | Typical questions |
|---|---|---|---|
| **Page** | one page: its appearances, lines, speakers, panels, captions, plus the chapter character table (names only) | precise single-page questions, spatial, speaker, captions | "Who says '…'?", "Who is left of Rin in the top panel?", "What is Yukio holding?" |
| **Window** | 2–10 consecutive pages | short chains, next/previous, local conversations | "After Rin's line on page 4, who speaks next, and where does that character appear again?" |
| **Selection** | non-consecutive pages chosen by the graph, e.g. all pages where a character or a pair of characters appears | cross-page relations, character-centred chains, comparisons | "On which pages do Rin and Shiemi appear together, and who speaks first on the last of them?" |
| **Chapter** | the whole chapter | long relational questions, aggregation, chapter-wide clue puzzles | "Which character is drawn on at least three pages but never speaks when Rin is present?" |

Rules:

1. **The answering model always sees the whole chapter** (earlier decision). A smaller pack only limits
   what the generator sees, not what the answering model gets.
2. Because of 1, **references must be unique across the whole chapter**, not just inside the pack. A
   quote that is unique on page 4 but repeated on page 20 is rejected, unless the question names the
   page.
3. If a question is about part of the chapter, **the question states the range** ("on pages 4–8",
   "on page 12"), and the program uses exactly that range.
4. Non-monotone claims (first, next, last, never, exact count) are checked over the range the question
   states. Unless the question says otherwise, "next" or "last" means in the whole chapter, so it is
   verified chapter-wide even if the pack was a window.
5. Every item records `pack_level` and `pack_pages`, so results can be reported per level and
   duplicates between levels can be found.

How the selection level picks pages:

- **Character-centred:** all pages where character X appears or speaks.
- **Pair-centred:** pages where X and Y appear, plus the pages between their joint appearances.
- **Path-centred:** pages along a supported graph path of ≥ 3 hops (from the preflight inventory,
  section 6.3).
- **Contrast:** pages where a relation holds, plus pages where it almost holds (near-miss distractors).

Suggested mix for the pilot: page 20%, window 30%, selection 30%, chapter 20%. Adjust after measuring
yield and quality per level.

### 8B.3 Steps

| Step | What happens | Where |
|---|---|---|
| 1. Build the pack | serialize the graph for the chosen level: pages, characters, appearances, lines with OCR, speaker links, tails, panels, reading order, presence, caption facts, each with a fact ID and provenance | CPU (CVC) |
| 2. Generate | the model reads the pack (optionally with page images) and writes candidate QA pairs, each citing fact IDs | MN5 (GPU) |
| 3. Validate structure | JSON schema; cited fact IDs exist; answer type is valid; no internal IDs in the question text | CPU |
| 4. Verify the answer | exact answers: translate the item into a CRL program (back-parse), run it, require the same answer. Sentence answers: split into atomic claims, check each claim against cited facts (section 9) | CPU + MN5 for back-parse |
| 5. Check the question | uniqueness of references across the whole chapter; necessity of each clause; page ablation; shortcut detectors | CPU |
| 6. Classify | `executed` (answer reproduced by a program), `claim_verified` (all claims verified), or rejected / `interpretive` | CPU |
| 7. Store and select | into the candidate store with the other generators; final selection uses the same policy (section 4) | CPU |
| 8. Review | same risk-based review (section 11); every sentence answer reviewed | human |

### 8B.4 Pack format (compact, ordered)

The example below is the chapter level. Page, window and selection packs use the same format, keep the
full chapter CHARACTERS table (so names and aliases stay consistent), and include only the selected
PAGE blocks plus DERIVED facts that involve those pages.

```
CHAPTER blue_exorcist/c002  pages=38  reading=right-to-left
CHARACTERS
  C1 Rin Okumura  (readable name; aliases: Rin)   pages: 1,2,3,5,…
  C2 Yukio Okumura (readable)                     pages: 2,3,7,…
  C7 [unnamed, generic] page 4 only
PAGE 3
  panels (MAGI-3, order est.): P3.1 top-right, P3.2 top-left, P3.3 bottom
  appearances: A3.1=C1 in P3.1 [H]; A3.2=C2 in P3.1 [H]; A3.3=C1 in P3.3 [H]
  lines (reading order):
    L3.1 "We're leaving now." speaker=A3.1 (C1) tail=T3.1 [H speaker, A OCR]
    L3.2 "Wait for me!" speaker=A3.2 (C2) [H]
  caption P3.1: "Rin grabs his bag while Yukio stands at the door." [A caption]
  caption facts: F812 holds(C1, bag, P3.1); F813 location(C2, door, P3.1)
PAGE 4
  …
DERIVED
  F901 next_speaks(C1, after=3) = page 5
  F902 co_present(C1, C2) pages: 2,3,7,12
COVERAGE
  char_boxes closed_assumed on all annotated pages; pages 37–38 unannotated
```

- Every line has an ID, so the model can cite exact facts.
- Provenance tags ([H], [A]) are visible to the generator, not to the answering model.
- Pack size: a chapter-level pack (about 38 pages × ≈10 appearances, plus lines and captions) is
  likely tens of thousands of tokens **[verify against the model's context limit]**. If too large, give
  the full character table and derived facts plus pages in windows, and ask for cross-window questions
  using the character table.

### 8B.5 What the model is asked to produce

For each item:

```json
{
  "question": "…",
  "answer": "…",
  "answer_format": "character | page | count | boolean | set | sequence | quote | sentence | paragraph | multi_part",
  "reasoning_structure": "direct | chain | branch_combine | aggregate | compare | long_relational",
  "steps": [
    {"claim": "The line 'We're leaving now' on page 3 is spoken by Rin.", "facts": ["L3.1", "A3.1"]},
    {"claim": "Rin next speaks on page 5.", "facts": ["F901"]}
  ],
  "necessary_pages": [3, 5],
  "for_sentence_answers": {
    "required_claims": ["…"],
    "forbidden_claims": ["…"]
  }
}
```

Prompt rules for the generator:

- Use only facts in the pack; cite fact IDs for every step.
- Mix answer formats: roughly one third sentence or paragraph answers, the rest exact (name, number,
  page, set, yes/no).
- Prefer questions needing several pages and several relations; include some long relational
  questions (section 9A).
- Refer to characters only by readable names, unique quotes or descriptions; never by IDs.
- No motives, feelings or causes unless a caption fact states them; no "talks to"; "before/after"
  means reading order.
- Don't put the answer in the question.
- Avoid the most frequent characters as answers when possible; vary page answers.

### 8B.6 Images or not

- Default: pack text only. Cheaper, and the model can't add details the graph doesn't contain.
- Optional variant: pack + page images (or crops of cited evidence), for more natural wording. Every
  claim must still cite fact IDs; uncited visual details cause rejection.
- Decide after a small pilot comparing yield and rejection reasons.

### 8B.7 Pilot before scale

- Run on 3–5 chapters, at all four pack levels; about 50 items per chapter in total, split by the
  suggested mix.
- Report per level: share passing each check, share `executed` vs `claim_verified`, rejection
  reasons, answer-format mix, page span, duplicate rate against existing generators.
- Hand-check about 50 accepted items before scaling to all 50 chapters.

---

## 8C. Creative generation strategies [proposal]

Each idea lists why strong models are likely to fail and how the answer is verified. Every one still
goes through the normal checks: proof or claim verification, uniqueness across the whole chapter,
necessity, shortcut detectors and human solvability.

### 8C.1 How we generate: smarter loops, not just smarter prompts

| Idea | How it works | Why it makes the benchmark harder | Verification |
|---|---|---|---|
| **Adversarial generate → solve → harden loop** | 1. Qwen writes items from a pack. 2. Several solver models answer from **images only**. 3. Items the solvers get right are **hardened**: add a clause, move evidence to far-apart pages, replace a name with a descriptor, add near-miss distractors. 4. Repeat 2–3 rounds. | items evolve toward real model weaknesses instead of our guesses | every hardened version is re-verified by the graph; hardening never touches the answer logic without re-execution |
| **Generator personas** | the same pack under different roles: *detective* (clue puzzles), *continuity editor* (who appears where, when), *script supervisor* (who said what, in which order), *fact-checker* (true/false, false premises), *puzzle maker* (multi-constraint), *skeptic* (what can't be determined) | each role produces a different kind of question | same checks for all personas |
| **Failure-guided generation** | the generator receives statistics on which families, structures and page spans solvers fail most, and writes more of those | focuses effort where models are weakest | normal |
| **Answer-first creative wording** | give the generator a fixed answer and its proof; ask for the most indirect but still unambiguous question leading to it | removes answer priors, encourages descriptor chains | back-parse must reproduce the program |
| **Cross-level combination** | combine a page-level detail with a chapter-level fact: "Of the characters in the top-right panel of page 3, who has the most lines in the whole chapter?" | forces close reading of one page plus chapter-wide aggregation | program over both levels |

### 8C.2 Question types that target known model weaknesses

| Type | Example | Why models fail | Verification |
|---|---|---|---|
| **False-premise questions** | "Why does Rin speak to Shiemi on page 5?" when Rin is not on page 5. Correct answer: point out the false premise. | models tend to accept the premise and invent an answer | premise false in the graph (with coverage); expected answer states the premise is false |
| **Absent-entity questions** | "What does Mephisto say on page 12?" when he is not there | hallucination of plausible content | closure on page 12; expected answer "he does not appear on page 12" |
| **Name-in-bubble ≠ speaker** | "Rin!" is said by Yukio. "Who says 'Rin, wait!'?" | models assume the named person or the nearest person is the speaker | human speaker link |
| **Proximity trap** | the balloon is closest to one character, but its tail points to another | layout heuristics instead of reading tails | human speaker and tail links + geometry |
| **Anti-memorization questions** | in this chapter a character is not yet named, or appears before their famous scene; ask what *these pages* show | popular-series knowledge overrides the pages | blind and series-knowledge baselines must fail |
| **Backward reasoning** | "The last character to speak in the chapter: on which page did they first appear?" | models reason forward and lose track | program (last → first) |
| **Rank and sort** | "Order Rin, Yukio, Shiemi and Mephisto by how many pages they appear on" | counting across many images is a known weakness | exact sequence; margins between neighbours |
| **Who is missing** | "Which character speaks on pages 4, 7 and 12, but is not drawn on page 7?" | needs both presence and off-panel speech | presence closure + speaker links |
| **Distant co-reference** | two quotes by the same unnamed character on pages 2 and 30: "Is the speaker of '…' on page 2 the same character who says '…' on page 30?" | cross-page identity without names | identity links |
| **Change across pages** (caption facts) | "What is Rin holding the first time he appears, and is he still holding it the last time?" | tracking state over the whole chapter | caption facts; multiple choice |

### 8C.3 Long answers that are still graded exactly

| Format | What the model must produce | Grading |
|---|---|---|
| **Script reconstruction** | "Write the dialogue of pages 4–6 as a script: speaker name, then line, in reading order." | per line: speaker and order correct (sequence F1, Kendall tau); text matched against OCR with tolerance |
| **Script error spotting** | a script of pages 4–8 with 1–2 swapped speaker names: "Which lines are wrongly attributed?" | exact set of line numbers |
| **Character timeline** | "List every page where Yukio appears, and mark the ones where he speaks." | exact set + per-page labels |
| **Relation table** | "For each of these four characters, list which of the others they appear together with." | exact table; per-cell F1 |
| **Guided explanation** | short exact answer + "explain which pages support each step" | exact answer + required claims (section 9) |

Script reconstruction is a strong candidate for a signature task: long and natural, it needs reading
order, speaker attribution and identity on every line, and is fully checkable against human
annotations.

### 8C.4 Verified edits to the input images

The answering model sees edited pages; the graph is edited in exactly the same way, so the answer is
known.

| Edit | Example question | Why it is powerful | Prerequisites |
|---|---|---|---|
| **Masked evidence** (section 10.2) | "With the masked panel on page 7, who speaks next after Rin?" | the answer differs from the original story; tests reading vs memory | masking pipeline |
| **Bubble text replacement** | blank a bubble and render new text, e.g. change "Rin" to "Yukio" in one line; ask about mentions or quotes | priors and memorized dialogue become useless | text inpainting/rendering; human check of every edited page |
| **Intruder page** | insert one page from another chapter of the same series: "Which page does not belong?" | needs chapter-level continuity, not just style | page from a different chapter, same split |
| **Shuffled pages** | shuffle 4–6 consecutive pages: "Put these pages in the correct order" | dialogue continuity and presence across pages | page order is ground truth |
| **Panel deletion** | remove one panel: "Which character's line is now missing from this conversation?" | reconstructing the conversation | panel masking |

Every edited page is labelled `edited` with the exact edit recorded, and gets human review in a pilot.

### 8C.5 New interaction formats

| Format | How it works | What it measures |
|---|---|---|
| **Multi-turn follow-ups** | Q1, then Q2 using Q1's answer, then a correction ("Now consider page 9 instead"), then Q3; each turn is its own program | tracking across turns; updating after a correction |
| **Answer + confidence** | answer plus confidence (0–100) | calibration (expected calibration error) |
| **Abstention items** | unanswerable questions (masked or out-of-range) mixed with answerable ones | over-answering; scored with determinability items |

### 8C.6 Rules that keep this fair

- Each item must be solvable by a careful human from the given pages (pilot human study).
- Traps must be honest: false premises are stated plainly, and the expected answer is to reject the
  premise.
- Edited images are labelled in the item metadata, and the benchmark card explains which tasks use
  edits.
- Adversarial filtering is reported openly: solver models are listed, and a natural (unfiltered) split
  is kept.
- No guarantee that every state-of-the-art model fails; the target is low model accuracy with high
  human accuracy, measured and reported.

### 8C.7 What to try first

1. **Script reconstruction and script error spotting:** long, natural answers, fully automatic to
   grade, human annotations only.
2. **False-premise and absent-entity questions:** cheap to generate; a known weakness.
3. **Name-in-bubble ≠ speaker and proximity traps:** existing data, very targeted.
4. **Adversarial generate → solve → harden loop:** strongest way to reach real failures; needs solver
   models on MN5.
5. **Masked evidence and contrast pairs:** counterfactuals tied to the input image.
6. **Rank-and-sort and backward reasoning:** chapter-wide aggregation.
7. **Bubble text replacement and intruder pages:** later; need an editing pipeline and careful human
   checks.

---

## 9A. Long relational questions across pages [proposal]

### 9A.1 What they are

A long relational question **describes several relations in its text** (as clues, steps or
conditions). The model must:

1. understand each described relation;
2. find where each one holds in the chapter, on **different pages**;
3. combine them to reach the answer.

The length comes from the relations the model must use, not from padding. Every described relation
maps to one clause of the program (clause alignment), and every clause must pass the necessity test.

### 9A.2 Hard requirements

| Requirement | Rule [default] |
|---|---|
| Described relations | ≥ 3 clauses, each necessary (removing it changes or breaks the answer) |
| Different pages | the clauses' evidence lies on ≥ 3 different pages; page span ≥ 5 |
| No single-page shortcut | page ablation: removing any key page breaks the answer |
| Readable references | names readable in the chapter, unique quotes, or relational descriptors; never internal IDs |
| No answer leakage | the answer never appears in the question text |
| Faithful wording | back-parse of the text gives the same clauses and answer (section 8.3) |
| Length class | L (81–250 words) or XL (> 250 words) |

### 9A.3 Forms

| Form | How the relations are given | Example shape |
|---|---|---|
| **Clue puzzle** | conditions that together identify one character, page or set | "I am thinking of a character. (1) … (2) … (3) … (4) … Who is it?" |
| **Relation walk** | a path described step by step; each step depends on the previous | "Start from the character who says '…'. Find the next page where they speak. On that page, take the character who speaks right after them. Where does that character appear next together with …?" |
| **Relation map** | a small network of relations between several characters, then a question about one missing link | "On one page, A and B appear together while A speaks. Later, B speaks just before C's first line. C is never drawn on a page where D speaks. Which character …?" |
| **Comparison story** | two described chains, then a comparison | "Follow X from … and follow Y from …. Who reaches … first, and by how many pages?" |
| **Dependent multi-part** | (a), (b), (c), each using the previous answer | each part graded separately, plus all-correct |
| **True/false relation check** | a paragraph of described relations, some false | "Which of these five statements are false?" answer = statement numbers |
| **Noise-augmented** | true but unnecessary relations mixed in | each noise clause verified true and unnecessary |

### 9A.4 Answers to long questions

- **Exact:** character, page, count, set, visual choice, statement numbers.
- **Sentence:** "Explain how the clues lead to the answer."
- **Both:** short exact answer + sentence explanation.

For sentence answers, required claims = the answer plus one claim per described relation, each
resolved to its page (e.g. "the line '…' is on page 4 and is spoken by Rin"). The judge checks each
claim individually (section 9.2), so the explanation is graded on whether the model found each
relation on the right page, not on style.

### 9A.5 Example (illustrative, not from our data)

> Read the whole chapter. One character fits all of these descriptions:
> (1) They are drawn on at least three different pages, but never speak on a page where Rin is drawn.
> (2) The first time they speak, the next different speaker is someone who is also drawn on page 12.
> (3) Their last appearance comes on an earlier page than Shiemi's last appearance.
> (4) They never appear in the same panel as Yukio.
> Who is it? Then explain, in two or three sentences, on which pages each condition is satisfied.

- Program: conjunction of 4 clauses (necessity recorded per clause).
- Exact part: character (or visual choice of 4 crops).
- Sentence part: required claims = the answer + four page-resolved claims; forbidden claims = the
  near-miss characters that fail exactly one condition.

### 9A.6 How they are generated

1. **Constraint accretion** (target first): add clauses whose evidence is on new, far-apart pages and
   from new relation families until the answer is unique; then remove redundant clauses.
2. **Path walks:** enumerate supported paths of ≥ 3 meaningful hops whose steps land on different
   pages.
3. **Relation maps:** pick 3–5 characters with several supported relations between them; hide one
   relation; ask for it.
4. Qwen words the question from the fixed clause list (paraphrase mode) and, for sentence answers,
   writes a reference explanation citing fact IDs per claim.
5. Back-parse and claim checks as in section 8.3. Items failing any check are rejected.

### 9A.7 Reported metrics

Accuracy split by number of described relations, number of necessary pages, page span and form. Also
the composition gap (section 10.4): each described relation can be asked as its own sub-question.

---

## Additions to other sections of brief v2

### Section 13 (allocation): new row

| Primary group | Target | Evidence class | Typical answer formats |
|---|---:|---|---|
| Long relational questions (9A), ≥ 3 described relations, ≥ 3 pages | 200 | executed (+ claim_verified explanation) | character, set, visual choice, statement numbers, short answer + explanation |

Take the 200 from "Long chains" (230 → 130) and "Branch-and-combine" (220 → 120); the total stays
1,000. Free-generation items (8B) compete in the same pool, capped at ≤ 30% of the final set until the
pilot measures their quality.

### Section 5 (taxonomy)

- Add `free_generation` to `generation_mode`.
- Add `long_relational` to `reasoning_tags`.
- Add a `question_form` field: `clue_puzzle`, `relation_walk`, `relation_map`, `comparison_story`,
  `relation_check`, `script_reconstruction`, `script_error`, `false_premise`, `absent_entity`.
- Add `pack_level` (`page`, `window`, `selection`, `chapter`) and `pack_pages`.

### Section 14 (decisions): new rows

| ID | Decision | Recommendation |
|---|---|---|
| D19 | Long relational questions? | Yes: ≥ 200 items, ≥ 3 necessary described relations on ≥ 3 different pages, L/XL length, about half with a graded sentence explanation. |
| D20 | Free QA generation from evidence packs? | Yes, as an extra generator (8B), at four pack levels. Every item must cite facts and pass verification; pilot on 3–5 chapters first; ≤ 30% of the final set until quality is measured. |
| D21 | Adversarial harden loop? | Yes, after the pilot: 2–3 rounds with diverse solver models on MN5; keep a natural split; list solver models. |
| D22 | Image edits (mask, bubble text, intruder, shuffle)? | Masking and shuffling first; bubble-text replacement only after a pilot with human checks of every edited page. |