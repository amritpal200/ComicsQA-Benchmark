"""Compare depth models on held-out manga panels (val split of prepare-manga).

There is no manga depth ground truth yet, so the default report is diagnostic:
  - side-by-side grids (panel | text mask | one column per model) for visual review;
  - text_contrast: |median depth inside the text mask - median depth in a ring around it|,
    divided by the panel's 5-95% depth range. Zero-shot MiDaS tends to make speech balloons
    pop out as near discs (the problem ComicsDepth targets); lower = less pop-out;
  - text_gradient_ratio: mean |gradient| of normalized depth inside text regions divided by
    outside (texture artefacts inside balloons). Neither is an accuracy measure;
  - pairwise ordering agreement between models on random pixel pairs (agreement, not accuracy).
If --annotations is given (files <panel_id>.txt in ordering.py format, coordinates in panel
pixels), inter/intra-object ordering accuracy is reported for each model.
"""

import argparse
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

from . import config as config_lib
from .depth_models import build_predictor, depth_to_png
from .io_utils import atomic_write_bytes, atomic_write_json, read_jsonl, run_metadata
from .ordering import ordering_accuracy, read_ordering, summarize


def normalized(depth):
    lo, hi = float(depth.min()), float(depth.max())
    return (depth - lo) / (hi - lo) if hi > lo else np.zeros_like(depth)


def text_gradient_ratio(depth, mask):
    """Mean gradient magnitude of normalized depth inside vs outside the text mask."""
    d = normalized(depth.astype(np.float32))
    gy, gx = np.gradient(d)
    grad = np.hypot(gx, gy)
    inside, outside = mask > 0, mask == 0
    if inside.sum() < 50 or outside.sum() < 50:
        return None
    return float(grad[inside].mean() / max(grad[outside].mean(), 1e-8))


def dilate(mask, radius):
    """Binary dilation with a (2r+1)^2 square, via a summed-area table."""
    padded = np.pad(mask.astype(np.int64), radius + 1)
    sat = padded.cumsum(0).cumsum(1)
    k = 2 * radius + 1
    sums = sat[k:, k:] - sat[:-k, k:] - sat[k:, :-k] + sat[:-k, :-k]
    return sums[: mask.shape[0], : mask.shape[1]] > 0


def text_contrast(depth, mask):
    """Text-region vs surrounding-ring depth difference, relative to the panel depth range."""
    inside = mask > 0
    if inside.sum() < 50 or (~inside).sum() < 50:
        return None
    radius = max(4, round(0.03 * min(mask.shape)))
    ring = dilate(inside, radius) & ~inside
    if ring.sum() < 50:
        return None
    lo, hi = np.percentile(depth, [5, 95])
    if hi <= lo:
        return None
    return float(abs(np.median(depth[inside]) - np.median(depth[ring])) / (hi - lo))


def ordering_agreement(a, b, rng, samples):
    height, width = a.shape
    ys1, xs1 = rng.integers(0, height, samples), rng.integers(0, width, samples)
    ys2, xs2 = rng.integers(0, height, samples), rng.integers(0, width, samples)
    sa = np.sign(a[ys1, xs1] - a[ys2, xs2])
    sb = np.sign(b[ys1, xs1] - b[ys2, xs2])
    keep = (sa != 0) & (sb != 0)
    return float((sa[keep] == sb[keep]).mean()) if keep.any() else None


def tile(image, height):
    width = max(1, round(image.width * height / image.height))
    return image.convert("RGB").resize((width, height), Image.BILINEAR)


def make_grid(rows, labels, row_height=256):
    """rows: list of lists of PIL images (same length as labels)."""
    tiles = [[tile(im, row_height) for im in row] for row in rows]
    col_widths = [max(r[c].width for r in tiles) for c in range(len(labels))]
    header = 24
    grid = Image.new("RGB", (sum(col_widths) + 4 * len(labels), header + len(rows) * (row_height + 4)),
                     "white")
    draw = ImageDraw.Draw(grid)
    x = 0
    for c, label in enumerate(labels):
        draw.text((x + 4, 4), label, fill="black")
        for r, row in enumerate(tiles):
            grid.paste(row[c], (x, header + r * (row_height + 4)))
        x += col_widths[c] + 4
    return grid


def mask_overlay(panel, mask):
    overlay = panel.convert("RGB").copy()
    red = Image.new("RGB", overlay.size, (255, 0, 0))
    return Image.composite(Image.blend(overlay, red, 0.5), overlay, mask.point(lambda v: 255 if v else 0))


