"""Read-only access to the Energon/WebDataset manga TARs (image + MAGI-3 JSON pairs)."""

import io
import json
import tarfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "gif", "image"}


def tar_source(tar_name: str) -> str:
    """'mangadex_v2-000012.tar' -> 'mangadex_v2'."""
    return Path(tar_name).name.rsplit("-", 1)[0]


def load_split_tars(splits_path, split, exclude_prefixes=()):
    with open(splits_path) as handle:
        splits = json.load(handle)
    if split not in splits:
        raise KeyError(f"split {split!r} not in {splits_path} (have {sorted(splits)})")
    names = list(splits[split])
    return [n for n in names if not any(tar_source(n).startswith(p) for p in exclude_prefixes)]


@dataclass(frozen=True)
class PageRef:
    key: str
    image_member: str
    json_member: str


def list_pages(tar: tarfile.TarFile):
    """Pair image and JSON members by WebDataset key (name up to the first dot), in TAR order.

    Returns (pages, skipped) where skipped counts keys without exactly one image and one JSON.
    """
    groups = defaultdict(lambda: {"image": [], "json": []})
    order = []
    for member in tar.getmembers():
        if not member.isfile():
            continue
        key, _, ext = member.name.partition(".")
        ext = ext.lower()
        if key not in groups:
            order.append(key)
        if ext == "json":
            groups[key]["json"].append(member.name)
        elif ext in IMAGE_EXTS:
            groups[key]["image"].append(member.name)
    pages, skipped = [], 0
    for key in order:
        group = groups[key]
        if len(group["image"]) == 1 and len(group["json"]) == 1:
            pages.append(PageRef(key, group["image"][0], group["json"][0]))
        else:
            skipped += 1
    return pages, skipped


def decode_image(data: bytes) -> Image.Image:
    """Decode by content (handles '.image' members); reject animated images."""
    image = Image.open(io.BytesIO(data))
    if getattr(image, "n_frames", 1) > 1:
        raise ValueError("animated image")
    image.load()
    return image.convert("RGB")


def read_json(tar: tarfile.TarFile, member: str):
    with tar.extractfile(member) as handle:
        return json.load(handle)


def read_bytes(tar: tarfile.TarFile, member: str) -> bytes:
    with tar.extractfile(member) as handle:
        return handle.read()
