# 00 — Architecture and contracts

## Goal
Implement a modular pipeline for chapter-scoped, evidence-grounded manga QA from the full supplied PopManga collection. QAs may answer with a name, phrase, sentence, number, date, boolean or list; favor deterministic evaluation, with a small configurable LLM-judge subset.

## Dependency DAG
```
Human PopManga annotations + images
        │
        ├── MAGI-3 structural annotations ──> Qwen-32B-Instruct captions/summaries ──> second MAGI-3 prose enrichment (verify actual tool capabilities)
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
