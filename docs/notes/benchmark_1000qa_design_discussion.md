# Discussion brief v2: 1,000 graph-grounded comics QA pairs

Date: 2026-10-29. Status: proposal and decision document. Nothing described here as new is implemented.
Revises the 2026-10-29 brief. Measured results in section 2 are unchanged. Every proposal is marked
**[proposal]** and needs agreement, a feasibility check on real pools, and versioned code review.

---

## 0. What changed from v1 of this brief

1. **Diagnosis:** v3 selected nothing because of two compounding problems: a selection policy built for
   large pools, and generation families that can only produce frequent characters and +1 page offsets.
   Section 3 separates the two.
2. **Fixes:** fixes for both the selection and the generation side (section 4). Most of them don't
   relax any correctness rule.
3. **One naming scheme:** a single taxonomy for item types, replacing the overlapping labels
   `graph_verified`, `graph_grounded_synthesis` and `qwen_answer_conditioned` (section 5).
4. **Sentence answers graded by atomic claims:** sentence answers are graded through a list of atomic
   claims, each tied to graph facts, instead of an open-ended LLM judgment (section 9).
5. **Seven new ideas** that make the benchmark harder to game and more diagnostic (section 10). The two
   most important are **visual-choice answers** (removing the name-readability bottleneck) and
   **masked-evidence items** (counterfactuals tied to the actual input image).
6. **Risk-based human review** with statistical acceptance sampling (section 11).
7. **Recommended answer for every decision D1–D14**, plus four new ones (section 14).

---

## 1. Requirements and existing decisions (unchanged)

- Every question is grounded in a graph, including questions phrased by Qwen.
- Meaningful chains: each relation identifies something that leads to the next, until the answer.
- Questions that need evidence from different pages combined.
- Longer questions where the wording helps. Length is not a measure of difficulty.
- Explicit type and verification flags on every item, so the required review is known.
- Target: 1,000 final QA pairs. Whether this includes GEN-1 is decision D1.
- About 30% sentence answers is a preference, not a fixed quota. No evaluator for them exists yet.
- Names in questions or answers must be readable in the chapter. Short forms also need alias review.
- No depth maps. Source annotations and completed runs are preserved.
- Qwen runs on MN5 later. This brief launches no inference.
- The answering model sees normal comic images. Graphs, annotations, proofs and generation context
  stay private, unless a diagnostic track explicitly says otherwise.

---

## 2. Current implementation and measured results (unchanged)

- Data: 50 chapters, 2,022 pages.
- Implemented: CKG-1 chapter graphs, CKG-2 name visibility, CKG-3 richer evidence, a CRL interpreter
  and an independent proof checker. Coverage and trust vary by page. An operation existing in code does
  not mean its prerequisites hold on every page.
- GEN-1 selected 3,477 items.
- GEN-2 has six families, all anchored on OCR text or a name, all template-worded:

| Anchor | Target | Family |
|---|---|---|
| Unique exact full OCR text on a given page | speaker identity | `quote_speaker` |
| Same quote anchor | speaker depiction count on that page | `quote_speaker_depictions` |
| Same quote anchor | next page where the speaker is depicted | `quote_speaker_next_page` |
| Text containing an exact readable name form on a given page | speaker identity | `name_speaker` |
| Same name anchor | speaker depiction count on that page | `name_speaker_depictions` |
| Same name anchor | next page where the speaker is depicted | `name_speaker_next_page` |

A name inside a bubble identifies the text. It does not show that the named person is speaking.

| GEN-2 run | Attempted | Passed gates | Selected |
|---|---:|---:|---:|
| v1 | 960 | 214 | 120 |
| v2 | 960 | 140 | 5 |
| v3 (four reviewed aliases) | 960 | 153 | 0 |

V3 keeps all 153 proof-passing candidates. The four Blue Exorcist c002 aliases were reviewed visually
by Codex. That is **AI visual review, not human approval**.

---

## 3. Diagnosis: why v3 is empty and yield is low [proposal]

