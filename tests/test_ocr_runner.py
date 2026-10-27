"""OCR runner: box selection, cropping, resume and read-only inputs. Fake recognizer; no model."""

import importlib.util
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1] / "src/comics_qa/annotations"
sys.path.insert(0, str(ROOT / "magi3"))
spec = importlib.util.spec_from_file_location("run_ocr", ROOT / "ocr/run_ocr.py")
run_ocr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_ocr)


class FakeRecognizer:
    def __init__(self, *a, **k):
        self.calls = []
        self.metadata = {"model": "fake"}

    def recognise(self, image):
        self.calls.append(image.size)
        return f"TEXT{len(self.calls)}", 3, False


class OcrTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.images, self.human, self.magi3, self.out = r / "images", r / "human", r / "magi3", r / "out"
        for rel, gt in (("S/c/p0.jpg", True), ("S/c/p1.jpg", False)):
            (self.images / rel).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (100, 80), "white").save(self.images / rel)
            sha = run_ocr.sha256_file(self.images / rel)
            if gt:
                path = run_ocr.output_path(self.human, Path(rel))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"page": {"image_sha256": sha}, "human": {"texts": [
                    {"index": 0, "box": [10, 10, 30, 20]}, {"index": 1, "box": [95, 70, 120, 90]}]}}))
            path = run_ocr.output_path(self.magi3, Path(rel))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"page": {"image_sha256": sha}, "magi3": {"texts": [[50, 50, 60, 60]]}}))

    def tearDown(self):
        self.tmp.cleanup()

    def argv(self, *extra):
        return ["--images", str(self.images), "--human", str(self.human), "--magi3", str(self.magi3),
                "--out", str(self.out), "--model", str(self.out.parent / "model"), *extra]

    def test_normalize(self):
        self.assertEqual(run_ocr.normalize("ＰＯＷ"), "POW")
        self.assertEqual(run_ocr.normalize("MY GRANDFATHER, STEENIE, FOR-\nTIFIED HIMSELF"),
                         "MY GRANDFATHER, STEENIE, FORTIFIED HIMSELF")
        self.assertEqual(run_ocr.normalize("SO I\nGUESS\nWE'RE"), "SO I GUESS WE'RE")

    def test_crop_box_margin_and_clip(self):
        self.assertEqual(run_ocr.crop_box([10.2, 10.7, 30.1, 20.0], 4, 100, 80), [6, 6, 35, 24])
        self.assertEqual(run_ocr.crop_box([95, 70, 120, 90], 4, 100, 80), [91, 66, 100, 80])

    def test_human_boxes_preferred_magi3_on_pages_without_ground_truth(self):
        before = {p: p.read_bytes() for p in Path(self.tmp.name).rglob("*") if p.is_file()}
        with patch.object(run_ocr, "Recognizer", FakeRecognizer):
            self.assertEqual(run_ocr.main(self.argv()), 0)
        gt = json.loads(run_ocr.output_path(self.out, Path("S/c/p0.jpg")).read_text())["ocr"]
        model = json.loads(run_ocr.output_path(self.out, Path("S/c/p1.jpg")).read_text())["ocr"]
        self.assertEqual(gt["boxes_source"], "human")
        self.assertEqual([t["index"] for t in gt["texts"]], [0, 1])
        self.assertEqual(gt["texts"][0]["status"], "ok")
        self.assertEqual(model["boxes_source"], "model:magi3")
        self.assertEqual(gt["_meta"]["status"], "complete")
        self.assertEqual(before, {p: p.read_bytes() for p in before})       # inputs untouched

    def test_resume_skips_complete_pages(self):
        with patch.object(run_ocr, "Recognizer", FakeRecognizer):
            run_ocr.main(self.argv())
            fake = FakeRecognizer()
            counts = Counter()
            args = run_ocr.parse_args(self.argv())
            run_ocr.process_page(Path("S/c/p0.jpg"), fake, args, counts)
            self.assertEqual(counts["skipped_existing"], 1)
            self.assertEqual(fake.calls, [])
            args = run_ocr.parse_args(self.argv("--margin", "8"))         # settings change -> redo
            run_ocr.process_page(Path("S/c/p0.jpg"), fake, args, counts)
            self.assertEqual(len(fake.calls), 2)

    def test_out_inside_inputs_rejected(self):
        with self.assertRaises(SystemExit):
            run_ocr.parse_args(["--images", str(self.images), "--human", str(self.human), "--magi3",
                                str(self.magi3), "--out", str(self.human / "x"), "--model", "m"])


if __name__ == "__main__":
    unittest.main()
