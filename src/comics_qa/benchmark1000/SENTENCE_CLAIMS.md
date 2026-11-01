# P10 executable factual claims and sentence contracts

P10 now prepares **private, graph-proved sentence plans** above admitted branch questions. It supplies typed claim programs, an independent claim checker, required/optional/verified-false claims, an ordered evidence plan, and controlled-language answer scoring. Existing `claims.py` remains an input-judgment helper; this new version does not silently reuse its unproved text/evidence contract.

These plans are not newly admitted sentence candidates, generated Qwen outputs or final benchmark entries. The existing candidate total is unchanged. Native sentence admission, unrestricted prose extraction, model prompting/ingestion, LLM judging and final human review belong to later integration.

## Prepare and check

From `ComicsQA_Benchmark/Code`, use the existing benchmark environment. No new dependency, GPU or model request is needed.

```bash
ROOT=/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000

bash scripts/benchmark1000.sh prepare-sentences \
  --source "$ROOT/branch_v1_admission" \
  --out "$ROOT/sentences_v1"

bash scripts/benchmark1000.sh check-sentences \
  --store "$ROOT/sentences_v1" \
  --out "$ROOT/sentences_v1.check.json"
```

`--bench-root PATH` changes the data root. Repeated `--chapter CHAPTER` restricts preparation. The first profile accepts the separately parsed two-speaker branch grammar in an admitted-native store; the completed `branch_v1_admission` has 11 supported seeds. It does not invent causal, emotional, spatial or caption-derived facts. Reviewed rich-world overlays need a separate ablation profile.

Preparation freshly reproduces every source admission and independently executes/checks the claim queries. Checkpoints bind configuration, source seed contents, source manifests, graph/visibility/rich snapshots and code. Repeating an identical command resumes and independently rechecks cached claim plans. A changed input/code/scope requires a new output path. Create-only publication and a writer lock preserve source and completed outputs.

`check-sentences` uses independent recipe checkers on the original source and all claim programs. It does not call the claim producer or recipe interpreter. It writes a separate hash-bound report. Use this command rather than the candidate-store `verify-store` or `check-proofs`: plan stores intentionally cannot enter candidate selection or inflate counts.

## Claim semantics and evidence

Every proposition has a typed signature, source-bound ID, exact wording, executable query, proof trace, execution hash and fact/coverage/OCR provenance. Page arguments are one-based context-image positions, as in the original question; spreads count once. Speaking/search claims are scoped to that question's declared range and conditions, not the last appearance or last dialogue in the entire chapter.

Supported predicates are:

- A specified speaker's final speaking-search page.
- A specified speaker's numbered intermediate search result.
- The final two pages in chronological order.
- The number of pages strictly between those endpoints.

Each predicate supports equality or explicit negation. Speaker roles refer to the independently resolved quoted speakers; private IDs never turn into invented readable names. Query programs are reconstructed from the source question, rather than accepting an arbitrary program with a coincidentally correct value.

Required facts are both speakers' final pages and the requested sequence/gap result. Optional facts cover intermediate search steps and the complementary gap/sequence summary. Near-miss forbidden claims swap speaker attribution, negate a supported endpoint, reverse sequence order, or shift a known gap count. A forbidden claim is recorded only after a checked exact value proves the proposition **false**. Missing facts, UNKNOWN, EMPTY and inexact values cannot establish falsity. The finite forbidden list is explicitly nonexhaustive.

Plans retain chapter page order separately from `claim_order` (branch steps, branch endpoints, combined results, near misses). Each query contains its typed dependency graph and checked witnesses. The canonical reference answer contains the three required claims; optional graph facts can support a longer later synthesis.

Example from a synthetic fixture:

> The first speaker's final speaking page is page 6. The second speaker's final speaking page is page 8. The final pages in chronological order are pages 6 and 8.

The plan also proves intermediate steps and the one-page gap. It proves that swapping the speaker assignments or asserting a reversed chronological sequence would be false. These are execution semantics, not a claim of narrative/emotional understanding.

