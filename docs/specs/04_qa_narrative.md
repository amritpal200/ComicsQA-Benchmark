# 04 — Narrative, temporal and causal QA

## Dependencies
Foundation + ordered pages/panels + captions/summaries + optional event timeline. No depth or graph dependency.

## Selection
Default configurable 5 consecutive pages from one chapter, including cases without reliable character names. Preserve right-to-left/top-to-bottom manga order. Vary context length when evidence requires it.

## Prepare → optionally enrich → generate
- Build evidence pack with ordered original page images, panel captions, page summaries, text/dialogue if available and candidate events.
- Optional Qwen3-VL-32B-Thinking intermediate pass to identify verifiable temporal/event links, retrieve extra pages if needed, and record source pointers.
- Separate task prompt generates questions about before/after, action consequences, narrative continuity, dialogue/action connections, changes across panels.
- Require a precise canonical answer, answer type, evaluation rule, evidence steps and uncertainty flag.

## Guardrails
Do not infer unobservable motives as facts. Avoid plot knowledge outside selected pages. Prefer objective short answers, but allow narrowly phrased sentence answers. Human review for causal claims.

## Outputs
`data/candidates/narrative/` immutable JSONL shards and task run manifest.

## Tests
Manga order; missing captions; all cited evidence within selected context; no trivial single-panel question mislabeled multi-page; idempotent resume.

## Codex request
Implement this as the first QA module to establish task interface, after foundation/evidence contracts are approved.
