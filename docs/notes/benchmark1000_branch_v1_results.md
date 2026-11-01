# Branch v1 results — 2026-11-01

The user completed generation, native admission and standalone proof validation across all 50 chapters. The run succeeded. It improves certified branching and long-relational supply, but does not complete the balanced 1,000-item benchmark.

## Verified artifacts

Read-only checks validate all 52 generation output hashes, 11 native-store outputs and 25 admission output hashes. Generation/admission config hashes and saved new-layer code fingerprints match current files. All 50 generation checkpoint config/payload bindings verify. The saved proof report binds to the admission manifest and each exact admitted item; all 11 rows report reproduced complete native admission certificates. This review did not rerun all expensive proofs; the user-run `check-proofs` report supplies those replays.

Artifacts under `/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/`:

- `branch_v1/`
- `branch_v1_admission/`
- `branch_v1_admission.check.json`

## Results

| Measurement | Result |
|---|---:|
| Chapters searched | 50 |
| Proposals / admitted | 11 / 11 |
| Held / duplicate | 0 / 0 |
| Saved proof replay verified / rejected | 11 / 0 |
| Certified branch-combine questions | 11 |
| Certified long-relational questions | 7 |
| Necessary visual pages | 4 for 3 items; 5 for 8 items |
| Private auxiliary probes | 88 |
| Seen / unseen | 3 / 8 |
| Distinct typed answers | 6 |

All retained questions are `branch_chain_pages`, with exact sequence answers; there are no `branch_chain_gap` questions in this run. This describes bounded search yield, not impossibility of that family. Earlier depth-two bounded tests produced a real admitted gap question.

All 11 items have measured maximum branch depth three: five have depths `[3, 2]`, six `[2, 3]`. Their five navigation clauses do not become five sequential hops. Word counts are 175–184. Four items fail only the long support-span threshold: three Food Wars c002 items span 4, 3 and 3 positions; one Blue Exorcist c002 item spans 4. Their ordinary branch admission remains valid. Do not weaken the long tag to include them.

| Chapter | Admitted |
|---|---:|
| Blue Exorcist c001 | 2 |
| Blue Exorcist c002 | 3 |
| Food Wars c002 | 3 |
| Jujutsu Kaisen c001 | 3 |

No character-identity target or sentence-answer supply is added by these sequence answers.

## Search limits

There were 224 checked main/dependency executions. Blue Exorcist c001 reached its dependency budget. Blue Exorcist c002, Chainsaw Man c001, and both Hell's Paradise chapters reached recipe-search budgets. These are unresolved search limits, not coverage approvals or negative feasibility certificates.

Recorded rejections: 3,323 insufficient known topologies; 929 unproved required probes; 600 coincident endpoints; 370 zero-gap/numeric-overlap cases; 136 repeated resolved paths; one dependency-budget exhaustion. The latter is a resource status. No automatic policy or evidence relaxation was applied.

## Existing pools and next work

The existing 3,762-record pool still validates. Its conservative source/path keys do not overlap any of these 11 admitted records; a later additive merge would have 3,773 representatives under that same deduplication rule. No merged pool has been published, and no stronger cross-family semantic-equivalence claim is made. All 142 frozen legacy files remain unchanged.

All 11 human/release statuses remain pending. Human crop/distractor/question review and intake stay deferred until after generation, Qwen and automated validation, before final freeze/export.

Recommended next implementation: P09 **one-clause contrast pairs** first, using the existing graph-backed questions, an explicit single semantic change, and independently proved distinct answers for both members. Preserve pair identity through admission/selection/scoring. Masked-image variants additionally need pixel/world agreement and residual-clue checks; UNKNOWN alone must not become a visual-unknowability claim. Then complete P10 claim-backed sentence preparation before P11 Qwen. Broader generation/coverage gaps and final quotas remain unresolved.