## Answer scoring

The extractor receives only the submitted text, not the expected answer or claim list. It independently parses each complete sentence into a typed proposition, then scores it against checked query results. The source procedure identifies its declared final step; that is an answer-independent alias for the final result. Required-claim recall uses distinct claims, so repetition does not improve coverage.

The bounded grammar accepts canonical statements plus explicit paraphrases such as:

- `The final speaking page for the first speaker is page 6.`
- `For the first speaker, the final speaking page is page 6.`
- `For the first speaker, speaking-search step 3 finds page 6.` when step three is the declared final step.
- `Chronologically, the final pages are 6 and 8.`
- `There are 2 pages strictly between the final pages.`

It checks optional and extra supported signatures, and detects false assertions even if absent from the forbidden list. Extra unparsed prose, unsupported predicates, out-of-range arguments and unresolved values stay **held**. For example, an added assertion that a speaker is angry is neither certified nor automatically declared false. No word matching to a required sentence can certify a longer clause containing additional unsupported assertions.

Metrics separate exact short-answer accuracy, required-claim recall, optional coverage, explicit forbidden claims, detected false assertions and unresolved clauses. `unsupported_assertions` and the within-grammar factuality flag remain null for unresolved or empty prose. A controlled answer passes only if its short answer is correct, every required claim is covered, and every asserted clause is supported. Correct short answers alone do not excuse wrong explanations. Style is not scored; an unrecognized stylistic sentence is held for later parsing/review rather than labeled a false fact.

To score externally supplied responses later:

```bash
bash scripts/benchmark1000.sh score-sentences \
  --store "$ROOT/sentences_v1" \
  --responses /path/to/sentence-responses.json \
  --out "$ROOT/sentences_v1.scores.json"
```

The versioned response file is:

```json
{
  "schema": "comics_qa.benchmark1000.sentence_responses.1",
  "store_manifest_sha256": "ACTUAL_SENTENCE_STORE_MANIFEST_HASH",
  "responses": [
    {
      "plan_id": "ACTUAL_PLAN_ID",
      "plan_sha256": "ACTUAL_PLAN_CONTENT_HASH",
      "answer": "Submitted sentence answer",
      "short_answer": [6, 8]
    }
  ]
}
```

Use the actual per-plan short-answer format (list or integer), IDs and hashes. These example values are placeholders, not a runnable model response. Missing responses count as missing/incorrect; duplicate/unknown IDs and stale hashes fail. Scores remain factual-contract diagnostics, not sentence admission or human/release approval. No Qwen request or LLM judge runs here.

## Validation and remaining work

The suite covers genuine synthetic graph proofs for sequence and count plans, independent checker execution, role/page/order swaps, negation, omissions, repetitions, supported paraphrases, extra false/unknown assertions, out-of-scope arguments, UNKNOWN-not-false, stale worlds, forged proofs and review flags, complete store publication/resume and scoring CLI/version binding. See STATUS for final test totals and bounded real artifacts.

P11 must prepare new task-specific packs and independently validate generated questions/prose. Existing VERB packs are not silently reused. New fact predicates require explicit typed proof rules and a versioned grammar/extractor; arbitrary prose cannot be promoted merely by attaching graph citations. All future sentence items require human review. Human crop/distractor/question review and intake remain deferred until after generation, Qwen and automated validation, before final freeze/export.

Validated on 2026-11-01: **201 tests pass**. A bounded Blue Exorcist c001 preparation produced two real plans with six required, eight optional and ten proved-false claims; separate checking passed 2/2, exact resume passed, and scoring their canonical reference answers passed 2/2 as an explicit reference fixture (no model inference or model-accuracy claim). Artifacts: `/tmp/comicsqa-sentence-trial-v1`, `/tmp/comicsqa-sentence-trial-v1.check.json`, `/tmp/comicsqa-sentence-reference.scores.json`. Existing pool 3,762 still validates and all 142 frozen files remain unchanged. Full `sentences_v1` preparation/check remains user-run.
