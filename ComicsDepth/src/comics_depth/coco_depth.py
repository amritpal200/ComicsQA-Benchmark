"""Stage: MiDaS v2.1 pseudo ground-truth depth for COCO val2017 (natural domain).

Upstream (datasets_preparation.py --coco17_depth) saved pred/max as 8-bit PNG plus the max in a
.txt, and fed MiDaS without ImageNet normalization. Here MiDaS gets its documented input
transform and the raw network output is saved as float32 .npy. (MiDaS v2.1 outputs are in the
thousands, where float16 steps by 2-4, so float16 would be barely finer than upstream's 8 bits.)

Output (never overwritten): {root}/data/<coco.name>/{depth/<stem>.npy, index.jsonl, prepare.json}
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
from .depth_models import MidasPredictor
from .io_utils import atomic_write_bytes, atomic_write_json, run_metadata, write_jsonl
from .webdataset import IMAGE_EXTS


def list_images(folder):
    return sorted(p for p in Path(folder).iterdir()
                  if p.is_file() and p.suffix.lower().lstrip(".") in IMAGE_EXTS)


def npy_bytes(array):
    buffer = io.BytesIO()
    np.save(buffer, array)
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="prepare-coco", description=__doc__.splitlines()[0])
    config_lib.add_config_args(parser)
    parser.add_argument("--limit", type=int, default=0, help="only the first N images (smoke test)")
    parser.add_argument("--device", default="cuda", help="cuda (default) or cpu for tiny tests")
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    out_dir = config_lib.coco_dir(cfg)
    if args.limit:
        # Keep smoke outputs separate from the full set.
        out_dir = out_dir.with_name(f"{out_dir.name}_limit{args.limit}")
    partial = out_dir.with_name(out_dir.name + ".partial")
    if out_dir.exists():
        print(f"Already prepared: {out_dir}. Choose a new --set coco.name=... to rebuild.")
        return 0
    images = list_images(cfg["paths"]["coco_images"])
    if args.limit:
        images = images[: args.limit]
    if not images:
        print(f"No images in {cfg['paths']['coco_images']}", file=sys.stderr)
        return 1
    if args.device == "cuda" and not torch.cuda.is_available():
        print("CUDA is not available; pass --gpu N to scripts/run.sh", file=sys.stderr)
        return 1
    device = torch.device(args.device)
    predictor = MidasPredictor("midas", cfg["paths"]["midas_weights"], device, cfg["coco"]["size"])

    # Resumable: existing .npy files in the partial folder are kept.
    records, start = [], time.time()
    for n, path in enumerate(images, 1):
        target = partial / "depth" / f"{path.stem}.npy"
        with Image.open(path) as handle:
            image = handle.convert("RGB")
        if target.exists():
            depth = np.load(target)
        else:
            depth = predictor.raw(image).astype(np.float32)
            if not np.isfinite(depth).all():
                print(f"non-finite prediction for {path}", file=sys.stderr)
                return 1
            atomic_write_bytes(target, npy_bytes(depth))
        records.append({"stem": path.stem, "image": str(path), "image_size": list(image.size),
                        "depth_shape": list(depth.shape), "depth_max": float(depth.max())})
        if n % 250 == 0 or n == len(images):
            rate = n / max(time.time() - start, 1e-6)
            print(f"  {n}/{len(images)} ({rate:.1f} img/s)")
    write_jsonl(partial / "index.jsonl", records)
    atomic_write_json(partial / "prepare.json", {
        "model": predictor.meta, "images": len(records), "limit": args.limit,
        "config": {"coco": cfg["coco"], "paths": cfg["paths"]}, "meta": run_metadata()})
    partial.rename(out_dir)
    print(f"Done: {out_dir}")
    return 0
