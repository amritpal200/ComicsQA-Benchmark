# Manga QA Benchmark — Codex implementation roadmap

## Objective
Create a chapter-scoped, annotation-grounded, human-traceable manga VQA benchmark from the **entire supplied PopManga collection**. The available collection is approximately 50 chapters / 1,925 pages; inspect actual files instead of assuming counts or schemas. Respect manga reading order (typically right-to-left, top-to-bottom, with panel-layout exceptions).

**Separation of concerns:** CVC GPU server produces/enriches annotations; evidence builders prepare task-specific facts; MN5 generates questions with Qwen3-VL-32B-Thinking; final stages validate and export. Question generation must not regenerate existing annotations.

## Read order
1. `AGENTS.md` — mandatory shared engineering rules.
2. `docs/specs/00_architecture.md` — design and data flow.
3. `docs/specs/01_foundation.md` — common schema, readers, storage.
4. `docs/specs/02_annotations_cvc.md` — existing annotation ingestion and optional preparation.
5. `docs/specs/03_evidence_builders.md` — reusable indexes and graph/timeline/depth evidence.
6. `docs/specs/04_qa_narrative.md` — consecutive-page narrative/temporal QA.
7. `docs/specs/05_qa_character_dialogue.md` — identity/dialogue/interactions QA.
8. `docs/specs/06_qa_graph_hybrid.md` — graph-first, constraint, multi-hop QA.
9. `docs/specs/07_qa_spatial_depth.md` — spatial/depth QA.
10. `docs/specs/08_mn5_inference.md` — vLLM and Slurm execution.
11. `docs/specs/09_validation_export.md` — scoring metadata, deduplication, review, export.

## Suggested execution order
Current execution order and ownership are tracked in `docs/STATUS.md`; read it before work and update it at every stage transition. The agreed graph sequence is CKG-0 review → CKG-1 → CKG-2 (name visibility) → CRL-1 → CRL-2 → GEN-1 → VERB-1 → CKG-3 → GEN-2 → EXP-1. Exact-name identity integration may be included in CKG-1. Name visibility must precede GEN-1, and guessability limits are enforced during GEN-1 and rechecked at export. Page-order generation is an independent side task. Depth is excluded (decision 2026-10-27).

## How to use with Codex
Open this repository in Codex. Start with `docs/prompts/01_start.md`. For each subsequent stage, point Codex to the matching spec and ask for a plan before changes. Keep separate commits/PRs per stage. Do not ask Codex to implement all specs at once. See `docs/prompts/02_stage_template.md`.

## Intended source tree
`src/comics_qa/{core,annotations,evidence,tasks,inference,validation,export}/`, `configs/{local,mn5,tasks}/`, `scripts/`, `slurm/`, `tests/`, `docs/`. Large data and generated artifacts are outside Git and configured by paths.

## Dataset boundary
Process all available chapters, not only a pilot. Small smoke tests are for checking correctness before full runs. Preserve original split metadata. Avoid cross-chapter reasoning initially; selected pages for each question must be from one chapter. Avoid leakage across partitions. (But later we will do at series level if possible, from different chapters, remind me).
