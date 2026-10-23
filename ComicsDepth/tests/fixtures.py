"""Synthetic webdataset TARs, splits and COCO-like folders for CPU tests."""

import io
import json
import tarfile
from pathlib import Path

import numpy as np
from PIL import Image


def page_image(width=400, height=600, seed=0):
    rng = np.random.default_rng(seed)
    array = rng.integers(0, 255, (height, width, 3), dtype=np.uint8)
    return Image.fromarray(array)


def page_doc(width=400, height=600, with_text=True):
    panels = [[10.2, 10.7, 390.0, 290.0], [10.0, 300.0, 200.0, 590.0], [210.0, 300.0, 390.0, 590.0],
              [5.0, 5.0, 40.0, 40.0]]  # last one is too small
    texts = [[300.0, 20.0, 380.0, 80.0]] if with_text else []
    return {
        "magi3": {"panels": panels, "texts": texts, "tails": [],
                  "ocr": {"bboxes": texts, "ocr_texts": ["hi"] * len(texts)}},
        "tasks": {"metadata": {"image_size": [width, height]}},
    }


def encode(image, fmt="PNG"):
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def add_member(tar, name, data):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def make_tar(path, prefix, pages=6, seed=0, extra_members=()):
    with tarfile.open(path, "w") as tar:
        for i in range(pages):
            key = f"{prefix}_{i:09d}"
            add_member(tar, f"{key}.png", encode(page_image(seed=seed * 100 + i)))
            add_member(tar, f"{key}.json", json.dumps(page_doc(with_text=i % 2 == 0)).encode())
        for name, data in extra_members:
            add_member(tar, name, data)


def make_dataset(root: Path):
    """Returns --set overrides pointing the config at a tiny synthetic world under root."""
    dataset = root / "dataset"
    dataset.mkdir(parents=True)
    splits = {"train": [], "val": [], "test": []}
    for source in ("mangadex", "MangaPark", "popmanga_extended"):
        for shard in range(2):
            name = f"{source}-{shard:06d}.tar"
            make_tar(dataset / name, f"{source}{shard}", seed=len(splits["train"]) + shard)
            splits["train" if shard == 0 else "val"].append(name)
    (root / "splits.json").write_text(json.dumps(splits))
    coco = root / "coco"
    coco.mkdir()
    for i in range(4):
        page_image(96, 72, seed=1000 + i).save(coco / f"{i:012d}.jpg")
    return [
        f'paths.storage="{root}"',
        f'paths.root="{root}/out"',
        f'paths.dataset="{dataset}"',
        f'paths.splits="{root}/splits.json"',
        f'paths.coco_images="{coco}"',
        f'paths.midas_weights="{root}/midas.pt"',
        "manga.train_panels=6", "manga.val_panels=3", "manga.pages_per_tar=4",
        "manga.val_pages_per_tar=3", "manga.min_panel_side=100", "manga.num_workers=1",
        "manga.textfree_size=64", "manga.textfree_min_side=16",
    ]
