# CRL-2: independent proof checker

CRL-2 verifies a saved CRL-1 result against the selected CKG-1 chapter and CKG-2 visibility
companion. It implements its own operation semantics in `proof_rules.py`; neither those rules
nor `ProofChecker` calls `Interpreter`, its evaluator, or its operation helpers. Parsing,
static types, canonical serialization, CKG structural schemas, name normalization, and artifact
IO are shared contracts. The checker verifies the program, not the natural-language question.

## Run

From `ComicsQA_Benchmark/Code`, check the result you already generated:

```bash
bash scripts/check_crl.sh \
  --result /tmp/crl-example.json \
  --out /tmp/crl-example.check.json

python3 -m json.tool /tmp/crl-example.check.json | less
```

For `count(texts(ctx()))` on Dragon Ball c002, expect `status=VERIFIED`, `proof_valid=true`,
`accepted_for_generation=true`, and `result_value=183`. Run this on the host holding the saved
`/tmp` file. The checker needs no GPU, model, new annotation job, or full-collection run.

The launcher defaults to `/data/151-3/comics/ComicsQA_Benchmark`. Use `BENCH_ROOT=/other/root`
or override `--graphs` / `--visibility` on another machine. Paths recorded in the result may
differ after relocation, but all four input content hashes must match. The checker reads only
the explicitly supplied artifact directories, never paths taken from the submitted proof.

To also bind the saved result to the query you intended to run:

```bash
bash scripts/check_crl.sh \
  --result /tmp/crl-example.json \
  --expected-program 'count(texts(ctx()))'
```

The optional query comparison uses CRL's syntactic canonical hash, not general logical
equivalence. The default verifies the program stored in the result.

Omit `--out` to print the report. Output files are published atomically and never overwritten;
choose a new filename for another check. The saved CRL result and graph/visibility files remain
unchanged. Outputs inside the evidence directories are rejected.

| Exit code | Meaning |
|---|---|
| 0 | Trace verified; inspect `accepted_for_generation` separately |
| 1 | Proof rejected; report identifies the first mismatching field |
| 2 | Invalid/unreadable/stale inputs, invalid CLI policy, or output error |

## What is checked

1. The CLI validates selected artifact checksums and the CKG-2 build's pinned CKG-1 manifest,
   and matches the result's four input hashes to those artifacts. CKG structures and companion
   visibility summaries are validated before checking steps.
2. The stored AST is type-checked; canonical syntax, program hash, chapter, language/schema
   version, and policy must match. No proof can promote `open` coverage into a closed status.
3. The checker walks the canonical AST and reconstructs its execution using independent rules.
   Each submitted step must match its expression, operation, type, value, status, exactness,
   ordering flag, sequential ID, and child IDs. Variables, sequential `let` bindings, lambda
   members/capture, and all evaluated branches are bound to the actual program. Extra, missing,
   reordered, cyclic, or substituted trace steps are rejected.
4. Graph queries enumerate the complete trusted relation table, not just submitted facts. Each
   step's fact IDs, coverage IDs, visibility IDs, node references, range pages, and minimum trust
   must match independently computed support. Missing-GT pages, incomplete domains, tied
   ordinals, ambiguous winners, and gated evidence keep their CRL-1 semantics.
5. Referenced derived graph facts are checked against their premise relations: identity,
   aliases, presence, dialogue lines, speaking presence, and co-presence. Premise closure must
   appear in the final proof. Source annotations and visibility decisions remain trusted inputs
   under the pinned CKG policy; this stage does not redo visual review or raw OCR alignment.
6. The final value/type/status/exactness, rendered names/page indices, eligibility, root,
   support pages, premise closure, answer-name evidence, and trust are independently checked.
   A visible alias does not authorize an unseen canonical name.

Diagnostic `reason` strings are required to be strings but are not certified semantic claims;
wording changes do not invalidate a mathematically identical proof. The meaningful failure
semantics are `status`, value, exactness, and the checked evidence. The producer's
`proof_check="pending_CRL-2"` field is not a verifier assertion and is never used to accept an
answer. The separate checker report is the verification record.

