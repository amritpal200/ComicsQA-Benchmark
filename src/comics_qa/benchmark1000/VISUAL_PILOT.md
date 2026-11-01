# P08: visual identity feasibility and four-image QA pilot

This implements a CPU preflight and a **human-review-pending pilot**, not the completed P08 release stage. Existing datasets, proof registries, name/alias decisions, native admission and the merged `pool_v1` remain unchanged. The new pilot is intentionally separate from native admission until visual/distractor review and a reviewed admission adapter are implemented.

Scheduling decision (2026-11-01): the user deferred human crop/distractor review and review intake to the final stage after all candidate generation, Qwen and automated checks. Keep visual items explicitly provisional/review-pending during preparation. Final reviewed admission/release still waits for actual final-version review; existing code/output gates are unchanged.

## Environment and commands

The image steps require Pillow >=10. Use your existing dedicated benchmark environment with Pillow by setting `BENCHMARK1000_PYTHON` to its Python. If needed, create a **new** environment (setup refuses to overwrite an existing path):

```bash
bash scripts/benchmark1000_setup.sh "$HOME/.cache/comicsqa-visual-v1"
export BENCHMARK1000_PYTHON="$HOME/.cache/comicsqa-visual-v1/bin/python"
```

From `Code/`, run these sequentially into fresh output roots:

```bash
bash scripts/benchmark1000.sh visual-preflight \
  --min-edge 48 --quote-budget 128 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/visual_preflight_v1

bash scripts/benchmark1000.sh visual-pilot \
  --preflight /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/visual_preflight_v1 \
  --per-chapter 4 --max-attempts 32 --seed 42 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/visual_pilot_v1

bash scripts/benchmark1000.sh check-visual \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/visual_pilot_v1 \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/visual_pilot_v1.check.json
```

All three accept `--bench-root ROOT`. The first two also accept repeated `--chapter ID`. Scope defaults to all source chapters; generation has caps and is not exhaustive. The agent runs bounded checks; the full collection jobs above are user-run. No GPUs, model weights, paid API calls, Qwen captions/inference or annotation regeneration are used.

Preflight and pilot checkpoint per chapter with one writer, atomic create-only publication, code/config/source hashes and explicit counters. Repeat the identical command to resume. Change output roots when source metadata, code, scope, crop thresholds, seed or budgets change. Pilot configuration pins the preflight manifest and Pillow version. Source-image corruption/hash or dimension mismatch fails rather than silently replacing a source. Recheck uses the recorded image paths; portable MN5 asset export remains a later integration task.

## What the preflight counts

`visual_preflight_v1/report.json` and `chapters/*.json` report trusted, non-generic appearance→identity links, cross-page link counts, usable reference identities and independently checked quote-speaker targets that can obtain four distinct identity options on other pages. The source is existing CKG-1/2/3 and full normalized Paddle/MAGI OCR agreement. Caption-based assertions are not added.

A usable crop has a uniquely admitted H/V `is_char` link, an in-bounds box, no pending geometry flag, minimum edge length, aspect ratio <=6, an available image path, no intersection with an annotated text box and no other annotated appearance covering more than 20% of the crop. These are deterministic quality filters, not proof of perceptual purity. Unannotated people/text and hard visual similarities still need review. Missing/generic identities, weak geometry and insufficient options stay excluded with reason counts.

Preflight uses metadata/existence checks for crops. Actual source hashes, dimensions and exact pixels are checked by the pilot and checker. No absence is inferred from missing annotations. Cross-page identity is only what the trusted source links establish; page-local unnamed clusters do not become persistent people.

`--quote-budget` limits considered source anchors per chapter; attempted independent programs and truncation are explicit. `counts` are sums of chapter-scoped counts; the top-level `unique_reference_ids` and `unique_verified_target_ids` are distinct source identity IDs across the selected chapters. A low verified target count is a capped, family-specific lower-bound observation, not proof that the full benchmark identity target is impossible.

## First pilot family

Example wording:

> Among the four pictured characters, who says "i don't want to become an exorcist to get revenge." on page 47? Answer A, B, C, or D using the labelled option sheet.

The program is the existing typed `speaker_char(quote(..., on=page(...)))`. The result is a uniquely proved private character ID, then mapped to exactly one of four trusted cross-page reference identities. The mapping carries the original speaker execution hash, each reference identity fact and four checked identity-equality claims (one true, three false).

Character names are not supplied as answer choices or used for target lookup. The final answer is a letter, so this separate profile does not require that the **private target character's canonical name** be readable. Literal canonical names inside the quoted text still undergo existing name eligibility checks. Original CRL proof semantics and name-answer acceptance rules are unchanged; a valid exact Char proof is used as private identity evidence rather than silently declaring a name answer eligible.

