# VERB-1 CPU preparation (v1)

Prepare the completed GEN-1 baseline for later Qwen inference on MN5. This stage
is stdlib-only, performs no downloads/model calls, and never modifies GEN-1.

```bash
# Small preview
bash scripts/prepare_verb1.sh --chapter dragon-ball__c002 --out /tmp/verb1-preview
# Full collection, user-run
bash scripts/prepare_verb1.sh
# Resume after interruption, or verify a completed output
bash scripts/prepare_verb1.sh --resume
```

Default input: `$BENCH_ROOT/items/gen1/v1`; default output:
`$BENCH_ROOT/items/verb1/v1_requests`, where BENCH_ROOT defaults to
`/data/151-3/comics/ComicsQA_Benchmark`. Override with `--source` and `--out`.
Repeated `--chapter` selects chapters; an unknown chapter fails rather than skips.

## What is checked

All files listed by the source manifest are hash checked. Each selected chapter
payload, program, saved execution/proof binding and rendered answer is checked.
An independent closed grammar parses the existing question text (not its attached
program) back into CRL; canonical programs must match exactly. It covers all eight
GEN-1 families, including ordered comparisons and two/three-clause intersections.
Unknown wording fails closed. These checks do not re-execute the graph or replace
the CRL-2 proof checker; they validate the frozen GEN-1 artifact's bindings.

Each chapter file contains:

- `payload.requests`: stable request IDs, chat messages and a response contract.
  Only these messages go to Qwen. They include the template and program but no
  answer, proof, captions or images: this task only rewrites existing semantics.
- `payload.private_records`: the full original item/proof, source item hash,
  `question_type=graph_verified`, `verbalization_type=qwen_paraphrase`, template
  round-trip result and pending G10/human-review status.

These packs are PRIVATE generation artifacts, not public evaluation examples.
No existing GEN-1 fields or files are changed. The planned
`question_type=qwen_answer_conditioned` track is separate and not implemented here.
This stage neither adds sentence answers nor changes page anchors or quotas.

## Restart and portability

Atomic per-chapter checkpoints in `<out>.partial`, a single-writer file lock,
source-manifest and code fingerprints, and final output checksums protect reuse.
Do not run two writers against one destination. Resume requires unchanged source
bytes and code; choose a fresh output after changes. Completed resume verifies
source/output checksums. No evidence or image files are accessed or copied.

Copy the pack directory to MN5. Request messages and IDs contain no local path
requirements. The private source items retain original absolute paths as
provenance; later evidence checking/export must resolve their `relative_path`
against the destination image root and use copied matching CKG/visibility
artifacts. Request preparation also supports relocating an identical GEN-1 tree.

## Deferred work and execution order

User decision 2026-10-28: prepare CPU evidence and question programs first:
GEN-1 -> VERB-1 request preparation -> CKG-3 -> GEN-2 (plus independent page-order
work when requested) -> Qwen inference on MN5 -> final validation/review/export.
GEN-2 now has a separate versioned request adapter (below); the original GEN-1 grammar
remains separate and does not accept GEN-2 templates. Sentence-answer/answer-conditioned generation requires
its own evidence/validation contract before the MN5 run.

**Not implemented/run by this preparation stage:** MN5 endpoint client/Slurm jobs,
Qwen response ingestion, blind natural-language parse-back, or final G10 approval.
The later parser must see the rewritten question and CRL grammar but not the
original AST/answer; compare its recovered program to the target, re-execute/check
it against pinned evidence, and check language uniqueness, names and leakage.
A Qwen response that simply echoes the supplied AST does not prove semantic
preservation. Even matching independently recovered programs need human language
review. Keep model provenance and raw outputs. Recheck quotas after filtering;
Qwen and final validation must complete before public export.

Tests: `python3 -m unittest discover -s tests -p test_verb1.py -v`.


## GEN-2 request adapter (2026-10-29)

Run **after** GEN-2 v2 publishes its completed manifest:

```bash
bash scripts/prepare_verb1_gen2.sh
bash scripts/prepare_verb1_gen2.sh --resume
```

Defaults: input `$BENCH_ROOT/items/gen2/v2`, output
`$BENCH_ROOT/items/verb1/gen2_v2_requests`. The command refuses unfinished inputs;
it never reads live `.partial` checkpoints as a completed collection. Override `--source`,
`--out`, `--graphs`, `--visibility`, `--rich`, or select `--chapter` for a bounded pack.
It supports the six GEN-2 families and uses an independent closed grammar, including
JSON-escaped quotes and explicit page scopes. The adapter does not edit generator code,
generated items, annotations or evidence. It can be developed while generation runs.

The same source-manifest, atomic checkpoint and single-writer protections apply. Each
selected proof is independently checked against supplied CKG-1/2/3 artifacts, whose pins
must match the source chapter. Answer type, displayed answer, full chapter context and
image hash/relative-path bindings are checked. Dependency code and all artifact manifests
are fingerprinted; completed resume also checks evidence output hashes. No raw images or
annotations are rescanned, no model is invoked, and no public export is created.

Each private record adds a hashed `evidence_pack`: fixed answer/program, supporting facts,
coverage, verified visibility records, relevant OCR alignments/transcripts/lexical records,
nodes and full context image references. Canonical absolute source paths remain provenance;
`context_images.relative_path` is the portable image lookup. Packs do not copy images or
full graph artifacts. Copy matching evidence/images separately for later full rechecking.

Only `requests[].messages` should be sent to Qwen. The answer and supporting evidence stay
in private records; the model receives the template, canonical task, answer type and scope
rules. This remains `question_type=graph_verified`, `verbalization_type=qwen_paraphrase`.
It does not implement the separate answer-conditioned question class.

`prepare_gen2.validate_rewrite(source_item, response)` checks a response with exactly one
`question` string. It parses that wording independently without using a model-supplied AST:

- Original templates and explicitly supported variants (`Which character is the speaker...`,
  `How many appearances of the speaker...`) can yield `closed_grammar_match`.
- Changed parsed scope, quote/name string or operation yields `rejected: semantic_drift`.
- Extra response fields (including an echoed program or answer) fail the response contract.
- Other wording yields `needs_blind_parse_back`; it is never silently certified.

Even a closed-grammar match leaves human language review pending. This helper is not a
free-form semantic parser or a response-ingestion pipeline. MN5 inference/client jobs,
blind free-form parse-back, response ingestion and final G10/human approval remain future
work. Selection quotas must be checked again after any wording/filtering losses.

Adding adapter files changes VERB-1 preparation fingerprints: preserve earlier request
packs and choose a fresh output rather than trying to resume an old-code pack. GEN-1/GEN-2
builders and their existing output fingerprints are unchanged by this adapter work.
