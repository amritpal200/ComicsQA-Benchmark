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

## Guarded recovery (2026-10-29)

The repository-local `guards.py` wraps the loaded language decoder, without
editing the installed model. Before each strict chunk it checks actual prefix
length plus requested new tokens against positional capacity. A trailing run of
64 location/special tokens without caption progress fails the panel safely.
Prediction validation rejects malformed spans/boxes, changed caption words in
strict mode, and more than 128 raw boxes (a conservative quarantine threshold,
not a dataset truth). These failures produce partial pages and a nonzero final
exit status instead of a CUDA device assertion. Fatal CUDA errors still stop the
worker; continuing a poisoned CUDA context is unsafe.

Strict postprocessing sometimes drops punctuation. Word-preserving punctuation/
whitespace changes remain explicitly `caption_exact=false`, with validation mode
`punctuation_or_whitespace_only`; they are never relabelled exact. The input
caption stays unchanged. Word changes are rejected. This is operational validation,
not proof that model boxes or character matches are visually correct.

To preserve an old run, use a new output and `--reuse-from`:

```bash
GROUNDING_OUT=/data/151-3/comics/ComicsQA_Benchmark/annotations/magi3_grounding_recovery_v1 \
  bash scripts/ground_magi3.sh --gpus 4 \
  --reuse-from /data/151-3/comics/ComicsQA_Benchmark/annotations/magi3_grounding
```

Do not launch this command while another worker holds the same output shard.
Current completed outputs are revalidated before skipping. Old pages are copied
only if their signature and every saved panel pass the new checks; otherwise the
page is inferred again. Original files stay untouched. Copied pages record
`revalidated_by` and `reused_from`; newly inferred pages record `guard_version`.
Existing signature settings remain compatible so safe old work can be reused.
Rerunning the same command skips validated completed pages and retries partial
ones; a deterministic guard failure may remain partial on repeated runs. Do not
interpret a successful restart as complete dataset coverage.

2026-10-29 tests: 19 CPU tests passed. On cudahpc51 GPU 4 (L40S), the three former
crash pages completed processing without CUDA failure: Chainsaw Man c002 p023
8/9 panels, Death Note c002 p024 4/5, Jujutsu Kaisen c002 p019 6/6. The two missing
panels were explicitly rejected by the no-progress guard. Smoke outputs:
`/tmp/comicsqa-grounding-guard-smoke`. Old-run reuse audit: 1,074 reusable pages,
10 needing retry, plus 938 previously missing pages. Full recovery was launched
with the command above; consult its logs for current progress.
