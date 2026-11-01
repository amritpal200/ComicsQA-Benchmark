# Necessary character-switch search

`switch-pilot` is an opt-in, switch-only discovery mode (`necessary_switches.1`). It reuses the existing explicit-range question grammar, `coverage_recipe` execution and independent checker. It changes which candidates get retained, not what answers or dependency claims are accepted. Old family, coverage and targeted-set outputs remain immutable.

## Run

From `Code/`, use fresh output roots:

```bash
bash scripts/benchmark1000.sh switch-pilot \
  --per-family 3 --max-executions 9 --search-budget 1000 \
  --window 10 --min-window 4 --max-shift 20 \
  --probe-budget 192 --dependency-budget 128 --max-windows 4 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/switch_v1

bash scripts/benchmark1000.sh admit-native \
  --proposal-root /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/switch_v1 \
  --max-ablation-pages 16 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/switch_v1_admission
```

Both run on CPU. Scope defaults to the full collection; repeat `--chapter ID` for a smaller run. Generation checkpoints per chapter and admission per proposal. Resume with exactly the same code, source snapshots, scope and budgets. Changed configuration requires a fresh output root. Do not rerun completed baselines in place. No Qwen or new annotation job is required.

A larger verification budget does not relax a gate. It permits more checks. Other than its existing chapter-wide support-page budget, admission is unchanged and may still hold an answer-proved path for visual dependence, names, wording, source agreement or other reasons.

## Preselection contract

1. Reuse known-positive topology to propose a two- or three-navigation walk in an explicitly stated range.
2. Resolve quote identities and required page/character predicates with independently checked probes, preserving UNKNOWN.
3. Apply the existing numeric-overlap prefilter. Do not spend dependency work on a known wording hold.
4. Independently execute the original complete recipe.
5. For each identity switch, re-execute the entire dependent suffix while keeping the previous character. For every navigation, re-execute while bypassing that navigation, using the same typed interventions as admission.
6. Retain the window only when all interventions prove a different answer or a proved EMPTY result. A same supported answer is redundant. UNKNOWN, ambiguity or another unsupported answer does not establish necessity. Check switches first and stop at the first blocker; unchecked interventions remain explicitly counted.
7. Only passing windows consume `--max-windows` retained slots. Then the usual proposal/execution caps apply. Every final proposal is independently executed again and must separately pass full native admission before it is a candidate.

This prevents known redundant early windows from filling the candidate pool and crowding out later necessary paths. It does not prove such paths exist in every chapter, replace visual-page ablation or award difficulty merely from program/word count. Existing two-/three-navigation syntax corresponds to three/five navigation-plus-switch interventions; certified meaningful hops still come from admission.

## Budgets and output

Existing source-anchor, window-trial and predicate-probe budgets remain separate and unchanged; see [coverage-aware windows](COVERAGE_WINDOWS.md).

`--dependency-budget` caps **new full checked recipe executions per chapter**, including original recipes and bypasses. Default: 128. Reusing an identical engine/program result within a pinned chapter uses the cache and is reported separately. This budget is additional work, not part of `--max-executions` (final proposal attempts) or `--probe-budget` (atomic discovery predicates). It bounds expensive suffix replay and never turns unfinished work into absence or failure of a mathematical claim.

Inspect:

- `report.json`: `dependency_search` totals, first-blocker outcome counts, budget-hit chapters, final proposal counts and discovery-rejection categories.
- `diagnostics.json`: per-chapter `probes.dependency_search` records, with main/intervention results, engine/program/execution hashes, independent-check flag, labels, remaining unchecked interventions and resource limits.
- `chapters/*.json`: the same pinned diagnostics and final executions. Retained execution rows link their dependency preselection record. Native proposals keep the established proof-bearing schema and contain no automatic admission/complexity approval.

Outcomes distinguish `redundant_switch`, `redundant_navigate`, `unproved_switch`, `unproved_navigate`, `main_answer_unproved`, `passed` and `dependency_budget_exhausted`. Counts describe the first blocking intervention for each assessed recipe, not every possible failed step. Exhaustion stops that chapter's dependency search; partial records cannot become retained windows. Other family entries in the common report schema stay zero because this mode searches only `speaker_walk`.

All discovery records are private preselection diagnostics. Their compact checked result/hashes are not formal candidate admission receipts. The recipe and intervention labels reconstruct the exact replay program; complete answer/admission proofs remain in the established native stores. No source graph facts, coverage status, visibility/alias decisions or legacy interpreter rules are changed.

## Validation and limits

Regression coverage includes a schema-valid synthetic walk passing all three dependency interventions and unchanged native admission, source immutability, checked EMPTY versus UNKNOWN, redundant-switch early rejection, independent-check disagreement, all five interventions for a three-navigation walk, cache/budget accounting, retained-window caps and resume/config binding. Real bounded trial outcomes are recorded in `docs/STATUS.md`; synthetic recovery is not a claim of real collection yield.

A zero-proposal run can be a correct result: inspect whether topology/predicates, redundancy, unresolved bypasses or resource limits prevented retention. Increasing budgets is useful only when the recorded limit blocked exploration. Keep redundant paths excluded; targeted evidence review remains necessary for unresolved proofs. Cross-run inventory/selection needs explicit deduplication, and the final 1,000-item benchmark, Qwen wording and human review remain later stages.


### Bounded implementation checks — 2026-10-31

All 134 benchmark1000 tests pass. A schema-valid synthetic two-navigation walk reaches page 7 with all three semantic interventions necessary and passes unchanged native admission; source graph/visibility/rich objects remain unchanged. Three-navigation regression verifies all five intervention labels.

A real CPU trial over `blue-exorcist__c002` and `spy-x-family__c001` uses search budget 100, predicate budget 64, dependency budget 40, proposal cap 1 and final execution cap 2. It checks 16 candidate recipes, performs 32 independent dependency executions and rejects all 16 for a redundant first switch. Other trial windows lack known topology or required predicate proof. No dependency budget is exhausted and no proposal is emitted. This demonstrates filtering, not real necessary-walk recovery. Exact resume produces the same report; unchanged native admission accepts the empty store with zero candidates. Local artifacts: `/tmp/comicsqa-switch-trial-1`, `/tmp/comicsqa-switch-trial-1-admission`.

Archived stores still validate 39 (`families_v1_admission`), 93 (`coverage_v1_admission`) and 11 (`coverage_v1_sets_admission`) candidates; all 142 frozen legacy files match. Full collection search is user-run and remains unexecuted by the implementation agent.
