"""MAGI v3 runner: input safety, output layout, resume, sharding and batch recovery.
No model, GPU or torch needed (Pillow only)."""

import importlib.util
import json
import tempfile
import types
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from PIL import Image

RUNNER = Path(__file__).resolve().parents[1] / "src/comics_qa/annotations/magi3/run_magi3.py"
spec = importlib.util.spec_from_file_location("run_magi3", RUNNER)
run_magi3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_magi3)


def make_tree(root):
    for rel in ["B/ch1/p001.jpg", "A/ch2/p000.png", "A/ch1/p000.jpg", "A/ch1/p001.jpg"]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (40, 60), "white").save(path)
    (root / "A/.hidden").mkdir()
    Image.new("RGB", (4, 4)).save(root / "A/.hidden/x.jpg")
    (root / "A/ch1/.manifest.json").write_text("{}")
    (root / "A/ch1/link.jpg").symlink_to(root / "A/ch1/p000.jpg")


def prediction(status="complete", truncated=False):
    return {"panels": [[0, 0, 10, 10]], "reading_order": {"status": status},
            "generation": {"ocr": {"possibly_truncated": truncated}},
            "_meta": {"status": status, "image_size": [40, 60]}}


class FakeEngine:
    def __init__(self, fail_above=None, status="complete"):
        self.calls = []
        self.fail_above = fail_above
        self.status = status
        self.torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: False))
        self.order = types.SimpleNamespace(close=lambda: None)

    def predict(self, images):
        self.calls.append(len(images))
        if self.fail_above and len(images) > self.fail_above:
            raise RuntimeError("CUDA out of memory")
        return [prediction(self.status) for _ in images]


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.images = self.root / "images"
        make_tree(self.images)
        self.out = self.root / "out"
        self.model = self.root / "model"
        self.model.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, *extra):
        return run_magi3.parse_args(["--images", str(self.images), "--out", str(self.out),
                                     "--model", str(self.model), *extra])

    def test_listing_sorted_and_skips_hidden_and_symlinks(self):
        found = [p.as_posix() for p in run_magi3.list_images(self.images)]
        self.assertEqual(found, ["A/ch1/p000.jpg", "A/ch1/p001.jpg", "A/ch2/p000.png", "B/ch1/p001.jpg"])

    def test_output_mirrors_tree_and_keeps_extension(self):
        path = run_magi3.output_path(self.out, Path("A/ch1/p000.jpg"))
        self.assertEqual(path, self.out / "A/ch1/p000.jpg.json")

    def test_output_inside_images_rejected(self):
        with self.assertRaises(SystemExit):
            run_magi3.parse_args(["--images", str(self.images), "--out", str(self.images / "x"),
                                  "--model", str(self.model)])

    def test_batch_writes_and_never_touches_images(self):
        before = {p: p.read_bytes() for p in self.images.rglob("*") if p.is_file()}
        args, counts = self.args(), Counter()
        pages = run_magi3.list_images(self.images)
        run_magi3.process_batch(pages, FakeEngine(), args, counts)
        self.assertEqual(counts["written"], 4)
        data = json.loads((self.out / "A/ch1/p000.jpg.json").read_text())
        self.assertEqual(data["schema"], run_magi3.SCHEMA)
        self.assertEqual(data["page"]["relative_path"], "A/ch1/p000.jpg")
        self.assertEqual(len(data["page"]["image_sha256"]), 64)
        self.assertEqual(data["magi3"]["_meta"]["status"], "complete")
        after = {p: p.read_bytes() for p in self.images.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(any(p.name.endswith(".tmp") for p in self.out.rglob("*")))

    def test_partial_predictions_not_written(self):
        counts = Counter()
        run_magi3.process_batch(run_magi3.list_images(self.images)[:2], FakeEngine(status="partial"),
                                self.args(), counts)
        self.assertEqual(counts["partial"], 2)
        self.assertFalse(self.out.exists() and any(self.out.rglob("*.json")))

    def test_failed_batch_is_split_until_it_fits(self):
        engine, counts = FakeEngine(fail_above=1), Counter()
        run_magi3.process_batch(run_magi3.list_images(self.images), engine, self.args(), counts)
        self.assertEqual(counts["written"], 4)
        self.assertEqual(engine.calls, [4, 2, 1, 1, 2, 1, 1])

    def test_fatal_cuda_error_stops(self):
        class Fatal(FakeEngine):
            def predict(self, images):
                raise RuntimeError("CUDA error: no kernel image is available for execution")
        with self.assertRaises(RuntimeError):
            run_magi3.process_batch(run_magi3.list_images(self.images), Fatal(), self.args(), Counter())

    def test_resume_and_shards(self):
        run_magi3.process_batch([Path("A/ch1/p000.jpg")], FakeEngine(), self.args(), Counter())
        (self.out / "A/ch1/p001.jpg.json").write_text('{"magi3": {"_meta": {"status": "partial"}}}')
        seen = {}

        def fake_engine(args, hashes):
            engine = FakeEngine()
            seen[args.shard] = engine
            return engine

        with patch.object(run_magi3, "check_model", return_value={}), \
             patch.object(run_magi3, "Magi", side_effect=fake_engine):
            for shard in ("0/2", "1/2"):
                self.assertEqual(run_magi3.main(["--images", str(self.images), "--out", str(self.out),
                                                 "--model", str(self.model), "--shard", shard]), 0)
        # Shards split the full sorted list: shard 0 = pages 0, 2 (page 0 already complete),
        # shard 1 = pages 1, 3 (page 1 was partial, so it is redone). Shard 0 having written
        # first must not change shard 1's pages.
        self.assertEqual(sum(seen["0/2"].calls), 1)
        self.assertEqual(sum(seen["1/2"].calls), 2)
        for rel in ["A/ch1/p000.jpg", "A/ch1/p001.jpg", "A/ch2/p000.png", "B/ch1/p001.jpg"]:
            self.assertEqual(run_magi3.existing_status(run_magi3.output_path(self.out, Path(rel))), "complete")
        reports = [json.loads(l) for l in (self.out / "runs.jsonl").read_text().splitlines()]
        self.assertEqual([r["status"] for r in reports], ["complete", "complete"])

    def test_check_only_loads_nothing(self):
        with patch.object(run_magi3, "check_model", return_value={}), \
             patch.object(run_magi3, "Magi", side_effect=AssertionError("must not load")):
            self.assertEqual(run_magi3.main(["--images", str(self.images), "--out", str(self.out),
                                             "--model", str(self.model), "--check-only"]), 0)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
