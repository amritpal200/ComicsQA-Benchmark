# CKG + CRL: graph-based, proof-carrying manga QA

**Comic Knowledge Graph (CKG)** and **Comic Reasoning Language (CRL)**: a specification for the
graph-reasoning part of the Manga QA benchmark.

- Version: draft 0.1, 2026-10-23 (Europe/Madrid).
- Status: **design only. Nothing has been implemented or run.**
- Scope: extends and replaces `specs/06_qa_graph_hybrid.md` of the comics-qa-codex package, and
  supplies the graph part of `specs/03_evidence_builders.md`. OCR, narrative QA and the other modules
  are discussed separately.

---

## 0. How to use this document (for the assistant)

- Before anything else, read `AGENTS.md`, `README.md` and `specs/00, 01, 03, 06` of comics-qa-codex.
  Inspect the real PopManga files and report every mismatch between this spec and the data.
- Work stage by stage (section 19): present a plan, wait for explicit approval, implement, run only
  CPU/synthetic tests, then give the user the exact commands. The user runs GPU, MN5 and full-dataset
  jobs.
- **[default]** marks a proposed value to tune after the data audit. **[verify]** marks something that
  depends on data not yet inspected.
- Never weaken a rule to make more questions pass. Report the yield instead.
- Sources are read-only. Large outputs go outside Git, under the user's configured big-files root.

---

## 1. Goal and principles

**Goal.** A benchmark of questions over manga chapters where:

- every answer is **computed by executing a program** over a graph of annotated facts;
- every question carries a **machine-checkable proof** back to page-level annotations;
- complexity is unbounded by construction (programs compose freely), while every step stays
  traceable.

**Principles**

| # | Principle | Meaning |
|---|---|---|
| P1 | Answer by execution | LLMs may propose or phrase questions. Only the interpreter decides answers. |
| P2 | Proof-carrying items | Each item = (question Q, answer A, program π, proof W, graph version, policy). A checker independent of the generator can verify W. |
| P3 | Every fact traceable | Each fact comes from an annotation record, a geometric computation over records, or a named rule over other facts. |
| P4 | Open world, three-valued logic | Absence is never inferred from missing annotations. Negation, exact counts, "first", "only" and "every" need explicit coverage certificates. |
| P5 | Explicit trust | Every fact has a trust level. Derived facts take the weakest trust of their inputs. |
| P6 | Robust answers | An item is accepted only if its answer stays the same across plausible alternative graphs (annotation-noise worlds). |
| P7 | Every clause matters | Each constraint in a question is necessary, and together they are sufficient. |
| P8 | Human-solvable | A careful human can solve it from the given pages alone, with no outside plot knowledge. |
| P9 | Privacy | Programs, proofs, internal IDs and trust labels never appear in model-facing text. |
| P10 | Versioned semantics | The language, graph builder, policy, generators and verbalizer are each versioned and hashed. |

---

## 2. Terminology

- **Context:** the ordered page images given to the evaluated model, labelled `Page 1..N` (local
  indices). The mapping to original page IDs is stored privately.
- **Scope:** the subset of the context a program ranges over. Default: the whole context.
- **Appearance:** one drawn instance of a character (one human-annotated box).
- **Character:** one person across a chapter, i.e. a set of linked appearances.
- **Text region:** one annotated text box. A **line** is a text region treated as spoken dialogue
  (section 4.4).
- **Reading position (Pos):** the position of an item in manga reading order (section 4.7).
- **Fact:** a typed relation instance with provenance (section 4.5).
- **Coverage certificate:** a statement that an annotation family is complete on a page (section 4.6).
- **World:** a chapter graph plus a policy. **Alternative world:** a perturbed graph (section 12).
- **Program:** a CRL expression (section 5).
- **Proof (witness):** the evaluation tree with every fact and certificate used (section 6).
- **Item:** a question with its answer, program, proof and metadata.

---

## 3. Source layers that feed the graph

All rows are **[verify]**: confirm against the actual PopManga export and the MAGI-3/OCR outputs.

| Layer | Content | Origin | Notes |
|---|---|---|---|
| PopManga human annotations | character boxes with names and page-local clusters; text boxes; tail boxes; text→character speaker links; text→tail links; text class (numeric) | H | Relation indices refer to category-filtered lists. **Text-class semantics are unverified.** |
| Page order | order of pages within a chapter folder | H | Confirm how order is encoded. Some chapter pages are unannotated. |
| Chapter identity links | linking page-local appearances to chapter-level characters (names + clusters + aliases) | rule over H | Separate spec. Produces confidence scores. |
| Panels | PopManga panel boxes are **model-generated proxies** (MAGI) | M (A after audit) | 9,578 boxes. |
| Reading order inside a page | computed from panel geometry (right-to-left, then top-to-bottom) | geometry over M | Has a confidence per panel. |
| OCR transcripts | from text crops (separate OCR plan) | M; V when two models agree or a human verifies | Needed for quotes and name mentions. |
| Captions / events | Qwen captions | M | **Extension layer only** (section 4.9). Not used in v1. |
| Depth | — | — | Excluded from v1. |

Approximate scale: 1,925 annotated pages in 50 chapter folders, so about 38 annotated pages per
chapter on average but uneven, plus about 18,778 character boxes (about 9.8 per page).

**Key design decision:** a large family of questions can use **page-level relations only**, which
depend only on human annotations plus identity links. Panel-level relations inherit the weaker panel
trust. v1 should get most of its yield from page-level programs.

---

## 4. Comic Knowledge Graph (CKG)

### 4.1 World

For each chapter k, the graph is **G_k = (V, F, C, M)**:

- **V:** nodes.
- **F:** facts (typed relations with provenance).
- **C:** coverage certificates.
- **M:** metadata (versions, source hashes, builder code hash, config hash).

Graphs are built per chapter. v1 does no cross-chapter reasoning.

### 4.2 Stable IDs

IDs are deterministic and derived from source identifiers, never from row order in derived tables.
CKG-1 implements the existing core ID policy (decision 2026-10-27); the explicit
CKG-0 generic identity corrections are the only overrides. See the graph README
for the executable v1 contract, including source selectors and coverage records.

| Entity | ID format |
|---|---|
| Chapter | `<series-slug>__cNNN` (core ID) |
| Page | `<chapter>__pNNN` or `<chapter>__pNNN-NNN` for a spread |
| Appearance | `<page>__hcharNN` (human category index) |
| Text | `<page>__htextNN` |
| Tail | `<page>__htailNN` |
| Panel | `<page>__panelNN` (core MAGI index; source hash pins the version) |
| Character | existing exact-name core identity or reviewed `<page>__unnamed<cluster>` |
| Fact | `f:` + full SHA-256 of canonical fact record, including sources, premises and version |
| Coverage | `cov:` + full SHA-256 of page/family/status/provenance/policy record |

Local page indices in a question context are separate and stored per item.

### 4.3 Node types

| Node | Attributes |
|---|---|
| Chapter | id, manga, chapter number, split (seen/unseen), ordered list of all page images with an `annotated` flag, reading direction (default rtl **[verify]**) |
| Page | id, chapter, index in chapter, image path, width, height, annotated (bool), split |
| Panel | id, page, bbox, source (`magi_proxy`), est. order index, order confidence |
| Appearance | id, page, bbox (original px plus normalized 0–1000), original cluster id, original name string, `generic_name` flag, `truncated` flag (touches page or panel edge), area, panel memberships with overlap fractions |
| Character | id, chapter, canonical name, aliases, generic (bool), link confidence, appearance ids |
| Text | id, page, bbox, raw class, mapped class (only after verification), OCR {consensus, per-model outputs, agreement score, status}, word count, panel memberships, reading position |
| Tail | id, page, bbox, linked text |
| *(extension)* Event, Object, Scene | see section 4.9 |

