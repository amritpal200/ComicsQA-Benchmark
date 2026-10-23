"""Stage 2: learn to paste real manga text into translated images (upstream
cyclegan_natural_comics_add_text).

generator_text(cat[real manga crop, its text mask, natural2comics(natural)]) -> manga with text.
Loss as upstream: LSGAN + 3 * L1 outside the mask (keep translated content) + 3 * L1 inside the
mask (copy real text) + 5 * identity L1 (cat[real, mask, real] -> real).
"""

import argparse

import torch

from . import config as config_lib
from .datasets import NaturalMangaDataset, load_coco_items, load_manga_items, manifest_identity
from .io_utils import sha256_file
from .networks.cyclegan import Discriminator, GeneratorResNet
from .training import (Run, adam, add_train_args, autocast, average_gradients, broadcast_module,
                       exit_after_smoke, finished, log_every, make_loader, per_rank_batch,
                       require_file, setup, steps_per_epoch, stop_requested, teardown, to_device, memory_format)

STAGE = "add_text"


def load_natural2comics(cfg, device):
    path = require_file(config_lib.run_dir(cfg, "without_text") / "final.pth",
                        "finish train-without-text first")
    state = torch.load(path, map_location=device, weights_only=False)
    model = GeneratorResNet(3, 3, cfg["without_text"]["residual_blocks"]).to(
        device, memory_format=memory_format(cfg))
    model.load_state_dict(state["natural2comics"])
    model.eval().requires_grad_(False)
    return model, path


def main(argv=None):
    parser = argparse.ArgumentParser(prog="train-add-text", description=__doc__.splitlines()[0])
    add_train_args(parser)
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    s, t = cfg[STAGE], cfg["train"]
    ctx = setup(args, cfg)
    device = ctx.device
    batch = per_rank_batch(s["batch_size"], ctx)
    natural2comics, prereq = load_natural2comics(cfg, device)
    coco_dir, manga_dir = config_lib.coco_dir(cfg), config_lib.manga_dir(cfg)
    identity = {"stage": cfg[STAGE], "crop": t["crop"], "seed": t["seed"],
                "without_text_final_sha256": sha256_file(prereq),
                "coco": manifest_identity(coco_dir), "manga": manifest_identity(manga_dir)}
    run = Run(cfg, STAGE, identity, s["keep_every"], ctx)
    if finished(run):
        teardown(ctx)
        return 0

    dataset = NaturalMangaDataset(load_coco_items(coco_dir, with_depth=False),
                                  load_manga_items(manga_dir, "train", "panels"), t["crop"])
    ctx.print(f"natural {len(dataset.natural)}, manga panels {len(dataset.manga)}, "
              f"{steps_per_epoch(dataset, s['batch_size'])} steps/epoch, {batch} per GPU")

    crop = t["crop"]
    generator_text = GeneratorResNet(7, 3, s["residual_blocks"]).to(
        device, memory_format=memory_format(cfg))
    discrim = Discriminator((3, crop, crop)).to(device, memory_format=memory_format(cfg))
    optimizer_G = adam(generator_text.parameters(), s)
    optimizer_D = adam(discrim.parameters(), s)
    mse, l1 = torch.nn.MSELoss(), torch.nn.L1Loss()

    modules = {"generator_text": generator_text, "discrim": discrim,
               "optimizer_G": optimizer_G, "optimizer_D": optimizer_D}
    epochs_done, step = 0, 0
    state = run.load_latest(device)
    if state:
        for name, module in modules.items():
            module.load_state_dict(state[name])
        epochs_done, step = state["epochs_done"], state["step"]
    broadcast_module(generator_text, ctx)
    broadcast_module(discrim, ctx)

    def snapshot():
        return {"epochs_done": epochs_done, "step": step, "stage": STAGE,
                **{name: m.state_dict() for name, m in modules.items()}}

    def rows(n):
        return [real_natural[:n], translated[:n], real_manga[:n], mask[:n], fake_manga[:n]]

    valid = torch.ones((batch, *discrim.output_shape), device=device)
    fake = torch.zeros_like(valid)
    while epochs_done < s["epochs"]:
        loader = make_loader(dataset, batch, t["num_workers"], t["seed"], epochs_done, ctx)
        for data in loader:
            real_natural = to_device(data["natural"], ctx, cfg)
            real_manga = to_device(data["manga"], ctx, cfg)
            mask = to_device(data["manga_mask"].unsqueeze(1), ctx, cfg)
            with torch.no_grad(), autocast(ctx, cfg):
                translated = natural2comics(real_natural)

            generator_text.train()
            optimizer_G.zero_grad(set_to_none=True)
            with autocast(ctx, cfg):
                loss_identity = l1(generator_text(torch.cat((real_manga, mask, real_manga), 1)),
                                   real_manga)
                fake_manga = generator_text(torch.cat((real_manga, mask, translated), 1))
                loss_gan = mse(discrim(fake_manga), valid)
                loss_notext = l1(translated * (1 - mask), fake_manga * (1 - mask))
                loss_text = l1(real_manga * mask, fake_manga * mask)
                loss_G = (loss_gan + s["lambda_notext"] * loss_notext
                          + s["lambda_text"] * loss_text + s["lambda_identity"] * loss_identity)
            loss_G.backward()
            average_gradients(generator_text, ctx)
            optimizer_G.step()

            discrim.train()
            optimizer_D.zero_grad(set_to_none=True)
            with autocast(ctx, cfg):
                loss_D = (mse(discrim(real_manga), valid)
                          + mse(discrim(fake_manga.detach()), fake)) / 2
            loss_D.backward()
            average_gradients(discrim, ctx)
            optimizer_D.step()

            step += 1
            if log_every(step):
                run.log_losses(epochs_done + 1, step, {
                    "G": loss_G.item(), "gan": loss_gan.item(), "notext": loss_notext.item(),
                    "text": loss_text.item(), "identity": loss_identity.item(),
                    "D": loss_D.item()})
            if stop_requested(args, step):
                run.save_samples(f"smoke_step{step:06d}", rows(t["vis_samples"]))
                exit_after_smoke(run, snapshot())
        epochs_done += 1
        run.save_samples(f"epoch_{epochs_done:03d}", rows(t["vis_samples"]))
        run.save(snapshot(), epoch_complete=True, final=epochs_done == s["epochs"])
        run.log({"epoch": epochs_done, "step": step, "event": "epoch_saved"})
    ctx.print(f"Done: {run.final_path}")
    teardown(ctx)
    return 0
