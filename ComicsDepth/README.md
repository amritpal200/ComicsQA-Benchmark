# ComicsDepth for manga

Depth estimation for manga panels, re-implementing **ComicsDepth** (Bhattacharjee et al.,
WACV 2022) on our own MAGI-3 annotated manga webdataset. Output is used by the ComicsQA
benchmark (spatial/depth questions, spec 07).

The upstream repository cannot be run as published: its pretrained models are gone (Drive link
returns 404, GitHub issue #8), and `models/models.py`, `utils/` and the depth inference scripts
were never committed (issues #1, #4, #5). This is a clean rewrite that keeps the paper's
networks, losses and hyperparameters. See `third_party/NOTICE.md` for the file mapping.

## Method
```
COCO val2017 (5K photos) --MiDaS v2.1--> pseudo-depth targets            [prepare-coco]
manga panels + text masks from MAGI-3 boxes (no PopManga)                 [prepare-manga]
CycleGAN 1: photo <-> text-free manga crops                               [train-without-text]
CycleGAN 2: paste real manga text into translated photos                  [train-add-text]
Fine-tune MiDaS v2.1 on translated photos, loss ignores text regions      [train-depth]
=> model.pt : manga panel -> relative inverse depth (larger = closer)     [predict, evaluate]
```

**Output convention.** Every model returns relative inverse depth (larger value = closer). Each
image has an unknown scale and shift, so values aren't metric distances. Compare values only
within one panel.

## Differences from upstream (deliberate)
| Upstream | Here | Why |
|---|---|---|
| DCM comic frames + eBDtheque U-Net text detector | MAGI-3 `panels`, `texts` + `ocr.bboxes` + `tails` from our TARs; text boxes grown by 50% of their short side (≥ 6 px) | manga only, our data only; MAGI-3 has no balloon outlines, so the margin approximates balloons |
| text-free crops: 20 random tries per size, then hand-filtered `_human` folder | largest text-free square found exactly (summed-area table), random position | the hand-filtered folder was never released |
| COCO depth via MiDaS **without** ImageNet normalization, saved as 8-bit PNG | MiDaS documented transform, raw output as float32 `.npy` | correct MiDaS usage, no quantization |
| depth loss `(B,H,W) * (B,1,H,W)` broadcasts to `(B,B,H,W)` | each sample masked by its own text mask | bug fix (regression test in `tests/`) |
| `torch.hub` downloads MiDaS code + WSL backbone at runtime | vendored MiDaS v2.1, weights from one local file | offline, reproducible |
| checkpoint every epoch (≈130 GB for depth) | `latest.pth` + every N epochs + `final.pth` (hard links) | disk is ~92% full |

Kept as upstream: generator/discriminator architectures, LSGAN + L1 loss weights, Adam defaults
(lr 1e-3) for the CycleGANs, lr 1e-6 for MiDaS, batch sizes 4/16/16, 384 crops, 100 epochs,
epoch = max(#photos, #manga crops).

Known limitations:
- **Sound effects stay in the "text-free" crops.** MAGI-3 does not detect onomatopoeia.
- **There's no manga depth ground truth yet.** `evaluate` is diagnostic until we annotate panels.
- **PopManga is excluded from training** (`popmanga_dev`, `popmanga_extended`), because the QA benchmark is built on it.

## Layout
| What | Where |
|---|---|
| code | this folder |
| environment | `/data/151-3/comics/.cache/ComicsDepth/venv-<host>` |
| caches | `/data/151-3/comics/.cache/ComicsDepth/`, shared uv cache, `/data/151-3/comics/.cache/hf_cache` |
| MiDaS weights | `/data/151-3/comics/models/MiDaS/midas_v21_384.pt` |
| prepared data | `/data/151-3/comics/ComicsDepth/data/{manga_v1,coco_val2017_midas_v21}` |
| training runs | `/data/151-3/comics/ComicsDepth/runs/<run>/{without_text,add_text,depth}` |
| final model | `/data/151-3/comics/ComicsDepth/runs/v1/depth/model.pt` (+ `model.json`) |
| inputs (read-only) | `mangas_webdatasets/combined_mangasDatasets` + `splits_balanced.json`; COCO at `/data/130-1/shared/coco/val2017` |

All settings are in `configs/default.toml`; override any setting with `--set section.key=value`.
Finished outputs are never overwritten: change `manga.name`, `coco.name` or `train.run` to
build a new version. Training resumes from `latest.pth` when rerun with the same config, and
refuses to resume if the config or inputs changed.

## Commands
Every command runs through `bash scripts/run.sh <command> [--gpu N] [options]`.

```bash
cd /home/asingh/Comics/ComicsQA_Benchmark/Code/ComicsDepth

# 1. environment (once per host) and weights (~420 MB)
bash scripts/setup_env.sh                 # add --baseline for Depth Anything V2 support
bash scripts/download_weights.sh          # add --baseline for Depth Anything V2 (~1.3 GB)
bash scripts/run.sh test                  # CPU unit tests
CD_SLOW_TESTS=1 bash scripts/run.sh test  # + end-to-end CPU smoke of every stage (~1 min)
bash scripts/run.sh verify-weights --gpu 2

# 2. smoke run on small data (separate names, safe to delete afterwards)
S="--set manga.name=manga_smoke --set manga.train_panels=200 --set manga.val_panels=20
   --set coco.name=coco_val2017_midas_v21_limit200 --set train.run=smoke
   --set without_text.epochs=1 --set add_text.epochs=1 --set depth.epochs=1"
bash scripts/run.sh prepare-manga $S
bash scripts/run.sh prepare-coco --gpu 2 --limit 200
bash scripts/run.sh train-without-text --gpu 2 $S
bash scripts/run.sh train-add-text --gpu 2 $S
bash scripts/run.sh train-depth --gpu 2 $S
bash scripts/run.sh evaluate --gpu 2 $S --output /data/151-3/comics/ComicsDepth/evaluation/smoke

# 3. full run (each training command can be rerun to resume)
bash scripts/run.sh prepare-manga
bash scripts/run.sh prepare-coco --gpu 2
bash scripts/run.sh train-without-text --gpu 2
bash scripts/run.sh train-add-text --gpu 2
bash scripts/run.sh train-depth --gpu 2

# 4. compare models on held-out manga panels and predict
bash scripts/run.sh evaluate --gpu 2 --models midas comicsdepth depth_anything_v2 \
  --output /data/151-3/comics/ComicsDepth/evaluation/v1
bash scripts/run.sh predict --gpu 2 --model comicsdepth --images /path/to/images \
  --output /data/151-3/comics/ComicsDepth/predictions/<name>
```

Monitor training: `tail -f <run dir>/metrics.jsonl`, and look at `<run dir>/samples/epoch_XXX.png`.
- CycleGAN 1 grid rows: photo, photo→manga, manga, manga→photo.
- CycleGAN 2 grid rows: photo, translated, real manga, mask, translated + text.
- Depth grid rows: training input, target, prediction, mask.

## Visual preview

Inspect 10 randomly selected held-out panels with the trained 512-pixel model:

```bash
bash scripts/run.sh preview --gpu 0 --config configs/fast512.toml \
  --count 10 --seed 42 \
  --output /data/151-3/comics/ComicsDepth/previews/random10_seed42
```

Open `index.html`, or view `overview_01.png` and `overview_02.png` in the output folder.
Originals appear on the left, depth on the right: **brighter = closer**. Values are relative
within each image, not metric distances. Individual original/depth/comparison PNGs, float32
depth arrays, and source/model provenance are saved too. Existing output folders are refused.
Change `--seed` and the output folder for a different sample. Add `--images /path/to/images`
to sample your own folder instead. The model was trained on panels; whole-page predictions
mix independent scenes. Use an available GPU instead of `0`, or `--device cpu` without a GPU.

## Evaluation
`evaluate` samples `evaluate.panels` val panels and writes:
- `grid_*.png`: side-by-side panel | text mask | each model;
- `report.json` / `report.md` with the **text gradient ratio** (depth edges inside text vs
  elsewhere; balloons are flat, so lower is better). This is a diagnostic, not accuracy;
- pairwise model agreement;
- with `--annotations DIR` (`<panel_id>.txt`, lines `inter intra x y`, 1 = closest, panel
  pixel coordinates), inter- and intra-object **depth-ordering accuracy**, as in the paper's
  benchmark.
