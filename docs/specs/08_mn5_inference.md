# 08 — MN5 vLLM inference and Slurm orchestration

## Dependencies
Evidence packs, task prompts and shared QA schema. Separate inference from CVC annotation production.

## Serving model
Initially Qwen3-VL-32B-Thinking via configurable local vLLM OpenAI-compatible endpoint. Verify actual model identifier, memory footprint, context length, image limits and vLLM compatibility on MN5; do not assume one GPU per 32B model replica.

## Parallelization model
- Preferred starting point: **shared vLLM server** with multiple independent task workers (narrative, graph, character, depth, etc.) issuing concurrent requests.
- Alternative: multiple server replicas on GPU groups if memory/throughput justify it.
- Assign **task jobs to workers, not permanently to GPUs**; a worker may be CPU-only while the model uses one or several GPUs.
- Use Slurm job arrays by task/chapter/shard; server job and worker jobs have explicit dependencies and endpoint discovery.
- MN5 may be network-isolated: use local model/data paths, no assumed Hugging Face downloads or external API access.

## Reliability
Per-request IDs, deterministic configs where possible, concurrency limits, backpressure, timeout/retry, JSON validation, atomic outputs, checkpoints, resume, dedupe and error logs. Log model/prompt/config/git versions, latency and tokens if available. Avoid sending giant annotation blobs; task-specific packs only.

## Deliverables
`slurm/serve_qwen32b.sbatch`, `slurm/generate_array.sbatch`, `configs/mn5/`, `src/comics_qa/inference/`, CLI documentation and dry-run mode.

## Acceptance checks
One task smoke test, concurrent distinct tasks against same server, no output collisions, graceful server failure/restart, no GPU oversubscription assumptions, correct resumption.

## Codex request
First propose resource plan based on **actual available MN5 GPU types/counts** and model fit; do not submit jobs until approved.