Two problems compound. Fixing only one of them will not be enough.

### 3.1 Selection problem: caps designed for large pools

- The caps are **percentages applied to very small pools** (per chapter, per split, within GEN-2 alone).
  - With 50 name candidates and only one non-frequent identity per split, the frequent-name cap (≤30%)
    and the repeated-identity cap (≤50%) cannot both hold. No nonempty subset is feasible.
  - All 10 page answers have offset +1, so the offset cap (≤50%) rejects every page subset.
  - Counts alone exceed the 70% count cap.
- The caps stand in for what we actually care about: **an answering model should not score well by
  guessing from answer priors**. Caps limit that only indirectly, and on small pools they block
  everything.
- Some caps are hard-coded in validation, so changing JSON values alone cannot change them.

### 3.2 Generation problem: families with a biased answer space

- **Quote and name anchors favour frequent speakers.** The characters who talk most and whose names
  appear in text are almost always the main characters. Answer-identity bias is built into the
  family, not something selection can fix.
- **"Next page where the speaker is depicted" is almost always +1.** A character who speaks on a page
  usually appears on the next one too. The family produces a near-constant answer.
- **Requiring exact full-OCR anchors and readable names shrinks the pool**. Every candidate must
  pass both, and most characters are never named in readable text.
- **Count answers concentrate** on small values because depiction counts per page are small.

**Conclusion:** relaxing caps without changing the families would produce a benchmark where "answer
the main character" and "answer page+1" score highly. Changing the families without changing the caps
still runs into the small-pool problem. Section 4 does both.

---

## 4. Solutions to the current problems [proposal]

### S1. Measure the shortcut directly, instead of capping proxies

Replace most hard percentage caps with **shortcut-baseline limits on the final benchmark**:

| Baseline | Definition | Proposed limit on final set, per split |
|---|---|---|
| Frequent-character guess | always answer the chapter's most frequent character, by trusted page presence | accuracy ≤ 20% on character answers |
| Second-guess | answer the top-2 characters (the better of the two) | ≤ 30% |
| Page+1 guess | answer anchor page + 1 | ≤ 20% on page answers |
| Mode count | answer the most common count value | ≤ 25% on count answers |
| Question-only model | text-only LLM given the question but no images | at or near chance (measured, not capped in v1) |
| Answer-type prior | most common answer per answer type | reported |

- The baselines are computed on the **final selection** (combined across item types), not per family
  and per chapter.
- Selection becomes a constrained optimization: maximize coverage (chapters, identities, families,
  reasoning structures) **subject to** the baseline limits and minimum diversity floors.
- Use an exact integer program (e.g. OR-Tools CP-SAT; small at this size) or greedy selection with
  repair. Report which constraints are binding.
- Keep a few hard floors that aren't about priors: ≥ 40 of 50 chapters represented; ≤ 40 items per
  chapter; ≤ 25% of character answers from any single identity.

This is a principled relaxation: it limits exactly the shortcut we care about and keeps working on
small pools.

### S2. Apply percentage rules only where the pool is large enough

- Any remaining per-chapter or per-split percentage cap applies only when its denominator ≥ n_min
  (e.g. 20) **[default]**.
- Below n_min, use absolute caps instead (e.g. ≤ 3 items with the same answer identity per chapter).
- This removes the "one candidate makes 100%" problem.

### S3. Generate answer-first for under-represented answers

- Choose the **target first**: non-frequent identities, page offsets ≥ 2, varied count values. Then
  search for programs that uniquely produce that target.
- Inventory per chapter: which identities have enough evidence (depicted on ≥ 2 pages, or speaking at
  least once) to be targets.
- Stratify the target distribution: e.g. at most 40% of character targets from the chapter's top 2
  identities.

### S4. Redesign the page-answer families so offsets vary

Replace or supplement "next page where the speaker is depicted":

