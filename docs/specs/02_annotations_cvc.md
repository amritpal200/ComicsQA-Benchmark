# 02 — CVC annotation pipeline and ingestion

## Dependencies
Foundation schemas; original images/human annotations. Annotation production occurs on CVC GPU server, not MN5 QA workers.

## Required sequence and branches
1. Load original PopManga human annotations (identity/name/bbox/text links if present).
2. MAGI-3 structural annotation: panels, characters, text and available associations.
3. Qwen-32B-Instruct: panel captions, page summaries, supported action/event descriptions.
4. Second MAGI-3 pass for prose captions/enrichment **only after confirming the actual implementation and required inputs**.
5. Depth estimation in parallel, if available, with recorded resize/crop transforms and depth convention. Depth model: our ComicsDepth fine-tune (`Code/ComicsDepth`), compared against MiDaS and Depth Anything V2.
6. **OCR transcription (required; not in human ground truth).** Run a dedicated OCR model (trained only for OCR, not a general VLM) on crops of the **human PopManga text boxes**, one crop per box, original pixel coordinates kept. Details below.

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
- Distinguish structured MAGI-3 outputs from prose enrichment and verify whether the latter is supported.

## Outputs
`data/annotations/{human,magi3,qwen,magi3_prose,depth,ocr}/`, stage manifests, normalization-ready source refs.

## Acceptance checks
Existing artifacts ingest without inference; missing stages skip gracefully; transformations invertible/documented; no source data overwritten; stage dependencies explicit.

## Codex request
Inspect current scripts and output samples, report what exists vs missing, propose adapters and stage commands; wait for approval.
