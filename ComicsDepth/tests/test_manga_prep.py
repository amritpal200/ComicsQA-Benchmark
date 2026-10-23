import random
import tarfile
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from comics_depth import config as config_lib
from comics_depth import manga_prep
from comics_depth.io_utils import read_jsonl
from comics_depth.webdataset import decode_image, list_pages, load_split_tars, tar_source

from .fixtures import encode, make_dataset, make_tar, page_image


class WebdatasetTest(unittest.TestCase):
    def test_pairs_and_skips_unpaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x-000000.tar"
            make_tar(path, "x", pages=3, extra_members=[("orphan.png", encode(page_image(8, 8)))])
            with tarfile.open(path) as tar:
                pages, skipped = list_pages(tar)
            self.assertEqual([p.key for p in pages], ["x_000000000", "x_000000001", "x_000000002"])
            self.assertEqual(skipped, 1)

    def test_animated_rejected_and_image_by_content(self):
        frames = [page_image(8, 8, seed=s).convert("P") for s in range(2)]
        import io
        buffer = io.BytesIO()
        frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:])
        with self.assertRaises(ValueError):
            decode_image(buffer.getvalue())
        self.assertEqual(decode_image(encode(page_image(8, 6), "WEBP")).size, (8, 6))

    def test_split_exclusion(self):
        self.assertEqual(tar_source("mangadex_v2-000012.tar"), "mangadex_v2")
        with tempfile.TemporaryDirectory() as tmp:
            make_dataset(Path(tmp))
            names = load_split_tars(Path(tmp) / "splits.json", "train", ["popmanga"])
            self.assertTrue(names)
            self.assertFalse(any(n.startswith("popmanga") for n in names))


class GeometryTest(unittest.TestCase):
    def test_clip_box(self):
        self.assertEqual(manga_prep.clip_box([10.2, 10.7, 390.1, 290.0], 400, 300), (10, 10, 391, 290))
        self.assertEqual(manga_prep.clip_box([-5, -5, 500, 500], 400, 300), (0, 0, 400, 300))
        self.assertIsNone(manga_prep.clip_box([50, 50, 40, 60], 400, 300))
        self.assertIsNone(manga_prep.clip_box([1, 2, 3], 400, 300))
        self.assertIsNone(manga_prep.clip_box([0, 0, float("nan"), 5], 400, 300))

    def test_text_mask_is_panel_local_clipped_and_grown(self):
        panel = (100, 100, 300, 300)
        mask = manga_prep.text_mask(panel, [[250, 90, 290, 130], [10, 10, 20, 20]],
                                    margin_ratio=0.25, margin_min_px=6)
        self.assertEqual(mask.shape, (200, 200))
        ys, xs = np.nonzero(mask)
        # box [250,90,290,130] grown by max(6, 0.25*40=10) -> [240,80,300,140], clipped to panel
        self.assertEqual((xs.min(), xs.max(), ys.min(), ys.max()), (140, 199, 0, 39))
        self.assertEqual(mask.max(), 255)

    def test_textfree_crop_avoids_text(self):
        image = page_image(200, 100)
        mask = np.zeros((100, 200), dtype=np.uint8)
        mask[:, 60:140] = 255
        crop, info = manga_prep.textfree_crop(image, mask, 64, 16, random.Random(0))
        x1, y1, x2, y2 = info["box_in_resized"]
        rw, rh = info["resized_size"]
        resized_mask = np.asarray(Image.fromarray(mask).resize((rw, rh), Image.NEAREST))
        self.assertEqual(resized_mask[y1:y2, x1:x2].max(), 0)
        self.assertEqual(crop.size, (x2 - x1, y2 - y1))
        # resized to 128x64; text covers columns 38..89, so the largest free square is 38 px
        self.assertEqual((rw, rh), (128, 64))
        self.assertEqual(x2 - x1, 38)

    def test_textfree_crop_none_when_all_text(self):
        mask = np.full((50, 50), 255, dtype=np.uint8)
        self.assertIsNone(manga_prep.textfree_crop(page_image(50, 50), mask, 64, 16, random.Random(0)))


def set_args(overrides):
    return sum((["--set", o] for o in overrides), [])


class PrepareTest(unittest.TestCase):
    def run_prepare(self, tmp, workers):
        overrides = make_dataset(Path(tmp)) + [f"manga.num_workers={workers}"]
        self.assertEqual(manga_prep.main(set_args(overrides)), 0)
        cfg = config_lib.load_config(overrides=overrides)
        return overrides, config_lib.manga_dir(cfg)

    def test_end_to_end_deterministic_across_workers(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            overrides, out1 = self.run_prepare(a, 1)
            _, out2 = self.run_prepare(b, 2)
            train1, train2 = read_jsonl(out1 / "train.jsonl"), read_jsonl(out2 / "train.jsonl")
            self.assertEqual(train1, train2)
            self.assertEqual(len(train1), 6)
            self.assertEqual(len(read_jsonl(out1 / "val.jsonl")), 3)
            self.assertFalse(any(r["source"].startswith("popmanga") for r in train1))
            self.assertEqual(len({r["id"] for r in train1}), 6)
            for r in train1:
                with Image.open(out1 / "train" / "panels" / f"{r['id']}.png") as panel, \
                        Image.open(out1 / "train" / "masks" / f"{r['id']}.png") as mask:
                    x1, y1, x2, y2 = r["panel_box"]
                    self.assertEqual(panel.size, (x2 - x1, y2 - y1))
                    self.assertEqual(mask.size, panel.size)
                if r["textfree"]:
                    self.assertTrue((out1 / "train" / "textfree" / f"{r['id']}.png").exists())
            # Idempotent: a second run leaves the finished folder alone.
            before = (out1 / "train.jsonl").read_bytes()
            self.assertEqual(manga_prep.main(set_args(overrides)), 0)
            self.assertEqual(before, (out1 / "train.jsonl").read_bytes())
            self.assertTrue((out1 / "prepare.json").exists())

    def test_refuses_interrupted_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            overrides = make_dataset(Path(tmp))
            cfg = config_lib.load_config(overrides=overrides)
            partial = config_lib.manga_dir(cfg).with_name(cfg["manga"]["name"] + ".partial")
            partial.mkdir(parents=True)
            self.assertEqual(manga_prep.main(set_args(overrides)), 1)


if __name__ == "__main__":
    unittest.main()
