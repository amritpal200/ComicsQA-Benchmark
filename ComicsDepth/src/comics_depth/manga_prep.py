"""Stage: prepare manga panels, text masks and text-free crops from the webdataset TARs.

Replaces the paper's DCM frame cropping + eBDtheque U-Net text detector with MAGI-3
annotations already stored in each page JSON:
  - panels:      magi3.panels                       ([x1, y1, x2, y2] pixels in the stored page)
  - text mask:   magi3.texts + magi3.ocr.bboxes (+ magi3.tails), grown by a margin to cover balloons
  - text-free:   the largest square crop with no masked pixel (upstream: random search, then
                 hand filtering into dcm_cropped_noballoons_human)

Output (never overwritten): {root}/data/<manga.name>/{train,val}/{panels,masks,textfree}/<id>.png,
{split}.jsonl manifests and prepare.json. Written to <name>.partial and renamed at the end.
"""

import argparse
import hashlib
import io
import math
import multiprocessing as mp
import random
import sys
import tarfile
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from . import config as config_lib
from .io_utils import atomic_write_bytes, atomic_write_json, run_metadata, write_jsonl
from .transforms import lower_bound_size
from .webdataset import decode_image, list_pages, load_split_tars, read_bytes, read_json, tar_source


def panel_id(tar_name, key, panel_index):
    return hashlib.sha1(f"{tar_name}|{key}|{panel_index}".encode()).hexdigest()[:16]


