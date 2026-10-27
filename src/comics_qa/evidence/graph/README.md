# Comic Knowledge Graph: audit, review and CKG-1

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
