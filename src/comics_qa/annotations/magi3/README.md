# annotations/magi3

MAGI v3 structural annotations (panels, characters, texts, tails, associations, OCR, reading
order) for the PopManga images. All outputs are **model-inferred**, not ground truth.

- `run_magi3.py`: self-contained runner (PEP 723 script; `uv` builds its environment from the
  inline dependencies and `run_magi3.py.lock`). MAGI v3's custom code needs `transformers==4.45.2`,
  so it has its own environment, separate from the rest of the repo.
- Launcher: `scripts/annotate_magi3.sh`.
- Tests (CPU, no model): `tests/test_magi3_runner.py`.

Adapted from the earlier in-place annotator (`annotations/magi3/annotate.py`). The model calls, score
capture, reading-order worker, OOM batch splitting and fatal-CUDA checks are the same. What changed:

| Earlier annotator | Here |
|---|---|
| adds a `magi3` key to a JSON next to each image | the image tree is read-only; one output JSON per page under `--out` |
| renames the dataset folder to `_done` | no changes to the input |
| filesystem order | sorted order, so `--limit` and reruns are deterministic |
| one process | `--shard K/N`; the launcher runs one shard per GPU |

## Model
Weights: [ragavsachdeva/magiv3](https://huggingface.co/ragavsachdeva/magiv3), loaded from a local
folder (`--model`, default `/data/151-3/comics/models/ocr/magiv3`) with `trust_remote_code`.
The authors state the MAGI models are for academic research use only.

## Output
`<out>/<relative image path>.json`, e.g. `Naruto/Naruto - 001 - .../Naruto - 001 - p000 - ....jpg.json`:
```json
{"schema": "comics_qa.magi3.v1",
 "page": {"relative_path": "...", "images_root": "...", "image_sha256": "...", "width": 1400, "height": 2100},
 "magi3": {"panels": [...], "characters": [...], "texts": [...], "tails": [...],
           "character_cluster_labels": [...], "text_character_associations": [...],
           "text_tail_associations": [...], "is_essential_text": [...],
           "ocr": {"bboxes": [...], "ocr_texts": [...]}, "reading_order": {...},
           "association_scores": {...}, "generation": {...}, "_meta": {...}}}
```
- **Boxes:** `[x1, y1, x2, y2]` in original image pixels.
- **Indices:** zero-based, into the arrays above.
- **Character clusters are page-local**, so they say nothing about identity across pages.
- **OCR boxes are separate from `texts`:** `ocr.ocr_texts[i]` belongs to `ocr.bboxes[i]`.
- **Run log:** each run appends a report to `<out>/runs.jsonl`; per-shard logs are in `<out>/logs/`.
- **Resume:** pages whose output has `_meta.status == "complete"` are skipped; `--overwrite` recomputes them.
- **Incomplete pages** (reading-order timeout, invalid boxes) are not written and are retried on the next run.
