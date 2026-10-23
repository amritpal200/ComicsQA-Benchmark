# 01 — Foundation: dataset adapters, schemas and storage

## Dependencies
`00_architecture.md`; original PopManga data access.

## Implement
- Inspect real PopManga directory layout and human annotation fields. Record uncertainties, chapter/page ordering, splits, character IDs, and image formats.
- Design typed schema adapters (Pydantic or equivalent) for chapter, page, panel, character appearance, dialogue/text, caption, depth pointer, evidence fact, evidence pack, QA candidate and run manifest.
- Stable IDs must survive reruns; retain original IDs and coordinates, plus normalized coordinate frames and transforms.
- Create chapter manifest with manga reading order (usually right-to-left, top-to-bottom; resolve irregular panels explicitly).
- Read-only source adapters; configurable paths; streaming iteration and lazy image loading; chapter-level indexing; deterministic sampling.
- Output JSONL/Parquet or similar documented interchange files, atomic writes, manifest checksums, resume support.
- CLI skeleton and tests with tiny synthetic fixtures. No assumptions about uninspected schema.

## Outputs
`data/normalized/` (configured externally), chapter manifests, source provenance map, validated schema definitions, CLI and tests.

## Acceptance checks
Can load one chapter and all chapters without mutating originals; stable IDs and page order reproducible; missing annotations handled; manifests validate; schemas consumed by downstream modules.

## Codex request
First show actual source fields, proposed schema, file tree, risks and tests. Wait for approval before implementation.
