# 03 — Evidence builders and task-specific packs

## Dependencies
Normalized chapter data, available annotation stages. Build evidence once, reuse across QA modules.

## Independent builders
- Character appearance index: human identity/name aliases, page/panel locations, appearance boxes.
- Dialogue index: text regions, transcription where available, speaker/recipient with confidence.
- Event/timeline index: ordered panels, caption-derived event candidates, temporal anchors and evidence.
- Spatial index: left/right/above/below/overlap computed from geometry, with coordinate frames.
- Depth index: within-panel robust comparisons after confirming near/far convention, alignment, uncertainty and sufficient margins. Do not assume cross-panel metric depth.
- Chapter graph: nodes for page/panel/character/appearance/text/object/event and typed edges with provenance; inferred edges must not masquerade as human ground truth.

## Task-specific pack builders
Each QA task requests only relevant facts and images. Example: narrative → 5 consecutive pages + captions + event timeline; character → indexed nonconsecutive appearances; graph → precomputed verified paths + candidate answer; depth → spatial/depth relation + identity/context. Optional Qwen reasoning may enrich a pack, but inferred facts must be verified before acceptance.

## Graph correctness
Support executable graph queries, unique-answer checks, alternative candidate enumeration, no fabricated edges, meaningful hop counting (avoid counting trivial structural edges as cognitive hops).

## Outputs
Versioned chapter-level evidence stores and immutable `EvidencePack` shards with original source pointers and dependency hashes.

## Acceptance checks
Every fact traceable to original annotation/image; packs can be reconstructed; no graph QA generated before graph query establishes an answer; depth absence does not block other builders; tests cover uncertain identities, duplicate entities and ambiguous answers.

## Codex request
Propose builder interfaces, on-disk layout and graph-vs-relational tradeoffs; implement only after approval.
