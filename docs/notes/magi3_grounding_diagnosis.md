# MAGI-3 caption grounding diagnosis — 2026-10-28

Read-only inspection of the latest logged four-worker run, started with log prefix
`20261028_174505` on **cudahpc30**. Inspection host: cudahpc51; no assertion about
live processes on cudahpc30 was made. The journals record all four workers ended.
No inference was launched, and no model, annotation or runner code was changed.

Output root: `/data/151-3/comics/ComicsQA_Benchmark/annotations/magi3_grounding`.

| Shard | Last finished page count | Outcome |
|---|---:|---|
| 0/4, GPU 0 | 506/506 | complete |
| 1/4, GPU 0 | 131/506 | fatal CUDA device-side assertion |
| 2/4, GPU 1 | 149/505 | fatal CUDA device-side assertion |
| 3/4, GPU 1 | 297/505 | fatal CUDA device-side assertion |

Current inventory: **1,084 / 2,022 page JSONs**, **938 missing**, zero extra files,
zero malformed JSONs. All saved pages and their 5,157 panels are marked complete.
All 1,084 page signatures match the current Qwen caption/crop/signature/settings
inputs. This is operational integrity, not visual validation of grounding quality.
The crash pages were not saved as partial output because fatal CUDA errors abort
before the page write; hence `panels_failed=0` does not mean the run succeeded.

## Likely crash mechanism

Each failed worker logs the warning about exceeding the predefined **1,024-token
maximum**, immediately followed by CUDA `indexSelectLargeIndex` assertions
(`srcIndex < srcSelectDimSize`) and `device-side assert triggered`. These logs do
not show a GPU out-of-memory failure.

The local model's `slowly_generate_grounded_caption` implementation has an unsafe
length bound: it counts loop iterations, while successful chunks append eight
tokens and take a `continue` that bypasses the bottom guard. Inserted location or
special tokens can also grow the decoder without advancing through the caption.
It requests nine new tokens per generation call without checking remaining
positional capacity. `config.json` sets `max_position_embeddings=1024`.
This is strong evidence for decoder positional overflow/runaway grounding, but
no GPU reproduction or synchronous traceback was run in this investigation.
The input captions on first unfinished pages are ordinary lengths (roughly
77–146 words), so simply shortening all captions is not justified.

First unfinished pages by deterministic shard ordering (inferred from the last
progress line, not a logged panel-level crash location):

- Shard 1: Chainsaw Man c002 p023.
- Shard 2: Death Note c002 p024.
- Shard 3: Jujutsu Kaisen c002 p019.

## Saved-output issue

114/5,157 panels have `caption_exact=false` despite strict mode. Of these, 113
preserve case-insensitive word sequences (punctuation/case changes); one changes
words: World Trigger c001 p018, panel index 6. That panel also has **218 merged
entities**, versus at most eight in every other saved panel. It is a clear review
outlier; do not treat `status=complete` as evidence that this grounding is usable.
No files were deleted or relabelled during this diagnosis.

## Recovery work needed before restarting

1. Add a repository-local, versioned strict-decoder guard based on actual decoder
   sequence length including reserved generation space, plus a no-progress guard.
   Preserve the installed model files and source captions.
2. Fail/record an offending panel safely *before* a CUDA assertion; retain page
   partial/failure provenance instead of accepting truncated or runaway output.
3. Define/test exact-caption normalization and quarantine the identified outlier;
   keep raw predictions. Do not silently rewrite captions or loosen to non-strict.
4. Test the three inferred failure pages in a bounded GPU run, then resume missing
   or invalid outputs. Preserve the 1,084 saved pages unless an explicit validation
   rule marks specific panels for retry. Signature/version migration must avoid
   blindly invalidating all good outputs or silently blessing old bad ones.

Rerunning the unchanged command may hit the same pages again. Reducing workers or
batch size alone does not address the observed decoder bound: strict inference
already uses one panel per call. CKG-3 currently does not consume this grounding,
so its CPU build can proceed independently.
