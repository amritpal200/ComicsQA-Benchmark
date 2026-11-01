# P09 one-clause contrast pairs

This additive P09 profile pairs two independently admitted questions on the **same unmodified chapter**. It changes either one branch-depth parameter between two and three next-speaking navigations, or the stated search-start boundary to immediately after the earliest first speaking witness. Every other recipe parameter remains fixed. These are single semantic condition changes; dependent template condition numbers or start references are rendered consistently.

Both questions must have exact, distinct answers, full native admission receipts and independently checked source/program/wording, name/OCR, clause, page and visual dependencies. Each source admission is freshly reproduced before use. UNKNOWN, EMPTY and coincident/same answers cannot become valid contrast answers. Every edited question passes its own original gates; changing a clause does not inherit admission from its partner.

This stage does not edit pixels or graphs. Masked-image variants, rebuilt edited worlds, residual-clue checks and visual-unknowability certificates remain separate unfinished P09 work. No UNKNOWN result is claimed as visual unknowability.

## Run

From `ComicsQA_Benchmark/Code`, use the existing benchmark environment. The commands use CPU; no new package or Qwen inference is required.

```bash
ROOT=/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000

bash scripts/benchmark1000.sh contrast-pilot \
  --source "$ROOT/branch_v1_admission" \
  --out "$ROOT/contrast_v1"

bash scripts/benchmark1000.sh check-proofs \
  --store "$ROOT/contrast_v1" \
  --out "$ROOT/contrast_v1.check.json"

bash scripts/benchmark1000.sh verify-store \
  --store "$ROOT/contrast_v1"
```

`--bench-root PATH` configures the data root. Repeated `--chapter CHAPTER` restricts scope. Defaults are `--per-chapter 2 --max-variants 8 --max-ablation-pages 16`: at most two retained pairs and eight edited-question executions per chapter. Each retained pair contains **two QA members**; pair counts and member counts are distinct. Each seed offers at most two depth edits and one search-start edit, and each member path can be used only once within a run. With the current 11 branch seeds in four chapters and the default cap, at most eight pairs (16 members) could be retained before evidence failures; broader seed support is still needed for the final paired quota. An unproved or held variant is recorded privately and never retained. Search is bounded and nonexhaustive.

The source must be an admitted-native store of the supported branch grammar. Existing full `branch_v1_admission` is suitable. This version rejects reviewed rich-world overlays pending a separate ablation profile. Alias decisions already present in a source receipt are revalidated; no alias is approved automatically.

Repeat an identical command to resume. Source manifests, seed contents, graph/visibility/rich snapshots, code and budgets are pinned. A changed configuration needs a fresh output path. Atomic create-only publication, per-chapter checkpoints and an exclusive writer lock preserve completed artifacts. Generation performs full member admission inline, so do **not** run `admit-native` on this separate pair store.

## Contract and downstream behavior

A private `contrast_pair.1` certificate contains both immutable admitted members, the exact semantic delta, and explicit unchanged-image/world scope. Two `contrast_member.1` views retain their original task proofs and measured complexity, receive primary group `paired`, and bind to the whole pair. Their underlying branch certificates keep their original group; the paired view does not rewrite the source member. Both human/release statuses remain pending.

The store loader validates paired certificates, both member views, seed hashes, chapter/checkpoint/decision bindings, counts and regenerated summaries. An incomplete, mixed or altered pair fails validation. Existing store/proof/pool readers support this schema; old stores remain unchanged. Pool deduplication preserves the two intentional members. Both selectors enforce all-or-none pair closure and prevent selecting a new paired task again as a standalone or another pair member.

Private review sampling treats these pairs as atomic units. Requested sample size is an upper bound in QA members, so a pair-only sample requested at size one contains zero members. This clustered sampling has no claimed individual-item binomial error bound. Pair-wide adjudication/release integration is still pending and cannot be bypassed with a single-member review.

For model evaluation, `contrast.public_input(member)` supplies one question, answer format and ordered original images. It omits answers, proofs, partner question, pair ID and role. Evaluate the two requests separately. Private `contrast.units(items)` keeps paired review/scoring units available without placing them in model inputs. Native/MN5 pack preparation and final export remain later work.

## Scoring

Predictions are a JSON object mapping opaque **member item IDs** to answers, using a JSON list for a page sequence or integer for a count:

```bash
bash scripts/benchmark1000.sh score-contrast \
  --store "$ROOT/contrast_v1" \
  --predictions /path/to/contrast-predictions.json \
  --out "$ROOT/contrast_v1.scores.json"
```

The scorer reports exact member accuracy and **both-correct pair accuracy**. Missing predictions count as incorrect; unknown item IDs and incomplete pair stores fail. No LLM judge is used. Equal guessed answers for both members cannot earn full pair credit because verified expected answers differ.

## Validation and limits

The suite covers positive synthetic proofs, one-condition and exact-answer checks, forged view/review changes, source uncertainty, resource limits, atomic store resume, incomplete-pair rejection, reference/CP-SAT closure, standalone duplication, review-unit sampling, public input separation and paired scoring. All 187 tests pass, including full independent admission replay of both synthetic members and CLI scoring. See shared STATUS for bounded real validation and saved artifact paths.

Full collection jobs remain user-run. This extension does not prove the 100-paired-member quota feasible, approve human review, publish a merged pool or complete masked-input P09. Human crop/distractor/question review and intake remain deferred until after generation, Qwen and automated validation, before final freeze/export.

Bounded real validation on Blue Exorcist c002 and Food Wars c002 tried three variants each and retained zero pairs per chapter: two endpoint collisions and one unproved range variant. These are legitimate rejection outcomes, not approved pairs. The Blue Exorcist empty store resumes exactly, and both empty stores validate; its standalone report is verified=0/rejected=0. Existing `pool_v1` still validates at 3,762 candidates, and all 142 frozen legacy files remain unchanged. No full collection contrast job was launched.
