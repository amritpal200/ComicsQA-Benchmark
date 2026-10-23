# 07 — Spatial and optional depth QA

## Dependencies
Character/panel bboxes and spatial index; optional aligned depth maps. No requirement to run if depth unavailable.

## Preparation
- Establish original-image ↔ panel ↔ depth map coordinate transforms; inspect prediction convention (near/far), normalization and scale.
- Compute geometry relations deterministically. For depth, use robust character-region statistics and uncertainty margins; bbox includes background, so prefer masks when available or flag low-confidence regions.
- Compare relative depth within the **same panel** unless calibrated cross-panel comparisons are justified. Do not call monocular relative depth metric distance.
- Join spatial facts with human identities, dialogue and event indexes to create compositional evidence packs.

## Tasks
Left/right/overlap/relative depth, changes in placement, which named speaker later appears behind whom, cross-page character retrieval plus within-panel spatial comparison.

## Generation
Task-specific prompt with verified relation and canonical answer; optional Qwen enrichment for selecting semantically meaningful spatial relations, not replacing computed checks.

## Outputs
`data/evidence/spatial/`, `data/candidates/depth/`, `data/candidates/spatial/` and provenance manifests.

## Tests
Coordinate transform accuracy, near/far convention, depth ties, background contamination, multi-panel confusion, no-depth fallback, answer uniqueness.

## Codex request
Require a depth reliability report and examples before enabling depth QA at scale.