All options come from another page than the quoted source. Generic/ambiguous identity links, same crop/pixel duplicates and exact repeated-art matches between the source depiction and correct reference are rejected. Labels are assigned in a seeded global A–D cycle and the option order is bound to the actual rendered pixels. The pilot favours verified speakers/present characters on the source page as distractors, then other trusted chapter identities; fallback is not a negative presence claim. Identity inequality proves a logical wrong answer, not a visually fair distractor.

The renderer uses the exact annotated source crop, a uniform cell size, consistent contain scaling/padding, fixed raster A–D glyphs and PNG output. It never edits the originals or fabricates appearance pixels. Minimum source crop size and full pilot inspection matter when contain scaling enlarges a small image.

## Independent checks

`check-visual` never invokes the QA producer or `Interpreter.execute`. It independently validates:

- Closed question parsing and equality to the exact program, with original `ProofChecker` replay.
- Matching graph/visibility/rich snapshots and quote page/source appearance, unique non-generic speaker, transcript agreement and quoted canonical-name eligibility.
- Four ordered A–D references with distinct graph identities, admitted identity derivations and cross-page source bindings.
- Crop transform coordinates, original image hashes/dimensions and exact crop pixel bytes; duplicates are tested by pixels as well as producer crop hashes.
- The derived option comparisons, answer identity/letter and complete deterministic option-sheet pixels/order/layout.
- A removed-source-page world and the established OCR-only world, checking both saved atomic proofs and loss of the same supported identity. UNKNOWN in an ablated world demonstrates loss of available evidence; it is not a proof that the character is absent or that the image is universally unknowable.
- The public input allowlist, stored model/scoring inputs, manifest-backed assets/transforms, crop policy, balanced label schedule, report counts and pending review queue bindings.

No claim is made that every option crop is necessary under arbitrary human elimination strategies. This pilot does not award multi-hop/branch certificates from the number of images or operations. It leaves visual distractor distinguishability, identity ambiguity and final review pending.

`exact_label` scores only an A–D response (case/outer whitespace normalized), not character names or free-form explanations. This is a deterministic answer class, not an LLM-judge family.

## Outputs and privacy

`visual_pilot_v1` contains:

- `model_inputs.json`: **model-facing allowlist only**—question, its normal unmodified source page with 1-based page mapping/hash, and an explicitly marked A–D answer-option sheet. No identities, boxes, OCR/graph annotations, answer keys or proof bodies.
- `scoring.json`: **private** exact gold letters and scorer type.
- `chapters/*.json`: **private** full questions, flags (`question_type=visual_quote_speaker`, `evidence_class=executed`, `generation_mode=template`, `answer_format=visual_choice`), graph programs/proofs, reference identity bindings, comparison claims, image manifests and ablation traces.
- `assets/*.png` and crop-transform JSON: source-bound derived crops and option sheets. Only the sheet and source page are passed to the model; sidecars and individual identity bindings remain private.
- `review.html`: **private** source pages, option sheets and gold answers for visual inspection.
- `review_requests.json`: **private** item-hash-bound human-review templates, initially flagged with blank reviewer. Copy this file outside the immutable artifact before recording real decisions. No acceptance is fabricated or ingested automatically.
- `report.json`, `config.json`, `manifest.json`: source/config hashes, identity and answer-position counts, failure reasons and `release_status=not_approved`.

Inspect crop quality, source/reference identity agreement, perceptual distinctness, similar faces/poses, all four options and answer-revealing layout. Reject/flag ambiguous or unfair sets. The artifact explicitly says `visual_pilot_not_native_admitted`; `pool-inventory`/`admit-native` do not silently accept these new review-pending records. These files are not a released 1,000-QA benchmark and must not be copied as a single public export.

## Bounded verification — 2026-10-31

All 158 benchmark1000 tests pass, including independent-checker isolation, source immutability, answer/label and pixel tampering, public identity leaks, ablation substitution, stale graphs, duplicate options, profile self-promotion, overlap filters, exact scoring, source/pilot checkpoint resume and source-frame raster label checks.

Final real one-chapter preflight (Blue Exorcist c002, anchor budget 16) finds nine usable reference identities and three independently checked target identities. A four-question pilot covers three targets with exactly one correct A/B/C/D answer. All four independently verify, zero rejected. The options were visually inspected to improve deterministic crop/purity filters; **no human distractor approval was granted**. Local artifacts are `/tmp/comicsqa-visual-preflight-final`, `/tmp/comicsqa-visual-pilot-final` and `/tmp/comicsqa-visual-pilot-final-check.json`. Full collection jobs and actual human pilot review remain user-pending. All 142 frozen legacy files match.
