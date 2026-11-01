# Two-branch and long-relational graph QA

This additive P06/P07 extension follows two different quote-identified speakers through separate two- or three-step speaking-page chains, then combines their endpoints. It reads existing CKG-1/2/3 worlds without modifying legacy generators, coverage decisions, quotas or completed artifacts. The grammar version is `branch_relations.1`.

| Family | Exact answer | Final operation |
|---|---|---|
| `branch_chain_pages` | Ordered page sequence | Two distinct final positions in increasing chapter order |
| `branch_chain_gap` | Nonzero integer | Pages strictly between the two final positions |

Questions state the quoted references, inclusive search range and every ordered navigation condition. The range starts after both references. Each branch starts immediately before the range and repeatedly finds its speaker's next speaking page. An unresolved earlier predicate blocks navigation; missing annotations never establish absence. Sequence order follows the chapter, rather than first/second speaker order.

For example, in a synthetic fixture, quotes on pages 1 and 3 identify two speakers. Inside range 4–10, their paths are 4→5 and 7→8. The sequence answer is `[5, 8]`; the gap answer is `2`. These illustrate semantics, not actual benchmark items.

## Run

From `ComicsQA_Benchmark/Code`, use the existing benchmark environment. This stage needs no new dependency or GPU.

```bash
export BENCH_ROOT=/data/151-3/comics/ComicsQA_Benchmark

bash scripts/benchmark1000.sh branch-pilot \
  --bench-root "$BENCH_ROOT" \
  --out "$BENCH_ROOT/reports/benchmark1000/branch_v1"

bash scripts/benchmark1000.sh admit-native \
  --bench-root "$BENCH_ROOT" \
  --proposal-root "$BENCH_ROOT/reports/benchmark1000/branch_v1" \
  --max-ablation-pages 16 \
  --out "$BENCH_ROOT/reports/benchmark1000/branch_v1_admission"

bash scripts/benchmark1000.sh check-proofs \
  --bench-root "$BENCH_ROOT" \
  --store "$BENCH_ROOT/reports/benchmark1000/branch_v1_admission" \
  --out "$BENCH_ROOT/reports/benchmark1000/branch_v1_admission.check.json"
```

Full collection jobs remain user-run. Repeat identical commands to resume. Changed code, sources, scope or budgets require fresh output paths. A writer lock and immutable, source/config-bound chapter checkpoints protect publication. Resume independently rechecks saved proposal proofs. Admitted records can later enter a new unified pool; existing `pool_v1` is preserved.

Optional repeated `--chapter CHAPTER` arguments restrict scope. Per-chapter defaults are `--per-family 3 --search-budget 1000 --window 10 --min-window 4 --max-shift 20 --max-steps 3 --probe-budget 192 --dependency-budget 128`. `--max-steps 2` restricts both branches to two navigations. Reference-pair and recipe streams are visited round-robin within caps. Explicit shorter/shifted windows reuse the existing coverage-aware enumeration. Search is nonexhaustive; zero yield does not establish impossibility.

The predicate budget limits new checked discovery queries, with a separately bounded anchor-query budget. The dependency budget separately limits main/counterfactual recipe executions during preselection. Cached queries cost no new execution; each retained recipe is freshly executed again. Later admission has its own ablation-page budget. Diagnostics distinguish these counts, uncertainty, dependency rejections and exhaustion. Budget exhaustion never proves emptiness or necessity.

## Proofs and classification

Programs use existing typed CRL operators and the independent `coverage_recipe` checker. Legacy interpreter/checker registries are unchanged. The sequence filters a finite ordered page range by equality to two proved endpoints, without assuming a complete character collection.

Before retention, both whole branches and every navigation must independently affect the final answer. A branch intervention substitutes the other endpoint in the final operation. A navigation intervention holds its preceding position and recomputes the remaining suffix. Every outcome must be independently checked, known `OK` or `EMPTY`, and different. UNKNOWN/AMBIGUOUS cannot establish necessity. Coincident endpoints, zero gaps and numeric answer leakage are rejected.

Normal native admission additionally checks source/program/wording bindings, verified quote agreement, rendered name eligibility, clause and page ablations, OCR-only answerability, at least three necessary visual pages and resolved-path deduplication. Swapping speakers preserves the deduplication key for these commutative operations. Full resolved paths, source reference positions, identities and range start stay bound; redundant upper bounds do not create new paths.

Passing candidates receive group `branch_combine`, branch count two and the **maximum** necessary branch depth as meaningful hops. Two parallel two-step chains have depth two. Individual branch depths and combine count are stored separately.

The additional `long_relational` tag requires all dependency checks, at least three necessary visual pages, at least three necessary support pages spanning five positions, at least three necessary navigation clauses and at least 81 words. Whole-branch labels are not counted again as navigation clauses. Validation recomputes certificates and verifies the root tag/certificate; length or supplied metadata alone cannot grant this classification. These are operational dependency measurements, not established human difficulty or narrative entailment.

Private compositional probes remain auxiliary. Human review and release remain pending. Crop/distractor/question review and intake are deferred until after generation, Qwen and automated validation, as decided on 2026-11-01. This stage does not run Qwen or establish final 1,000-item feasibility.

## Validation

171 tests pass, including both answer types, all depth combinations, independent checker execution, all branch/navigation interventions, correct parallel-depth measurement, open coverage, same-speaker rejection, certificate tampering, deduplication, private probes, budgets and immutable resume.

A bounded two-chapter trial at 150 recipes per chapter retained zero proposals: 138 unproved required probes, 115 insufficient known paths and 47 coincident endpoints. Both search caps were reached; no dependency execution was attempted. Its empty proposal/admission stores are valid. A larger bounded Blue Exorcist c002 trial at 1,000 recipes/depth two retained one proposal per family with 14 independently checked main/intervention executions. Both proposals passed full native admission, with five/six necessary visual pages and measured long-relational certificates. Standalone full certificate replay passed 2/2, generation/admission resume passed, and the pool inventory recognizes both new groups/tags. The existing 3,762-item pool validates and all 142 legacy files are unchanged. See `docs/STATUS.md` for artifact paths. No full collection job or human review was run.
