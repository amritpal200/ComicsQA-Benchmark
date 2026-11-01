# CKG-3 richer evidence and individual visual review

CKG-3 builds an immutable companion to CKG-1/2. It adds full-transcript OCR
verification, lexical name occurrences, review-gated semantic mentions, panel
memberships, within-page reading order and same-panel spatial relations. It uses
only existing annotations and CPU code; Qwen and MAGI inference are not run.

## Run

From `Code/`:

```bash
# Bounded preview
bash scripts/build_ckg3.sh --chapter dragon-ball__c002 --out /tmp/ckg3-preview
# Entire collection, user-run
bash scripts/build_ckg3.sh
# Restart or verify a completed build
bash scripts/build_ckg3.sh --resume
```

Default input roots are `$BENCH_ROOT/evidence/ckg/v1` and
`$BENCH_ROOT/evidence/name_visibility/v1`. Default output is
`$BENCH_ROOT/evidence/ckg3/v1`, with BENCH_ROOT defaulting to
`/data/151-3/comics/ComicsQA_Benchmark`.
Use `--graphs`, `--visibility`, `--out`, and repeated `--chapter` to override.

The default verifies original image/annotation source hashes as well as the
pinned chapter/manifests. A changed source aborts: investigate/rebuild upstream;
do not silently reuse old review decisions. For a relocated frozen snapshot where
original source paths are unavailable, `--snapshot-only` explicitly skips raw
source freshness. The report records this limitation. Review images must still
be available at the paths in the HTML, or viewed separately from the source.

Output:

- `report.md`, `report.json`: verified/candidate counts and eligible relation totals.
- `chapters/<chapter>.json`: checksummed companion with source hashes, original
  stable node IDs, transcripts, memberships, orders, mentions, facts, coverage,
  review decisions and remaining review queue.
- `review/<chapter>.html`: original-page overlays and expandable review records.
  Open locally in a browser on a machine that can read the referenced original
  image paths. These private files contain `file:` image references, not embedded
  image copies; they are not public web pages.
- `review/<chapter>.json`: machine-readable queue with decision templates.
- `build_config.json`, `manifest.json`: code/dependency fingerprints and output hashes.

Atomic chapter checkpoints live in `<out>.partial` until successful publication.
One writer per destination; stop an existing run before restarting. `--resume`
checks source/code/review fingerprints and recomputes pure evidence derivations
against checkpoints. Changed decisions, code or dependencies require a new output.
No original graph, annotation, image or GEN-1 item is rewritten.

## Trust and geometry rules

**Panels:** MAGI panels remain M until an individual reviewer confirms every box
and the complete page panel inventory. This implementation makes no sample-audit
precision/recall claim and does not automatically assign tier A. Invalid panel
geometry requires a corrected upstream snapshot, not a review override.

**Membership:** region area inside a panel must be at least 0.6. If two panels each
contain at least 0.3 of a region, membership is ambiguous even if one scores
higher. Invalid/outside geometry remains unavailable. Only valid human regions
with unique assignments to a reviewed panel set produce V memberships. Open human
inventory coverage stays open even when individual memberships are known.

**Geometry:** compare human appearances only within the same uniquely assigned
panel. `left_of` and `above` use center separation strictly greater than 5% of
panel width/height; ties have no directional fact. `overlaps` uses IoU >= 0.1.
`larger_than` uses area ratio >= 1.5 and excludes boxes touching/crossing a panel
or image boundary. Candidate geometry over unreviewed panels stays M.
`present_panel` preserves human identity premises; `offpanel_line` requires a
unique human speaker link and different unambiguous text/speaker panel assignments.
It describes the linked depiction being outside the text's panel, not an unseen
speaker anywhere in the story. Missing facts never mean false or absent.

**Order:** estimated panel ranks are retained as candidates. Reviewed panel order
must be an exact permutation of a verified panel inventory. Reviewed text order
must be a complete permutation of human text IDs on a page whose text coverage is
closed. It supplies `text_order_rank` and `next_text`. Exact `reading_pos`
(page index, panel rank, text rank) additionally requires both reviewed orders and
complete unambiguous text-to-panel mapping. Contradictory orders fail closed.
Stored ranks are zero-based; future question rendering must convert explicitly.
Discourse reading order does not establish story chronology.

