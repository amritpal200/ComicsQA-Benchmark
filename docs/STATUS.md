# Project status and to-do

Last updated: 2026-10-27 (CKG-1 implemented; 38 CKG tests passed; complete-chapter smoke and resume verified). Update this file whenever a stage finishes or the plan changes.

Current decision: depth maps are excluded from the benchmark (checked manually; not good enough).
Current stage: **CKG-1 implementation complete; full collection build pending user execution**. Run `bash scripts/build_ckg1.sh` → `evidence/ckg/v1/`. Next implementation stage: **CKG-2 name visibility**; exact-name identity integration is already included in CKG-1.

## How to update this file (all agents)
Two agents work in this repo at the same time; this file is the shared source of truth.
- Re-read the file just before editing it; change only the lines you need (no full rewrites).
- When a stage starts, finishes or is blocked, update its row in the plan table, with the date, output
  path and test result. Change the "Current stage" line and the "Last updated" line too.
- Write down a new decision under "Decisions to remember" with its date. Don't silently change
  someone else's entry; put disagreements under "Open questions".
- Check outputs on disk before marking something done. Long jobs are run by the user; give the
  command in the row instead of marking it done.

Paths: code in `/home/asingh/Comics/ComicsQA_Benchmark/Code` (git, GitHub amritpal200); data in
`/data/151-3/comics/ComicsQA_Benchmark/` (`PopManga_Test/` is the read-only source; `annotations/`; `core/`);
models in `/data/151-3/comics/models/`; caches in `/data/151-3/comics/.cache/`.
Working rules: the user runs every long job (in `screen`); I test on small samples and hand over the
exact commands. Ground truth and source data are never modified.

## Done
| Stage | Output | Notes |
|---|---|---|
| CKG-1 implementation (2026-10-27) | `scripts/build_ckg1.sh`; [contract/usage](../src/comics_qa/evidence/graph/README.md) | Typed chapter graphs, source/premise provenance, review overrides and coverage, current source/image hash checks, atomic/resumable chapter shards. 17 new CKG-1 tests; 38 total CKG tests passed. Full collection not run. |
| CKG-0 review (2026-10-27) | `reports/ckg0/review_v1/`; [decisions](notes/ckg0_review.md); `scripts/review_ckg0.sh` | Generated from the existing audit/core snapshot. Six identity errors resolved conditional on applying six overrides to three generic identities. 4,519 review warnings retained. 21 audit/review tests passed; input/code/output hashes verified. |
| CKG-0 audit implementation (2026-10-27) | `scripts/audit_ckg0.sh`; [documentation](../src/comics_qa/evidence/graph/README.md) | Read-only, stdlib CPU audit; synthetic tests and a bounded real-data smoke test. Full collection audit run 2026-10-27 (see below). |
| Depth visual preview (2026-10-27) | `ComicsDepth` command `preview` | Reproducible random sample (10 validation panels by default), original/depth comparisons, overview PNGs and HTML gallery. Two CPU tests passed with synthetic images and mocked inference; user runs trained-model inference. |
| Human GT export | `annotations/human/` (1,925 pages) | read-only copy; `text_char_matches` = [text, character] (verified) |
| MAGI v3 pass 1 | `annotations/magi3/` (2,022 pages, all complete) | panels, characters, texts, OCR, reading order |
| Core v1 (spec 01) | `core/v1/{chapters,pages,characters}.jsonl` | 50 chapters, stable IDs, reading order (MAGI v3 rules ported exactly), 314 named identities (269 on ≥2 pages, 112 in both chapters) |
| Docs and decisions | `docs/specs/00,02,05,07,09`, `docs/notes/imp.md` | source precedence (GT first), OCR stage, grounding stage, guessability rules |

