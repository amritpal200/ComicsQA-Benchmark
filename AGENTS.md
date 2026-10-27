# Codex instructions — Manga QA Benchmark

Read `docs/ROADMAP.md`, `docs/specs/00_architecture.md`, and the specific stage specification before editing code.

## Working agreement
- Read `docs/STATUS.md` at the start of every task. It is the shared coordination file for both agents. Re-read it immediately before a targeted edit; record stage start/completion/blockers, output paths, tests and dated decisions. Preserve the other agent's entries and do not mark unexecuted work done.
- Work on **only the requested stage**. First inspect the existing repository and actual data; report assumptions, missing fields, design and planned files. **Wait for explicit approval before changing code** unless the user explicitly authorizes implementation.
- Do not invent PopManga/MAGI-3/Qwen/depth annotation fields, model capabilities, paths, GPUs, or successful validation results. Build adapters around inspected schemas.
- Never overwrite source images or source annotations. Maintain immutable provenance and stable IDs. No large downloads, GPU jobs, paid API calls, or full dataset runs without approval.
- Keep CVC annotation generation separate from MN5 QA generation. Use configurable paths and model endpoints. Never commit secrets or large data.
- Respect manga page/panel reading order; preserve original chapter/page IDs and dataset split metadata.
- QA tasks have distinct evidence preparation and prompts; do not send every annotation to every task. Graph QA requires graph construction and executable answer selection first.
- Most answers should be deterministically gradable (entity, numeric, date, boolean, category, list, normalized phrase). A **limited, configurable minority** may require LLM judging; store rubrics and accepted factual elements, do not implement LLM judging until requested.
- Distinguish human annotations, geometric computations, and model-inferred assertions. Captions and depth estimates are fallible; verify visual support. Never infer absence from missing annotations.
- All questions need image references, evidence pointers, a canonical answer, answer type, evaluation method, reasoning provenance, and review status. Keep privileged evidence separate from model-facing export.
- Add tests and documentation for each implemented stage. Prefer reproducible, resumable, idempotent jobs, atomic shard writes, and manifest-based dependency tracking.
- Do not change unrelated modules or training pipelines. Explain any cross-stage interface change before making it.