| New target | Why the offset varies |
|---|---|
| Next page where X **speaks** after page A | speaking is sparser than being depicted |
| Next page where X and Y **appear together** | joint presence is sparse |
| Next page where X is depicted **after being absent for at least one page** | removes the +1 case by construction |
| **Last** page on which X appears | depends on the whole chapter |
| Page where X **first** speaks after Y's last line | a chain with a variable gap |
| **How many pages** pass between two anchored events | integer answer with a wide range |

### S5. Fix the name-readability bottleneck without weakening it

1. **Visual-choice answers** (section 10.1): the answer options are character crops from the chapter,
   labelled A–D. No readable name is needed.
2. **Descriptor references** in questions: refer to unnamed characters by a unique quote ("the
   character who says '…'"), by a relation ("the character who speaks right after Rin's first line"),
   or by an unambiguous position, instead of a name.
3. **Faster alias review**: propose aliases automatically from OCR name mentions, then confirm them in
   batches in a review page showing the mention, its crop and the character's crops. Human
   confirmations are recorded separately from AI reviews.

### S6. Widen anchors safely

- Allow **normalized substring quote anchors**: at least 4 consecutive words, unique across the whole
  chapter after normalization (NFKC, case, punctuation). This is still exact on normalized text; it
  just doesn't need the full bubble.
- Uniqueness must hold over the **whole chapter**, since the model sees the whole chapter.
- Measure the yield gain before adopting it.

### S7. Treat the candidate pool as a permanent asset

- All candidates that pass gates go into a **versioned private candidate store**, with gate results,
  dimensions and baseline features.
- Final selection is a separate, re-runnable step over the store. Policy changes then mean re-selecting,
  not regenerating, where eligibility is unchanged.
- Policy versions are recorded per selection run. Older selections remain reproducible.

### S8. Separate validity from policy in every report

Each gate result is tagged `validity` (the answer would be wrong or unproven) or `policy` (valid but
over-represented). Reports then always show "N valid candidates rejected by policy X", which makes
trade-offs visible instead of hidden as empty selections.

---

## 5. One taxonomy for item types [proposal]

Replace `graph_verified`, `graph_grounded_synthesis` and `qwen_answer_conditioned` with **four
independent axes**:

| Axis | Values | Meaning |
|---|---|---|
| `evidence_class` | `executed` | the answer is computed by a CRL program and verified by the independent proof checker |
| | `claim_verified` | the answer is a sentence or paragraph; every factual claim maps to graph facts or a sub-program, and is verified |
| | `interpretive` | contains claims the graph cannot verify (e.g. motivation, tone); always human-reviewed; **excluded from v1** |
| `generation_mode` | `template`, `paraphrase`, `synthesis` | who wrote the words: a template; Qwen rephrasing a fixed program; Qwen writing the question and answer from an evidence pack |
| `reasoning_structure` | `direct`, `chain`, `branch_combine`, `aggregate`, `compare`, `counterfactual`, `determinability` | the shape of the program (section 6) |
| `answer_format` | `character`, `page`, `count`, `boolean`, `set`, `sequence`, `quote`, `visual_choice`, `multiple_choice`, `sentence`, `multi_part` | what the answering model returns |

- `qwen_answer_conditioned` becomes `evidence_class=executed` + `generation_mode=paraphrase`: the
  answer is fixed and Qwen only words it.
- `graph_grounded_synthesis` becomes `generation_mode=synthesis` + `evidence_class=claim_verified`
  once every claim passes, otherwise `interpretive`.
- Cross-page is a **tag**, not a structure: any structure can be cross-page.

---

## 6. Reasoning structures and how to measure complexity [proposal]

### 6.1 Structures

| Structure | Example shape |
|---|---|
| Direct | one relation, or one computation |
| Chain | quote → speaker X → next page where X speaks → who speaks first on that page → … |
| Branch and combine | branch 1 and branch 2, each retrieving evidence, then intersect, compare, order or aggregate |
| Aggregate | count, argmax or set over a range of pages |
| Compare | compare two aggregates or two positions |
| Counterfactual | formal edit (ignore pages, mask evidence), then re-evaluate (section 10.2) |
| Determinability | can the question be answered from what is shown? (section 10.2) |

Every transition must be a supported, unambiguous graph relation. No conversation, cause, motive or
event link may be inferred from proximity.

### 6.2 Complexity measures (record all; no single score)

| Measure | Definition |
|---|---|
| `meaningful_hops` | transitions whose removal breaks the answer (necessity test); bookkeeping steps count 0 |
| `branch_count` | independent branches that are combined |
| `combine_ops` | intersect, compare, aggregate, order operations |
| `necessary_pages` | pages whose removal (page ablation) changes or breaks the answer |
| `page_span` | distance between the first and last necessary page |
| `evidence_position` | where the necessary pages sit in the chapter (start, middle, end) |
| `candidate_elimination` | candidates removed by each clause |
| `distractor_density` | candidates satisfying all but one clause |
| `relation_families` | distinct families used (identity, discourse, presence, spatial, caption, OCR) |
| `trust_mix` | share of facts by provenance tier |

Necessity proves dependency under our evidence model. It does not guarantee difficulty for every model.
Difficulty is measured later from model and human results.

### 6.3 Feasibility preflight (before choosing thresholds)

For each chapter, enumerate the supported paths and branches up to depth 5 and report:

- the number of distinct paths per depth;
- the distribution of necessary pages and page span;
- eligible target identities;
- the coverage status on the pages involved;
- the expected yield after gates.

Choose depth thresholds (e.g. "long chain = ≥ 3 meaningful hops") **from this inventory**, not in
advance.

---

## 7. Families to add, in priority order [proposal]

| Priority | Family | Structure | Prerequisites |
|---|---|---|---|
| 1 | Speaker chains: quote → speaker → next page where they **speak** → first speaker there | chain | existing relations, plus `next_speaks` in CRL and the checker |
| 1 | Co-presence: who appears together with both X and Y, and never with Z | branch_combine | presence; coverage for "never" |
| 1 | Next joint appearance of X and Y; last appearance; page gaps | chain / aggregate | presence, coverage |
| 1 | Speaking-turn order: who speaks after X's k-th line | chain | speaker links, reading order |
| 2 | Comparisons: does X speak more before or after Y first appears | compare | line counts, coverage |
| 2 | Mention vs presence: who is named in dialogue before first being drawn | branch_combine | name mentions, alias review |
| 2 | Proximity trap: the speaker of a bubble is not the character nearest to it | chain | geometry + speaker links |
| 2 | Spatial within a panel at an anchored event | chain | MAGI-3 panels (tier A) |
| 3 | Caption-fact chains: who speaks first on page 3 → what is that character doing when next drawn | chain | caption fact extraction; multiple-choice answers |
| 3 | Visual choice and masked evidence | section 10 | crop and masking pipeline |
| 3 | Claim-verified sentence answers | section 9 | claim extraction and checking |

Each family needs: a CRL operation (if new), a checker rule, synthetic tests including wrong-proof,
redundant-step and missing-page cases, and a bounded real-data trial before a full build.

---

## 8. Evidence packs for Qwen [proposal]

### 8.1 Pack contents, in order

1. Chapter context: ordered page list with stable IDs and reading direction.
2. **The target**: a fixed program and answer (for paraphrase), or a fixed claim list (for synthesis).
3. Relevant nodes, with types and readable descriptors (names only if readable; quotes; positions).
4. Directed relations, each with fact ID, provenance tier and coverage status.
5. Dependency structure: the proof tree, preserving branches and shared nodes.
6. Attached OCR text, captions and crop references for the relevant nodes.
7. Boundaries: what may not be claimed (no motives, no addressee, no story-time "before").

The pack is task-specific, never a dump of all annotations. Page order (reading order) and reasoning
order (proof traversal) are kept separate.

### 8.2 Images for Qwen

- Paraphrase mode: **text only**. The meaning is fixed by the program, and images could tempt Qwen to
  add unsupported details.
- Synthesis mode: text pack **plus the crops of the necessary evidence**, so wording is natural, with
  the rule that every claim must cite a fact ID.
- The submitted pack and raw response are stored for audit.

### 8.3 Checking Qwen's output

| Mode | Check |
|---|---|
| Paraphrase | independent back-parse to CRL → execute → same answer and same necessary pages; plus a meaning check that every clause is present and nothing is added |
| Synthesis | split the output into atomic claims → map each claim to cited fact IDs → verify each claim by CRL execution or fact lookup → **reject the item if any claim is unsupported** |

---

## 9. Sentence answers graded by atomic claims [proposal]

The goal: keep sentence answers (about 30%) without relying on an open-ended LLM judgment.

### 9.1 Answer structure

Each sentence-answer item stores:

- `required_claims`: atomic facts the answer must state (e.g. "Rin speaks first on page 12";
  "Shiemi is present on pages 12–14"), each linked to fact IDs.
- `optional_claims`: correct but not required.
- `forbidden_claims`: likely errors, each verified false in the graph (e.g. swapped speaker, wrong
  page). These come from the near-miss distractors already computed by the generator.
- A reference answer (for readers only, not used for scoring).

### 9.2 Scoring

- A judge model checks each claim **individually**: is this atomic claim entailed by the model's
  answer? (yes/no). This is much more reliable than "rate this paragraph".
- Score = required claims recall, with a penalty for each forbidden claim stated.
- Report three numbers: claim recall, hallucination rate (forbidden or unsupported claims), and
  all-required-correct.

### 9.3 Judge reliability

- Use a judge from a different model family from the generator (Qwen) and from the main evaluated
  models, or report results with two judges.
- Calibrate on a human-labelled set (about 200 claim–answer pairs); report agreement (Cohen's κ).
- Disagreements between two judges go to human adjudication.

### 9.4 Cheaper variant

**Short answer + explanation:** the model gives an exact short answer (graded exactly) plus an
explanation, graded by required claims. Most of the score stays deterministic.

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
| **Clue puzzle** | a list of conditions that together identify one character, page or set | "I am thinking of a character. (1) … (2) … (3) … (4) … Who is it?" |
| **Relation walk** | a path described step by step; each step depends on the previous | "Start from the character who says '…'. Find the next page where they speak. On that page, take the character who speaks right after them. Where does that character appear next together with …?" |
| **Relation map** | the question describes a small network of relations between several characters, then asks about one missing link | "On one page, A and B appear together while A speaks. Later, B speaks just before C's first line. C is never drawn on a page where D speaks. Which character …?" |
| **Comparison story** | two described chains, then a comparison | "Follow X from … and follow Y from …. Who reaches … first, and by how many pages?" |
| **Dependent multi-part** | (a), (b), (c), each using the previous answer | each part answer graded separately, plus all-correct |
| **True/false relation check** | a paragraph of described relations, some false | "Which of these five statements are false?" answer = statement numbers |
| **Noise-augmented** | true but unnecessary relations mixed in | the model must ignore irrelevant clues (each noise clause verified true and unnecessary) |

### 9A.4 Answers to long questions

Long questions can take any answer format:

- **exact:** character, page, count, set, visual choice, statement numbers;
- **sentence:** "Explain how the clues lead to the answer";
- **both:** short exact answer + sentence explanation.

For sentence answers, required claims = the answer plus one claim per described relation, each
resolved to its page (e.g. "the line '…' is on page 4 and is spoken by Rin"). The judge checks each
claim individually (section 9.2). So the explanation is graded on whether the model actually found
each relation on the right page, not on style.

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
   from new relation families, until the answer is unique; then remove redundant clauses.
2. **Path walks:** enumerate supported paths of ≥ 3 meaningful hops whose steps land on different
   pages.
3. **Relation maps:** pick 3–5 characters with several supported relations between them; hide one
   relation; ask for it.
4. Qwen words the question from the fixed clause list (paraphrase mode) and, for sentence answers,
   writes a reference explanation that cites fact IDs per claim.
5. Back-parse and claim checks as in section 8.3. Items failing any check are rejected.

### 9A.7 Reported metrics

Accuracy split by number of described relations, number of necessary pages, page span and form. Also
the composition gap (section 10.4): each described relation can also be asked as its own
sub-question.

---

## 10. Signature ideas [proposal]

### 10.1 Visual-choice answers

- Options are **crops of characters from the chapter**, labelled A–D (sometimes "E: none of these").
- Removes the name-readability requirement, so minor and unnamed characters can be answers.
- Distractors are chosen deliberately: characters on the same pages; similar-looking characters (same
  page-local cluster confusion, similar outfit); near-miss candidates from the generator.
- The correct crop comes from a **different page** than the evidence page, so the model has to
  re-identify the character, not match the same image.
- Scored exactly, with no LLM judge.

### 10.2 Masked-evidence items: counterfactuals tied to the input image

- Black out one region (a character, a balloon or a panel) on a page, and correspondingly remove its
  facts from the graph.
- Ask a question whose answer changes, or becomes undeterminable, because of the mask:
  - "With the masked panel on page 7, who is the next character to speak after Rin?" (the answer moves
    to the next visible line);
  - "Can you determine who speaks the masked line?" → cannot be determined (or yes, if a tail or later
    reference still settles it).
- Pair each masked item with the unmasked original: the pair measures whether the model reads the
  pages or guesses.
- Unlike graph-only counterfactuals, the edit is **visible in the input**, so it is not a hypothetical
  story but a concrete, checkable change.

### 10.3 Contrast pairs

- Two items differing by one clause, one page, or one mask, with different answers.
- Score consistency: credit only when both items of a pair are answered correctly.
- Strongly reduces the value of guessing.

### 10.4 Compositional consistency probes

- For each chain item, also ask each sub-question (one per proof step).
- Report the **composition gap**: how often a model answers every step correctly but the full question
  wrongly, and the reverse (right answer, wrong steps, which suggests a shortcut).

### 10.5 Evidence-page answers ("right for the right reasons")

- Optional second output: the pages supporting the answer.
- Scored against the necessary pages (precision/recall).
- A correct answer with wrong evidence is reported separately.

### 10.6 Evidence-position control ("lost in the middle")

- Because models see the whole chapter, control where the necessary pages sit: start, middle, end.
- Report accuracy by position and by page span.

### 10.7 Diagnostic input tracks

| Track | Input | Isolates |
|---|---|---|
| Main | chapter images + question | full task |
| Images + extracted facts | images + an ID-free fact list | perception vs reasoning |
| Facts only | fact list + question | pure reasoning |
| Text only | OCR transcripts + question | text shortcut |
| Blind | question only | priors and series knowledge |

The facts-only track is cheap to run, and very informative: if models solve it but fail the main
track, the bottleneck is perception.

---

## 11. Risk-based human review [proposal]

### 11.1 Review level by risk

| Stratum | Review |
|---|---|
| `executed`, template wording, all facts H | sampled |
| `executed`, Qwen paraphrase | sampled, plus every item that failed any automatic meaning check twice |
| `executed`, uses tier-A facts (MAGI-3, OCR, captions) | sampled, stratified by fact source |
| `executed`, uses `closed_assumed` coverage for absence, first, next or count | sampled, with reviewers checking specifically for missed annotations |
| `claim_verified` (sentence answers) | **every item** |
| masked-evidence, visual-choice | sampled; every distractor set checked in a pilot |
| `interpretive` | excluded from v1 |

### 11.2 Acceptance sampling

- Per stratum, review n randomly sampled items.
- If 0 errors are found in n items, the 95% upper bound on the error rate is about 3/n (rule of three):
  0 errors in 60 → below 5%; in 150 → below 2%.
- If errors are found: fix the cause (generator or gate), regenerate the stratum, and review a new
  sample.
- Report the measured bound per stratum in the benchmark card.

### 11.3 Review tooling

- A review page per item: question, answer, proof trail with crops of each step, and buttons for
  accept, reject, or flag (reason codes).
- Reviewer type is recorded: `human` or `ai`. AI review never counts as human approval.

---

## 12. Item metadata [proposal]

```json
{
  "item_id": "q:…",
  "evidence_class": "executed",
  "generation_mode": "paraphrase",
  "reasoning_structure": "chain",
  "reasoning_tags": ["cross_page", "discourse", "presence"],
  "answer_format": "visual_choice",
  "complexity": {
    "meaningful_hops": 4, "branch_count": 1, "combine_ops": 0,
    "necessary_pages": [3, 9, 15], "page_span": 12,
    "evidence_position": "middle", "distractor_density": 3
  },
  "trust_mix": {"H": 0.75, "A": 0.25},
  "coverage_assumptions": ["closed_assumed:char_boxes:p4-p8"],
  "proof_status": "verified",
  "wording_status": "back_parse_passed",
  "claims": null,
  "shortcut_features": {"is_top2_identity": false, "page_offset": 6},
  "pair_id": "pair:…",
  "review": {"required": "sampled", "reasons": ["tier_A_facts"], "status": "pending",
             "records": []},
  "versions": {"graph": "…", "crl": "…", "policy": "…", "generator": "…", "selection": "…"}
}
```

Also retained: graph snapshot hash; evidence subgraph IDs; program and proof; sources and trust per
fact; image references; canonical answer and accepted variants; scoring method; versioned review
records.

Proof validity (premises → answer) and wording validity (question expresses the program) are separate
checks with separate statuses.

---

## 13. Revised allocation of 1,000 final items [proposal]

Generate about 3× surplus, then select with the section 4 policy. One primary group per item; other
groups are tags.

| Primary group | Target | Evidence class | Typical answer formats |
|---|---:|---|---|
| Short precise questions | 120 | executed | character, page, count, quote, visual choice |
| Long chains (≥ 3 meaningful hops) | 230 | executed | character, page, visual choice |
| Branch-and-combine across pages | 220 | executed | set, boolean, compare, character |
| Aggregation and comparison over the chapter | 80 | executed | count, compare, character |
| Masked-evidence and contrast pairs | 100 (50 pairs) | executed | any; includes "cannot be determined" |
| Claim-verified sentence answers | 250 | claim_verified | sentence, short answer + explanation |
| **Total** | **1,000** | | |

- Sentence answers: 25% here, plus the explanation part of some short-answer items, which keeps the
  ~30% preference within reach without forcing unsupported claims.
- Floors: ≥ 40 chapters; both splits (seen/unseen) in proportion to the source; ≥ 150 distinct target
  identities; visual-choice items ≥ 15% of character answers.
- All targets are adjustable after the feasibility preflight (section 6.3).

| Long relational questions (9A), ≥ 3 described relations, ≥ 3 pages | 200 | executed (+ claim_verified explanation) | character, set, visual choice, statement numbers, short answer + explanation |
---

## 14. Decisions with recommendations

| ID | Decision | Recommendation |
|---|---|---|
| D1 | What does 1,000 include? | One combined final benchmark selected from all preserved pools (GEN-1, GEN-2 and new families). GEN-1 items compete under the same policy. |
| D2 | What is mandatory? | Everything in "validity" (S8) is mandatory: proof, checker, exact anchors, readable names or visual choice, no leakage, necessary pages, provenance. Everything else is policy. |
| D3 | Where does balance apply? | Shortcut baselines on the final benchmark per split (S1). Absolute caps per chapter (S2). No per-family percentage caps. |
| D4 | Which caps change? | Replace frequent-name, identity, offset and count caps with baseline limits. Keep the two-option cap, as "≤ 5% of all items have only two possible answers" on the final set. Version the change in code and policy. |
| D5 | How to measure complexity? | Section 6.2 measures; thresholds chosen from the preflight. |
| D6 | Which families first? | Section 7, priority 1: speaker chains, co-presence, joint and last appearance, turn order. They need no new evidence sources. |
| D7 | How much synthesis? | 250 claim-verified sentence items plus short-answer + explanation items. No interpretive items in v1. |
| D8 | How is synthesis evaluated? | Claim-level entailment with required and forbidden claims (section 9). Judge from a different family, calibrated against human labels, two-judge adjudication. |
| D9 | Who reviews what? | Section 11: every sentence item; sampled acceptance for the rest; AI and human reviews kept separate. |
| D10 | What does Qwen receive? | Section 8: ordered task-specific pack; text-only for paraphrase; text plus evidence crops for synthesis. Verify the MN5 model and its context limits first. |
| D11 | Can absence/first/next claims use assumed closure? | Yes, labelled per item, with a dedicated review stratum focused on missed annotations. Report accuracy with and without these items. |
| D12 | Split and leakage? | Keep seen/unseen as in the source. Dedup across items by program, answer and necessary-page overlap. Report series-knowledge with the blind track. |
| D13 | Wording and references? | Readable names, unique quotes, relational descriptors or visual choice. "Page k" = k-th page of the chapter as shown. Drop page numbers from anchors only if the anchor stays unique chapter-wide. |
| D14 | Counterfactuals? | Use masked-evidence items (10.2) as the main counterfactual form. Graph-only edits ("ignoring pages 3–5…") are allowed only with that explicit wording, labelled `formal_hypothetical`. |
| D15 (new) | Visual-choice answers? | Yes. Crops from a different page than the evidence; distractors from near-miss candidates. |
| D16 (new) | Contrast pairs and consistency scoring? | Yes, about 10% of items in pairs; report both item and pair accuracy. |
| D17 (new) | Diagnostic tracks? | Run facts-only, text-only and blind on every model; release them as diagnostics. |
| D18 (new) | Candidate store and re-selection? | Yes (S7): store everything that passes validity; selection is a separate, versioned run. |

| D19 (new) | Long relational questions? | Yes: ≥ 200 items, ≥ 3 necessary described relations on ≥ 3 different pages, L/XL length, about half with a graded sentence explanation. |
---

## 15. Suggested next sequence

1. Agree on D1–D18.
2. **Selection-only experiment on the existing v3 pool** with the S1/S2 policy: no regeneration needed.
   It shows whether the new policy behaves as expected.
3. Feasibility preflight (section 6.3) on all chapters: path inventory, eligible targets, expected yield.
4. Implement the priority-1 families (section 7) with CRL and checker extensions; synthetic tests
   including wrong-proof, redundant-step and missing-page cases.
5. Bounded real trial (a few chapters), then a full build into the candidate store.
6. Crop and mask pipeline for visual-choice and masked-evidence items; pilot with human review of
   distractors.
7. MN5: Qwen paraphrase and synthesis with ordered packs; automatic back-parse and claim checks; raw
   responses retained.
8. Final selection of 1,000 under the agreed policy, with split counts and group assignment.
9. Human review by stratum; judge calibration; shortcut baselines; diagnostic tracks; leakage and
   dedup audit.
10. Export: public items (images + question + format instruction), private evidence, and a benchmark
    card reporting baselines, review bounds, coverage assumptions and trust mix.

No production generation or inference is requested by this brief.

## References in this repository

- [Shared status](../STATUS.md)
- [Original graph-reasoning design](graph_reasoning.md)
- [GEN-2 v3 measured results and quota conflict](gen2_v3_results.md)
- [GEN-2 supported family contract](../../src/comics_qa/tasks/graph/gen2/README.md)
- [V3 pools, aliases and selection contract](../../src/comics_qa/tasks/graph/gen2/V3.md)
- [GEN-1 results](gen1_results.md)
- [CKG-3 results and review limitations](ckg3_results.md)