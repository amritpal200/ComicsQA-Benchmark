# Comic Knowledge Graph: audit, chapter graphs and name visibility

## CKG-2: OCR alignment and name visibility

Run after the full CKG-1 build:

```bash
bash scripts/build_ckg2.sh
```

Output: `$BENCH_ROOT/evidence/name_visibility/v1/`, with the usual default root
`/data/151-3/comics/ComicsQA_Benchmark`. Inspect `report.md` or `report.json`.
This is a CPU/stdlib companion to the existing graph, using saved OCR outputs.
It performs no model inference and does not modify CKG-1 or its coverage records.

For a bounded run or restart:

```bash
bash scripts/build_ckg2.sh --chapter dragon-ball__c002 \
  --out /tmp/ckg2-dragon-ball
bash scripts/build_ckg2.sh --chapter dragon-ball__c002 \
  --out /tmp/ckg2-dragon-ball --resume
```

Every selected chapter includes all its pages. The input graph hashes, pinned
core/audit/review dependencies, current source hashes and image bytes are checked.
Changed sources require new upstream snapshots. Partial output uses atomic
chapter writes/checkpoints and a process lock; completed shards are verified on
resume. Changed policy/code/decisions/configuration requires a fresh output path.
Existing output is rejected without `--resume`. Individual roots are configurable
with `--graphs`, `--core`, `--audit`, `--review`, `--images`, `--human`, `--magi3`,
`--ocr`, and `--out`.

### Verification policy

- Align PaddleOCR's source boxes to **MAGI OCR bboxes**, not MAGI detection indices.
  Default IoU is at least 0.5. Both sides must have a unique substantial overlap;
  competing overlaps covering at least 0.5 of the smaller box reject split/merge
  or duplicate matches. `--min-iou` may be raised; `--ambiguity-overlap` may be
  lowered for stricter rejection. Regions are never concatenated automatically.
- Match exact contiguous word-token sequences after NFKC, casefold and apostrophe
  normalization. Whitespace/punctuation separate tokens. No fuzzy spelling,
  word reordering, invented aliases or automatic hyphen joining is used.
- Only canonical names and allowed graph aliases can verify an identity. Ambiguity
  is checked against stored core flags and normalized aliases across the series,
  including identities absent from the selected chapter. An alias inside a longer
  name of another identity is blocked. Generic identities are excluded.
- Automatic V evidence requires the **same exact form** in both aligned regions,
  usable PaddleOCR (`ok`, not truncated, complete page), and complete MAGI OCR with
  `generation.ocr.possibly_truncated == false`. Missing quality metadata is not
  accepted as confirmation. Forms shorter than three alphanumeric characters
  require individual visual review, even when both OCR models agree.
- Verification applies to the name span, not the surrounding transcript. For
  example, both models can verify `Bulma` while disagreeing on another word.
  `full_transcript_agreement` is reported separately and does not automatically
  certify quote-answer tasks.

The evidence establishes lexical readability of a form, not whether an ordinary
word is being used as a name, who is mentioned, who speaks, or who is addressed.
Those question semantics require their own evidence and checks. This distinction
matters for name parts that are also common words or role labels.

### Companion contract for CRL/GEN-1

`chapters/<chapter_id>.json` contains:

| Field | Contents |
|---|---|
| `page_ids`, `graph_source` | Full chapter scope and pinned CKG-1 shard |
| `alignments` | All PaddleOCR regions plus unmatched MAGI OCR regions; geometric scores/status, raw transcripts, boxes and quality flags |
| `evidence` | Stable evidence IDs, exact forms, token spans, identity/page/text references, source pointers/hashes and verification decisions |
| `visibility` | Per-identity verified forms, canonical-name visibility, visible pages, verified/candidate/rejected evidence IDs |
| `policy`, `coverage_effect` | Explicit thresholds/normalization and unchanged graph coverage |

The root also contains `report.md`, `report.json`, `inputs.jsonl`, `build_config.json`,
`checkpoints/`, and `manifest.json`. Report identity/form counts are summed over
chapter scopes; the same named identity in two chapters can count twice.

Evidence is `verified` (V), `candidate` (M) or `rejected` (M). Identity status is
`verified`, `not_verified` or `generic_excluded`. **Not verified does not mean the
name is absent.** Failed alignment or missing OCR can prevent verification.

Names on pages without human annotations can support chapter readability if both
OCR models agree. Such evidence uses `text_id: null` and a separate OCR `region_id`;
it creates no human text node or speaker fact. Human coverage stays absent.

GEN-1 must check the actual string it plans to put in the question or answer:

