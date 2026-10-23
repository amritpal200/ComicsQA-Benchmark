import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import torch

from comics_depth import config as config_lib
from comics_depth.networks.cyclegan import Discriminator, GeneratorResNet
from comics_depth.networks.midas_v21 import MidasNet, extract_state_dict
from comics_depth.ordering import ordering_accuracy, summarize
from comics_depth.train_depth import masked_l1
from comics_depth.training import Run


class CycleGanTest(unittest.TestCase):
    def test_generator_shape_and_range(self):
        gen = GeneratorResNet(7, 3, num_residual_blocks=1)
        out = gen(torch.rand(2, 7, 64, 64))
        self.assertEqual(out.shape, (2, 3, 64, 64))
        self.assertTrue(((out >= 0) & (out <= 1)).all())

    def test_discriminator_output_shape_matches_attribute(self):
        disc = Discriminator((3, 64, 64))
        self.assertEqual(disc(torch.rand(2, 3, 64, 64)).shape[1:], disc.output_shape)

    def test_state_dict_names_match_upstream_layout(self):
        keys = GeneratorResNet().state_dict().keys()
        self.assertIn("model.1.weight", keys)            # first 7x7 conv after ReflectionPad
        self.assertIn("model.10.block.1.weight", keys)    # first residual block


class MidasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = MidasNet().eval()

    def test_keys_match_released_checkpoint_layout(self):
        keys = set(self.model.state_dict())
        for key in ["pretrained.layer1.0.weight", "pretrained.layer1.1.running_mean",
                    "pretrained.layer1.4.0.conv1.weight", "pretrained.layer4.2.conv3.weight",
                    "scratch.layer1_rn.weight", "scratch.layer4_rn.weight",
                    "scratch.refinenet4.resConfUnit2.conv1.weight",
                    "scratch.refinenet1.resConfUnit1.conv2.bias",
                    "scratch.output_conv.0.weight", "scratch.output_conv.4.weight"]:
            self.assertIn(key, keys)
        self.assertFalse(any(k.startswith("pretrained.fc") for k in keys))

    def test_forward_shape_and_nonnegative(self):
        with torch.no_grad():
            out = self.model(torch.rand(1, 3, 64, 96))
        self.assertEqual(out.shape, (1, 64, 96))
        self.assertTrue((out >= 0).all())

    def test_extract_state_dict_formats(self):
        sd = {"a": torch.zeros(1)}
        self.assertIs(extract_state_dict(sd), sd)
        self.assertIs(extract_state_dict({"model": sd, "optimizer": {}}), sd)
        self.assertIs(extract_state_dict({"comics2depth_state_dict": sd}), sd)


class LossTest(unittest.TestCase):
    def test_masked_l1_uses_each_samples_own_mask(self):
        pred = torch.zeros(2, 4, 4)
        target = torch.ones(2, 4, 4)
        mask = torch.zeros(2, 4, 4)
        mask[0] = 1  # sample 0 fully text -> ignored
        # only sample 1 contributes: 16 errors of 1 over 32 pixels
        self.assertAlmostEqual(masked_l1(pred, target, mask).item(), 0.5)

    def test_masked_l1_rejects_broadcasting(self):
        with self.assertRaises(ValueError):
            masked_l1(torch.zeros(2, 4, 4), torch.zeros(2, 4, 4), torch.zeros(2, 1, 4, 4))


class OrderingTest(unittest.TestCase):
    def test_inter_intra_and_ties(self):
        pred = np.array([[3.0, 2.0, 1.0, 1.0]])
        points = [(1, 1, 0, 0), (2, 1, 1, 0), (2, 2, 2, 0), (3, 1, 3, 0), (1, 1, 9, 9)]
        counts = ordering_accuracy(pred, points)
        self.assertEqual(counts["out_of_bounds"], 1)
        # inter pairs: (1,2a) ok, (1,2b) ok, (1,3) ok, (2a,3) ok, (2b,3) tie -> wrong
        self.assertEqual((counts["inter_correct"], counts["inter_total"]), (4, 5))
        self.assertEqual((counts["intra_correct"], counts["intra_total"]), (1, 1))
        self.assertEqual(counts["ties"], 1)
        self.assertAlmostEqual(summarize([counts])["inter_accuracy"], 0.8)


class TextMetricTest(unittest.TestCase):
    def test_dilate_square(self):
        from comics_depth.evaluate import dilate
        mask = np.zeros((9, 9), dtype=bool)
        mask[4, 4] = True
        out = dilate(mask, 2)
        self.assertEqual(out.sum(), 25)
        self.assertTrue(out[2:7, 2:7].all())

    def test_text_contrast_detects_popping_balloon(self):
        from comics_depth.evaluate import text_contrast
        depth = np.tile(np.linspace(0, 1, 200, dtype=np.float32)[:, None], (1, 200))
        mask = np.zeros((200, 200), dtype=np.uint8)
        mask[80:120, 80:120] = 255
        flat = text_contrast(depth, mask)
        popped = depth.copy()
        popped[80:120, 80:120] = 1.0  # balloon predicted as nearest object
        self.assertLess(flat, 0.05)
        self.assertGreater(text_contrast(popped, mask), 0.4)
        self.assertIsNone(text_contrast(depth, np.zeros_like(mask)))


class RunTest(unittest.TestCase):
    def test_checkpoints_links_and_identity_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = config_lib.load_config(overrides=[f'paths.root="{tmp}"'])
            run = Run(cfg, "stage", {"a": 1}, keep_every=2)
            for epoch in (1, 2, 3, 4):
                run.save({"epochs_done": epoch, "step": epoch * 10}, epoch_complete=True,
                         final=epoch == 4)
            names = sorted(p.name for p in run.dir.glob("*.pth"))
            self.assertEqual(names, ["epoch_002.pth", "epoch_004.pth", "final.pth", "latest.pth"])
            self.assertEqual(torch.load(run.dir / "epoch_002.pth")["epochs_done"], 2)
            self.assertEqual(os.stat(run.final_path).st_ino, os.stat(run.dir / "latest.pth").st_ino)
            self.assertEqual(run.load_latest("cpu")["step"], 40)
            Run(cfg, "stage", {"a": 1}, keep_every=2)  # same identity: fine
            with self.assertRaises(SystemExit):
                Run(cfg, "stage", {"a": 2}, keep_every=2)


if __name__ == "__main__":
    unittest.main()
