# ComicsQA Benchmark

A chapter-level, evidence-grounded manga question-answering benchmark built from PopManga, plus
the tools that produce its annotations, including a manga depth model.
Plan and rules: [docs/ROADMAP.md](docs/ROADMAP.md), [AGENTS.md](AGENTS.md), [docs/specs/](docs/specs/).

## Pipeline
```
PopManga images + human annotations (read-only)
   │
   ├─ annotations/human        human boxes, names, speaker/tail links          (spec 02)
   ├─ annotations/magi3        panels, characters, text, reading order          (model)
   ├─ annotations/qwen         panel captions, page summaries                    (model)
   ├─ annotations/magi3_prose  prose enrichment (only once verified)            (model)
   ├─ annotations/ocr          OCR of human text boxes, OCR-only model           (model)
   └─ annotations/depth   <──  ComicsDepth/  manga depth model (trained here)   (model)
   │
   ▼  core/  shared schemas, stable IDs, reading order, manifests               (spec 01)
   │
   ▼  evidence/  characters · dialogue · timeline · spatial · depth · graph      (spec 03)
   │             └─ packs/: per-task selection of pages + facts
   │
   ▼  tasks/  narrative · character · dialogue · graph · hybrid · spatial ·      (specs 04-07)
   │          depth · page_order
   │
   ▼  inference/ + slurm/  Qwen3-VL-32B-Thinking on MN5 (vLLM)                   (spec 08)
   │
   ▼  validation/  checks, unique answers, name visibility, dedupe, review       (spec 09)
   │
   ▼  export/  benchmark_public.jsonl · benchmark_private.jsonl · reports        (spec 09)
```

## Layout
| Folder | Contents |
|---|---|
| `ComicsDepth/` | Manga depth model (ComicsDepth re-implementation); its own environment, see its README |
| `src/comics_qa/` | Benchmark package; one subfolder per pipeline stage (each has a README) |
| `configs/{local,mn5,tasks}` | Run configurations |
| `scripts/`, `slurm/` | Launchers and MN5 Slurm jobs |
| `tests/` | CPU tests with synthetic fixtures |
| `docs/specs/` | Stage specifications 00-09 |
| `docs/prompts/` | Prompts for running a stage with a coding assistant |
| `docs/notes/` | Design notes (e.g. name visibility, page-order task) |

Large data, model weights, environments and outputs live outside the repository, under
`/data/151-3/comics/` (for example `/data/151-3/comics/ComicsDepth/`); see `.gitignore`.

## Status
| Part | State |
|---|---|
| ComicsDepth | Implemented and tested; full training running |
| Everything under `src/comics_qa/` | Planned (folders only) |
