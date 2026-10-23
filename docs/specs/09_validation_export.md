# 09 — Validation, grading metadata, human review and export

## Dependencies
Candidate QA shards from any tasks. Can run incrementally; final merge after completed jobs.

## Grading policy
Default to deterministic: canonical entity/alias, normalized exact text, numeric with explicit tolerance/units, ISO date, boolean, category, ordered/unordered list. Allow short phrases/sentences with accepted paraphrases or fact-specific rules. A **small configurable minority** may use `llm_judge` later; require reference facts, rubric and evidence, and report its share. Do not implement/run LLM judging now.

## Immediate checks
Schema and references, selected-context evidence, unique answer or explicitly defined multi-answer, graph query execution, duplicates/near duplicates, answer type/evaluation compatibility, provenance, source completeness, basic review queue. Avoid accepting inferred facts solely from model confidence. Human review for uncertain/causal/depth claims.

## Deferred but supported in schema
Independent VLM solving, image-free ablations, page removal ablations, multi-model difficulty calibration, LLM judge and human accuracy. Save necessary prompts, evidence IDs and evaluation rules to add later.

## Exports
- `benchmark_public.jsonl`: question, ordered image refs, canonical answer, answer type, evaluation method and necessary aliases; no privileged graph/annotation facts supplied to evaluated model.
- `benchmark_private.jsonl`: source evidence, reasoning chain, graph program, review decisions, model outputs, provenance, rubrics.
- `reports/`: coverage by chapter/task/answer type, validation status, dedupe, deterministic vs judge proportions, split integrity.

## Dataset coverage
Process complete provided PopManga collection; preserve split metadata, chapter boundaries, selected page ordering, and leakage protections. Smoke test only verifies correctness, not final coverage.

## Acceptance checks
Two task shards merge without collisions; deterministic scoring metadata valid; private/public separation; all exported answers traceable; reruns stable; no raw annotation leakage into model inputs.

## Codex request
Propose scoring contract and public/private export examples, then wait for approval.
