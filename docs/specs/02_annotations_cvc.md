# 02 — CVC annotation pipeline and ingestion

## Dependencies
Foundation schemas; original images/human annotations. Annotation production occurs on CVC GPU server, not MN5 QA workers.

## Required sequence and branches
1. Load original PopManga human annotations (identity/name/bbox/text links if present).
2. MAGI-3 structural annotation: panels, characters, text and available associations.
3. Qwen-32B-Instruct: panel captions, page summaries, supported action/event descriptions.
4. **Second MAGI-3 pass: character grounding** (runs after stages 2 and 3). Details below.
5. Depth estimation in parallel, if available, with recorded resize/crop transforms and depth convention. Depth model: our ComicsDepth fine-tune (`Code/ComicsDepth`), compared against MiDaS and Depth Anything V2.
6. **OCR transcription (required; not in human ground truth).** Run a dedicated OCR model (trained only for OCR, not a general VLM) on crops of the **human PopManga text boxes**, one crop per box, original pixel coordinates kept. Details below.

## Character grounding stage (stage 4)
Source: "From Panels to Prose" (Sachdeva & Zisserman, arXiv:2503.23344), pipeline step 4; MAGI v3
API `predict_character_grounding` (already checked present in the checkpoint by `run_magi3.py`).
- **Why:** Qwen captions refer to characters only by appearance ("the boy with spiky hair", "he").
  Grounding puts a box on every character-referring phrase, including pronouns. Matching these boxes
  to the **human** PopManga character boxes (IoU + Hungarian matching, within the same panel) gives
  each phrase a human cluster and **ground-truth name**. That makes the captions character-aware
  without letting the VLM guess names (`docs/notes/imp.md`).
- **Input:** each MAGI v3 panel crop plus its Qwen panel caption (prompt v4: no names, no quoted
  dialogue, so no pronouns inside quotes reach the grounder). Page summaries are not grounded,
  because grounding works per panel.
- **Output:** `annotations/magi3_grounding/<page>.json`. For each panel: caption, phrases with
  character-span offsets and predicted boxes (page coordinates), then matches to MAGI v3 character
  boxes and to human character boxes, with IoU, the matched human cluster and name, and status
  (`matched` / `ambiguous` / `unmatched`). The raw model output is kept.
- **Reliability:** grounding is model-inferred. The paper reports F1 0.69–0.74 on PopCaptions,
  dropping in crowded panels. Keep IoU and margin thresholds configurable, never treat a link as
  human ground truth, and send uncertain links to review before they are used in questions.
- **Constraints:** the decoder has a 1024-token limit (caption plus interleaved box tokens). Panel
  captions are capped at 150 words, which fits, but flag truncation the same way as for MAGI v3.
- **Optional later step (paper step 5):** page prose from grounded panel captions plus the OCR
  transcript in reading order. The paper (Fig. 11–12) shows that direct whole-page VLM descriptions
  misorder panels and confuse characters, so for evidence prefer per-panel facts over the Qwen page
  summary.

## OCR stage (stage 6)
- **Why:** dialogue/speaker questions, quoting text in answers, and the name-visibility rule (see `imp.md`: a character name used in a question/answer must be readable in the selected pages) all need the actual text. Human PopManga annotations have text boxes but no transcriptions.
- **Input:** human text boxes (category 1) per page; crop with a small configurable margin; record crop box, padding, rotation (vertical text) and any resize.
- **Model selection (before full run):** shortlist OCR-only models suited to English (and possibly Japanese) comic lettering. Pick by measured accuracy on a held-out set with reference transcripts: eBDtheque English text lines and Manga109 text regions (both have transcriptions locally), plus a small hand-checked PopManga sample. Report CER/exact match per candidate. Existing `magi3.ocr` outputs (present in the `popmanga_*` TARs) are a comparison/fallback, not the default source.
- **Output:** `data/annotations/ocr/` per page: `text_id` (human box index), box, transcription, normalized text (case/whitespace/hyphenation joined), confidence if the model gives one, model id + revision + crop settings, status (`ok` / `empty` / `low_confidence` / `failed`).
- **Provenance:** OCR text is a **model-inferred** source, never human ground truth. Questions whose answer depends on exact OCR text need verification (confidence threshold and/or human review).
- **Uses downstream:** dialogue index (03), name-visibility check against character names/aliases (05, 09), text-dependent QA families.

## Design
- Inspect existing outputs and scripts first. Build **ingestion adapters** and manifests; do not rerun or reimplement models if outputs are already provided.
- Make stages individually runnable and resumable; each stage records prerequisites, model revision, prompt/config, input hash, output location and status.
- Preserve human and model annotations separately; do not silently reconcile conflicting facts.
- Align bounding boxes and masks with original page/panel coordinate systems. Validate panel and page associations.
- Mark depth unavailable/low-confidence where appropriate; depth processing must not block non-depth tasks.
- Keep structural MAGI-3 outputs (stage 2) separate from grounding outputs (stage 4); grounding depends on a specific caption version (record the Qwen prompt version and caption hashes).

## Outputs
`data/annotations/{human,magi3,qwen,magi3_grounding,depth,ocr}/`, stage manifests, normalization-ready source refs.

## Acceptance checks
Existing artifacts ingest without inference; missing stages skip gracefully; transformations invertible/documented; no source data overwritten; stage dependencies explicit.

## Codex request
Inspect current scripts and output samples, report what exists vs missing, propose adapters and stage commands; wait for approval.
