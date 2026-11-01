# Semantic inventory and native records

Implemented 2026-10-30 in the additive benchmark1000 namespace. Legacy CKG/CRL/GEN/VERB implementation and completed foundation v1 artifacts remain unchanged.

## Run the next full CPU inventory

From `ComicsQA_Benchmark/Code`:

```bash
bash scripts/benchmark1000.sh semantic-preflight \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/semantic_v1
```

Default scope: all chapters in the matching CKG-1/2/3 manifests. Defaults: at most four proposals per pattern, eight support pages for each page-ablation experiment, and 2,000 combinations in clue search. This is a CPU-only, budgeted capability inventory. No Qwen, new OCR, annotation generation or final QA selection runs.

For a different host use `--bench-root ROOT`. For a smaller trial use repeated `--chapter ID`, `--per-pattern N`, `--max-ablation-pages N` and `--clue-search N`. A page-ablation budget of zero records dependencies as unmeasured for supported answers, rather than inventing a measurement.

Repeat the identical command to resume. Completed chapters are checksum/pin checked and reused; the unfinished chapter restarts. A single-writer lock prevents concurrent writes to one output. Changed source manifests, relevant code, scope or budgets require a new output directory. Completed manifests and native child stores are checked rather than overwritten. Invalid budgets fail before publication.

**Do not rebuild foundation v1.** Its 3,630 records remain readable unchanged. The importer-code pin in an old store is historical; repeating an import into that same store after schema-adapter edits intentionally rejects a changed code fingerprint. Semantic inventory reads the immutable evidence independently and writes a new output.

## What is executed

| Pattern | Typed shape | Checks |
|---|---|---|
| Quote to next speech | Text → Char → Page | Minimal-prefix scan, exact scoped quote, independent probe proofs |
| Speaker relay | Text → Char A → Page B → only other Char C on B → C's next appearance page | Each stage checked independently; stage inputs are reconstructed from verified earlier outputs |
| Two-quote joint appearance | Two Text → Char branches, combined to a later joint-presence Page | Both branches, negative prefix and positive target; relax each character condition |
| Three-page clue | Three presence/speech constraints intersect to identify a character | Existing typed CRL execution/checker; remove each clause and test required pages |

The relay uses **the only different character drawn on the intermediate page**, rather than “the only speaker on their next speaking page,” which could just return the original speaker. Multiple eligible other characters yield AMBIGUOUS, not an arbitrary ID. Unreviewed within-page speaking order is not used.

Quotes must have admitted full transcripts and closed OCR scope. The report counts transcripts held for incomplete OCR scope. Two-quote pairs are grouped across pages before bounded enumeration, avoiding quadratic rejection of same-page pairs. Clue combination/emit limits and exhaustion are explicit.

This is a catalogue of supported typed patterns, not enumeration of all possible graph programs. Nominal pattern depths (up to four transitions here) and branch counts describe templates. `meaningful_hops` stays null until a separate certification justifies it; operation count and a dependency type list are not proof of narrative difficulty. No claim of exhaustive depth-five coverage is made.

For answer-supported cases the tool:

1. Executes and independently checks the answer, including negative coverage obligations.
2. Collects fact/certificate support, including pages supporting necessary absence checks.
3. Tests defined clause relaxations. UNKNOWN cannot certify clause necessity; known ambiguity can show that a condition disambiguates.
4. Removes support pages one at a time within the budget, deletes dependent facts, removes OCR alignments and rebuilds rich evidence before re-execution.
5. Records which removals change the answer or make it unknown, page span and explicit unmeasured states.

Page necessity is dependency under our annotation/coverage model, not a universal claim that humans cannot infer an answer by another route. Reviewed-rich ablation is not yet enabled; such input fails explicitly. `closed_assumed` evidence remains assumed and is recorded in native provenance, never upgraded.

## Output layout

```text
semantic_v1/
  config.json
  chapters/<chapter>.json
  report.json
  manifest.json
  native_store/
    config.json
    proposals/<hash>.json
    manifest.json
```

Each chapter records per-pattern status counts, budgets/admission, source pins, actual executions, independent checks, measured dependencies and answer-proved native proposals. The report has no `exhaustive=true` or automatic release claim. The native child store is independently verifiable.

## Native record contract

Schema: `comics_qa.benchmark1000.native.1`; stable IDs begin `b1000n:` and bind the complete record content. Native records do not masquerade as legacy records and have no required `legacy` wrapper.

Fields include the four taxonomy axes; question/answer; page context; native program/execution and engine; source artifact pins and graph/visibility/rich snapshots; fact/certificate/visibility evidence; used `closed_assumed` certificates; fact-origin counts; complexity; options/claims when applicable; and independent answer-check receipts.

- `crl`, `scan` and `relay` engines have independent answer checks. Scalar type coincidences do not pass: a Page result is not a count, even when both display `1`.
- Visual-choice and sentence record shapes can be stored. Pending assets/claim certification stay pending. These shapes do not implement visual-choice generation or sentence entailment certification.
- Evidence class labels describe the intended route for pending proposals; `verification` fields determine what is actually certified. A pending sentence record is not a set of verified claims.
- New records have `admission=proposal`, an unassigned primary group, pending question gates/wording/human review/release, and no invented meaningful-hop value.
- Proof receipts bind execution and answer hashes. Source context indices/images/hashes must match the loaded chapter, and provenance must match actual execution support.
- A native record may have `verification.proof=verified` while remaining a proposal: this proves the executable answer, not faithful wording, visual necessity or completion of all question gates.
- Neither human acceptance alone nor a manually changed flag admits a proposal. Both selectors and release helpers exclude proposals. A future explicit admission/certification stage is required.

