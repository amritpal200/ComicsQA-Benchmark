"""Inference wrappers with one output convention.

Every model returns relative inverse depth (disparity-like): larger = closer. Values are
affine-ambiguous per image (unknown scale/shift), not metric distances. Compare values only
within one image/panel.
"""

import numpy as np
import torch
from PIL import Image

from .io_utils import sha256_file
from .networks.midas_v21 import load_midas
from .transforms import IMAGENET_MEAN, IMAGENET_STD, image_to_tensor, upper_bound_size

CONVENTION = ("relative inverse depth (disparity-like): larger = closer; per-image affine "
              "ambiguity, not metric; compare only within the same image/panel")
MODEL_NAMES = ("midas", "comicsdepth", "depth_anything_v2")


def midas_input(image: Image.Image, size=384):
    """MiDaS v2.1 default transform: upper-bound resize (multiple of 32), bicubic, ImageNet norm."""
    width, height = image.size
    resized = image.convert("RGB").resize(upper_bound_size(width, height, size, 32), Image.BICUBIC)
    tensor = image_to_tensor(resized)
    mean = torch.tensor(IMAGENET_MEAN).view(3, 1, 1)
    std = torch.tensor(IMAGENET_STD).view(3, 1, 1)
    return ((tensor - mean) / std).unsqueeze(0)


class MidasPredictor:
    def __init__(self, name, weights, device, size=384):
        self.name, self.size, self.device = name, size, device
        self.model = load_midas(weights).to(device).eval()
        self.meta = {"model": name, "architecture": "MiDaS v2.1 (MidasNet, ResNeXt-101 WSL)",
                     "weights": str(weights), "weights_sha256": sha256_file(weights),
                     "input": f"upper_bound {size}, multiple of 32, bicubic, ImageNet normalization",
                     "convention": CONVENTION}

    @torch.no_grad()
    def raw(self, image: Image.Image) -> np.ndarray:
        """Network-resolution output."""
        return self.model(midas_input(image, self.size).to(self.device))[0].float().cpu().numpy()

    @torch.no_grad()
    def __call__(self, image: Image.Image) -> np.ndarray:
        """Output resized (bilinear) to the input image size, float32 (H, W)."""
        pred = self.model(midas_input(image, self.size).to(self.device))
        pred = torch.nn.functional.interpolate(pred.unsqueeze(1), size=image.size[::-1],
                                               mode="bilinear", align_corners=False)
        return pred[0, 0].float().cpu().numpy()


class DepthAnythingPredictor:
    def __init__(self, model_id, device):
        try:
            from transformers import AutoImageProcessor, AutoModelForDepthEstimation
        except ImportError as exc:
            raise SystemExit("depth_anything_v2 needs: bash scripts/setup_env.sh --baseline") from exc
        self.device = device
        self.processor = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModelForDepthEstimation.from_pretrained(model_id).to(device).eval()
        self.meta = {"model": "depth_anything_v2", "architecture": "Depth Anything V2",
                     "weights": model_id, "input": "transformers image processor defaults",
                     "convention": CONVENTION}

    @torch.no_grad()
    def __call__(self, image: Image.Image) -> np.ndarray:
        inputs = self.processor(images=image.convert("RGB"), return_tensors="pt").to(self.device)
        outputs = self.model(**inputs)
        post = self.processor.post_process_depth_estimation(
            outputs, target_sizes=[image.size[::-1]])
        return post[0]["predicted_depth"].float().cpu().numpy()


def build_predictor(name, cfg, device, comicsdepth_weights=None):
    size = cfg["predict"]["size"]
    if name == "midas":
        return MidasPredictor("midas", cfg["paths"]["midas_weights"], device, size)
    if name == "comicsdepth":
        if comicsdepth_weights is None:
            from .config import run_dir
            comicsdepth_weights = run_dir(cfg, "depth") / "model.pt"
        return MidasPredictor("comicsdepth", comicsdepth_weights, device, size)
    if name == "depth_anything_v2":
        return DepthAnythingPredictor(cfg["paths"]["depth_anything_model"], device)
    raise ValueError(f"unknown model {name!r}; choose from {MODEL_NAMES}")


def depth_to_png(depth: np.ndarray) -> Image.Image:
    """Per-image min-max normalized 8-bit visualization (bright = closer)."""
    lo, hi = float(np.min(depth)), float(np.max(depth))
    scaled = (depth - lo) / (hi - lo) if hi > lo else np.zeros_like(depth)
    return Image.fromarray((scaled * 255).round().astype(np.uint8))