The checker accepts the current CRL-1 profile, including typed operations that deliberately
return `UNKNOWN` for unavailable evidence. Unsupported future language versions fail closed.
`ERROR` results—including invalid programs and exhausted interpreter budgets—are rejected;
partial execution is not a proof. Checker limits are 50,000 steps by default and 128 MiB per CLI
result file. `--max-steps` sets an explicit checker budget; a producer-declared budget above it
is rejected. `--require-verified-coverage` must match the strict coverage mode used to produce
the result; by default the accepted CKG `closed_assumed` policy is retained.

## Verification versus generation acceptance

`proof_valid=true` means the trace agrees with the independent semantics. It does **not** mean
that a usable answer exists. For example:

| Program on Dragon Ball c002 | Result | Proof valid | Accepted for generation |
|---|---|---|---|
| `count(texts(ctx()))` | 183, exact | true | true |
| `at_least(pages_with(char("Bulma")),1)` | true, lower bound | true | true |
| `count(pages_with(char("Bulma")))` | UNKNOWN | true | false |

A verified `EMPTY` or `AMBIGUOUS` trace is also ineligible. Internal App/Text/Turn/Map outputs,
unverified rendered names, and most nonexact answers remain ineligible under CRL-1's policy.

`accepted_for_generation=true` is permission to proceed to **GEN-1's candidate checks**, not
an accepted final benchmark question. GEN-1 still applies necessity, robustness, shortcut
controls, readable names in actual wording, answer balancing, and subsequent review rules.

## Output and API

Reports use `comics_qa.crl_check.v1` and contain:

- `status`: `VERIFIED` or `REJECTED`;
- `proof_valid`, `accepted_for_generation`, and `checked_steps`;
- `errors`: first mismatch path/message, empty on success;
- on success: checked program hash, result status/exactness/value;
- from the CLI: original result file hash, current input artifact hashes, checker implementation
  hashes, and the checker policy.

The result hash binds a report to the exact saved JSON. The CLI hashes the current checker code;
it does not require producer code files to remain at their old paths or byte hashes. Correctness
is established by independent semantics and pinned evidence, not by trusting the producer's
self-reported code hashes. This is reproducible validation, not cryptographic authentication of
the artifact publisher. Treat the supplied CKG manifests as trusted evidence snapshots.

```python
from comics_qa.tasks.graph.crl.artifacts import load_world
from comics_qa.tasks.graph.crl.proof_checker import ProofChecker

graph, visibility, sources = load_world(graph_dir, visibility_dir, chapter_id)
report = ProofChecker(graph, visibility).check(saved_result)
```

The in-memory API validates graph/visibility structure and program semantics. It does not
know their original file bytes; the CLI additionally verifies `inputs_sha256`. A caller using
the API must pin the evidence itself (or use `verify_input_pins` from `check_crl.py`). Neither
interface rescans raw images/annotations or unrelated chapters.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_crl*.py' -v
python3 -m unittest discover -s tests -p 'test_ckg*.py' -q
```

`test_crl2.py` includes the existing semantic corpus, a sweep over all 83 registered operations,
and adversarial tests for altered answers, coherent count forgeries, missing/foreign evidence,
coverage/trust/order promotion, incorrect rendered names, lambda substitution, broken derivation
premises, topology tampering, mismatched programs/policies, stale input pins, strict JSON, and
safe output publication. Tests disable the producer's execution methods while checking a proof
and deliberately break the producer to confirm rejection. The checked input dictionaries and
saved artifacts are never modified by verification.

Validated 2026-10-28: 47 checker tests, 30 CRL-1 tests, and 57 CKG tests pass. Independent
checking exposed a producer bug in `longest_streak` for computed scopes with repeated interior
pages; CRL-1 now deduplicates page membership before counting the run. The synthetic regression
verifies the correct three-page streak. Existing text-count/presence results are unaffected.

## Optional CKG-3 input

Pass the same `--rich <companion-root>` used to generate a rich result. The checker verifies all
six artifact pins and `rich_evidence_sha256`, validates the CKG-3 derivations, and independently
enumerates full quote matches / literal name-form text regions. Missing/mismatched companion
hashes, fabricated support, altered answers and false exactness are rejected. Rich facts retain
source premises in the pinned companion; they are transported as verified source facts rather
than importing CKG-3 record IDs into CKG-1's derivation-premise namespace. OCR coverage is checked
alongside human text-box coverage. See [the operator contract](README.md#optional-verified-ocrlexical-profile-2026-10-29).
