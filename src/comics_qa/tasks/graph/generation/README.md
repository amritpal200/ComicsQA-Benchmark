# GEN-1: first graph-grounded question candidates

GEN-1 runs on CPU using the Python standard library. It reads completed CKG-1 chapter graphs
and CKG-2 name-visibility companions, generates typed CRL programs and fixed question templates,
checks them with both CRL-1 and CRL-2, applies acceptance gates, then selects a balanced subset.
It does not run Qwen, modify evidence, or export a final public benchmark.

## Run a sample

From `ComicsQA_Benchmark/Code`:

```bash
bash scripts/build_gen1.sh \
  --chapter dragon-ball__c002 \
  --max-candidates-per-chapter 120 \
  --max-items-per-chapter 24 \
  --out /tmp/gen1-preview

cat /tmp/gen1-preview/report.md
```

If VS Code Remote SSH is connected to the same host:

```bash
code /tmp/gen1-preview/report.md
code /tmp/gen1-preview/chapters/dragon-ball__c002.json
```

The checked snapshot produced 24 selected questions from 120 proposals, with 66 passing the
semantic gates before selection. This is a bounded sample, not a full collection build.
All page numbers are **1-based supplied chapter image positions**. A spread counts once.

## Full collection (user-run)

```bash
bash scripts/build_gen1.sh
```

Default output:

```text
/data/151-3/comics/ComicsQA_Benchmark/items/gen1/v1/
```

All chapters in the CKG-1 manifest must have matching CKG-2 companions. The builder refuses to
silently reduce the collection to an intersection. `--chapter` can be repeated for an explicitly
selected subset. `BENCH_ROOT=/another/root` relocates the default data root; `--graphs`,
`--visibility`, and `--out` can also be overridden individually.

Policy is in `configs/tasks/gen1.json`. Defaults: seed 42, at most 600 distinct proposals per
chapter, at most 80 selected items, at most 24 items from one family. These are **search and
selection ceilings**, not promised yields or exhaustive enumeration. Some chapters can have
zero selected items. Every chapter remains in the report, with its rejection counts and shortfall.

## Resume and reproducibility

Rerun the **same command and overrides** with `--resume`:

```bash
bash scripts/build_gen1.sh --resume
```

Interrupted builds retain `<out>.partial/` and completed chapter checkpoints. Resume verifies and
reuses those chapters; the interrupted chapter is regenerated. Checkpoints are published
atomically and carry their payload checksum, build fingerprint, and input hashes. Completed
outputs are verified and reused without generation. The output lock permits only one writer.
No existing final output is replaced.

Changing code, policy, selected chapters, seed, or dependency manifests requires a **new output
path**. Resume also verifies current selected graph/visibility shard bytes against their manifests.
It does not rescan raw images or OCR; source freshness remains the CKG build/verification contract.
Outputs cannot overlap the supplied graph or visibility directories.

A rejected candidate is normal and counted. Invalid generated programs or any CRL-1/CRL-2
disagreement stop the build with an error; they are never silently filtered as low-yield examples.
Exit codes: 0 completed/verified, 2 build/input error, 130 interrupted.

## Generated families and strategies

| Strategy | Current shapes |
|---|---|
| Answer-first aggregates | Choose configured count targets (2–12 by default), then search page-level character-depiction, text-region, and named-speaker text counts matching those targets |
| Forward typed shapes | Unique dialogue-region speaker, a named character's next appearance after an observed page appearance, presence, and text-count comparison across two pages |
| Target-first constraint accretion | Choose a readable named character, combine two or three positive drawing/speaker-page clauses, retain a unique intersection, and test removal of every clause |

Forward search enumerates this versioned shape library; it is not arbitrary enumeration of all
83 CRL operations. Searches are seeded and bounded. Constraint search permits at most the
configured emitted candidates per target and examines at most 64 times that budget for each
clause count. Proposals from the three strategies are interleaved to avoid exhausting the whole
budget on the first strategy. Unsupported quote, mention, panel, spatial, world-edit, and
determinability operators are excluded by the static generation profile.

Character questions use named identities; anonymous page-local groups cannot become a named
answer. Character-depiction counts count appearances, not distinct people. Text-region counts
count human text boxes. Speaker questions use human-linked dialogue regions. These distinctions
are explicit in the templates; they do not rely on unverified balloon classes or OCR transcripts.

All items provide the full chapter context, including pages without human annotations. Search
subspans constrain the question, not which images are shown. Missing coverage remains UNKNOWN.
The current profile separates single-page baselines from multi-page questions with `scope_tier`.
The design's L1–L6 difficulty label is left `null`, rather than equating a page count with semantic
difficulty. Raw operation counts, clause counts, visual page span, and support are retained for
later difficulty classification. No level-specific quota or calibrated difficulty claim is made.

## Gates and their limits

