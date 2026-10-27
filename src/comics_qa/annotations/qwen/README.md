# annotations/qwen

Qwen3-VL-32B captions: one description per MAGI v3 panel (using only that panel's crop) and one per
full page (panel by panel, right-to-left / top-to-bottom). Outputs are **model-inferred**
descriptions, not ground truth.

**Prompt version 4** is for benchmark evidence. Version 2 was written for training captions; v4 differs as follows:
- **No length targets.** v2 asked for "80–100" and "400–500" words; fixed targets invite filler on simple
  images. v4 asks for complete but unpadded descriptions, at most 120 (panel) and 450 (page) words.
  The saved caps are 150 and 500; longer text is shortened at a sentence boundary, and the original is kept
  in `original_caption`.
- **No text from the image** (no quotes from speech, captions, signs or sound effects); the caption may
  say that a character is speaking. This follows "From Panels to Prose" (Sachdeva & Zisserman 2025):
  VLMs misread and misattribute text, and OCR provides it. It also keeps pronouns inside quotes out of
  the later MAGI v3 grounding.
- **No names**, and no knowledge of the series. Characters are described only by appearance, so the
  MAGI v3 grounding pass can link each phrase to a human character box and its ground-truth name.
- **Content asked for:** who does what to whom, positions (left/right/foreground/background), important
  objects, changes between panels, and events in reading order. **Uncertainty** is stated instead of guessed.

Checked on Death Note ch. 1: no names, no quoted dialogue. Labels printed in the art (for example
"The Human World") are still occasionally quoted.

| File | Purpose |
|---|---|
| `serve.py` | vLLM launcher with GPU-size presets (unchanged copy of the earlier `annotations/qwen/serve.py`) |
| `run_qwen.py` | caption client; reads the images (read-only) and the MAGI v3 annotation tree |
| `pyproject.toml`, `uv.lock` | environment (copied unchanged: vLLM 0.11.2 in the `server` group) |
| `scripts/qwen_server.sh`, `scripts/annotate_qwen.sh` | launchers |
| `tests/test_qwen_runner.py` | CPU tests with a mock HTTP server |

The client keeps the earlier client's prompts (version 2), crop rules (floor/ceil, clipped to the page),
pixel caps, word limits and their shortening policy, token budgets, retries, and resume of only the missing
captions. Differences:
- **No source changes:** no sidecar edits or folder renaming; there's one output JSON per page.
- **Panels from MAGI v3:** they're read from the MAGI v3 annotation tree, and the image's sha256 must match
  the image MAGI v3 annotated.
- **Several servers:** repeat `--base-url`; requests are spread round-robin, and `--concurrency` is per server.

## Run (two screens)
```bash
# screen 1: server(s), one per GPU, ports 18001, 18002, ...
bash scripts/qwen_server.sh --gpus 0 --profile 46gb --max-num-seqs 16
# screen 2, once a server log shows "Application startup complete":
bash scripts/annotate_qwen.sh --ports 18001 --concurrency 16 --page-workers 4
```
- **Environment:** `/data/151-3/comics/.cache/qwen_annotations/venv-<host>`.
- **Weights:** read offline from `/data/151-3/comics/.cache/hf_cache`.
- **Rerunning** the client skips pages that are already complete and retries only the captions that are
  missing or failed. Changed settings require `--overwrite`.

## Output
`/data/151-3/comics/ComicsQA_Benchmark/annotations/qwen32B/<relative image path>.json`:
```json
{"schema": "comics_qa.qwen32B.v1",
 "page": {"relative_path": "...", "image_sha256": "...", "width": 1400, "height": 2100, "magi3_root": "..."},
 "qwen32B": {"panels": [{"panel_index": 0, "bbox": [...], "crop_bbox": [...], "caption": "...",
                         "word_count": 87, "shortened": false, "finish_reason": "stop", "usage": {...}}],
             "page": {"caption": "...", "word_count": 430},
             "_meta": {"status": "complete", "signature": "...", "base_model": "Qwen/Qwen3-VL-32B-Instruct",
                       "model": "Qwen/Qwen3-VL-32B-Instruct-FP8", "prompt_version": 2}}}
```
- **Panel order:** `panel_index` matches the `magi3.panels` array, not reading order.
- **Pages without panels** get only the page caption.
- **Run reports** are appended to `runs.jsonl` in the output folder.
