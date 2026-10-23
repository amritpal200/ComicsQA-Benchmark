"""End-to-end CPU smoke of every stage on a tiny synthetic world with random MiDaS weights.

Slow (builds ResNeXt-101 several times, writes a ~350 MB random checkpoint): set
CD_SLOW_TESTS=1 to run it.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from comics_depth import coco_depth, evaluate, manga_prep, predict, train_add_text, train_depth
from comics_depth import train_without_text
from comics_depth import config as config_lib
from comics_depth.networks.midas_v21 import MidasNet

from .fixtures import make_dataset
from .test_manga_prep import set_args

TINY = ["train.crop=64", "train.num_workers=0", "train.vis_samples=2",
        "without_text.epochs=2", "without_text.batch_size=2", "without_text.residual_blocks=1",
        "without_text.keep_every=1",
        "add_text.epochs=1", "add_text.batch_size=2", "add_text.residual_blocks=1",
        "depth.epochs=1", "depth.batch_size=2", "predict.size=64",
        "evaluate.panels=2", "evaluate.pair_samples=50"]


@unittest.skipUnless(os.environ.get("CD_SLOW_TESTS") == "1", "set CD_SLOW_TESTS=1")
class PipelineTest(unittest.TestCase):
    def test_all_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            overrides = make_dataset(Path(tmp)) + TINY
            args = set_args(overrides)
            cfg = config_lib.load_config(overrides=overrides)
            torch.manual_seed(0)
            torch.save(MidasNet().state_dict(), cfg["paths"]["midas_weights"])

            self.assertEqual(manga_prep.main(args), 0)
            self.assertEqual(coco_depth.main(args + ["--device", "cpu"]), 0)
            coco = config_lib.coco_dir(cfg)
            self.assertEqual(len(list((coco / "depth").glob("*.npy"))), 4)
            self.assertEqual(np.load(next((coco / "depth").glob("*.npy"))).dtype, np.float32)

            self.assertEqual(train_without_text.main(args + ["--device", "cpu"]), 0)
            stage1 = config_lib.run_dir(cfg, "without_text")
            self.assertTrue((stage1 / "final.pth").exists())
            self.assertTrue((stage1 / "epoch_001.pth").exists())
            self.assertTrue((stage1 / "samples" / "epoch_002.png").exists())
            # Re-running a finished stage is a no-op.
            self.assertEqual(train_without_text.main(args + ["--device", "cpu"]), 0)

            self.assertEqual(train_add_text.main(args + ["--device", "cpu"]), 0)
            self.assertEqual(train_depth.main(args + ["--device", "cpu"]), 0)
            stage3 = config_lib.run_dir(cfg, "depth")
            self.assertTrue((stage3 / "model.pt").exists())
            meta = json.loads((stage3 / "model.json").read_text())
            self.assertIn("larger = closer", meta["output"])

            out = Path(tmp) / "pred"
            self.assertEqual(predict.main(args + ["--manga-split", "val", "--output", str(out)]), 0)
            records = [json.loads(l) for l in (out / "predictions.jsonl").read_text().splitlines()]
            self.assertEqual(len(records), 3)
            depth = np.load(records[0]["depth"])
            self.assertEqual(depth.shape, tuple(records[0]["size"][::-1]))
            self.assertEqual(predict.main(args + ["--manga-split", "val", "--output", str(out)]), 1)

            report_dir = Path(tmp) / "eval"
            self.assertEqual(evaluate.main(args + ["--output", str(report_dir)]), 0)
            report = json.loads((report_dir / "report.json").read_text())
            self.assertEqual(set(report["models"]), {"midas", "comicsdepth"})
            self.assertTrue((report_dir / "grid_000.png").exists())


@unittest.skipUnless(os.environ.get("CD_SLOW_TESTS") == "1", "set CD_SLOW_TESTS=1")
class MultiProcessTest(unittest.TestCase):
    """The torchrun path (2 CPU ranks, gloo): per-rank batches, gradient averaging, rank-0 I/O."""

    def torchrun(self, module, args):
        import subprocess
        import sys
        torchrun = Path(sys.executable).with_name("torchrun")
        env = {**os.environ, "OMP_NUM_THREADS": "2"}
        cmd = [str(torchrun), "--standalone", "--nproc_per_node=2", "-m", "comics_depth",
               module, *args, "--device", "cpu"]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-3000:])
        return result.stdout

    def test_two_ranks_all_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            overrides = make_dataset(Path(tmp)) + TINY
            args = set_args(overrides)
            cfg = config_lib.load_config(overrides=overrides)
            torch.manual_seed(0)
            torch.save(MidasNet().state_dict(), cfg["paths"]["midas_weights"])
            self.assertEqual(manga_prep.main(args), 0)
            self.assertEqual(coco_depth.main(args + ["--device", "cpu"]), 0)
            out = self.torchrun("train-without-text", args)
            self.assertIn("data parallel on 2 GPUs", out)
            self.assertIn("1 per GPU", out)
            self.torchrun("train-add-text", args)
            self.torchrun("train-depth", args)
            stage3 = config_lib.run_dir(cfg, "depth")
            self.assertTrue((stage3 / "model.pt").exists())
            info = json.loads((stage3 / "run.json").read_text())
            self.assertEqual(info["created"]["world_size"], 2)
            # every logged step appears once (rank 0 only writes)
            steps = [json.loads(l)["step"] for l in (stage3 / "metrics.jsonl").read_text().splitlines()
                     if "event" not in l]
            self.assertEqual(len(steps), len(set(steps)))
            # batch size must divide across ranks
            bad = set_args(overrides + ["train.run=bad", "depth.batch_size=3"])
            import subprocess, sys
            result = subprocess.run([str(Path(sys.executable).with_name("torchrun")), "--standalone",
                                     "--nproc_per_node=2", "-m", "comics_depth", "train-depth",
                                     *bad, "--device", "cpu"], capture_output=True, text=True,
                                    timeout=600)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not divisible", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
