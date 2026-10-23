import random
import unittest

import numpy as np
from PIL import Image

from comics_depth import config as config_lib
from comics_depth.transforms import (lower_bound_size, random_crop_box, resize_float,
                                     upper_bound_size)


class ConfigTest(unittest.TestCase):
    def test_default_paths_expand(self):
        cfg = config_lib.load_config()
        self.assertEqual(cfg["paths"]["root"], "/data/151-3/comics/ComicsDepth")
        self.assertNotIn("{", "".join(cfg["paths"].values()))

    def test_overrides_and_reexpansion(self):
        cfg = config_lib.load_config(overrides=['paths.storage="/x"', "depth.lr=2e-6",
                                                'manga.exclude_prefixes=["a"]', "train.run=smoke"])
        self.assertEqual(cfg["paths"]["root"], "/x/ComicsDepth")
        self.assertEqual(cfg["depth"]["lr"], 2e-6)
        self.assertEqual(cfg["manga"]["exclude_prefixes"], ["a"])
        self.assertEqual(cfg["train"]["run"], "smoke")
        self.assertEqual(str(config_lib.run_dir(cfg, "depth")), "/x/ComicsDepth/runs/smoke/depth")

    def test_unknown_key_rejected(self):
        with self.assertRaises(KeyError):
            config_lib.load_config(overrides=["depth.learning_rate=1"])
        with self.assertRaises(ValueError):
            config_lib.load_config(overrides=["depth.lr"])

    def test_section_hash_changes(self):
        a = config_lib.load_config()
        b = config_lib.load_config(overrides=["depth.lr=2e-6"])
        self.assertEqual(config_lib.section_hash(a, "manga"), config_lib.section_hash(b, "manga"))
        self.assertNotEqual(config_lib.section_hash(a, "depth"), config_lib.section_hash(b, "depth"))


class TransformTest(unittest.TestCase):
    def test_lower_bound_keeps_aspect_and_covers_crop(self):
        self.assertEqual(lower_bound_size(1000, 500, 384), (768, 384))
        self.assertEqual(lower_bound_size(200, 300, 384), (384, 576))
        w, h = lower_bound_size(1774, 2500, 384)
        self.assertEqual(w, 384)
        self.assertGreaterEqual(h, 384)

    def test_upper_bound_multiple_of_32(self):
        self.assertEqual(upper_bound_size(640, 480, 384), (384, 288))
        w, h = upper_bound_size(1774, 2500, 384)
        self.assertEqual((w % 32, h % 32), (0, 0))
        self.assertLessEqual(max(w, h), 384)

    def test_random_crop_within_bounds(self):
        rng = random.Random(0)
        for _ in range(100):
            x1, y1, x2, y2 = random_crop_box(500, 400, 384, rng)
            self.assertTrue(0 <= x1 and x2 <= 500 and 0 <= y1 and y2 <= 400)
            self.assertEqual((x2 - x1, y2 - y1), (384, 384))

    def test_resize_float_preserves_values(self):
        depth = np.full((10, 20), 1234.5, dtype=np.float32)
        out = resize_float(depth, (40, 20))
        self.assertEqual(out.shape, (20, 40))
        self.assertTrue(np.allclose(out, 1234.5))


if __name__ == "__main__":
    unittest.main()
