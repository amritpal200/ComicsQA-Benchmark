"""Check that downloaded MiDaS v2.1 weights load strictly into the vendored network and run."""

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from . import config as config_lib
from .depth_models import MidasPredictor


def main(argv=None):
    parser = argparse.ArgumentParser(prog="verify-weights", description=__doc__)
    config_lib.add_config_args(parser)
    parser.add_argument("--weights", type=Path, default=None,
                        help="checkpoint to check (default: paths.midas_weights)")
    parser.add_argument("--image", type=Path, default=None, help="optional real image to run")
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    weights = args.weights or Path(cfg["paths"]["midas_weights"])
    if not weights.exists():
        print(f"Missing {weights}; run scripts/download_weights.sh", file=sys.stderr)
        return 1
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    predictor = MidasPredictor("midas", weights, device)
    params = sum(p.numel() for p in predictor.model.parameters())
    print(f"loaded strictly: {weights}\n  sha256 {predictor.meta['weights_sha256']}\n"
          f"  parameters {params / 1e6:.1f}M on {device}")
    if args.image:
        with Image.open(args.image) as handle:
            image = handle.convert("RGB")
    else:
        # Synthetic scene: bright floor (bottom) fading to dark sky (top).
        ramp = np.linspace(0, 255, 384, dtype=np.float32)[:, None].repeat(512, 1)
        image = Image.fromarray(np.stack([ramp] * 3, -1).astype(np.uint8))
    depth = predictor(image)
    ok = bool(np.isfinite(depth).all()) and depth.shape == image.size[::-1]
    print(f"  output {depth.shape} min {depth.min():.3f} max {depth.max():.3f} finite={ok}")
    return 0 if ok else 1
