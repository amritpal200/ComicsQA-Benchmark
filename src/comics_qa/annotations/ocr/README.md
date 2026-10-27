# annotations/ocr

OCR of every text box with **PaddleOCR-VL-1.6** ([PaddlePaddle/PaddleOCR-VL-1.6](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6),
0.9B, Apache-2.0), used for **element-level recognition**: each box is cropped (4 px margin) and read
separately with the prompt `OCR:`. This is the transformers path the model card recommends for cropped
elements; the full PaddlePaddle pipeline is meant for whole-page layout parsing, which we don't need.
Output text is **model-inferred**, not ground truth.

- **Which boxes:** the human PopManga text boxes (20,843 on 1,925 pages). On the 97 pages without ground
  truth, the MAGI v3 text boxes (`boxes_source: model:magi3`) are read for context only.
- **Model:** `/data/151-3/comics/models/ocr/PaddleOCR-VL-1.6`, revision `c5630abae1d9…`. It loads with
  transformers 5.16.1 natively (no remote code).
- **Environment:** PEP 723 script, `run_ocr.py` plus `run_ocr.py.lock` (torch 2.9.0 cu128,
  transformers 5.16.1).
- **Speed and precision** (tested on a Quadro RTX 6000, which has no bf16): fp16 gave identical text to
  fp32 at 0.6 s per box. Batching was slower, because one long output holds up the batch, so the runner
  reads one box per call. Four processes fill one 24 GB GPU (~200 boxes/min, ~12 GB).
- **Inputs are read-only.** Finished pages are skipped on rerun and redone if the boxes or settings change.

```bash
bash scripts/annotate_ocr.sh --gpus 6,6,6,6          # 4 processes on GPU 6
```

Output: `/data/151-3/comics/ComicsQA_Benchmark/annotations/ocr_paddleocr_vl/<relative image path>.json`
```json
{"schema": "comics_qa.ocr.v1",
 "page": {"relative_path": "...", "image_sha256": "...", "has_ground_truth": true},
 "ocr": {"boxes_source": "human",
         "texts": [{"index": 3, "box": [...], "crop_box": [...],
                    "text": "SO I\nGUESS\nWE'RE NOT\nDOING THE\nPLEDGE\nTHEN...",
                    "text_normalized": "SO I GUESS WE'RE NOT DOING THE PLEDGE THEN...",
                    "generated_tokens": 21, "truncated": false, "status": "ok"}],
         "_meta": {"model_revision": "...", "dtype": "float16", "prompt": "OCR:", "status": "complete"}}}
```
- `index` is the position in the human `texts` list (core id `<page>__htext<index>`).
- `text` is the raw output; `text_normalized` applies NFKC (full-width → ASCII), joins hyphenated
  line breaks, and turns whitespace into single spaces.
- `status` is one of `ok`, `empty`, `truncated` (hit `--max-new-tokens`), `empty_box` or `failed`.
- **Typical errors** seen in tests: single letters in stylised lettering ("GLINSHOTS" for "GUNSHOTS",
  "POM" for "POW"). Questions that depend on exact OCR text need a check.