```python
from name_visibility import form_is_visible
form_is_visible(chapter_visibility, identity_id, rendered_form)
```

This helper expects a validated, manifest-pinned companion. Seeing `Goku` alone
does not authorize rendering `Son Goku`. Neither name readability nor a verified
positive occurrence closes OCR/character/speaker coverage or proves name absence.
Richer semantic `mentions` relations remain a later-stage concern.

### Optional individual visual review

Use a JSONL file with one explicit decision per evidence ID. Inspect the original
page/region first and copy the exact evidence ID, chapter ID and image checksum
from the candidate. Example record shape (replace placeholders):

```json
{"evidence_id":"namevis:<copy exact ID>","chapter_id":"death-note__c001","image_sha256":"<copy image hash>","status":"verified","reviewer":"reviewer identifier","note":"Checked the original region; the letter is readable as the name L.","transcription":"I am L."}
```

Then create a new output:

```bash
bash scripts/build_ckg2.sh --decisions /path/to/decisions.jsonl \
  --out /data/151-3/comics/ComicsQA_Benchmark/evidence/name_visibility/reviewed_v1
```

Allowed verdicts are `verified` and `rejected`. Verification requires a transcription
containing the exact form, reviewer and note. Rejection can revoke automatic
agreement evidence; it does not need a transcription. Decisions pin the image hash
and evidence ID, so stale/unknown targets fail. Ambiguous identity aliases cannot
be approved through a visibility-only review. Decisions for unselected chapters
in the same graph collection are left for those chapter builds.

The output records both the automatic result and the explicit decision/source hash.
No human review decisions are invented or applied by default. Exit 0 means the
build completed, not that every name was verified; exit 1 indicates a failure and
exit 2 invalid CLI usage.

## CKG-1 chapter graph builder

From the `Code` directory, run the full CPU build:

```bash
bash scripts/build_ckg1.sh
```

Inputs default to `$BENCH_ROOT/core/v1`, `reports/ckg0/v1`, `reports/ckg0/review_v1`
and the audited image/human/MAGI/OCR directories. `BENCH_ROOT` defaults to
`/data/151-3/comics/ComicsQA_Benchmark`. Every root is individually configurable.
The full collection output is `$BENCH_ROOT/evidence/ckg/v1`.

To build one **complete** chapter for inspection:

```bash
bash scripts/build_ckg1.sh --chapter death-note__c001 \
  --out /tmp/ckg1-death-note
```

Repeat `--chapter` for multiple chapters. There is no page-limit option: graphs
always retain the full supplied chapter, including pages without human annotations.
Selection is marked in the manifest and report. All images are hashed, so runtime
depends on filesystem throughput; no GPU or additional Python packages are needed.

Output contract:

| File | Contents |
|---|---|
| `chapters/<chapter_id>.json` | Nodes, facts, coverage certificates, metadata and ordered complete page IDs |
| `relations.json` | Typed registry, positive-relation semantics, functional/symmetric properties and coverage dependencies |
| `inputs.jsonl` | Current image/annotation checksums and missing-source states for built chapters |
| `build_config.json` | Input roots, selected chapters, policy version, pinned dependencies and code hashes |
| `checkpoints/<chapter_id>.json` | Completed shard checksum and source dependencies |
| `report.json` | Counts, selected scope and remaining name-visibility requirement |
| `manifest.json` | Config fingerprint and checksums of all output artifacts |

These are private evidence artifacts for CRL/generation, not model-facing QA data.

### Nodes, relations and provenance

Core chapter/page/appearance/text/tail/panel IDs are preserved. Named identities
reuse the exact-name core IDs within each series; each graph includes only that
chapter's appearances. The six reviewed generic appearances receive the explicit
page-local identity overrides, preserving the old IDs and names as provenance.
Generic identities have no canonical name or aliases; ambiguous named aliases are
excluded. Name visibility remains `not_checked` until CKG-2.

Relations: `page_in`, `next_page`, `on_page`, `is_char`, `named`, `alias`,
`spoken_by`, `has_tail`, `is_line`, `present`, `speaks_on`, `co_present`.
`co_present` stores one lexically ordered pair of distinct identities and declares
symmetry in the registry. Repeated positive tuples retain one deterministic witness;
all appearance nodes and primitive speaker links remain available for later queries.
`is_line` follows an explicit human speaker link, independently of raw 0/1 text class.

Facts carry deterministic full SHA-256 IDs, source file hashes/pointers (JSONL
records use a `record_key` selector), origin H/M, derivation S/R, rule IDs,
premise fact IDs, supporting page IDs and coverage references. Derived trust never
exceeds its weakest premise/node. Policy confidence `1.0` is not a measured probability.
`answer_eligible` means origin meets the H/V policy; it does not establish that
an entire query, name anchor or exact aggregate is valid.