## Read, review and import

```bash
bash scripts/benchmark1000.sh verify-store \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/semantic_v1/native_store \
  --include-proposals

bash scripts/benchmark1000.sh review-page \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/semantic_v1/native_store \
  --include-proposals \
  --out /data/151-3/comics/ComicsQA_Benchmark/reviews/benchmark1000/semantic_v1.html
```

Without `--include-proposals`, readers return only selection-admitted candidates. A native-only store can therefore correctly show zero candidates and several proposals. The review page supports native executions and pending flags; no approval is inferred from opening it. `check-reviews --include-proposals` validates separately stored review records against native content hashes.

To make a new mixed store from an explicit JSON list of native records plus the completed legacy imports:

```bash
bash scripts/benchmark1000.sh import-native \
  --records /path/to/native-records.json \
  --base-store /data/151-3/comics/ComicsQA_Benchmark/items/benchmark1000/v1/candidates \
  --out /data/151-3/comics/ComicsQA_Benchmark/items/benchmark1000/mixed_proposals_v1
```

`native-records.json` must contain actual native records, not hand-written fake proofs. This command loads the pinned evidence and independently rechecks records claiming verified answers, then publishes a new mixed store. Existing legacy records are copied unchanged; originals are untouched. Native rows stay under `proposals/`, legacy rows under `candidates/`. Default selection still sees only admitted rows. New mixed manifests need newly bound validation reports; the original foundation report is not silently rebound to a different manifest.

## Verified bounded results

- Chainsaw Man c001, two proposals per pattern, clue search 100, ablation page budget four: **six executed queries**, **one answer-proved native proposal**, **one measured two-page dependency**.
- Example: after page 14, find the next speaking page for the speaker of “this is a contract...”; answer **page 15**. Removing either supporting page breaks the result.
- The two relay attempts returned AMBIGUOUS/UNKNOWN. Two joint-appearance attempts were UNKNOWN. The clue search hit its explicit 100-combination budget and produced no proposal. None of these outcomes proves that other supported chains do not exist.
- Real semantic inventory and native import resume were checked. A bounded real mixed store contains 21 unchanged legacy rows plus one native proposal: default readers return 21, while explicit proposal-inclusive readers return all 22. Pending native rows are excluded from default selection. Existing foundation still loads all **3,630 records**; all **142 legacy files** remain unchanged.
- The expanded suite passes **82 CPU tests**, including tampering, type checks, source/context bindings, stage dependencies, budget reporting, OCR removal, mixed stores and checkpoint reuse.
- Development outputs are under `/tmp/benchmark1000-semantic-native-complete` (final source run), with earlier bounded snapshots retained. No full semantic collection run was launched by the agent.

## Next stage

Review the full report by pattern, known/unknown coverage, measured dependencies and ambiguity. Use that evidence to choose bounded new families and implement native question-level validity/admission checks. Complete native Qwen packing/wording validation and claim/asset certification in their planned stages. A final 1,000-item release or relaxation of the small-denominator policy is outside these two steps.


## Recovery from the native program/execution binding error

The first full run exposed a native-validator bug on `assassination-classroom__c002`: its three-constraint CRL program was canonicalised by the interpreter, reordering equivalent commutative operands. Raw AST equality incorrectly rejected it. Native validation now uses the same official canonical program hash as the independent checker. It still rejects genuinely different programs, even when they return the same answer. Legacy CRL code was not changed.

The exact failed chapter was rerun with the original budgets: three native CRL answers were proved and all three have measured multi-page dependencies. The completed c001 checkpoint was separately re-executed and its complete payload matches byte-for-byte at the canonical payload-hash level; its original file hash is unchanged. The updated suite passes 85 tests.

Because the fix changes a pinned code fingerprint, use a new recovery directory:

```bash
bash scripts/benchmark1000.sh semantic-preflight \
  --reuse-from /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/semantic_v1 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/semantic_v2
```

Inputs, chapter scope and budgets must match the source run. Recovery checks hashes/pins, fully re-executes completed chapters using current producer/checkers, and references a previous checkpoint only if the whole result is unchanged. This safety check costs a bounded replay of completed chapters; it does not blindly copy old verdicts. Originals stay untouched. Missing chapters build normally. Repeat this same recovery command after interruption; checkpoints already written in the new directory are reused without execution. Use a different fresh version if `semantic_v2` already belongs to another run.

Progress is printed per chapter as `built`, `resumed` or `revalidated_previous`. No full recovery was launched by the agent; the user runs it.


## Full semantic v2 run reviewed

The user completed the full recovery: 250 executions, 34 proved answers, 32 native proposals. All 32 native answer proofs were independently rechecked. See [full review](../../../docs/notes/benchmark1000_semantic_v2_results.md) for missing readable names, redundant branches, duplicate relay paths and the next native admission stage. No unchanged rerun is needed.

## Admission of completed semantic runs

The separate [native admission stage](NATIVE_ADMISSION.md) now checks necessary clues, exact name forms, template wording and resolved-path duplicates. It writes a new candidate store and preserves all original proposals. Free wording, primary-group certification, human review and release remain pending.
