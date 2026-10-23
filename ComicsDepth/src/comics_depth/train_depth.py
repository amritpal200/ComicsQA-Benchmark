"""Stage 3: fine-tune MiDaS v2.1 on translated natural images with real manga text pasted in,
ignoring the text regions in the loss (upstream depth_add_text_ignoretext, lr 1e-6).

Target: MiDaS v2.1 pseudo-depth of the original natural image (prepare-coco).
Fix vs upstream: upstream multiplied a (B, H, W) prediction by a (B, 1, H, W) mask, which
broadcasts to (B, B, H, W) and masks every sample with every other sample's text. Here each
sample uses its own mask; the loss is still the mean over all pixels, as upstream.
MiDaS stays in train mode as upstream; with several GPUs its BatchNorm becomes SyncBatchNorm so
statistics cover the full batch. Exports model.pt (weights only) when the schedule completes.
"""

import argparse

import torch

from . import config as config_lib
from .datasets import NaturalMangaDataset, load_coco_items, load_manga_items, manifest_identity
from .io_utils import atomic_write_json, run_metadata, sha256_file
from .networks.cyclegan import GeneratorResNet
from .networks.midas_v21 import MidasNet, load_midas
from .train_add_text import load_natural2comics
from .training import (Run, adam, add_train_args, autocast, average_gradients, broadcast_module,
                       exit_after_smoke, finished, log_every, make_loader, per_rank_batch,
                       require_file, setup, steps_per_epoch, stop_requested, teardown, to_device, memory_format)
from .transforms import imagenet_normalize

STAGE = "depth"


def masked_l1(pred, target, mask):
    """pred, target: (B, H, W); mask: (B, H, W) with 1 = text (ignored). Mean over all pixels."""
    if pred.shape != target.shape or pred.shape != mask.shape:
        raise ValueError(f"shape mismatch: pred {tuple(pred.shape)}, target {tuple(target.shape)}, "
                         f"mask {tuple(mask.shape)}")
    keep = 1 - mask
    return torch.abs(pred * keep - target * keep).mean()


def load_text_generator(cfg, device):
    path = require_file(config_lib.run_dir(cfg, "add_text") / "final.pth",
                        "finish train-add-text first")
    state = torch.load(path, map_location=device, weights_only=False)
    model = GeneratorResNet(7, 3, cfg["add_text"]["residual_blocks"]).to(
        device, memory_format=memory_format(cfg))
    model.load_state_dict(state["generator_text"])
    model.eval().requires_grad_(False)
    return model, path


def plain_state_dict(model):
    """State dict loadable into a plain MidasNet (SyncBatchNorm keeps BatchNorm's key names)."""
    state = model.state_dict()
    MidasNet().load_state_dict(state, strict=True)
    return state