MAGI panels are retained as M nodes and M `on_page` facts. Their inner-order rank
is explicitly an estimate. OCR text, spatial relations, panel memberships, name
mentions and inner-order predicates await their later stages. Original pixel boxes
and normalized copies are retained without clipping; overflow flags remain visible.
Invalid boxes or regions entirely outside the raster stop construction.

### Coverage and validation

Every supplied page has a certificate for each reviewed family plus `page_sequence`.
Human `closed_assumed`, `open` and `absent` states are carried from the review.
Models remain open. The extra `page_sequence` certificate is `closed_assumed` for
the **supplied chapter image inventory**, after its structure/inventory checks; it
does not claim that unprovided pages before/after the collection do not exist.

`next_page` means the next supplied chapter image and includes unannotated images.
Positive facts on annotated pages can remain usable when completeness is open.
Non-monotone operations require closed coverage across every relevant page and
relation family. `scope_is_closed` is a coverage helper; the CRL interpreter and
independent proof checker are separate stages. Fact coverage references cover that
fact's witnesses, not the full range of a future query.

The builder checks types, referential integrity, complete chapter adjacency,
functional/symmetric constraints, premise cycles, trust propagation and coverage
references. It verifies saved audit/review/core hashes, recomputes the v1 review
dispositions, and checks current image inventory, image bytes and all audited
human/MAGI/OCR source hashes/missing states for selected chapters. Changed sources
require a new audit/review snapshot. A different manual review policy requires an
explicit new review contract; editing the current review silently is rejected.

### Interruption and resume

```bash
bash scripts/build_ckg1.sh --resume
```

Use the same chapter selection, roots and output path when resuming a selected run.
Completed chapter shards are written atomically under `<out>.partial`. On resume,
current source hashes and saved shard checksums are verified before reuse. A shard
written without its checkpoint is rebuilt. Changed code/configuration/dependencies
or corrupted shards fail with an error; use a new `--out` after resolving the cause.
A lock prevents simultaneous writers to the same build directory.

The final directory is renamed into place only after all selected chapters finish.
`--resume` on a completed output verifies it and its current source dependencies.
Existing outputs are rejected without `--resume`; sources are never overwritten.
Exit 0 means success, exit 1 an input/build failure, exit 2 invalid CLI usage.

Tests:

```bash
python3 -m unittest discover -s tests -p 'test_ckg*.py' -v
```

## CKG-0 audit

CKG-0 audits core v1, human annotations, MAGI panels/order and PaddleOCR artifacts.
It is CPU-only and uses Python's standard library. It does not build a graph,
implement CRL, generate questions, or use depth maps. Qwen captions and grounding
are outside this foundational audit.

## Run

From the `Code` directory:

```bash
bash scripts/audit_ckg0.sh
```

Default data root: `/data/151-3/comics/ComicsQA_Benchmark`.
Default output: `$BENCH_ROOT/reports/ckg0/v1` (the same default root applies when
`BENCH_ROOT` is unset). Override the root or any individual input/output:

```bash
BENCH_ROOT=/path/to/ComicsQA_Benchmark bash scripts/audit_ckg0.sh \
  --out /path/to/new-report
```

A bounded source audit, explicitly labeled `sample`:

```bash
bash scripts/audit_ckg0.sh \
  --chapter assassination-classroom__c001 --limit-pages 3 \
  --out /tmp/ckg0-sample
```

Repeat `--chapter` to select several exact chapter IDs. Core indexes are always
read in full; chapter structure is checked across each selected chapter even when
source inspection is limited. `--verify-images` additionally hashes image bytes;
the default checks image existence and compares annotation/core image hashes.
File inventory checks cover selected chapter directories, not unknown directories
outside the core chapter catalog. Filename gaps identify internal missing numbers;
they cannot prove that a chapter's beginning or ending is complete.

## Outputs and interpretation

| File | Contents |
|---|---|
| `report.md`, `report.json` | Counts, findings, scope and candidate coverage |
| `pages.jsonl` | Per-page source hashes, counts, raw class statistics, coverage and issue codes |
| `chapters.jsonl` | Order, spreads, gaps, image inventory, GT counts and closure prerequisites |
| `names.jsonl` | Exact names, generic names, identity IDs, aliases and source examples |
| `text_classes.jsonl` | Raw 0/1 correlations with links/tails and capped OCR examples |
| `issues.jsonl` | Severity, page/chapter IDs, source paths and JSON pointers where available |
| `inputs.jsonl` | Consumed-file checksums and missing/unreadable input records |
| `manifest.json` | Arguments, code checksums, output checksums and timestamp |