def main(argv=None):
    parser = argparse.ArgumentParser(prog="evaluate", description=__doc__.splitlines()[0])
    config_lib.add_config_args(parser)
    parser.add_argument("--output", type=Path, required=True, help="new report folder")
    parser.add_argument("--models", nargs="+", default=None, help="override evaluate.models")
    parser.add_argument("--weights", type=Path, default=None, help="comicsdepth model.pt override")
    parser.add_argument("--annotations", type=Path, default=None,
                        help="folder of <panel_id>.txt depth-ordering annotations")
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    e = cfg["evaluate"]
    models = args.models or e["models"]
    if args.output.exists():
        print(f"{args.output} exists; choose a new folder", file=sys.stderr)
        return 1

    manga_dir = config_lib.manga_dir(cfg)
    records = read_jsonl(manga_dir / "val.jsonl")
    if args.annotations:
        annotated = {p.stem for p in args.annotations.glob("*.txt")}
        records = [r for r in records if r["id"] in annotated]
        print(f"{len(records)} val panels have annotations")
    else:
        records = random.Random(e["seed"]).sample(records, min(e["panels"], len(records)))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    predictions = {m: {} for m in models}
    report = {"models": {}, "panels": [r["id"] for r in records],
              "manga": str(manga_dir), "meta": run_metadata()}
    for name in models:
        predictor = build_predictor(name, cfg, device, args.weights)
        start = time.time()
        for record in records:
            with Image.open(manga_dir / "val" / "panels" / f"{record['id']}.png") as handle:
                predictions[name][record["id"]] = predictor(handle.convert("RGB"))
        report["models"][name] = {"meta": predictor.meta,
                                  "seconds_per_panel": (time.time() - start) / max(len(records), 1)}
        del predictor
        if device.type == "cuda":
            torch.cuda.empty_cache()

    masks = {}
    for record in records:
        with Image.open(manga_dir / "val" / "masks" / f"{record['id']}.png") as handle:
            masks[record["id"]] = handle.convert("L")
    for name in models:
        ratios = [text_gradient_ratio(predictions[name][pid], np.asarray(masks[pid]))
                  for pid in predictions[name]]
        ratios = [r for r in ratios if r is not None]
        report["models"][name]["text_gradient_ratio_median"] = (
            float(np.median(ratios)) if ratios else None)
        report["models"][name]["text_gradient_ratio_panels"] = len(ratios)
        contrasts = [text_contrast(predictions[name][pid], np.asarray(masks[pid]))
                     for pid in predictions[name]]
        contrasts = [c for c in contrasts if c is not None]
        report["models"][name]["text_contrast_median"] = (
            float(np.median(contrasts)) if contrasts else None)
        report["models"][name]["text_contrast_panels"] = len(contrasts)
        if args.annotations:
            counts = [ordering_accuracy(predictions[name][r["id"]],
                                        read_ordering(args.annotations / f"{r['id']}.txt"))
                      for r in records]
            report["models"][name]["ordering"] = summarize(counts)

    rng = np.random.default_rng(e["seed"])
    report["agreement"] = {}
    for i, a in enumerate(models):
        for b in models[i + 1:]:
            values = [ordering_agreement(predictions[a][pid], predictions[b][pid], rng,
                                         e["pair_samples"]) for pid in predictions[a]]
            values = [v for v in values if v is not None]
            report["agreement"][f"{a}~{b}"] = float(np.mean(values)) if values else None

    per_grid = e["panels_per_grid"]
    for g in range(0, len(records), per_grid):
        rows = []
        for record in records[g:g + per_grid]:
            with Image.open(manga_dir / "val" / "panels" / f"{record['id']}.png") as handle:
                panel = handle.convert("RGB")
            rows.append([panel, mask_overlay(panel, masks[record["id"]])]
                        + [depth_to_png(predictions[m][record["id"]]) for m in models])
        grid = make_grid(rows, ["panel", "text mask"] + models)
        path = args.output / f"grid_{g // per_grid:03d}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        grid.save(path)
    atomic_write_json(args.output / "report.json", report)
    write_markdown(args.output / "report.md", report)
    print((args.output / "report.md").read_text())
    return 0


def write_markdown(path, report):
    lines = ["# Depth evaluation on manga val panels", "",
             f"Panels: {len(report['panels'])}. Diagnostics only unless ordering annotations "
             "were supplied.", "",
             "| model | s/panel | text contrast (median, lower = less balloon pop-out) | "
             "text gradient ratio (median) | inter acc | intra acc |",
             "|---|---:|---:|---:|---:|---:|"]
    for name, info in report["models"].items():
        ordering = info.get("ordering") or {}
        fmt = lambda v: "n/a" if v is None else f"{v:.3f}"
        lines.append(f"| {name} | {info['seconds_per_panel']:.3f} | "
                     f"{fmt(info['text_contrast_median'])} | "
                     f"{fmt(info['text_gradient_ratio_median'])} | "
                     f"{fmt(ordering.get('inter_accuracy'))} | {fmt(ordering.get('intra_accuracy'))} |")
    if report["agreement"]:
        lines += ["", "Pairwise ordering agreement (random pixel pairs):", ""]
        lines += [f"- {k}: {v:.3f}" if v is not None else f"- {k}: n/a"
                  for k, v in report["agreement"].items()]
    atomic_write_bytes(path, ("\n".join(lines) + "\n").encode())
