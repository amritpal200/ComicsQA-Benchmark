"""Unaligned natural/manga training datasets (upstream ImageDataset_* classes).

As upstream: an epoch has max(len(natural), len(manga)) items; item i uses natural image
i % N and a random manga crop; images are resized so both sides >= crop (aspect kept) and
randomly cropped to crop x crop. Randomness uses Python's `random`, which the DataLoader seeds
per worker from its generator, so a fixed seed and worker count give reproducible epochs.
"""

import json
import random
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset

from .io_utils import read_jsonl
from .transforms import (image_to_tensor, lower_bound_size, mask_to_tensor, random_crop_box,
                         resize_float, resize_image, resize_mask)


def load_coco_items(coco_dir: Path, with_depth: bool):
    index = coco_dir / "index.jsonl"
    if not index.exists():
        raise FileNotFoundError(f"{index} missing; run prepare-coco first")
    items = []
    for record in read_jsonl(index):
        item = {"image": record["image"]}
        if with_depth:
            item["depth"] = str(coco_dir / "depth" / f"{record['stem']}.npy")
        items.append(item)
    return items


def load_manga_items(manga_dir: Path, split: str, kind: str):
    """kind='textfree': text-free crops; kind='panels': panels with their text masks."""
    manifest = manga_dir / f"{split}.jsonl"
    if not manifest.exists():
        raise FileNotFoundError(f"{manifest} missing; run prepare-manga first")
    items = []
    for record in read_jsonl(manifest):
        if kind == "textfree":
            if record["textfree"]:
                items.append({"image": str(manga_dir / split / "textfree" / f"{record['id']}.png")})
        elif kind == "panels":
            items.append({"image": str(manga_dir / split / "panels" / f"{record['id']}.png"),
                          "mask": str(manga_dir / split / "masks" / f"{record['id']}.png")})
        else:
            raise ValueError(kind)
    if not items:
        raise ValueError(f"no {kind} items in {manifest}")
    return items


def _open_rgb(path):
    with Image.open(path) as handle:
        return handle.convert("RGB")


def _open_l(path):
    with Image.open(path) as handle:
        return handle.convert("L")


def load_crop(image_path, crop, rng, mask_path=None, depth_path=None):
    """Lower-bound resize to >= crop, then one random crop applied to all given layers."""
    image = _open_rgb(image_path)
    size = lower_bound_size(*image.size, crop)
    image = resize_image(image, size)
    box = random_crop_box(*size, crop, rng)
    out = {"image": image_to_tensor(image.crop(box))}
    if mask_path is not None:
        mask = resize_mask(_open_l(mask_path), size)
        out["mask"] = mask_to_tensor(mask.crop(box))
    if depth_path is not None:
        depth = resize_float(np.load(depth_path).astype(np.float32), size)
        x1, y1, x2, y2 = box
        out["depth"] = torch.from_numpy(depth[y1:y2, x1:x2].copy())
    return out


class NaturalMangaDataset(Dataset):
    def __init__(self, natural_items, manga_items, crop=384):
        self.natural = natural_items
        self.manga = manga_items
        self.crop = crop

    def __len__(self):
        return max(len(self.natural), len(self.manga))

    def __getitem__(self, index):
        rng = random
        natural = self.natural[index % len(self.natural)]
        manga = self.manga[rng.randrange(len(self.manga))]
        nat = load_crop(natural["image"], self.crop, rng, depth_path=natural.get("depth"))
        man = load_crop(manga["image"], self.crop, rng, mask_path=manga.get("mask"))
        item = {"natural": nat["image"], "manga": man["image"]}
        if "depth" in nat:
            item["natural_depth"] = nat["depth"]
        if "mask" in man:
            item["manga_mask"] = man["mask"]
        return item


def manifest_identity(path: Path):
    """Small identity record for a prepared input (used to refuse resuming on changed data)."""
    path = Path(path)
    prepare = path / "prepare.json"
    if not prepare.exists():
        return {"path": str(path), "prepare_json": None}
    with open(prepare) as handle:
        info = json.load(handle)
    return {"path": str(path), "config": info.get("config"), "time": info.get("meta", {}).get("time")}
