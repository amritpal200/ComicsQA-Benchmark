"""Predict depth for a folder of images or for prepared manga panels.

Output folder (new, or resumed with --resume): <id>.npy (float16 inverse depth at the input
resolution), <id>.png (per-image min-max visualization, bright = closer), predictions.jsonl
and predict.json (model, weights checksum, convention, inputs).
"""

import argparse
import io
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from . import config as config_lib
from .depth_models import MODEL_NAMES, build_predictor, depth_to_png
from .io_utils import atomic_write_bytes, atomic_write_json, read_jsonl, run_metadata, write_jsonl
from .webdataset import IMAGE_EXTS


def folder_items(folder: Path):
    paths = sorted(p for p in folder.rglob("*")
                   if p.is_file() and p.suffix.lower().lstrip(".") in IMAGE_EXTS)
    for path in paths:
        rel = path.relative_to(folder)
        yield {"id": str(rel.with_suffix("")).replace("/", "__"), "image": str(path),
               "source": {"file": str(rel)}}


def manga_items(manga_dir: Path, split: str):
    for record in read_jsonl(manga_dir / f"{split}.jsonl"):
        yield {"id": record["id"], "image": str(manga_dir / split / "panels" / f"{record['id']}.png"),
               "source": {k: record[k] for k in ("tar", "key", "panel_index", "panel_box", "page_size")}}


def npy_bytes(array):
    buffer = io.BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="predict", description=__doc__.splitlines()[0])
    config_lib.add_config_args(parser)
    parser.add_argument("--model", choices=MODEL_NAMES, default="comicsdepth")
    parser.add_argument("--weights", type=Path, default=None, help="comicsdepth model.pt override")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--images", type=Path, help="folder of images (searched recursively)")
    source.add_argument("--manga-split", choices=["train", "val"], help="prepared manga panels")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true", help="continue an existing output folder")
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)

    if args.output.exists() and not args.resume:
        print(f"{args.output} exists; pass --resume to continue it or choose a new folder",
              file=sys.stderr)
        return 1
    items = list(folder_items(args.images) if args.images
                 else manga_items(config_lib.manga_dir(cfg), args.manga_split))
    if args.limit:
        items = items[: args.limit]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    predictor = build_predictor(args.model, cfg, device, args.weights)
    atomic_write_json(args.output / "predict.json", {
        "model": predictor.meta, "inputs": str(args.images or f"manga:{args.manga_split}"),
        "items": len(items), "meta": run_metadata()})

    records, start = [], time.time()
    for n, item in enumerate(items, 1):
        target = args.output / f"{item['id']}.npy"
        with Image.open(item["image"]) as handle:
            image = handle.convert("RGB")
        if not target.exists():
            depth = predictor(image)
            atomic_write_bytes(target, npy_bytes(depth.astype(np.float16)))
            if not args.no_png:
                buffer = io.BytesIO()
                depth_to_png(depth).save(buffer, format="PNG")
                atomic_write_bytes(args.output / f"{item['id']}.png", buffer.getvalue())
        records.append({"id": item["id"], "image": item["image"], "size": list(image.size),
                        "depth": str(target), "model": args.model, **item["source"]})
        if n % 100 == 0 or n == len(items):
            print(f"  {n}/{len(items)} ({n / max(time.time() - start, 1e-6):.1f} img/s)")
    write_jsonl(args.output / "predictions.jsonl", records)
    print(f"Done: {args.output}")
    return 0
