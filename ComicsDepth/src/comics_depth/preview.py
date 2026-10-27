"""Preview depth on a reproducible random sample of validation panels or folder images."""

import argparse
import html
import io
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageOps

from . import config as config_lib
from .depth_models import build_predictor, depth_to_png
from .io_utils import atomic_write_bytes, atomic_write_json, run_metadata, write_jsonl
from .predict import folder_items, manga_items, npy_bytes


def sample_items(items, count, seed):
    if not 1 <= count <= len(items):
        raise ValueError(f"--count must be between 1 and {len(items)} (available images)")
    return random.Random(seed).sample(items, count)


def save_png(path, image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    atomic_write_bytes(path, buffer.getvalue())


def comparison(image, depth, label):
    """Fit originals and maps without distortion into equally sized viewing areas."""
    canvas = Image.new("RGB", (960, 528), "#dddddd")
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 8), f"{label} | Original", fill="black")
    draw.text((492, 8), "Relative depth: brighter = closer", fill="black")
    draw.text((492, 26), "Normalized separately for each image", fill="black")
    for offset, source in ((0, image), (480, depth.convert("RGB"))):
        tile = ImageOps.contain(source, (480, 480), Image.Resampling.LANCZOS)
        canvas.paste(tile, (offset + (480 - tile.width) // 2, 48 + (480 - tile.height) // 2))
    return canvas


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    config_lib.add_config_args(parser)
    parser.add_argument("--images", type=Path, help="image folder; default: prepared validation panels")
    parser.add_argument("--weights", type=Path, help="override the configured run's model.pt")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True, help="new output directory")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    if args.output.exists():
        parser.error("--output already exists; choose a new directory")
    if args.images is not None and not args.images.is_dir():
        parser.error(f"Image directory does not exist: {args.images}")
    items = list(folder_items(args.images) if args.images is not None else
                 manga_items(config_lib.manga_dir(cfg), "val"))
    try:
        selected = sample_items(items, args.count, args.seed)
    except ValueError as exc:
        parser.error(str(exc))
    for item in selected:
        if not Path(item["image"]).is_file():
            parser.error(f"Image missing: {item['image']}")
    device = torch.device(("cuda" if torch.cuda.is_available() else "cpu")
                          if args.device == "auto" else args.device)
    predictor = build_predictor("comicsdepth", cfg, device, args.weights)
    args.output.mkdir(parents=True, exist_ok=False)
    atomic_write_json(args.output / "preview.json", {
        "model": predictor.meta, "seed": args.seed, "count": args.count,
        "population": len(items), "source": str(args.images or config_lib.manga_dir(cfg) / "val"),
        "selected": selected, "device": str(device), "meta": run_metadata()})
    records, cards, previews = [], [], []
    for number, item in enumerate(selected, 1):
        stem = f"{number:02d}"
        with Image.open(item["image"]) as handle:
            image = handle.convert("RGB")
        depth = predictor(image)
        if depth.shape != (image.height, image.width) or not np.isfinite(depth).all():
            raise ValueError(f"Invalid depth prediction for {item['image']}")
        depth_image = depth_to_png(depth)
        visual = comparison(image, depth_image, stem)
        save_png(args.output / f"{stem}_original.png", image)
        save_png(args.output / f"{stem}_depth.png", depth_image)
        save_png(args.output / f"{stem}_comparison.png", visual)
        atomic_write_bytes(args.output / f"{stem}_depth.npy", npy_bytes(depth.astype(np.float32)))
        previews.append(visual)
        records.append({**item, "number": number, "depth": f"{stem}_depth.npy",
                        "comparison": f"{stem}_comparison.png", "size": list(image.size)})
        cards.append(f'<article><h2>{number:02d}</h2><p>{html.escape(item["image"])}</p>'
                     f'<a href="{stem}_comparison.png"><img src="{stem}_comparison.png" '
                     f'alt="Original and predicted depth for image {number}"></a></article>')
        print(f"[{number}/{len(selected)}] {item['image']}", flush=True)
        image.close()
    for start in range(0, len(previews), 5):
        group = previews[start:start + 5]
        sheet = Image.new("RGB", (960, 528 * len(group)), "white")
        for row, visual in enumerate(group):
            sheet.paste(visual, (0, row * 528))
        save_png(args.output / f"overview_{start // 5 + 1:02d}.png", sheet)
    write_jsonl(args.output / "predictions.jsonl", records)
    page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>ComicsDepth preview</title><style>'
            'body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 16px}'
            'img{width:100%;height:auto}p{overflow-wrap:anywhere}article{margin:32px 0}'
            '</style><h1>ComicsDepth preview</h1>'
            '<p>Original on the left; relative inverse depth on the right. Brighter means closer. '
            'Each image is normalized independently; values are not metric distances.</p>'
            f'<p>Random seed: {args.seed}. Input size: {cfg["predict"]["size"]}.</p>'
            + ''.join(cards) + '</html>')
    atomic_write_bytes(args.output / "index.html", page.encode("utf-8"))
    print(f"Open {args.output / 'index.html'} or overview_*.png to view the results.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