**OCR:** aligned, usable, nontruncated Paddle and MAGI outputs must agree on the
*whole* normalized transcript. Normalize Unicode NFKC, case, whitespace and curly
apostrophes; retain punctuation. CKG-2's looser name-span agreement does not certify
a full transcript. Store both raw strings. Individual visual transcription can
resolve disagreement. No-GT regions may have verified transcripts but do not
become human Text nodes or answer-eligible quote facts.

**Names:** `name_occurs` is the exact CKG-2 verified lexical occurrence. It does not
establish a semantic referent. `mentions` additionally requires a reviewer to
confirm the identity, a verified complete transcript and the name form in it.
This prevents ordinary words such as `and` being treated automatically as genuine
character references. Semantic-mention completeness always stays open: reviewing
positive occurrences does not certify absence or exhaustively find all mentions.

**Coverage:** new certificates cover specific evidence families. Closed OCR
coverage means all supplied human text regions have verified transcripts, subject
to the original human text-box coverage. `closed_assumed` and `closed_audited`
are inherited rather than promoted to `closed_verified`. The base graph's
certificates remain unchanged. Spatial coverage remains open because ties,
truncation and unassigned regions are not exhaustive negatives.

## Supply review decisions

First run without decisions to inspect the report/overlays. Copy a queue entry's
`decision_template` into a JSONL file (one object per line). Every decision must
retain chapter/page/target IDs, graph/visibility/image SHA-256 values and include
`status=verified|rejected`, a nonempty `reviewer` and a `note`. Templates with
`status=pending` are deliberately rejected by the builder.

For a verified decision, add the fields below:

| kind | target_id | Additional fields |
|---|---|---|
| `panels` | page ID | `panel_ids`: exact complete inventory; `complete_inventory: true` |
| `panel_order` | page ID | `ordered_ids`: all panel IDs in reading order; panel inventory must also be verified |
| `text_order` | page ID | `ordered_ids`: all human text IDs in reading order |
| `transcript` | alignment ID | `transcription`: full region text |
| `mention` | CKG-2 evidence ID | `identity_id`: the same reviewed character identity |

Use a separate output after review:

```bash
bash scripts/build_ckg3.sh \
  --decisions /path/to/ckg3-decisions.jsonl \
  --out /data/151-3/comics/ComicsQA_Benchmark/evidence/ckg3/v1_reviewed
```

Include all decisions you want applied, not just changes since the previous build.
Unmentioned targets remain automatic candidates/consensus; duplicate, stale,
unknown or out-of-selection decisions fail. Panel/mention rejection does not
rewrite the source annotation. Do not approve boxes or transcripts solely because
a model or the queue proposes them. No actual human decisions are shipped here.

## Consumer boundary

```python
from comics_qa.evidence.graph.rich.loader import load_rich
from comics_qa.evidence.graph.rich.model import eligible_facts
companion = load_rich(graphs_dir, visibility_dir, rich_dir, chapter_id)
transcript_facts = eligible_facts(companion, 'transcript')
```

The loader checks artifact hashes and source bindings, then recomputes all review
and derivation rules. `eligible_facts` is a positive-witness helper, not an exact
query engine. It must not be used to infer uniqueness, absence, first/last, counts
or negative answers without complete scope-specific coverage checks.

The existing CRL/independent proof checker and GEN-1 are intentionally unchanged:
they do **not** consume these companion relations yet. GEN-2 integration must
extend interpreter rules and independent proof rules together, pin this companion
in execution provenance and implement uncertainty/coverage tests. No claim is made
that quote, spatial or within-page CRL programs are enabled by this build alone.
The same applies to captions/grounding: they are not ingested or promoted here.

Tests: `python3 -m unittest discover -s tests -p test_ckg3.py -v`.
