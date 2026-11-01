# GEN-2: initial supported OCR/lexical families

CPU-only deterministic generation over the immutable CKG-1, CKG-2 and CKG-3 artifacts.
This extends the language and independent checker together; it preserves the completed
GEN-1 and GEN-2 v1 baselines. It is an initial supported subset, not completion of every planned GEN-2 family.

## Run

From `ComicsQA_Benchmark/Code`:

```bash
bash scripts/build_gen2.sh
# After interruption, or to verify a completed build with unchanged inputs/code/config:
bash scripts/build_gen2.sh --resume
```

Default output: `/data/151-3/comics/ComicsQA_Benchmark/items/gen2/v2/`.
Policy: `configs/tasks/gen2_v2.json`; generator version `gen2.2`.
The completed `items/gen2/v1/` stays immutable. New code cannot resume that old
build fingerprint; this is expected and does not mean its stored artifacts are corrupt.
Inspect `report.md`, `report.json`, and `chapters/<chapter>.json` (items in `payload.items`).
`BENCH_ROOT=/other/root` relocates all default inputs and output; `--graphs`, `--visibility`,
`--rich`, `--out`, `--config` override paths. No GPU or new OCR inference is required.

For a bounded run, use a separate output and repeat the same options when resuming:

```bash
bash scripts/build_gen2.sh --chapter chainsaw-man__c001 \
  --max-candidates-per-chapter 18 --max-items-per-chapter 10 \
  --out /tmp/gen2-smoke
```

The versioned config attempts at most 180 candidates/chapter and selects at most 60;
these are search limits, not promised yields. Chapter checkpoints are atomic; interruption
retains completed chapters and restarts the unfinished one. Changed code/config/input pins
require a new output path. Completed outputs are never silently overwritten. This code change
also changes older builders' resume code fingerprints; do not regenerate the GEN-1 and GEN-2 v1 baselines.

## v2 quality policy

Only a full canonical character name with verified same-form readability can be used
as an explicit name anchor or character answer. Automatically split aliases such as
`The` from `The student council president` or `DEBT` from `DEBT COLLECTOR` are excluded.
Accepted answer variants are filtered by the same rule. This conservative rule also
holds out legitimate shortened names until reviewed-alias support is implemented.
It does not automatically replace an unreadable name with its canonical form. Complete
canonical role labels such as `Boss` remain subject to human review. Raw names, aliases,
visibility evidence and CRL semantics are unchanged. Ordinary words inside quoted text
are not interpreted as character names merely because they match a discarded alias.

Selection deduplicates the resolved target across quote/name anchors:
- Depiction counts: character identity + target page.
- Next appearances: character identity + anchor page.
- Speaker identity: resolved text region.

Different target identities/pages remain distinct even if the numeric answer is equal.
Each item stores its semantic target/hash and next-page offset (where applicable).

These defaults apply separately within each chapter:

| Config field under `quality` | Default | Denominator |
|---|---:|---|
| `max_count_share` | 0.70 | All selected questions |
| `max_count_value_share` | 0.35 | Selected count questions |
| `max_page_offset_share` | 0.50 | Selected next-page questions |

These are explicit new configurable policy choices, not measured guarantees of difficulty.
The existing frequent-name and two-option limits also remain enforced. The selector
first deduplicates, applies the existing quotas, then deterministically trims concentration
violations and rechecks the old quotas after every removal. It does not refill or optimize
for maximum yield. All caps must hold simultaneously; a small chapter can yield zero.
For example, if every supported next-page answer is the immediately following page,
that subset is held out instead of silently weakening the offset cap.

`report.json` and `report.md` include selected count/offset distributions, majority-answer
shares, and the always-next-page baseline. Chapter reports additionally include before/after
quality distributions and explicit rejection reasons. Qwen preparation and human review
remain pending; these checks do not certify narrative difficulty or visual truth.

## Supported families

| Anchor | Result | Family |
|---|---|---|
| Exact full OCR text on a specified page | Speaker identity | `quote_speaker` |
| Exact full OCR text on a specified page | Same-page speaker depiction count | `quote_speaker_depictions` |
| Exact full OCR text on a specified page | Next page where that speaker is drawn | `quote_speaker_next_page` |
| Only text containing an exact readable name form on a page | Speaker identity | `name_speaker` |
| Same literal name-form anchor | Same-page speaker depiction count | `name_speaker_depictions` |
| Same literal name-form anchor | Next page where that speaker is drawn | `name_speaker_next_page` |

Name-form matching means literal text, not a semantic reference to that person. Quote lookup
requires a unique full normalized transcript, not a substring or fuzzy match. Current CKG-3
has no fully closed OCR chapter, so page-scoped anchors are deliberate. More varied scope
wording must not create an unsupported chapter-wide uniqueness claim.

Each accepted candidate executes with the independent checker, then passes the shared GEN-1
necessity, visual support, page ablation, shortcut, representation and balancing gates. Rich OCR
coverage and source facts are included in proof support. Text-only ablation preserves verified
OCR, text locations and lexical names, while removing character/speaker facts; page removal
also removes OCR alignments and closes no unknown domain. Next-page families require two
necessary visual pages. All chapter images remain in the delivered context.

Names embedded in quoted questions also undergo exact-form readability and ambiguity checks.
The selection limits remain unchanged: at most 30% frequent-character answers among name
answers, at most 5% two-option answers among all items, balanced booleans when present.
They apply per chapter to this new subset; final combined benchmark selection still needs its
own audit. A chapter may yield zero items. No quota is silently relaxed.

W4 checks that both OCR models give the same full normalized text for every transcript used
in the proof. It does not claim robustness to arbitrary OCR noise. Manually reviewed CKG-3
companions are currently rejected by this generator until decision-aware ablation is defined;
the CRL interpreter/checker themselves support validated reviewed companions.

## Boundaries and next work

All output has `question_type=graph_verified`, template wording, exact typed answers, and pending
human review/G10. The [GEN-2 VERB-1 adapter](../verbalization/README.md#gen-2-request-adapter-2026-10-29)
now supports these templates and private evidence packs: run `bash scripts/prepare_verb1_gen2.sh`
after the completed GEN-2 build. Free-form parse-back and final language review remain pending. Qwen stays deferred to MN5.
The separate `qwen_answer_conditioned` class and approximately 30% sentence-answer/LLM-judge
track remain future work. Panel/order/spatial/semantic-mention, counterfactual, constraint-puzzle
and summary-verification families are not enabled by this implementation.

No collection run is performed by installing this code. Review `docs/STATUS.md` for measured
bounded results and the distinction between implementation and full generation.

## Retained-pool revision v3

The separate [v3 workflow](V3.md) adds retained candidate pools, split-level distribution
selection and explicit reviewed aliases. Use `scripts/build_gen2_v3.sh` for a fresh v3
output; `scripts/build_gen2.sh` still targets the completed v2 policy/output. Review the
name-diversity bottleneck and alias workflow before another full run.