Human families begin as `closed_assumed` only when human annotations are present.
Relevant review flags downgrade them to `open`; missing ground truth is `absent`,
never evidence of absence. Model panels, reading order and OCR remain `open` when
present. These are **audit candidates, not coverage certificates or measured recall**.
Any integrity error blocks every selected chapter's closure prerequisites until
reviewed; per-page states retain their local findings.

Checks include source/core provenance, boxes and links, exact-name identity references,
page-local unnamed groups, cluster/name conflicts, slug collisions, empty character
pages, neighbor count drops, text with tails but no speakers, multiple speakers,
panel overlap ambiguities, OCR box/index alignment, truncation and empty transcripts.
Neighbor and overlap flags are heuristics for review, not proof of annotation errors.
Names `none` and `Unnamed ...` are generic; role names remain named. The audit reports
exporter-policy mismatches without changing identities or source files.

Raw text classes remain semantically unverified. Unlinked text is not automatically
dialogue. OCR excerpts help manual review but do not establish quote accuracy, name
visibility, OCR agreement or visual support. Model panel recall needs visual review.

Reports use a fresh `.partial` directory and are renamed on completion. Inputs are
never modified; output paths overlapping inputs and existing outputs are rejected.
An interruption does not resume: inspect any `.partial` directory, then rerun with
a new `--out`. No destructive cleanup is performed.

Exit codes: `0` = report written without integrity errors (warnings may remain);
`2` = report written with integrity errors, or invalid CLI usage (check the printed
message); `1` = fatal input/write failure. Inspect `report.md` before proceeding to
CKG-1. Resolve errors and review flags; do not automatically promote model evidence.

## Tests

```bash
python3 -m unittest discover -s tests -p test_ckg0.py -v
```

## Review the completed audit (CKG-0 follow-up)

```bash
bash scripts/review_ckg0.sh
```

This consumes the saved `reports/ckg0/v1` snapshot and core v1. It verifies the
audit output checksums and the core checksums recorded by that audit, then writes
a fresh `reports/ckg0/review_v1` directory. It does not repeat the annotation audit.
Override `--audit`, `--core` and `--out` or use `BENCH_ROOT` for another location.
Existing outputs and `.partial` directories are rejected; choose a new output for
a rerun. Exit codes are 0 for no unresolved errors, 2 for unresolved errors (or
CLI usage errors), and 1 for input/write failures.

The review is a companion input contract for CKG-1:

- `identity_overrides.jsonl`: stable appearance IDs, original identity IDs and
  corrected page-local generic identities. `none`/`Unnamed ...` identities lose
  name aliases in the graph; exact named identities stay intact. Conflicting
  page clusters remain unresolved.
- `resolutions.jsonl`: original issue line and checksum plus the explicit override
  that resolves it. Original audit records are retained.
- `coverage.jsonl`: previous and reviewed candidate coverage for all pages. Only
  a resolved identity flag can be removed; other geometry/speaker flags remain.
  Positive-fact eligibility still requires individual valid evidence.
- `chapters.jsonl`: recomputed whole-chapter closure prerequisites.
- `geometry_review.jsonl`: human character/text/tail overflow cases ranked by
  relative boundary excursion, with original coordinates. This is a review queue;
  it does not clip boxes or certify visual completeness.
- `unresolved_issues.jsonl`: remaining findings, including model panel proxies.
- `report.md`, `report.json`, `manifest.json`: decisions, limitations and hashes.

**CKG-1 must verify these dependencies and apply the overrides before using the
reviewed coverage.** The review does not change core v1. Current source images and
annotations are not rehashed by this snapshot review; dependency freshness must
be checked when building a graph. Never treat an absent human page as an empty
page. Never promote raw OCR to verified name visibility solely because it matches.

Validation:

```bash
python3 -m unittest discover -s tests -p 'test_ckg0*.py' -v
```

## CKG-3 richer evidence

Implemented as a separate immutable companion under `evidence/ckg3/v1`, preserving
CKG-1/2 and GEN-1. Run `bash scripts/build_ckg3.sh` (CPU, user-run); see
[CKG-3 contract and visual review workflow](rich/README.md). Full OCR consensus is
automatic where strict agreement holds; panels, within-page order and semantic
mentions require explicit snapshot-bound visual decisions. The initial build is
expected to retain unreviewed candidates. CRL consumption remains a separate
interpreter/checker integration for GEN-2.