**Generic-name policy (agreed).** Only `none` and `Unnamed …` names are generic;
role names remain named. Generic appearances:

- never link across pages;
- share a page-local Character only within the same human page cluster, with `generic=true`;
- can be referred to only through descriptors (section 5.6), never as a named answer.

### 4.4 Relation registry (v1 core)

| Relation | Signature | Definition | Origin / derivation |
|---|---|---|---|
| `page_in` | Page → Chapter | source structure | H / source |
| `next_page` | Page → Page | consecutive images in chapter order | H / source |
| `on_page` | App, Text, Tail, Panel → Page | source structure | H / source |
| `in_panel` | App, Text → Panel | box area fraction inside the panel ≥ 0.6 **[default]**; if two panels each get ≥ 0.3, the item is `ambiguous_panel` | geometry over H boxes and M panels |
| `is_char` | App → Char (confidence) | identity linker output | rule over H names and clusters |
| `named` | Char → Str | canonical name | H |
| `alias` | Char → Str | name variants (word order, honorific-stripped) | rule |
| `spoken_by` | Text → App | human speaker link | H |
| `has_tail` | Text → Tail | human text–tail link | H |
| `is_line` | Text | text with a speaker link (v1). Class-based only after the class mapping is verified. | rule over H |
| `reading_pos` | Text → Pos | section 4.7 | page part H; inner part geometry over M |
| `mentions` | Text → Char | OCR text contains a name or alias (normalized, honorifics stripped) | rule over OCR (M/V) |
| `left_of`, `above`, `overlaps`, `larger_than` | App × App | section 4.8, same panel only | geometry |
| `nearest_to_text` | Text → App | appearance closest to the balloon (used for distractors) | geometry |
| `present` | Char × Page | some appearance on the page links to the character | rule |
| `present_panel` | Char × Panel | same, at panel level | rule (panel trust) |
| `speaks_on` | Char × Page | some line on the page is spoken by one of the character's appearances | rule |
| `co_present` | Char × Char × unit | both present on the same page or panel | rule |

Each registry entry stores:

- signature;
- origin and derivation;
- functional or not;
- monotonicity class (section 5.4);
- coverage family required for negation or exact counting;
- hop weight;
- gloss template;
- tests.

### 4.5 Provenance and trust

Every fact has two provenance axes.

**Origin of the base evidence:**

| Tier | Meaning |
|---|---|
| **H** | human annotation |
| **V** | model output individually verified, by a human or by two-model agreement |
| **A** | model output from a source audited on a sample, with measured precision/recall stored |
| **M** | model output, unaudited |

**Derivation:** **S** source record, **G** geometric computation, **R** named rule, **X** aggregate.

**Trust order:** H > V > A > M.

- Trust of a fact = the minimum origin over its whole support (weakest link).
- Confidence of a derived fact = min(confidence of inputs) × rule confidence **[default]**. Stored for
  filtering only; it is not a calibrated probability.

Fact record:

```json
{
  "fact_id": "f:9c1e…",
  "rel": "spoken_by",
  "args": ["txt:pg:ch:naruto/002/p003/t2", "app:pg:ch:naruto/002/p003/c1"],
  "origin": "H",
  "derivation": "S",
  "rule_id": null,
  "premises": [],
  "sources": [{"file": "dataset/…", "pointer": "pages[17].text_char_links[2]"}],
  "confidence": 1.0,
  "audit_id": null,
  "graph_version": "ckg-…"
}
```

The agreed policy requires H/V for answer-critical steps. Model panels remain M
in CKG-1; a later sample audit may assign A, which does not automatically satisfy
the H/V answer-critical policy. Quote/name anchors require verification.

### 4.6 Coverage certificates and the open world

For each (page, relation family) there is one certificate with a status:

| Status | Meaning |
|---|---|
| `closed_verified` | a human checked that this page is fully annotated for this family |
| `closed_audited` | the source was audited dataset-wide with recall ≥ r_min, and the page has no red flags |
| `closed_assumed` | human completeness accepted by project policy; no unresolved flag for this page/family; not measured recall (decision 2026-10-23) |
| `open` | completeness unknown |
| `absent` | the page is not annotated for this family (e.g. an unannotated page) |

Relation families: `char_boxes`, `names`, `text_boxes`, `speaker_links`, `ocr`, `panels`.

Example red flags:

- a text that looks like dialogue with no speaker link;
- empty names;
- character-box count far below the page's neighbours.

**Rules**

1. A **non-monotone** operation (section 5.4) needs a closed certificate for every page in its range.
   Otherwise its result is `UNKNOWN`.
2. Certificates used become part of the proof, so a "never" answer is proven by certificates.
3. On an unannotated page, human coverage is `absent`; available model families
   remain `open`. Supplied page-sequence coverage is separate. Non-monotone human
   queries ranging over that page return `UNKNOWN`; existence facts elsewhere remain valid.
4. Missing labels never produce "no", "zero" or "cannot be determined" answers. They produce
   `UNKNOWN`, and the program is rejected.

### 4.7 Order and time

- **Page order** is H.
- **Pos** = (page index, panel rank, text rank within panel). The page component is H; the inner
  components are estimates with confidence.
  - Comparisons that only need the page component are H.
  - Within-page comparisons inherit panel and order trust.
- **Discourse time only.** "Before", "after", "next" and "first" mean **reading order**. Story time
  (flashbacks, parallel scenes) is not modelled in v1. Questions must say "on an earlier page" or "the
  next line in reading order", never "happened before".
- Manga direction: right-to-left, then top-to-bottom. Irregular layouts get a low order confidence.

### 4.8 Geometry conventions

- Coordinates are original pixels, with normalized 0–1000 copies. Every transform is recorded.
- Spatial predicates are evaluated **only between appearances in the same panel**. Page-level layout
  words ("upper half of page 4") form a separate, explicitly labelled family.
- `left_of(a, b)`: center_x(a) + δ < center_x(b), with δ = 0.05 × panel width **[default]**.
  - If |Δx| ≤ δ, the result is `UNKNOWN` (a tie, never a guess).
  - `above` works the same way on the y axis.
- `overlaps`: IoU ≥ 0.1 **[default]**.
- `larger_than`: area ratio ≥ 1.5 **[default]**. Truncated boxes are excluded from size comparisons.

### 4.9 Comics ontology extension layer (not in v1)

Each of these needs new annotation, an audit, registry entries and tests before use. Once registered,
CRL gets navigation, inverse and predicate operations for it automatically.

- **Text function:** dialogue, narration, thought, sound effect (SFX). Needs text-class verification.
- **Balloon type:** speech, thought, whisper, shout, electronic.
- **Off-panel speech:** speaker's appearance is not in the balloon's panel. Derivable in v1 once panels
  are audited.
- **Emanata:** sweat drops, motion lines, anger marks.
- **Gaze / addressee:** who looks at, or talks to, whom.
- **Objects and attributes:** held objects, clothing, expressions.
- **Scene / location segmentation.**
- **Panel transitions (McCloud):** moment-to-moment, action-to-action, subject-to-subject,
  scene-to-scene, aspect-to-aspect, non-sequitur.
