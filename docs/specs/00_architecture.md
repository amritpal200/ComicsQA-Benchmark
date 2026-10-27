# 00 — Architecture and contracts

Current scope (2026-10-27): depth is excluded; depth references in the original DAG
and source table below describe historical architecture only. Follow `docs/STATUS.md`
for the active CKG/CRL stage order, review inputs and coordination between agents.

## Goal
Implement a modular pipeline for chapter-scoped, evidence-grounded manga QA from the full supplied PopManga collection. QAs may answer with a name, phrase, sentence, number, date, boolean or list; favor deterministic evaluation, with a small configurable LLM-judge subset.

## Dependency DAG
```
Human PopManga annotations + images
        │
        ├── MAGI-3 structural annotations ──> Qwen3-VL-32B panel captions/page summaries ──> MAGI-3 character grounding (caption phrase → box → human identity/name)
        ├── OCR on human text boxes (dedicated OCR model; required, model-inferred)
        └── Depth estimation (independent / optional; ComicsDepth fine-tune)
                        │
        All available annotation artifacts → schema adapters → normalized chapter evidence
                        │
          ┌─────────────┼─────────────────────────┐
          ▼             ▼                         ▼
     character index  event/timeline index   spatial/depth relations
          └─────────────┼─────────────────────────┘
                        ▼
            graph / task-specific evidence packs
                        │
           ┌────────────┼──────────────────────┐
           ▼            ▼                      ▼
        narrative    character/dialogue     graph/hybrid / spatial-depth
           └────────────┼──────────────────────┘
                        ▼
         Qwen3-VL-32B-Thinking on MN5 (optional evidence enrichment first)
                        ▼
            candidates → checks → human review → export
```

## Source precedence (decided 2026-10-23)
Use **human ground truth wherever it exists**; use model annotations only for what the ground truth
lacks. Every fact records its source (`human`, `derived`, `model:<name>`).

| Field | Source |
|---|---|
| character boxes, names (`"none"` = unnamed), page-local clusters | human (PopManga) |
| text boxes, tails, text→speaker and text→tail links, text class | human |
| chapter-level character identity | derived from human names + aliases (no human chapter IDs exist) |
| panel boxes | MAGI v3 (the PopManga export's panels are model proxies, not human) |
| panel / text reading order | MAGI v3 geometry |
| text content | OCR model run on the human text boxes |
| panel captions, page summaries | Qwen3-VL-32B (context, never sole answer evidence) |
| caption phrase → character | MAGI v3 grounding, matched to human character boxes (name from human) |
| depth | ComicsDepth |

- Answers come from human facts or deterministic computation on them (counts, geometry, names).
- Model facts serve as bridges or context. Questions whose answer depends on a model fact (OCR text,
  caption claim, depth, grounding link) need a confidence check or human review.
- MAGI v3 character/text/association predictions are used only on pages **without** ground truth
  (97 of 2,022 images). Those pages may give story context but don't produce questions.

## Separation
- **CVC:** existing annotation production and normalization/precomputation as appropriate; no dependency on MN5 for annotation generation.
- **MN5:** inference workers for question generation, optionally evidence enrichment, using shared vLLM service or multiple replicas if memory/throughput allow.
- **CPU-friendly:** indexing, deterministic graph traversal, validation, deduplication, export.

## Data contracts (propose then finalize after inspection)
- `ChapterManifest`: chapter_id, ordered page IDs, image paths, source split, annotation versions.
- `EvidenceFact`: fact_id, typed relation, entity refs, page/panel refs, source kind, source pointer, confidence, verification status.
- `EvidencePack`: pack_id, task, chapter_id, ordered selected page refs, evidence fact refs, optional structured graph/timeline, expected answer candidates, prerequisites, provenance.
- `QACandidate`: question_id, pack_id, question, canonical answer, answer_type, accepted variants, evaluation_method, categories, supporting evidence, reasoning steps, model/prompt versions, status.
- `RunManifest`: git revision, config hash, data/version hashes, completed/failed shards, resource metadata.

Keep generation-only reasoning, ground truth and private metadata **out of** evaluation-facing examples.

## Acceptance criteria
- A single shared schema is used by every task module.
- All evidence and QAs are chapter-scoped, stable-ID based, traceable to original images.
- One task can be run independently without executing other QA tasks.
- Dependency changes invalidate only affected cached artifacts.
- Full dataset coverage is supported, with small smoke tests for development.

## First Codex action
Inspect data and repository, propose schema and directory design, and wait for approval.