def export(run, state_dict, cfg):
    path = run.dir / "model.pt"
    tmp = run.dir / ".model.pt.tmp"
    torch.save(state_dict, tmp)
    tmp.replace(path)
    atomic_write_json(run.dir / "model.json", {
        "architecture": "MiDaS v2.1 (MidasNet) fine-tuned with ComicsDepth on manga",
        "weights_sha256": sha256_file(path), "init": cfg["paths"]["midas_weights"],
        "input": f"upper_bound {cfg['predict']['size']}, multiple of 32, ImageNet normalization",
        "output": "relative inverse depth (larger = closer), compare within a panel only",
        "run": str(run.dir), "meta": run_metadata()})
    print(f"Exported {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="train-depth", description=__doc__.splitlines()[0])
    add_train_args(parser)
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    s, t = cfg[STAGE], cfg["train"]
    ctx = setup(args, cfg)
    device = ctx.device
    batch = per_rank_batch(s["batch_size"], ctx)
    natural2comics, prereq1 = load_natural2comics(cfg, device)
    generator_text, prereq2 = load_text_generator(cfg, device)
    midas_weights = require_file(cfg["paths"]["midas_weights"], "run scripts/download_weights.sh")
    coco_dir, manga_dir = config_lib.coco_dir(cfg), config_lib.manga_dir(cfg)
    identity = {"stage": cfg[STAGE], "crop": t["crop"], "seed": t["seed"],
                "without_text_final_sha256": sha256_file(prereq1),
                "add_text_final_sha256": sha256_file(prereq2),
                "midas_init_sha256": sha256_file(midas_weights),
                "coco": manifest_identity(coco_dir), "manga": manifest_identity(manga_dir)}
    run = Run(cfg, STAGE, identity, s["keep_every"], ctx)
    if finished(run):
        if ctx.main and not (run.dir / "model.pt").exists():
            export(run, load_midas(run.final_path).state_dict(), cfg)
        teardown(ctx)
        return 0

    dataset = NaturalMangaDataset(load_coco_items(coco_dir, with_depth=True),
                                  load_manga_items(manga_dir, "train", "panels"), t["crop"])
    ctx.print(f"natural {len(dataset.natural)}, manga panels {len(dataset.manga)}, "
              f"{steps_per_epoch(dataset, s['batch_size'])} steps/epoch, {batch} per GPU")

    depth_model = load_midas(midas_weights)
    if ctx.distributed and device.type == "cuda":
        depth_model = torch.nn.SyncBatchNorm.convert_sync_batchnorm(depth_model)
    depth_model = depth_model.to(device, memory_format=memory_format(cfg))
    optimizer = adam(depth_model.parameters(), s)
    epochs_done, step = 0, 0
    state = run.load_latest(device)
    if state:
        depth_model.load_state_dict(state["model"])
        optimizer.load_state_dict(state["optimizer"])
        epochs_done, step = state["epochs_done"], state["step"]
    broadcast_module(depth_model, ctx)

    def snapshot():
        return {"epochs_done": epochs_done, "step": step, "stage": STAGE,
                "model": depth_model.state_dict(), "optimizer": optimizer.state_dict()}

    while epochs_done < s["epochs"]:
        loader = make_loader(dataset, batch, t["num_workers"], t["seed"], epochs_done, ctx)
        depth_model.train()
        for data in loader:
            real_natural = to_device(data["natural"], ctx, cfg)
            target = to_device(data["natural_depth"], ctx, cfg)
            real_manga = to_device(data["manga"], ctx, cfg)
            mask = to_device(data["manga_mask"], ctx, cfg)
            with torch.no_grad(), autocast(ctx, cfg):
                translated = natural2comics(real_natural)
                fake_manga = generator_text(torch.cat((real_manga, mask.unsqueeze(1), translated), 1))
            fake_manga = fake_manga.float()

            optimizer.zero_grad(set_to_none=True)
            with autocast(ctx, cfg):
                pred = depth_model(imagenet_normalize(fake_manga))
            loss = masked_l1(pred.float(), target, mask)
            loss.backward()
            average_gradients(depth_model, ctx)
            optimizer.step()

            step += 1
            if log_every(step):
                run.log_losses(epochs_done + 1, step, {"loss": loss.item(),
                                                       "text_fraction": mask.mean().item()})
            if stop_requested(args, step):
                save_depth_samples(run, f"smoke_step{step:06d}", fake_manga, target, pred, mask, t)
                exit_after_smoke(run, snapshot())
        epochs_done += 1
        save_depth_samples(run, f"epoch_{epochs_done:03d}", fake_manga, target, pred, mask, t)
        run.save(snapshot(), epoch_complete=True, final=epochs_done == s["epochs"])
        run.log({"epoch": epochs_done, "step": step, "event": "epoch_saved"})
    if ctx.main:
        export(run, plain_state_dict(depth_model), cfg)
    ctx.print(f"Done: {run.final_path}")
    teardown(ctx)
    return 0


def save_depth_samples(run, name, fake_manga, target, pred, mask, t):
    n = min(t["vis_samples"], fake_manga.shape[0])

    def norm(x):
        x = x[:n].detach().float()
        lo = x.flatten(1).min(1).values.view(-1, 1, 1)
        hi = x.flatten(1).max(1).values.view(-1, 1, 1)
        return ((x - lo) / (hi - lo).clamp_min(1e-6)).unsqueeze(1)

    run.save_samples(name, [fake_manga[:n], norm(target), norm(pred), mask[:n].unsqueeze(1)])
