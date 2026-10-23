"""Resizing/cropping identical in effect to MiDaS' Resize (keep aspect ratio), without OpenCV."""

import math
import random

import numpy as np
import torch
from PIL import Image

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def _constrain(x, multiple, min_val=0, max_val=None):
    y = int(round(x / multiple) * multiple)
    if max_val is not None and y > max_val:
        y = int(math.floor(x / multiple) * multiple)
    if y < min_val:
        y = int(math.ceil(x / multiple) * multiple)
    return y


def lower_bound_size(width, height, size, multiple=1):
    """Smallest aspect-preserving size with both sides >= size (MiDaS 'lower_bound')."""
    scale = max(size / width, size / height)
    return (_constrain(scale * width, multiple, min_val=size),
            _constrain(scale * height, multiple, min_val=size))


def upper_bound_size(width, height, size, multiple=32):
    """Largest aspect-preserving size with both sides <= size (MiDaS 'upper_bound')."""
    scale = min(size / width, size / height)
    return (_constrain(scale * width, multiple, min_val=multiple, max_val=size),
            _constrain(scale * height, multiple, min_val=multiple, max_val=size))


def resize_image(image: Image.Image, size_wh):
    return image if image.size == tuple(size_wh) else image.resize(size_wh, Image.BICUBIC)


def resize_mask(mask: Image.Image, size_wh):
    return mask if mask.size == tuple(size_wh) else mask.resize(size_wh, Image.NEAREST)


def resize_float(array: np.ndarray, size_wh, resample=Image.BILINEAR):
    image = Image.fromarray(np.ascontiguousarray(array, dtype=np.float32))
    return np.asarray(image.resize(size_wh, resample), dtype=np.float32)


def random_crop_box(width, height, crop, rng: random.Random):
    x = rng.randint(0, width - crop)
    y = rng.randint(0, height - crop)
    return x, y, x + crop, y + crop


def image_to_tensor(image: Image.Image) -> torch.Tensor:
    """RGB PIL -> float32 CHW in [0, 1]."""
    array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(array.transpose(2, 0, 1).copy())


def mask_to_tensor(mask: Image.Image) -> torch.Tensor:
    """L PIL (0/255) -> float32 HW in [0, 1]."""
    return torch.from_numpy(np.asarray(mask.convert("L"), dtype=np.float32) / 255.0)


def imagenet_normalize(batch: torch.Tensor) -> torch.Tensor:
    mean = batch.new_tensor(IMAGENET_MEAN).view(1, 3, 1, 1)
    std = batch.new_tensor(IMAGENET_STD).view(1, 3, 1, 1)
    return (batch - mean) / std