## Finished runs (checked 2026-10-27)
| Job | Output | Result |
|---|---|---|
| CKG-1 bounded chapter smoke + completed-output resume (2026-10-27) | `/tmp/comicsqa-ckg1-death-note-c001-final/` | Death Note c001: all 47 pages (44 GT, 3 without), 1,560 nodes, 6,131 facts, 376 coverage records. Six overrides applied to three generic identities; missing-GT coverage and all artifact checksums verified. |
| Qwen3-VL-32B captions, prompt v4 | `annotations/qwen32B/` | 2,022 / 2,022 pages saved (379 min); permissions fixed to 644 |
| PaddleOCR-VL-1.6 OCR | `annotations/ocr_paddleocr_vl/` | 2,022 pages, all shards status 0 (21,079 texts read, incl. MAGI v3 boxes on pages without GT) |
| CKG-0 audit, full collection | `reports/ckg0/v1/` | run 2026-10-27 19:11; review `report.md` before CKG-1 |
| ComicsDepth training (fast512) | `/data/151-3/comics/ComicsDepth/runs/v2_512/` | finished; **depth excluded from the benchmark** after visual review |
| MAGI v3 grounding | `annotations/magi3_grounding/` | **not run yet** (needs a free GPU; Qwen is done) |

**Git:** nothing has been committed since the initial commit. All the work above is uncommitted (about 53 files).

## Plan (in order; agreed 2026-10-27)
Each stage produces inspectable outputs and passes its tests before the next stage consumes it.
Design: `docs/notes/graph_reasoning.md` (replaces spec 06).

