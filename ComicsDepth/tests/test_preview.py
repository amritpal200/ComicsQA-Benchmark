import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from comics_depth import preview


class PreviewTest(unittest.TestCase):
    def test_sampling_is_reproducible_without_replacement(self):
        items = list(range(30))
        selected = preview.sample_items(items, 10, 42)
        self.assertEqual(selected, preview.sample_items(items, 10, 42))
        self.assertEqual(len(set(selected)), 10)
        self.assertNotEqual(selected, preview.sample_items(items, 10, 43))
        for count in (0, -1, 31):
            with self.assertRaises(ValueError):
                preview.sample_items(items, count, 42)

    def test_gallery_and_raw_depth_with_mock_predictor(self):
        class Predictor:
            meta = {"model": "synthetic"}

            def __call__(self, image):
                return np.tile(np.linspace(0, 1, image.width, dtype=np.float32),
                               (image.height, 1))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images, output = root / "images", root / "preview"
            images.mkdir()
            for i in range(12):
                Image.new("RGB", (32, 48), (i, i, i)).save(images / f"{i:02d}.png")
            before = {p.name: p.read_bytes() for p in images.iterdir()}
            args = ["--images", str(images), "--output", str(output), "--device", "cpu"]
            with patch.object(preview, "build_predictor", return_value=Predictor()), \
                    patch.object(preview, "run_metadata", return_value={}):
                self.assertEqual(preview.main(args), 0)
                with self.assertRaises(SystemExit):
                    preview.main(args)  # existing output is preserved
            manifest = json.loads((output / "preview.json").read_text())
            expected = random.Random(42).sample(sorted(str(p) for p in images.iterdir()), 10)
            self.assertEqual([r["image"] for r in manifest["selected"]], expected)
            self.assertEqual(len(list(output.glob("*_comparison.png"))), 10)
            self.assertTrue((output / "overview_02.png").is_file())
            self.assertEqual((output / "index.html").read_text().count("<article>"), 10)
            depth = np.load(output / "01_depth.npy")
            self.assertEqual(depth.shape, (48, 32))
            self.assertEqual(depth.dtype, np.float32)
            with Image.open(output / "01_depth.png") as im:
                self.assertEqual((im.getpixel((0, 0)), im.getpixel((31, 0))), (0, 255))
            self.assertEqual(before, {p.name: p.read_bytes() for p in images.iterdir()})
