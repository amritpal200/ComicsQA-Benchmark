# annotations/magi3_grounding

Second MAGI v3 pass: **character grounding** of the Qwen panel captions (spec 02, stage 4;
"From Panels to Prose", Sachdeva & Zisserman 2025, step 4). It needs `annotations/human` (from
`scripts/export_human.sh`), `annotations/magi3` and `annotations/qwen32B`. All inputs are read-only.

For every MAGI v3 panel with a complete Qwen caption:
1. MAGI v3 `predict_character_grounding(panel crop, caption, strict=True)` inserts box tokens into the
   caption for each character it refers to. In strict mode the caption words stay unchanged; MAGI v3
   sometimes drops a comma, so positions are mapped back to the exact Qwen text.
2. Boxes are shifted to page coordinates, and near-duplicate boxes ("a boy", "he") are merged into **entities**.
3. Entities are matched one-to-one (IoU, Hungarian) to the **human** character boxes centred in the panel,
   which gives the name, the `named` flag and the human cluster, and to the MAGI v3 character boxes.
   Each match has a status: `matched` (IoU ≥ 0.5), `ambiguous` (another box within a 0.1 IoU margin),
   `unmatched`, or `no_ground_truth` (pages without human labels).
4. `named_caption`: the caption with `[Name]` / `[unnamed]` inserted at each grounded position matched
   to a human character (the paper's "character identity aware caption").

**Phrase text is approximate.** Strict-mode MAGI v3 marks only where a box goes, not where its phrase
starts. Usually the box follows the head noun or pronoun ("a boy⟦⟧ with…", "his⟦⟧"). After a locative
lead-in it refers to the next noun phrase ("On the far right,⟦⟧ a girl…"). `text_in_caption` is
reconstructed from these rules (`reconstructed: true`, `phrase_direction`). The anchor positions,
entity boxes and human links are exact model outputs and matches.

Strict decoding (`slowly_generate_grounded_caption`) fails on batches with different caption lengths,
so it runs one panel per call. On an A40 it does about 4–5 pages/min per process. Two processes per
GPU fill it (`--gpus 0,0`). `--no-strict` is ~4× faster, but rewrites the caption text (typos, changed
words) and finds fewer characters, so it isn't used by default.

## Output
`/data/151-3/comics/ComicsQA_Benchmark/annotations/magi3_grounding/<relative image path>.json`:
```json
{"schema": "comics_qa.magi3_grounding.v1",
 "page": {"relative_path": "...", "image_sha256": "...", "has_ground_truth": true},
 "grounding": {"panels": [{"panel_index": 1, "crop_bbox": [...], "caption": "...", "status": "complete",
     "caption_exact": true, "grounded_caption": "...",
     "named_caption": "In the foreground center, a boy [Nagisa Shiota] with spiky light hair ...",
     "phrases": [{"phrase_index": 0, "anchor_in_caption": 117, "text_in_caption": "a boy",
                  "reconstructed": true, "boxes_page": [[...]], "entity_ids": [0], "names": ["Nagisa Shiota"]}],
     "entities": [{"entity_id": 0, "box_page": [...],
                   "human_character": {"status": "matched", "ref": 3, "iou": 0.907, "name": "Nagisa Shiota",
                                       "named": true, "cluster": 5},
                   "magi3_character": {"status": "matched", "ref": 2, "iou": 0.93}}]}],
   "_meta": {"status": "complete", "strict": true, "match_iou": 0.5, "qwen_prompt_version": 4, ...}}}
```
- **Pages are rerun** when their Qwen captions or the settings change (signature); otherwise finished
  pages are skipped.
- **Reliability:** grounding is model-inferred; the paper reports F1 0.69–0.74 on PopCaptions.
  Use only `matched` links as names, and send `ambiguous` links to review.