| # | Stage | What | Status |
|---|---|---|---|
| 1 | **CKG-0** audit | Page order, missing annotations, identities, speaker links, text-class meaning, OCR issues, panel reliability; report of which questions the data supports. | Review disposition complete 2026-10-27 → `reports/ckg0/review_v1/report.md`; 21 tests passed. Original `v1` audit preserved. Six explicit identity corrections; zero unresolved integrity errors under the override contract. Visual review queue remains open. |
| 2 | **CKG-1** chapter graphs | Nodes/relations for pages, character appearances, text regions, speaker links; source references and coverage status. Consume review coverage and identity overrides; integrate existing exact-name identities here. | Implemented 2026-10-27; 17 new tests / 38 total CKG tests pass; Death Note c001 smoke and resume verified. Full run pending: `bash scripts/build_ckg1.sh` → `evidence/ckg/v1/`. Resume with the same command plus `--resume`. |
| 3 | **CKG-2** identities + name visibility | Verify which names are readable per page/chapter with OCR agreement or individual verification (ambiguous name parts don't count, `imp.md`). Needed before GEN-1. | Name visibility not started; identity integration is implemented in CKG-1. |
| 4 | **CRL-1** language + interpreter | Find appearances, follow speaker links, intersect sets, count, compare page order; answers with evidence traces; flag missing/ambiguous evidence. | not started |
| 5 | **CRL-2** proof checker | Independent check of every answer and step against graph facts and coverage; tests that wrong proofs are caught. | not started |
| 6 | **GEN-1** first questions | Generate programs, execute, keep supported answers; uniqueness, necessary constraints, robustness, shortcuts; template wording. Apply the name-readability rule and the guessability limits here (≤30% frequent-name answers, ~5% two-option). | not started |
| 7 | **VERB-1** natural wording | Qwen phrases the questions; parse back into a program and check meaning and answer are unchanged. | not started |
| 8 | **CKG-3** richer evidence | Audited panels, within-page reading order, spatial relations from GT boxes, verified OCR, name mentions. | not started |
| 9 | **GEN-2** harder families | Multi-part, counterfactuals, constraint puzzles, summary verification, contrast pairs. | not started |
| 10 | **EXP-1** review + export | Human review, dedup, answer balancing check, baselines (random, frequency, text-only); export model-facing questions/images separately from private programs, proofs, annotations. | not started |

Side tasks (not prerequisites of the graph):
- **Page-order task** (CPU, `docs/notes/extra_ideas.md`): shuffle consecutive GT pages of one chapter; the
  answer is the order. Can go into GEN-1 or stand alone. Not started.
- **MAGI v3 grounding**, only when caption-based evidence is needed. User-run:
  `bash scripts/ground_magi3.sh --gpus <g>,<g>` (strict mode, ~4 h on one GPU with 2 processes) →
  `annotations/magi3_grounding/`. Code ready and tested; not run.
- **Core v2** integration is deferred. The current `--version v2` option only chooses an output
  directory; it does not integrate OCR, Qwen or grounding. Extend the adapters before claiming that integration.

## Open questions
- GEN-1 must define the frequent-character set/tie handling and quota denominators in configuration.
  The agreed limits remain ≤~30% frequent-character name answers and ~5% two-option answers.

## Decisions to remember
- **CKG-1 contract (2026-10-27):** one graph per full supplied chapter; retain no-GT pages.
  Core node IDs remain stable except reviewed generic identity overrides. Positive relations have
  deterministic IDs, typed signatures, source hashes/pointers and premise traces. Co-presence
  stores one canonical unordered pair; repeated positive tuples retain one deterministic witness.
  Model panel nodes/on-page facts remain M and ineligible as answer evidence. `is_line` requires
  a human speaker link. Name visibility remains unchecked until CKG-2. Pixel boxes are not clipped.
- **CKG-1 coverage (2026-10-27):** carry reviewed family states as certificates with their assumption
  basis. Additional `page_sequence=closed_assumed` applies only to the supplied, inventory-checked
  chapter images. Fact coverage references describe witness pages; CRL must check the complete
  query scope for non-monotone operations. A positive fact's eligibility does not certify a query.
- **CKG-1 freshness/resume (2026-10-27):** validate audit/core/review hashes and current image/source
  hashes before building or reusing each chapter. Source changes require updated audit/review;
  changed code/config/dependencies require a fresh output. `.partial` checkpoints support restart;
  `--resume` also verifies completed outputs. These are private evidence artifacts, not public QAs.
- **CKG-0 review (2026-10-27):** original sources/core/audit remain immutable. CKG-1 applies
  `review_v1/identity_overrides.jsonl` for six `Unnamed woman` appearances in Death Note p032–034,
  preserving source IDs as provenance and removing generic name aliases. This is the explicit
  exception to reusing core identity IDs; appearance IDs and valid named identities stay stable.
- **Coverage disposition (2026-10-27):** character/name coverage is open on 727 pages; text boxes
  on 53; speaker links on 1,003; all human families absent on 97. `coverage.jsonl` contains every
  page decision. Keep flagged geometry open without automatic clipping/tolerance relaxation.
  The 1,012-record human geometry queue has only a limited spot-check; full visual review is pending.
  No chapter is closed for character/speaker coverage. Build supported positive facts; require
  relevant coverage for exact count/absence/first/only, otherwise CRL returns UNKNOWN.
- **Generation order (2026-10-27):** chapter name readability is required before GEN-1. Enforce
  guessability limits during GEN-1; EXP-1 confirms limits and runs baselines. Page-order generation
  remains an independent side task. Exact-name linking can be integrated into CKG-1.
- **Source precedence:** human GT where it exists; MAGI v3 only for panels, reading order and pages
  without GT; OCR model for text; Qwen captions as context only; grounding links phrases to human boxes.
- **Qwen prompt v4:** no names, no quoted text, no length targets (following "From Panels to Prose").
- **Grounding:** strict mode (exact caption); names come only from GT matches with status `matched`.
- **Identity:** the same exact name within a series. No automatic merging (`L` ≠ `Lind L. Tailor`).
- **Questions:**
  - Names used in questions or answers must be readable somewhere in the full chapter context.
  - At most ~30% of name answers may be the chapter's most frequent characters.
  - Two-option answers (yes/no, left/right) are kept to ~5%.
  - Report random, frequency and text-only baselines.
- **Graph QA decisions** (2026-10-23, for `docs/notes/graph_reasoning.md`):
  - **Completeness:** human annotations are treated as complete (coverage status `closed_assumed`;
    the user accepts occasional annotation errors). Pages flagged by automatic red-flag checks (e.g.
    dialogue balloons but no speaker links, no character boxes) stay `open` and are excluded from
    non-monotone questions.
  - **Trust for answer-critical steps:** H and V. A model fact (e.g. MAGI v3 reading order inside a
    page, panels) becomes usable as tier A only after a small sample audit. OCR counts as V where
    PaddleOCR-VL and MAGI v3 OCR agree.
  - **Role names** ("DEBT COLLECTOR", "The student council president") count as named characters; only
    `"none"` and "Unnamed …" are generic.
  - **Context:** always the full chapter plus the question.
  - **IDs:** keep the core v1 IDs, panels from MAGI v3, and the exact-name identity rule
    (confidence 1.0).