def clip_box(box, width, height):
    """Round outward to integer pixels and clip; None if empty or malformed."""
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        return None
    x1, y1 = max(0, math.floor(x1)), max(0, math.floor(y1))
    x2, y2 = min(width, math.ceil(x2)), min(height, math.ceil(y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def text_boxes(magi3, include_tails=True):
    boxes = list(magi3.get("texts") or [])
    ocr = magi3.get("ocr")
    if isinstance(ocr, dict):
        boxes += list(ocr.get("bboxes") or [])
    if include_tails:
        boxes += list(magi3.get("tails") or [])
    return boxes


def text_mask(panel_box, boxes, margin_ratio, margin_min_px):
    """uint8 mask (panel-local, 0/255) of text boxes grown by max(margin_min, ratio * short side)."""
    px1, py1, px2, py2 = panel_box
    mask = np.zeros((py2 - py1, px2 - px1), dtype=np.uint8)
    for box in boxes:
        clipped = clip_box(box, 10**9, 10**9)
        if clipped is None:
            continue
        x1, y1, x2, y2 = clipped
        margin = max(margin_min_px, margin_ratio * min(x2 - x1, y2 - y1))
        x1, y1 = math.floor(x1 - margin), math.floor(y1 - margin)
        x2, y2 = math.ceil(x2 + margin), math.ceil(y2 + margin)
        x1, y1 = max(x1, px1) - px1, max(y1, py1) - py1
        x2, y2 = min(x2, px2) - px1, min(y2, py2) - py1
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
    return mask


def _has_free_window(sat, n):
    """Return (ys, xs) top-left corners of n x n windows with zero masked pixels."""
    sums = sat[n:, n:] - sat[:-n, n:] - sat[n:, :-n] + sat[:-n, :-n]
    return np.nonzero(sums == 0)


def textfree_crop(image: Image.Image, mask: np.ndarray, size, min_side, rng: random.Random):
    """Resize so both sides >= size, then pick (uniformly among positions) the largest square
    n x n (min_side <= n <= size) containing no masked pixel. Returns (crop, info) or None."""
    width, height = image.size
    new_w, new_h = lower_bound_size(width, height, size)
    resized = image.resize((new_w, new_h), Image.BICUBIC)
    resized_mask = np.asarray(Image.fromarray(mask).resize((new_w, new_h), Image.NEAREST)) > 0
    sat = np.zeros((new_h + 1, new_w + 1), dtype=np.int64)
    sat[1:, 1:] = resized_mask.cumsum(0).cumsum(1)
    lo, hi, best = min_side, min(size, new_w, new_h), None
    while lo <= hi:
        mid = (lo + hi) // 2
        ys, xs = _has_free_window(sat, mid)
        if len(ys):
            best, lo = (mid, ys, xs), mid + 1
        else:
            hi = mid - 1
    if best is None:
        return None
    n, ys, xs = best
    pick = rng.randrange(len(ys))
    x, y = int(xs[pick]), int(ys[pick])
    crop = resized.crop((x, y, x + n, y + n))
    info = {"resized_size": [new_w, new_h], "box_in_resized": [x, y, x + n, y + n],
            "scale": new_w / width}
    return crop, info


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=3)
    return buffer.getvalue()


def process_tar(job):
    """Worker: sample pages/panels from one TAR. Returns encoded files; writes nothing."""
    tar_path, split, opts, seed = job
    tar_name = Path(tar_path).name
    rng = random.Random(f"{seed}:{split}:{tar_name}")
    stats, records, files = Counter(), [], {}
    try:
        tar = tarfile.open(tar_path, "r:")
    except (OSError, tarfile.TarError) as exc:
        stats["tar_error"] += 1
        return {"tar": tar_name, "records": [], "files": {}, "stats": dict(stats), "error": str(exc)}
    with tar:
        pages, unpaired = list_pages(tar)
        stats["unpaired_keys"] += unpaired
        chosen = sorted(rng.sample(range(len(pages)), min(opts["pages_per_tar"], len(pages))))
        for page_index in chosen:
            ref = pages[page_index]
            try:
                doc = read_json(tar, ref.json_member)
            except (ValueError, OSError):
                stats["bad_json"] += 1
                continue
            magi3 = doc.get("magi3") if isinstance(doc, dict) else None
            if not isinstance(magi3, dict) or not magi3.get("panels"):
                stats["no_magi3_panels"] += 1
                continue
            try:
                image = decode_image(read_bytes(tar, ref.image_member))
            except (ValueError, OSError, Image.DecompressionBombError):
                stats["bad_image"] += 1
                continue
            width, height = image.size
            stated = (doc.get("tasks") or {}).get("metadata", {}).get("image_size")
            if stated and list(stated) != [width, height]:
                stats["size_mismatch"] += 1
                continue
            candidates = []
            for index, box in enumerate(magi3["panels"]):
                clipped = clip_box(box, width, height)
                if clipped is None:
                    stats["invalid_panel"] += 1
                elif min(clipped[2] - clipped[0], clipped[3] - clipped[1]) < opts["min_panel_side"]:
                    stats["small_panel"] += 1
                else:
                    candidates.append((index, clipped))
            if not candidates:
                continue
            picked = sorted(rng.sample(candidates, min(opts["panels_per_page"], len(candidates))))
            boxes = text_boxes(magi3, opts["include_tails"])
            for index, box in picked:
                pid = panel_id(tar_name, ref.key, index)
                crop = image.crop(box)
                mask = text_mask(box, boxes, opts["text_margin_ratio"], opts["text_margin_min_px"])
                record = {
                    "id": pid, "split": split, "tar": tar_name, "source": tar_source(tar_name),
                    "key": ref.key, "image_member": ref.image_member, "panel_index": index,
                    "panel_box": list(box), "page_size": [width, height],
                    "text_fraction": round(float((mask > 0).mean()), 5),
                    "textfree": None,
                }
                files[f"{split}/panels/{pid}.png"] = png_bytes(crop)
                files[f"{split}/masks/{pid}.png"] = png_bytes(Image.fromarray(mask))
                if opts["textfree"]:
                    found = textfree_crop(crop, mask, opts["textfree_size"],
                                          opts["textfree_min_side"], rng)
                    if found is None:
                        stats["no_textfree_crop"] += 1
                    else:
                        free, info = found
                        files[f"{split}/textfree/{pid}.png"] = png_bytes(free)
                        record["textfree"] = info
                records.append(record)
                stats["panels"] += 1
    return {"tar": tar_name, "records": records, "files": files, "stats": dict(stats)}


def interleave_by_source(tar_names, rng: random.Random):
    """Shuffle TARs within each source, then round-robin across sources for diversity."""
    groups = defaultdict(list)
    for name in tar_names:
        groups[tar_source(name)].append(name)
    for source in sorted(groups):
        rng.shuffle(groups[source])
    ordered, queues = [], [groups[s] for s in sorted(groups)]
    while any(queues):
        for queue in queues:
            if queue:
                ordered.append(queue.pop(0))
    return ordered


def split_options(cfg, split):
    m = cfg["manga"]
    train = split == "train"
    return {
        "pages_per_tar": m["pages_per_tar"] if train else m["val_pages_per_tar"],
        "panels_per_page": m["panels_per_page"] if train else m["val_panels_per_page"],
        "min_panel_side": m["min_panel_side"],
        "text_margin_ratio": m["text_margin_ratio"],
        "text_margin_min_px": m["text_margin_min_px"],
        "include_tails": m["include_tails"],
        "textfree": train,
        "textfree_size": m["textfree_size"],
        "textfree_min_side": m["textfree_min_side"],
    }


def prepare_split(cfg, split, target, out_dir: Path, num_workers, log=print):
    m = cfg["manga"]
    tars = load_split_tars(cfg["paths"]["splits"], split, m["exclude_prefixes"])
    ordered = interleave_by_source(tars, random.Random(f"{m['seed']}:{split}:order"))
    dataset = Path(cfg["paths"]["dataset"])
    opts = split_options(cfg, split)
    jobs = [(str(dataset / name), split, opts, m["seed"]) for name in ordered]
    accepted, stats, used_tars = [], Counter(), []
    start = time.time()

    def consume(result):
        stats.update(result["stats"])
        if result.get("error"):
            log(f"  ! {result['tar']}: {result['error']}")
        take = result["records"][: max(0, target - len(accepted))]
        if take:
            used_tars.append(result["tar"])
        for record in take:
            for kind in ("panels", "masks") + (("textfree",) if record["textfree"] else ()):
                rel = f"{split}/{kind}/{record['id']}.png"
                atomic_write_bytes(out_dir / rel, result["files"][rel])
            accepted.append(record)
        log(f"  [{split}] {result['tar']}: +{len(take)} -> {len(accepted)}/{target} "
            f"({time.time() - start:.0f}s)")

    if num_workers <= 1:
        for job in jobs:
            consume(process_tar(job))
            if len(accepted) >= target:
                break
    else:
        with mp.get_context("spawn").Pool(num_workers) as pool:
            for result in pool.imap(process_tar, jobs):
                consume(result)
                if len(accepted) >= target:
                    pool.terminate()
                    break
    if len(accepted) < target:
        log(f"  ! {split}: only {len(accepted)} panels available (target {target})")
    write_jsonl(out_dir / f"{split}.jsonl", accepted)
    return {
        "panels": len(accepted),
        "target": target,
        "textfree": sum(1 for r in accepted if r["textfree"]),
        "tars_used": used_tars,
        "tars_available": len(tars),
        "per_source": dict(Counter(r["source"] for r in accepted)),
        "skips": dict(stats),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(prog="prepare-manga", description=__doc__.splitlines()[0])
    config_lib.add_config_args(parser)
    parser.add_argument("--num-workers", type=int, default=None)
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    m = cfg["manga"]
    out_dir = config_lib.manga_dir(cfg)
    partial = out_dir.with_name(out_dir.name + ".partial")
    if out_dir.exists():
        print(f"Already prepared: {out_dir}. Choose a new --set manga.name=... to rebuild.")
        return 0
    if partial.exists():
        print(f"Found an interrupted preparation at {partial}.\n"
              f"Inspect it and remove it yourself before rerunning.", file=sys.stderr)
        return 1
    partial.mkdir(parents=True)
    num_workers = args.num_workers or m["num_workers"]
    summary = {"config": {"manga": m, "paths": cfg["paths"]},
               "config_hash": config_lib.section_hash(cfg, "manga"),
               "meta": run_metadata(), "splits": {}}
    for split, target in (("train", m["train_panels"]), ("val", m["val_panels"])):
        print(f"Preparing {split}: target {target} panels")
        summary["splits"][split] = prepare_split(cfg, split, target, partial, num_workers)
    atomic_write_json(partial / "prepare.json", summary)
    partial.rename(out_dir)
    for split, info in summary["splits"].items():
        print(f"{split}: {info['panels']} panels ({info['textfree']} text-free) from "
              f"{len(info['tars_used'])} TARs; per source {info['per_source']}")
    print(f"Done: {out_dir}")
    return 0