- **Narrative grammar roles (Cohn's Visual Narrative Grammar):** Establisher, Initial, Prolongation,
  Peak, Release.
- **Layout:** splash page, double-page spread, inset, bleed, borderless panel.
- **Flashback markers and page-turn reveals.**

---

## 5. Comic Reasoning Language (CRL)

### 5.1 Design

CRL is:

- **typed and functional:** the result of each operation feeds the next;
- **set-oriented:** most operations take and return sets or ordered sequences;
- **total:** no recursion, so every program terminates;
- **three-valued:** true / false / unknown;
- **proof-producing:** every evaluation records the facts it used.

It is inspired by lambda-DCS, KoPL and GQA-style functional programs, with Datalog-style rules for
derived relations. It can express:

- chains, intersections, set difference;
- quantifiers, aggregation, comparison, nested ordinals;
- spatial and discourse relations;
- name mentions;
- counterfactual world edits;
- questions about what can be determined from the shown pages.

### 5.2 Types

| Kind | Types |
|---|---|
| Entities | `Page`, `Panel`, `App`, `Char`, `Text`, `Tail` |
| Scalars | `Int`, `Str`, `Bool3` (true/false/unknown), `Pos`, `Span` (contiguous local pages; coerces to `Seq[Page]`), `Dir` (left/right/above/below), `Cmp` (more/fewer/equal), `Tri` (yes/no/cannot_determine) |
| Collections | `Set[T]`, `Seq[T]` (sorted by Pos, ties broken by ID), `Map[K, V]` |
| Functions | `T → U`, allowed only as lambda arguments to operations |
| Results | `Res[T]` (section 5.4) |

### 5.3 Syntax

**Surface form** (docs, prompts, human reading):

```
next_app(speaker_char(quote("We're leaving now", on=page(3))), after=page(3))
```

**Canonical S-expression** (used for hashing and dedup):

- keyword arguments sorted;
- arguments of commutative operations sorted;
- literals normalized.

```
(next_app :after (page 3) (speaker_char (quote :on (page 3) "we're leaving now")))
```

**JSON AST** (storage):

```json
{"op": "next_app",
 "args": [{"op": "speaker_char",
           "args": [{"op": "quote", "args": ["we're leaving now"], "kw": {"on": {"op": "page", "args": [3]}}}]}],
 "kw": {"after": {"op": "page", "args": [3]}}}
```

**Grammar (EBNF)**

```
program  := expr
expr     := literal | var | call | let | lambda
call     := OP "(" [arg ("," arg)*] ")"
arg      := expr | NAME "=" expr
let      := "let" NAME "=" expr ("," NAME "=" expr)* "in" expr
lambda   := "\" NAME "." expr          (rendered as λx. expr in docs)
literal  := INT | STRING | "true" | "false" | ENUM
var      := NAME
```

- Programs are type-checked statically before execution.
- Unknown operations and type mismatches are rejected.

### 5.4 Semantics

`⟦e⟧(W, S) → Res{value, status, exact, proof}` for world W and scope S.

**Status**

| Status | When |
|---|---|
| `OK` | evaluation succeeded |
| `EMPTY` | `the`, `first` or `nth` applied to an empty set |
| `AMBIGUOUS` | `the` gets more than one element; `argmax` tie within the margin; spatial tie |
| `UNKNOWN` | a needed coverage certificate is missing; an identity link is unresolved; an evidence page is unannotated |
| `ERROR` | type or runtime error (a bug) |

**Propagation.** A non-OK child makes its parent non-OK, unless the operation absorbs it under Kleene
logic (e.g. `or(true, unknown) = true`).

**Logic.** Kleene three-valued `and`, `or`, `not` (Appendix B). For a set S:

- `exists(S, φ)` is true if φ is true for some element. It is false only if φ is false for all
  elements **and** S is closed. Otherwise unknown.
- `forall` is the dual.

**Monotonicity classes**

| Class | Operations | Requirement |
|---|---|---|
| Monotone | `exists`, `at_least`, `present` (true direction), membership, `union`, navigation along existing facts | safe in an open world |
| Non-monotone | `not`, `none`, `forall`, `count` (exact), `argmax`/`argmin`, `first`/`last`/`next`/`prev`/`nth`, `the` over sets, `diff` (set), `mode` | need closed coverage over their whole range |

**Exactness.** `Res.exact = true` only if every range is closed. A program whose final result is not
exact is rejected, unless its answer type is an at-least form ("at least 4 pages?").

**Definite description (iota).** `the(S)` is OK if and only if |S| = 1 **and** S is exact. A
description is unique only if no unannotated element could also match.

**Determinism.** Every operation is deterministic. Ties are handled only as each operation specifies.
Randomness exists only in generators, never in the interpreter.

### 5.5 Operator library v1

Hop weights are listed in Appendix B. **NM** marks non-monotone operations.

#### A. Anchors and scope

| Operation | Signature | Semantics |
|---|---|---|
| `ctx()` | → Span | all context pages |
| `page(i)` | Int → Page | i-th context page |
| `pages(i, j)` | Int, Int → Span | pages i..j inclusive |
| `char(name)` | Str → Char | name or alias must resolve uniquely to a non-generic character with link confidence ≥ θ_id |
| `quote(s, on=)` | Str, Page/Span → Text | fuzzy match against consensus OCR. Must be unique in the context, with normalized edit distance ≥ 0.3 to every other text **[default]**. OCR trust ≥ V. |
| `chars(span)` | → Set[Char] | characters present in the span |
| `apps(span)`, `texts(span)`, `lines(span)` | → Seq[...] | items in the span, in reading order |
| `panels(page)` | → Seq[Panel] | panels of a page |

#### B. Navigation

| Operation | Signature | Semantics |
|---|---|---|
| `char_of(a)` | App → Char | via `is_char` |
| `apps_of(c, span)` | Char, Span → Seq[App] | the character's appearances |
| `page_of(x)`, `panel_of(x)` | → Page / Panel | containing page or panel |
| `speaker(t)` | Text → App | via `spoken_by` |
| `speaker_char(t)` | Text → Char | `char_of(speaker(t))` |
| `lines_of(c, span)` | → Seq[Text] | lines spoken by c |
| `chars_on(x)` | Page/Panel → Set[Char] | characters present |
| `pages_with(c, span)` | → Seq[Page] | pages where c is present |
| `pages_speaking(c, span)` | → Seq[Page] | pages where c speaks |
| `mentions_of(c, span)` | → Seq[Text] | texts mentioning c's name or alias |
| `mentioned_in(t)` | Text → Set[Char] | characters named in t |
| `co_present(c, unit, span)` | → Set[Char] | characters sharing a page or panel with c |

#### C. Predicates (return Bool3)

| Operation | Semantics |
|---|---|
| `present(c, p)` | c drawn on page p (false needs `char_boxes` closed on p) |
| `speaks_on(c, p)` | c has a line on page p (false needs `speaker_links` closed) |
| `silent_on(c, p)` | `present ∧ ¬speaks_on` |
| `together(c1, c2, unit)` | both present in the same page or panel |
| `offpanel_line(t)` | the speaker's appearance is not in t's panel (panel trust) |
| `is_named(c)` | c is a non-generic named character |
| `eq`, `neq`, `in(x, S)` | equality and membership |

#### D. Order (reading order)

| Operation | Semantics |
|---|---|
| `first(S)`, `last(S)`, `nth(S, k)` | by Pos (NM) |
| `next(x, S)`, `prev(x, S)` | neighbour in S by Pos (NM) |
| `rank(x, S)` | 1-based position (NM) |
| `precedes(x, y)` | Bool3, by Pos |
| `span_before(x, within=)`, `span_after(x, within=)` | **page-granular** spans strictly before or after x's page (the anchor page is excluded) |
| `between(x, y)` | pages strictly between |
| `first_app(c, span)`, `last_app(c, span)` | first or last appearance (NM) |
| `next_app(c, after=)` | first appearance on a page after the given page or Pos (NM; needs closure on intervening pages) |
| `gap(p1, p2)` | number of pages strictly between |
| `longest_streak(c, span)` | longest run of consecutive pages with c present (NM) |
| `sort_by(S, λx.e)` | stable sort by key |

#### E. Discourse

| Operation | Semantics |
|---|---|
| `next_line(t)`, `prev_line(t)` | adjacent line in reading order (NM) |
| `next_other_speaker(t)` | speaker of the first later line spoken by a **different** character. `UNKNOWN` if any intervening line lacks a speaker link or a resolved identity. |
| `turns(span)` | Seq[Turn]: maximal runs of consecutive lines by the same character. A Turn has a speaker, lines and pages. |
| `exchanges(c1, c2, span)` | number of adjacent line pairs alternating c1↔c2 |
| `first_line(c, span)`, `nth_line(c, k, span)` | NM |
| `line_count(c, span)` | exact count (NM) |
| `first_mention(c, span)` | first text mentioning c (NM) |

v1 deliberately has **no "talks to" or addressee operation**: recipients are not annotated.

#### F. Spatial (same panel only)

| Operation | Semantics |
|---|---|
| `left_of`, `right_of`, `above`, `below`, `overlaps`, `larger` | Bool3 with margins (section 4.8) |
| `leftmost(S)`, `rightmost(S)`, `topmost(S)`, `largest(S)` | App; `AMBIGUOUS` if the runner-up is within the margin |
| `direction(a, b)` | Dir of b relative to a |
| `nearest_to_text(t)` | App closest to the balloon (for proximity-trap questions) |

#### G. Sets and logic

`filter(S, λx.φ)`, `map(S, λx.e)`, `union`, `intersect`, `diff` (NM), `distinct`, `the(S)` (NM),
`exists`, `forall` (NM), `none` (NM), `and`, `or`, `not` (NM).

#### H. Aggregation and comparison

| Operation | Semantics |
|---|---|
| `count(S)` | exact count (NM) |
| `at_least(S, n)` | monotone; open-world safe |
| `argmax(S, λx.e)`, `argmin` | NM. Margin **[default]**: winner − runner-up ≥ max(2, 0.25 × winner), otherwise `AMBIGUOUS`. |
| `max`, `min`, `sum`, `mode` | NM |
| `group_count(S, λx.key)` | Map; NM |
| `top_k(S, λx.e, k)` | NM, with the margin applied at the k/k+1 boundary |
| `compare(x, y)` | Cmp (more/fewer/equal) |
| `minus(x, y)` | Int difference |

#### I. World edits (counterfactual)

`with_edit(edit, e)` evaluates e in W′ = apply(edit, W). Available edits:

| Edit | Effect |
|---|---|
| `drop_pages(span)` | remove those pages |
| `keep_pages(span)` | keep only those pages |
| `drop_char(c)` | remove c's appearances and lines |
| `drop_lines(c)` | remove c's lines only |
| `reassign(t, c)` | attribute line t to c |

- Edits are syntactic transforms on facts and certificates. They are recorded in the proof.
- The edit must be stated explicitly in the question.
- The generator prefers edits that change the answer. "Trivial counterfactuals" (same answer as the
  real world) are flagged and capped.

#### J. Scope and determinability

`determinable(e, given=Span)` returns `Tri` (or a value of e's type plus `CANNOT_DETERMINE`):

- If e is **monotone-certain** from the given pages alone (e.g. existence already shown, an at-least
  threshold already reached), the result is e's value.
- If e is non-monotone and its range extends beyond the given pages, the result is
  `cannot_determine`.
- `cannot_determine` comes **only from the scope of the shown pages**, never from annotation gaps.
  Annotation gaps cause rejection.
- Always pair such items with an answerable control item.

#### K. Binding

`let x = e1 in e2`, with several bindings allowed. Bound names appear in the proof.

### 5.6 Referring-expression sublanguage

Questions mention entities through **descriptors**. A descriptor is itself a CRL program D such that
`the(D) == target` across the **whole context**, not just the anchor page.

| Descriptor family | Example program | Weight | Trust |
|---|---|---|---|
| Name | `char("A")` | 0 | H/R |
| Quote | `speaker_char(quote("…"))` | 1 | V (OCR) |
| Position | `leftmost(apps_in(panel_at(page(4), "top-right")))` | 1 | panel trust |
| Relational | `next_other_speaker(first_line(char("A")))` | program weight | weakest step |
| Visual attribute | "the man in the hat" | — | extension only |

Rules:

- A descriptor must not reveal the answer.
- It must be unique and pass robustness checks (section 12).
- It counts toward the item's hops.
- **Descriptor depth** is a generator setting: complexity can be placed inside references, e.g. "the
  character who speaks right after the boy who first mentions A".
- Panel position words ("top-right panel of page 4") come from geometry, and only when unambiguous: no
  other panel's center within the margin of that region. Avoid ordinal panel references ("the 3rd
  panel") unless order confidence is high.
- Quotes need at least 3 words **[default]**, must be unique in the context, and must not contain the
  answer.

### 5.7 Extensibility

A registry entry declares:

- name and signature;
- origin and derivation rule;
- monotonicity and coverage family;
- hop weight;
- gloss templates;
- tests.

Registering a relation automatically generates navigation (`rel(x)`), inverse (`inv_rel(y)`) and
predicate (`has_rel(x, y)`) operations. Any change to semantics bumps `crl_version`. Items record the
version they were built with.

---

## 6. Proofs and traces

### 6.1 Proof tree

Each node records:

```json
{"nid": 3,
 "op": "speaker_char",
 "args": "(quote :on (page 3) \"we're leaving now\")",
 "value": "chr:ch:naruto/002/link-v1/hinata",
 "status": "OK", "exact": true,
 "facts": ["f:9c1e…", "f:41aa…"], "certificates": [],
 "children": [2], "pages": [3], "trust": "V", "confidence": 0.97}
```

Full example for *"The character who says 'We're leaving now' on page 3: on which later page does she
next appear?"*:

```json
{
  "program": "(page_of (next_app :after (page 3) (speaker_char (quote :on (page 3) \"we're leaving now\"))))",
  "steps": [
    {"op": "quote", "out": "txt:p3/t2", "evidence": [{"tier": "V", "src": "ocr/consensus/p3_t2"}]},
    {"op": "speaker", "out": "app:p3/c1", "evidence": [{"tier": "H", "src": "popmanga/p3/text_char_links/2"}]},
    {"op": "char_of", "out": "chr:…/hinata", "evidence": [{"tier": "H", "derivation": "R", "src": "identity_link/v1/p3_c1"}]},
    {"op": "next_app", "out": "app:p7/c4",
     "evidence": [{"tier": "H", "src": "popmanga/p7/char_boxes/4"},
                  {"tier": "H", "derivation": "R", "src": "identity_link/v1/p7_c4"}],
     "certificates": ["cov:p4/char_boxes", "cov:p5/char_boxes", "cov:p6/char_boxes"]},
    {"op": "page_of", "out": 7}
  ],
  "answer": 7,
  "key_support_pages": [3, 7],
  "range_pages": [3, 4, 5, 6, 7],
  "semantic_hops": 3,
  "page_span": 4,
  "trust_min": "V"
}
```

The certificates for pages 4–6 are what prove the character is **not** on those pages.

### 6.2 Support

- **Support set:** all facts and certificates in the proof.
- **Key support pages:** pages of the positive facts needed for the answer.
- **Range pages:** all pages that a non-monotone operation ranged over. For aggregation, negation and
  quantifiers, the whole range is required.
- **Minimal positive support:** the smallest subset of positive facts sufficient for the answer.
  Shown to reviewers as the "evidence trail".

### 6.3 Trust of an item

Item trust = minimum trust over its support. Per-step trust is kept so results can be reported by
tier, e.g. "all-human evidence" versus "includes OCR".

### 6.4 Independent proof checker

A **separate, small module**, not calling the interpreter, re-verifies each proof step against the
fact and certificate tables using its own implementation of each operation's semantics.

- An item is accepted only if the checker passes.
- Any disagreement between the checker and the interpreter is a bug and blocks the stage.
- This is the trust anchor of the benchmark.

### 6.5 Human-readable explanation

Each proof node renders a template sentence plus image crops, for example:

> Page 3: the line "We're leaving now" (text box t2) is linked by a human annotation to character box
> c1 → c1 is Hinata (identity link, confidence 0.97) → Hinata is not drawn on pages 4–6 (pages fully
> annotated) → she is drawn on page 7 (box c4).

Reviewers see only this trail and the crops, not the whole chapter.

### 6.6 Step-level sub-questions

Each internal proof node whose value can be named (a character, page, count) can be turned into a
sub-question, using descriptors of its inputs. This shows whether a model fails at perception (wrong
step 1) or at combining steps (all steps right, final answer wrong).

---

## 7. Complexity and difficulty

### 7.1 Raw dimensions (recorded for every item)

- `n_ops`, `depth`, `semantic_hops` (weighted, Appendix B).
- `n_relation_families`: identity, discourse, presence, order, spatial, mention, aggregation,
  quantifier, edit, determinability.
- `n_entities` (referenced or eliminated) and `n_constraints`.
- `page_span` (max − min support page), `n_key_support_pages`, `n_range_pages`, `context_pages`.
- `evidence_position`: where the key evidence sits in the context (start, middle or end).
- `aggregation_cardinality`: how many elements are aggregated.
- `candidate_pool`, plus the elimination profile per clause.
- `distractor_density`: number of candidates satisfying all but one constraint.
- `has_negation`, `quantifier_depth`, `ordinal_depth`, `descriptor_depth`.
- `has_edit` (counterfactual) and `has_determinability`.
- `modality`: whether the key facts are visual-only (box, identity) or text-derivable (OCR, mentions).
- `trust_min`, question length in tokens, answer type, format.

### 7.2 Levels

| Level | Definition |
|---|---|
| L1 | one relation, one page |
| L2 | 2–3 hops or a single aggregation; ≤ 3 key support pages |
| L3 | 3–4 hops; ≥ 2 relation families; page span ≥ 5 or aggregation over ≥ 5 pages |
| L4 | ≥ 5 hops or nested aggregation/comparison; ≥ 3 families; page span ≥ 10 or whole chapter; ≥ 1 non-monotone operation |
| L5 | quantifiers or negation over the chapter; comparison of aggregates; descriptor depth ≥ 2; distractor density ≥ 3 |
| L6 | counterfactual edits; determinability; dependent multi-part questions; constraint puzzles with ≥ 5 necessary clauses; summary verification |

An optional scalar difficulty score can be computed from the raw dimensions with configurable
weights. Always report the raw dimensions as well.

---

## 8. Program generation

### 8.1 Pipeline

chapter graph → candidate programs (several generators) → execute → acceptance gates (section 11) →
robustness check (section 12) → verbalize (section 10) → round-trip check → item.

### 8.2 Forward typed enumeration

- Start from anchors.
- Apply type-compatible operations up to depth d, with beam search and shape weights.
- Prune:
  - empty or non-OK results;
  - trivial answers (the answer equals an input entity, or is constant across chapters);
  - answers equal to the chapter's most frequent character beyond the cap.

**Shape library**

- `Chain(k)`, `Intersect(k)`, `Compare(agg, agg)`, `Argmax(derived set)`.
- `Quantified(∀/∃/none)`, `Ordinal(nth of filtered sequence)`, `Window(between two events)`.
- `SpatialAt(event)`, `MentionVsPresence`, `Counterfactual(edit, inner)`, `Determinability(scope, inner)`.
- `MultiPart(dependent)`, `Puzzle(accretion)`, `SummaryVerify(k statements)`.

### 8.3 Backward constraint accretion (target first)

This produces the strongest multi-constraint questions:

```
choose target t (balanced across characters, pages, chapters)
C ← all candidates of t's type in context
clauses ← []
while |C| > 1 or len(clauses) < k_min:
    P ← unary predicates true of t (from templates over the graph)
    pick p in P maximizing:
        eliminated(C, p)
        × distance of p's evidence from existing clauses' pages
        × relation-family novelty
        × trust
    clauses.append(p); C ← {x ∈ C : p(x) = true}
minimize: drop any clause whose removal keeps |C| = 1  → every clause is necessary
if len(clauses) < k_min after minimization: continue accretion with new families
```

Store the elimination profile: which clause removed which candidates. These near-miss candidates
become multiple-choice distractors.

### 8.4 Answer-first for aggregates

Choose a target answer distribution first: uniform over count values, page positions spread across
the chapter, non-protagonist answers. Then search for programs whose answer matches. This removes
answer priors.

### 8.5 Counterfactual generator

Take an accepted base program, search for edits that change its answer, and keep the edit with the
clearest change (margins still apply in the edited world).

### 8.6 Summary-verification generator

1. Pick k true statements (programs returning true) whose support pages are spread across the chapter.
2. Create m corrupted versions by minimal perturbation: swap an entity with its nearest distractor,
   change a count by ±1, swap an order.
3. Verify each corrupted statement is **false by execution**, uses entities that exist in the chapter,
   and is not trivially false.
4. Answer = indices of the false sentences.

### 8.7 Optional LLM-guided proposals

Qwen gets a compact, ID-free graph summary and proposes "interesting" programs in CRL. They are
parsed, type-checked and executed, and they **never bypass the gates**. Their purpose is narrative
interest and diversity.

### 8.8 Balancing and coverage quotas

- Quotas per chapter, split (seen/unseen), level, relation family, format, answer type.
- GEN-1 acceptance quotas (decision 2026-10-27): at most ~30% of character-name answers may be the chapter's most frequent characters; two-option answers (including yes/no and left/right) have a ~5% share. Enforce while constructing the accepted generation set; EXP-1 rechecks and runs baselines. Define the frequent-character set, ties and quota denominators explicitly in GEN-1 configuration and its manifest.
- Before GEN-1, every character name used in a question or answer must have verified readability evidence somewhere in the full chapter context. CKG-2 supplies this from aligned OCR agreement or individual verification; ambiguous aliases and generic labels do not establish name visibility. Raw OCR matches are candidates, not automatic verification.
- Support page position: spread across the start, middle and end of the context.
- Booleans 45–55% true; count values spread.

### 8.9 Determinism

Seeds are derived from (chapter_id, generator, generator_version, seed). Shards are idempotent and
resumable, with atomic writes.

---

## 9. Question formats and lengths

| ID | Format | Example form |
|---|---|---|
| F1 | Direct short | "Who speaks right after A's first line?" |
| F2 | Explicit chain | "Find X. Then find Y. Which…?" |
| F3 | Constraint puzzle | a list of 4–10 clauses identifying one entity |
| F4 | Dependent multi-part | (a), (b), (c), each using the previous answer |
| F5 | Verification | one true/false statement, or a multi-sentence summary where the model must find the false sentence(s) |
| F6 | Multiple choice | distractors from near-miss candidates; the reason for each distractor is stored |
| F7 | Ordering | sort quotes, pages or appearances by reading order |
| F8 | Counterfactual | "Suppose…, then who…?" |
| F9 | Determinability | "Based only on the pages shown, can you determine…? Answer yes, no, or cannot be determined." Always paired with a control. |
| F10 | Set answer | "List all characters who…" |
| F11 | Noise-augmented | the question includes true but irrelevant statements (verified true and verified unnecessary) |
| F12 | Evidence-required | answer plus the page numbers supporting it, scored separately |

**Length classes**

| Class | Length |
|---|---|
| S | ≤ 25 words |
| M | 26–80 words |
| L | 81–250 words |
| XL | > 250 words (multi-part, summaries) |

Length is controlled **independently** of difficulty. Deliberately produce long-but-easy and
short-but-hard items so length doesn't predict difficulty.

**Clause alignment.** Each clause's text span maps to the proof nodes it expresses. Stored privately.

---

## 10. Verbalization

### 10.1 Deterministic gloss

Every operation has a gloss template. A program renders into canonical, robotic English. The gloss is
always generated and can serve as a template-only track.

### 10.2 LLM paraphrase

Qwen3-VL-32B on MN5, text-only; no images are needed for phrasing.

Input: gloss, clause list, descriptor texts, target style and length.

Output JSON: `{question, clause_spans}`.

Rules:

- Keep every clause; add none.
- No internal IDs, trust labels or hints toward the answer.
- "Page k" means the k-th provided image.
- Use reading-order wording only: no "happens before", no "talks to".
- Use the requested length class.

### 10.3 Round-trip check

1. An **independent parse** turns the paraphrase back into CRL, using a different prompt and ideally a
   different model.
2. Canonicalize and execute it.
3. Accept only if:
   - it gives the same answer;
   - the key support pages match;
   - every clause is matched (structural comparison of canonical forms where possible).

### 10.4 Language-level uniqueness

Sample 3 parses **[default]**. All must agree, which shows the wording itself has one reading.

### 10.5 Prompt to the evaluated model

Page images labelled "Page 1..N", the question, and an answer-format instruction per answer type. No
graph, program or IDs, except in the diagnostic tracks of section 15.

---

## 11. Acceptance gates (in order)

| Gate | Check |
|---|---|
| G1 | type check and static policy (allowed operations; minimum trust per family) |
| G2 | execution status OK and exact (or an at-least answer type) |
| G3 | uniqueness: `the`, `argmax` margins, well-defined set answers |
| G4 | independent proof checker passes |
| G5 | coverage: every non-monotone range is certified |
| G6 | necessity: removing any clause changes the answer or makes it non-unique; every intermediate value is non-trivial |
| G7 | context: support ⊆ context. Page ablation: removing any key support page gives UNKNOWN or a different answer (deliberate redundancy is recorded) |
| G8 | graph-side shortcut detectors (below) |
| G9 | robustness across possible worlds (section 12) |
| G10 | verbalization round-trip and language-level uniqueness |
| G11 | dedup: identical canonical program means duplicate; items with the same (answer, support set) are capped |
| G12 | human review, stratified; mandatory for L5–L6, counterfactual, determinability and any item with A/M trust |

**G8 shortcut detectors**

- The answer equals the chapter's most frequent character (prior guess).
- The answer is derivable from the anchor page alone.
- The answer is derivable from text-only facts (OCR, mentions) when the item is meant to be visual.
- Only one support page for an item at L2 or above.
- The answer appears verbatim in the question.

Pass/fail is recorded for every gate, and yields are reported per generator, shape and level.

---

## 12. Robustness: possible worlds

Annotation noise becomes a measurable filter rather than hidden label noise. Perturbation families:

| ID | Perturbation |
|---|---|
| W1 | identity: linker thresholds {strict, default, loose}; top-2 alternative links for uncertain appearances |
| W2 | reading order: swap adjacent panels or texts with order confidence < τ |
| W3 | panel membership: alternative assignments for ambiguous `in_panel` |
| W4 | OCR: each model's own transcript instead of the consensus; the quote must still resolve uniquely |
| W5 | single-fact deletion: delete each A/M fact in the support, one at a time |
| W6 | spatial margins: δ × {0.5, 2} |

- **Accept** only if the answer is identical in every generated world **[default: strict]**.
- Store `robustness = fraction of worlds with the same answer`.
- Cap at 64 worlds per item, sampling when there are more **[default]**.

---

## 13. Hard but fair

### 13.1 Levers that target known weaknesses of current VLMs

- **Long multi-image context:** whole chapters (20–40 pages), evidence far apart, key evidence in the
  middle ("lost in the middle").
- **Cross-page identity** under changing angle, chibi style, partial or occluded views.
- **Counting** across many pages, with exact answers and margins.
- **Nested ordinals:** "the second line after the third time…".
- **Negation and universal quantifiers**, backed by coverage certificates.
- **Proximity trap:** the speaker is *not* the character nearest the balloon (choose items where
  `nearest_to_text ≠ speaker`).
- **Off-panel speakers** (once panels are audited).
- **Mention vs presence:** named but not drawn yet, or drawn but never named.
- **Anti-prior answers:** not the protagonist, not the first or last page, uncommon counts.
- **Look-alike distractors:** similar outfits, the same page-local cluster confused.
- **Counterfactual edits.**
- **Determinability**, with answerable controls.
- **Noise clauses** inside the question.
- **Dependent multi-part questions**, where errors propagate.
- **Contrast pairs:** the same question with one clause or page changed and a different answer. These
  detect guessing and give a consistency metric.

### 13.2 Fairness constraints (non-negotiable)

- **Human solvability:** pilot study. Each L4+ item is solved independently by ≥ 2 humans within a time
  budget (≤ 10 min for L4–L5, ≤ 20 min for L6 **[default]**). Keep items where humans agree; report
  human accuracy as the ceiling.
- **No outside knowledge:** the question-only (blind) baseline must be near chance. Run a probe for
  series knowledge, since popular titles such as Naruto are well known to models.
- **No annotation-artifact answers:** guaranteed by certificates, robustness worlds and the proof
  checker.

### 13.3 Adversarial filtering (optional, and transparent)

- An optional **Hard** split keeps items failed by ≥ k of N diverse strong models.
- The **Natural** split stays unfiltered.
- Never filter with the model being reported as the main result, and publish the list of filter
  models.
- There is no guarantee that every state-of-the-art model fails. The aim is **low model accuracy with
  high human accuracy**, measured and reported.

---

## 14. Answer types and scoring

Graph items are scored deterministically, with no LLM judge.

| Type | Canonical form | Normalization | Scoring |
|---|---|---|---|
| `char` | canonical name plus aliases (annotation names, word-order variants, honorific-stripped) | NFKC, casefold, strip honorifics and punctuation | match against any alias |
| `page` | local integer | — | exact |
| `int` | integer | — | exact (tolerance 0 by default) |
| `bool` | yes/no | — | exact |
| `tri` | yes/no/cannot_determine | — | exact |
| `dir` / `cmp` | enum | — | exact |
| `quote` | prefer multiple choice; free text allowed | NFKC, whitespace | normalized CER ≤ threshold |
| `set[char]` | set of canonical names | as `char` | exact set, plus F1 |
| `seq` | ordered list | as element type | exact order, plus Kendall tau |
| `choice` | letter | — | exact |
| `multi` | dict of parts | per part | per-part score, plus all-correct |
| `sentence_ids` | set of indices | — | exact set, plus F1 |
| evidence pages (F12) | set of pages | — | precision and recall against key support pages |

---

## 15. Evaluation protocols the graph enables

| Track | Model input | What it isolates |
|---|---|---|
| T-img (main) | images + question | full task |
| T-img+graph | images + serialized, ID-free fact list | perception vs reasoning |
| T-graph | serialized facts only | pure reasoning |
| T-text | OCR transcripts + question | how much the text shortcut gives |
| T-blind | question only | priors and series knowledge |
| Step-level | sub-questions from proof nodes | where chains break |
| Consistency | contrast pairs, multi-part | guessing and coherence |

Also report **scaling curves**: accuracy versus hops, page span, context length, distractor density,
evidence position and trust tier.

---

## 16. Records and storage

Layout under the user's big-files root, outside Git:

```
<root>/comics_qa/graph/<graph_version>/<chapter_id>/
    nodes.parquet  facts.parquet  coverage.parquet  manifest.json
<root>/comics_qa/programs/<generator_version>/<chapter_id>/shard-*.jsonl
<root>/comics_qa/items/<item_version>/{private,public}/shard-*.jsonl
<root>/comics_qa/reports/<item_version>/
```

**Versions**

- `crl_version` (e.g. `crl-0.1`).
- `graph_version` = hash(source annotation hashes, builder code hash, config hash).
- `policy_version`, `generator_version`.
- `verbalizer_version` (model id, prompt hash, decoding settings).

**Item ID** = hash(canonical program, graph_version, context spec, format, verbalization seed).

**Private item (sketch)**

```json
{
  "item_id": "q:…",
  "chapter_id": "ch:…", "split": "unseen",
  "context": {"local_pages": [1, 2, "…", 24], "orig_page_ids": ["pg:…"]},
  "program": "(…canonical S-expression…)",
  "program_ast": {"op": "…"},
  "proof": {"nodes": ["…"], "support_facts": ["f:…"], "certificates": ["cov:…"]},
  "answer": {"type": "page", "value": 7, "aliases": []},
  "dims": {"semantic_hops": 3, "page_span": 4, "level": "L3", "trust_min": "V", "…": "…"},
  "gates": {"G1": "pass", "…": "…", "G12": "pending"},
  "robustness": 1.0,
  "verbalization": {"gloss": "…", "question": "…", "clause_spans": ["…"],
                    "model": "…", "prompt_sha256": "…"},
  "distractors": [{"value": "…", "reason": "fails clause 3 only"}],
  "review": {"status": "pending", "reviewers": []},
  "versions": {"crl": "0.1", "graph": "…", "policy": "…", "generator": "…"}
}
```

**Public item**

```json
{"item_id": "q:…", "images": ["…page refs in order…"], "question": "…",
 "answer_type": "page", "answer_format_instruction": "…",
 "choices": null}
```

Public items contain no program, proof, IDs or trust labels. Answers are released according to the
benchmark's split policy.

---

## 17. Policy configuration (example)

```yaml
crl_version: "0.1"
policy_version: "p1"
trust_order: [H, V, A, M]
min_trust:
  answer_critical: A
  quote_anchor: V
  exact_count: H            # presence/line counts: human boxes + rule-derived identity
identity:
  min_link_conf: 0.9
  generic_names_file: "<path>"   # [verify] reuse evaluation adapter list
coverage:
  allow_closed_audited: true
  audit_min_recall: 0.98
geometry:
  in_panel_min_frac: 0.6
  in_panel_ambiguous_frac: 0.3
  spatial_margin_frac: 0.05
  overlap_iou: 0.1
  larger_ratio: 1.5
aggregation:
  argmax_min_abs_margin: 2
  argmax_min_rel_margin: 0.25
quote:
  min_words: 3
  min_separation_ned: 0.3
robustness:
  max_worlds: 64
  require_invariance: 1.0
gates:
  necessity: true
  page_ablation: true
  round_trip_parses: 3
balance:
  max_answer_share_per_char: 0.25
  bool_true_share: [0.45, 0.55]
human:
  time_budget_min: {L4: 10, L5: 10, L6: 20}
  min_solvers: 2
```

---

## 18. Tests (CPU, synthetic)

- **Operation unit tests:** hand-built synthetic chapters with known answers, including `UNKNOWN`,
  `EMPTY` and `AMBIGUOUS` cases for every operation.
- **Logic:** Kleene truth tables; `the` with 0, 1 and 2 matches; argmax margins; spatial ties.
- **Coverage:** an open or absent page inside a range gives `UNKNOWN`; an unannotated page breaks
  `next_app`.
- **Determinism:** same seed gives the same programs; shards are idempotent; reruns are stable.
- **Metamorphic:**
  - consistently renaming characters keeps structure-level answers the same;
  - adding pages outside the scope changes nothing;
  - reversing page order swaps first and last;
  - deleting a support fact changes the answer or gives UNKNOWN;
  - splitting one character's identity makes `the` ambiguous.
- **Differential:** proof checker versus interpreter on fuzzed random programs.
- **Round trip:** fixed glosses parse back to the same canonical program.
- **Leakage:** public text contains no `app:`, `chr:`, `txt:`, `pg:`, tier names or program syntax
  (regex check).
- **Sources:** no source file is modified (checksums before and after).

---

## 19. Implementation stages

Each stage: plan → approval → implement → CPU tests → commands for the user.

| Stage | Content |
|---|---|
| CKG-0 | **Audit and review**: full audit already run; review findings, resolve integrity issues with traceable decisions, retain open/absent coverage where needed. Rerun only if inputs/audit logic change. See `docs/STATUS.md` for artifacts. |
| CKG-1 | Graph builder v1: page-level H facts, IDs, coverage certificates, manifests, tests. Consume CKG-0 review coverage and explicit generic-identity overrides. Can integrate existing exact-name core identities as `is_char` here. |
| CKG-2 | Finish any remaining identity integration; **verify chapter name visibility before GEN-1**, using OCR agreement or individual verification. Keep exact-name identities and exclude ambiguous aliases; no fuzzy linker. |
| CRL-1 | Language core: types, parser (surface, S-expression, JSON), type checker, interpreter, three-valued semantics, proofs. Operation families A–E and G–H at page level. |
| CRL-2 | Independent proof checker plus differential tests |
| GEN-1 | Generators: forward enumeration, constraint accretion, answer-first aggregates. Gates G1–G9 and possible worlds, using glosses only. Enforce chapter name readability and generation-time guessability quotas (§8.8). |
| VERB-1 | Verbalization and round trip on MN5 via the spec 08 interface. Dry run with glosses first. |
| CKG-3 | Panel, spatial, inner reading order and richer mention operations, after the panel audit and OCR. Basic name visibility is already required before GEN-1. |
| GEN-2 | Counterfactual edits, determinability, multi-part, summary verification, noise clauses, contrast pairs |
| EXP-1 | Export to the spec 09 contract; reports for yield, coverage, dimensions and trust mix; recheck generation quotas and run random/frequency/text-only baselines |

Page-order generation needs no graph and may be implemented as an independent side task or alongside GEN-1.

---

## 20. Non-goals, risks and open decisions

**Non-goals in v1:** story time, addressee/recipient, caption-derived events as answers, depth,
cross-chapter reasoning, LLM judging.

**Risks**

- Identity-linking quality (the main bottleneck).
- Unknown completeness of human character boxes.
- Speaker-link completeness.
- OCR errors breaking quote anchors.
- Unverified text-class semantics.
- Reading-order errors.
- Series knowledge in models.
- Paraphrase drift.
- Low yield under strict gates.
- Human review cost.

**Open decisions for the user**

1. Which tiers may support answer-critical steps (A allowed, or only H/V)?
2. Coverage audit design and the recall threshold for `closed_audited`.
3. Context sizes: whole chapter vs windows, and the evidence-span buckets.
4. Target item counts per chapter and per level.
5. Whether a Hard (adversarially filtered) split is wanted, and which models filter it.
6. Human review budget and solver protocol.
7. Whether to release the T-graph and T-img+graph diagnostic tracks publicly.

---

## Appendix A: Example bank

A, B and C are named, non-generic characters; "…" stands for a real quote. All page numbers are local.

**E1 · L1 · F1 · S**
Q: Who says "I'll handle the rest" on page 2?
`speaker_char(quote("I'll handle the rest", on=page(2)))` → char. Trust V (OCR) + H.

**E2 · L2 · F1 · S**
Q: On how many of the pages shown does A appear?
`count(pages_with(char("A"), ctx()))` → int. Needs `char_boxes` closed on all context pages.

**E3 · L2 · F1 · S**
Q: After A's first line, which different character is the next to speak?
`next_other_speaker(first_line(char("A"), ctx()))` → char.

**E4 · L3 · F2 · M**
Q: Find the character who says "We're leaving now" on page 3. On which later page does that character
next appear?
`page_of(next_app(speaker_char(quote("We're leaving now", on=page(3))), after=page(3)))` → page.
Proof in section 6.1.

**E5 · L3 · F1 · S** (mention vs presence)
Q: Which character is mentioned by name in dialogue before first being drawn?
`the(filter(chars(ctx()), λc. precedes(first_mention(c, ctx()), first_app(c, ctx()))))` → char.
Trust V (OCR mentions).

**E6 · L4 · F1 · M** (argmax with margin)
Q: Of the characters drawn on page 2, which one appears on the most of the later pages?
`argmax(chars_on(page(2)), λc. count(pages_with(c, span_after(page(2), within=ctx()))))` → char.

**E7 · L4 · F2 · M**
Q: Find the last page on which A and B are both drawn. On the pages after it, who speaks first?
```
let p = last(filter(ctx(), λp. and(present(char("A"), p), present(char("B"), p))))
in speaker_char(first(lines(span_after(p, within=ctx()))))
```
→ char.

**E8 · L5 · F1 · M** (comparison of aggregates)
Q: Does A have more lines on the pages before B's first appearance, or on the pages after it?
```
let p = page_of(first_app(char("B"), ctx()))
in compare(line_count(char("A"), span_before(p, within=ctx())),
           line_count(char("A"), span_after(p, within=ctx())))
```
→ cmp, verbalized as before / after / equal.

**E9 · L5 · F1 · M** (universal quantifier)
Q: Other than A, which character is drawn on every page where A speaks?
`the(filter(chars(ctx()), λc. and(neq(c, char("A")), forall(pages_speaking(char("A"), ctx()), λp. present(c, p)))))`
→ char. Certificates needed for every page in A's speaking pages.

**E10 · L5 · F1 · M** (discourse + spatial)
Q: In the panel where B speaks for the first time, is B to the left or right of the character who spoke
the line just before?
```
let t = first_line(char("B"), ctx())
in direction(speaker(t), speaker(prev_line(t)))
```
→ dir. Rejected if the two appearances are not in the same panel.

**E11 · L6 · F8 · M** (counterfactual)
Q: Suppose every page on which A is drawn were removed. Who would then have the most lines?
`with_edit(drop_pages(pages_with(char("A"), ctx())), argmax(chars(ctx()), λc. line_count(c, ctx())))`
→ char. Kept only if the answer differs from the real-world argmax.

**E12 · L6 · F3 · L** (constraint puzzle, built by accretion)
Q: I am thinking of one character in these pages.
(1) They are drawn on at least three different pages.
(2) They never speak on a page where A is drawn.
(3) Right after their first line, the next different speaker is someone who is also drawn on page 12.
(4) Their last appearance comes on an earlier page than B's last appearance.
(5) They never appear in the same panel as C.
Who is it?
```
the(filter(chars(ctx()), λx.
  and(at_least(pages_with(x, ctx()), 3),
      none(pages_speaking(x, ctx()), λp. present(char("A"), p)),
      present(next_other_speaker(first_line(x, ctx())), page(12)),
      precedes(last_app(x, ctx()), last_app(char("B"), ctx())),
      not(together(x, char("C"), "panel")))))
```
→ char. Necessity is recorded for each of the 5 clauses, with its elimination profile.

**E13 · L6 · F5 · XL** (summary verification)
Q: Here are eight statements about these pages. Exactly one is false. Which one?
Each statement is the verbalization of a true program. One is corrupted by a minimal perturbation and
verified false by execution. → `sentence_ids` {4}.

**E14 · L6 · F9 · M** (determinability, with paired control)
Context: pages 1–12 of a longer chapter.
- Q: Based only on the pages shown, can you determine whether A appears on more pages of the whole
  chapter than B? → `cannot_determine` (non-monotone, the range extends beyond the shown pages).
- Control: Based only on the pages shown, does A appear on more of *these* pages than B? → yes/no.

**E15 · L4 · F4 · L** (dependent multi-part)
Q: (a) Who speaks first on page 5? (b) How many pages pass before that character speaks again?
(c) In the panel where that next line occurs, who is the leftmost character?
Each part is its own program; parts (b) and (c) bind the answer of the previous part. Scored per part
and all-correct.

**E16 · L3 · F11 · L** (noise-augmented)
E4 plus two true but irrelevant statements in the question (e.g. "B appears on page 9. A has several
lines on page 2."). Both are verified true and verified unnecessary by the necessity gate.

---

## Appendix B: Hop weights and logic tables

**Hop weights [default]**

| Operation kind | Weight |
|---|---|
| anchor (`page`, `char`, `ctx`) | 0 |
| structural lookup on one item (`page_of`, `panel_of`) | 0.5 |
| navigation to a different entity (`speaker`, `char_of`, `next_app`…) | 1 |
| order operation (`first`, `next`, `nth`) | 1 |
| each filter clause | 1 |
| negation | 1 |
| quantifier (`forall`, `exists`, `none`) | 2 |
| aggregation (`count`, `argmax`, `top_k`) | 2 |
| comparison of two aggregates | +1 |
| world edit | 3 |
| determinability | 2 |
| descriptor | weight of its own program |

**Kleene three-valued logic** (T true, F false, U unknown)

| a | b | a ∧ b | a ∨ b |
|---|---|---|---|
| T | T | T | T |
| T | U | U | T |
| T | F | F | T |
| U | U | U | U |
| U | F | F | U |
| F | F | F | F |

¬T = F, ¬F = T, ¬U = U.
