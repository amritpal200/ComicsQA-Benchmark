# P11: private Qwen packs and checked responses

CPU implementation is ready. Full pack preparation, actual processor preflight, MN5 deployment and model inference are user-run and have not been completed. Endpoint, served model ID, model path and runtime context are intentionally unconfigured. Human review remains after Qwen and automated validation, before release.

## Prepare everything without MN5 settings

Run from `ComicsQA_Benchmark/Code`. Use the dedicated benchmark environment from [setup](README.md#environment), including Pillow; system Python may lack it. Set `BENCHMARK1000_PYTHON` to that environment's Python on your host.

```bash
export BENCH_ROOT=/data/151-3/comics/ComicsQA_Benchmark
export QWEN_REPORTS="$BENCH_ROOT/reports/benchmark1000"

bash scripts/benchmark1000.sh pool-inventory \
  --bench-root "$BENCH_ROOT" \
  --source-plan configs/benchmark1000/pool_sources_v2.json \
  --out "$QWEN_REPORTS/pool_v2"

bash scripts/benchmark1000.sh prepare-qwen-packs \
  --bench-root "$BENCH_ROOT" --source "$QWEN_REPORTS/pool_v2" \
  --mode paraphrase --out "$QWEN_REPORTS/qwen_paraphrase_v1"

bash scripts/benchmark1000.sh prepare-qwen-packs \
  --bench-root "$BENCH_ROOT" --source "$QWEN_REPORTS/sentences_v1" \
  --mode synthesis --out "$QWEN_REPORTS/qwen_synthesis_v1"

bash scripts/benchmark1000.sh check-qwen-packs \
  --bench-root "$BENCH_ROOT" --store "$QWEN_REPORTS/qwen_paraphrase_v1" \
  --out "$QWEN_REPORTS/qwen_paraphrase_v1.check.json"
bash scripts/benchmark1000.sh check-qwen-packs \
  --bench-root "$BENCH_ROOT" --store "$QWEN_REPORTS/qwen_synthesis_v1" \
  --out "$QWEN_REPORTS/qwen_synthesis_v1.check.json"
```

The new source plan retains all nine earlier sources and adds admitted branches and contrast-member views. It leaves `pool_v1` and its plan unchanged. The expected physical union is 3,777 representations, including paired member views; the previously verified union contains **3,774 distinct underlying tasks**. These are different counts. Inspect actual reports rather than treating the expectation as a completed build. The 45 unreviewed visual pilots are excluded; 11 sentence plans are separate synthesis inputs, not additional admitted questions.

Paraphrase mode preserves the fixed program/answer and sends a text-only, ordered graph context. Synthesis mode preserves the P10 short answer and checked factual claims, and adds exact source-page PNGs. Packs retain private source/proof provenance, hydrated H/V facts and coverage, referenced nodes, verified readable forms/OCR, dependency order, original question and bounded alternative wordings. The model receives a compact view rather than full admission replay logs. No unverified caption is promoted into a trusted fact.

Default `--crop-scope full-page` uses the full image rectangle on each proof-referenced page. It retains geometry flags and review requirements; it does not clip boxes or approve geometry. Optional `--crop-scope proof-union` requires valid, unflagged evidence boxes. The independent checker reconstructs required rectangles and compares derived pixels against original image hashes. Image/byte limits produce explicit holds, never truncated evidence. Preparation defaults to 16 images and 1,000,000 bytes of model context per task.

Repeat an identical command to resume. Changed source/config/code requires a new versioned output directory. Per-chapter preparation is available with repeated `--chapter`; checks and source pins remain explicit. Packs, requests and raw responses contain answers/private evidence and are not benchmark evaluation inputs.

## Configure later, then preflight a two-request pilot

Inspect a local checkpoint without loading its weights:

```bash
bash scripts/benchmark1000.sh qwen-model-info \
  --model-path /data/151-3/comics/models/Qwen3-VL-32B-Thinking \
  --out /tmp/benchmark1000-qwen-model-info.json
```

Copy `configs/benchmark1000/qwen_runtime.example.json` to a new host-specific file. Fill `model_path`, `served_model`, `endpoint` (complete `/v1/chat/completions` URL) and `max_context_tokens`. Placeholder values deliberately fail validation. Set actual runtime/image/output limits and chat-template options for the server you deploy. The local architecture limit is not evidence that MN5 can serve that context. No GPU count, partition, account, quantization or server allocation is assumed.

Use a compatible existing Qwen environment with Transformers, Pillow and its required processor dependencies for request preparation. It uses local tokenizer/processor files, not model weights or downloads. The benchmark setup alone does not install Transformers. Exact token measurement applies the actual chat template and image processor, including image-token expansion; reserve output space for thinking and final JSON. Request preparation fails clearly if a task exceeds a budget; it does not shorten the question, graph or evidence. Completed checkpoints remain available; choose a new scope/profile/output when inputs change.

After filling a runtime file, these are the later pilot commands; they are not needed for CPU packs above:

```bash
bash scripts/benchmark1000.sh prepare-qwen-requests \
  --packs "$QWEN_REPORTS/qwen_synthesis_v1" \
  --runtime configs/benchmark1000/qwen_runtime.mn5.json \
  --limit 2 --out "$QWEN_REPORTS/qwen_synthesis_requests_pilot_v1"

bash scripts/benchmark1000.sh run-qwen \
  --requests "$QWEN_REPORTS/qwen_synthesis_requests_pilot_v1" \
  --dry-run --out "$QWEN_REPORTS/qwen_synthesis_run_pilot_v1"

# Requires the configured server to be running; this sends requests.
bash scripts/benchmark1000.sh run-qwen \
  --requests "$QWEN_REPORTS/qwen_synthesis_requests_pilot_v1" \
  --max-requests 2 --out "$QWEN_REPORTS/qwen_synthesis_run_pilot_v1"

bash scripts/benchmark1000.sh ingest-qwen \
  --requests "$QWEN_REPORTS/qwen_synthesis_requests_pilot_v1" \
  --responses "$QWEN_REPORTS/qwen_synthesis_run_pilot_v1" \
  --bench-root "$BENCH_ROOT" \
  --out "$QWEN_REPORTS/qwen_synthesis_validation_pilot_v1"
```

Repeat for paraphrase in separate stores. Review both real pilot results before preparing all requests (`--limit 0`) or allowing all selected requests (`--max-requests 0`). Optional credentials come only from `BENCHMARK1000_API_KEY` and are not saved in artifacts. The server's models endpoint must advertise the chosen served ID and adequate `max_model_len`; the observed prompt-token usage must match local preflight. A mismatch is held for investigation.

## Recovery, sharding and validation

Request IDs bind pack, model metadata, runtime and exact payload. Raw HTTP bodies, failures, timing, attempt starts/results and completion hashes are retained. Completed requests are not resent. Stored successful responses are recovered after a crash even if the completion pointer was not written. Timeouts/interrupted starts are ambiguous and stay held unless the user explicitly invokes `--retry-ambiguous`; the idempotency header does not guarantee server-side exactly-once generation. Transient HTTP errors have bounded retries. Use one writer per run directory.

`run-qwen --shard-index N --shards K` partitions IDs deterministically; give each shard a separate output directory. [Worker template](../../../slurm/benchmark1000/qwen_worker.sh) uses caller-provided paths/environment and defaults to two requests per invocation. It does not launch a model server or prescribe MN5 resources. Ingest each shard separately. Ingestion is a versioned snapshot and may report pending requests; after more responses, write a fresh validation output rather than overwrite the snapshot.

The question parser receives only generated text, independently reconstructs its program, and requires the same canonical semantics and answer contract. Matching the saved answer alone is insufficient. Supported controlled variants cover existing templates, elementary count/speaker/appearance/comparison/constraint wording and compact two-branch questions. Unfamiliar wording or extra clauses stays held. This is a bounded language, not a general semantic or LLM judge.

Synthesis also checks the exact short answer and P10 required/optional/false-claim contracts; unsupported extra assertions and missing facts stay held. Generated character references must satisfy verified form visibility. Truncated responses, wrong model/token usage, malformed output and unknown prose are held. Raw reasoning is preserved privately; a balanced leading thinking block can be separated for JSON validation.

Validated outputs carry generation/type flags and `verified_pending_human`. **Ingestion does not promote questions into the admitted pool, approve human review, select the final 1,000 or grant release.** Rich narrative claims outside the current P10 profile still need their own evidence contracts. P11 wording also does not fix the count-heavy source-family distribution.

## Verification completed on the implementation host

The benchmark1000 suite includes 17 P11 tests covering typed graph proofs, source/target binding, exact pixels, controlled wording, sentence facts, budgets, mocked HTTP transport and crash recovery. Bounded real-data preparation/checks cover an earlier GEN question and two sentence plans; actual processor execution and model inference have not run. Local checkpoint metadata was inspected without loading weights. See [shared status](../../../docs/STATUS.md) for final regression results and frozen-file checks.

Processor/token implementation follows the [Transformers Qwen3-VL documentation](https://huggingface.co/docs/transformers/model_doc/qwen3_vl) and [processor source](https://raw.githubusercontent.com/huggingface/transformers/v4.57.1/src/transformers/models/qwen3_vl/processing_qwen3_vl.py). Server request/model fields follow the [vLLM OpenAI protocol](https://raw.githubusercontent.com/vllm-project/vllm/v0.11.2/vllm/entrypoints/openai/protocol.py). These references do not establish the installed MN5 runtime or its capacity.