| Gate | Implemented check |
|---|---|
| G1 | Typed programs, allowed page-core operations, valid shape contract, H/V support |
| G2–G5 | Eligible result, selection uniqueness/margins, independent proof verification, and complete relevant coverage for non-monotone queries; only positive top-level `at_least` can use lower bounds |
| Name visibility | Exact wording form must resolve to the intended identity and pass CKG-2 visibility; rendered character answers and accepted answer forms must be verified too |
| G6 | Execute each constraint-removal program; reject unchanged answers or inconclusive UNKNOWN relaxations. Store elimination profiles. Atomic shapes have no removable descriptive clauses and are labeled as such |
| G7 | Withhold each evidence page in turn, delete dependent facts transitively, mark its visual coverage absent, and check the new result independently. Require necessary evidence; Multi-page shapes require at least two necessary visual-support pages |
| G8 | Reject answer/input identity coincidences, names/numbers leaking the answer, visual-free answers, and one-page shortcuts in multi-page shapes. Test each anchor alone and a lexical-evidence-only world. Enforce distribution quotas during selection |
| G9 | Strict page-core applicability audit plus execution/checking after reversing relation/node/coverage storage order |
| G11 | Canonical program deduplication, answer/support-set cap, and family cap |

Page ablation preserves chapter indices and image placeholders but hides the removed page's
facts/readability evidence. It does not renumber pages or edit real annotations. Necessary and
redundant pages are both recorded. Anchor-only tests retain full-chapter lexical name visibility
so readability outside the anchor does not itself manufacture multi-page reasoning. The
lexical-only test removes human visual relations; it is **not** a model answering from complete
OCR transcripts. Full text-only and frequency baselines remain EXP-1 work.

For G9, W1–W6 are currently **inapplicable**: this profile uses no uncertain identity alternatives,
within-page reading order, panels, quote transcripts, A/M support facts, or spatial margins.
The record therefore reports `applicable_noise_worlds=0` and `noise_invariance_fraction=null`,
with a reason for each family. It separately records representation invariance. It does not
claim measured robustness to errors in accepted human annotations. New uncertain-evidence
families must add their applicable perturbation worlds before generation can use them.

Numerical answer leakage is checked conservatively: a count equal to a page number literally
present in its question is rejected even when the equality could be coincidental. Comparison
questions explicitly offer all three outcomes (`more`, `fewer`, `equal`); mentioning the full
answer domain is not treated as answer leakage.

G10 remains `pending_VERB-1`: these are fixed glosses tied to stored programs, not Qwen
paraphrases with a parse-back check. G12/human review remains pending. An accepted GEN-1 item
is a candidate for subsequent stages, not a final benchmark release.

## Balancing policy

Limits apply **per chapter**, so combining completed chapters preserves the two main caps.

- Frequent characters are the top two named identities by **trusted distinct-page presence**.
  All ties at the second-place cutoff are included. This is observed graph frequency, not a
  claim of complete whole-chapter annotation coverage. The metric, cutoff size, ties, IDs, and
  observed frequencies are recorded in each shard/report.
- Frequent-character answers are at most **30% of selected scalar character-name answers**.
  They are not divided by all questions. A chapter with only frequent-character answer candidates
  can therefore select no name answers. Numeric questions can still name these characters.
- Two-option answers are at most **5% of all selected questions**. This includes boolean answers
  and any other generated answer type whose configured answer domain has size two.
- Boolean questions are selected in true/false pairs, yielding 50% true within the required
  45–55% range. A pool with only one polarity produces no boolean items. Small collections may
  have no booleans because of the 5% cap; the cap is not rounded up.
- Selection rotates through family/answer-value buckets, uses seeded tie breaking, and caps
  each family and each identical answer/support signature. Selection is deterministic and
  conservative, not a maximum-cardinality quota optimizer.

Hard limits are never relaxed to fill the requested item count. Before/after distributions,
shortfalls, family counts, and held-out candidate answers are recorded. `chance_level` uses a
uniform configured typed domain: count targets, chapter page positions, verified named identities,
two boolean values, or three comparison values. It is metadata, not an empirical model baseline.

## Artifacts and review

```text
build_config.json           effective policy, selected chapters, dependency/code hashes
chapters/<chapter>.json     checksummed payload with selected private items and rejection ledger
report.json                yields, rejection reasons, chapter-level quotas/distributions
report.md                  readable summary and example questions/answers
manifest.json              fingerprint, counts, hashes of all completed outputs
```

In a chapter shard, selected items are under `payload.items`. Each contains:

- question, answer type/value, verified accepted name forms, deterministic grading metadata;
- full ordered image references with original page IDs, relative paths, and image hashes;
- canonical program/AST/hash, CRL execution/proof, independent check and execution hash;
- gate results, clause-removal outcomes, elimination profiles, and page ablations;
- strategy/family/scope tier, unassigned difficulty level, support dimensions, version pins, and pending review/verbalization state.

These are **private** artifacts: they contain answers, stable IDs, annotations, and reasoning.
Only question/context fields should eventually reach the evaluated model through a separate
validated exporter. No public/model-facing export is created by GEN-1.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_gen1.py' -v
python3 -m unittest discover -s tests -p 'test_crl*.py' -q
python3 -m unittest discover -s tests -p 'test_ckg*.py' -q
```

29 GEN-1 tests cover real synthetic graph/visibility builds, two-clause identification with
independent removal proofs, incomplete pages, exact-form visibility, leaks, shortcuts, policy
caps/ties/denominators, deterministic selection, cross-process hash seeds, source immutability,
atomic checkpoints, interrupted/completed resume, changed inputs/configuration, missing companion
chapters, and zero yield without policy relaxation.
