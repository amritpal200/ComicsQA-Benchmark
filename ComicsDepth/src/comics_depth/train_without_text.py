"""Stage 1: CycleGAN natural <-> text-free manga (upstream cyclegan_natural_comics_without_text).

Losses and weights as upstream: LSGAN (MSE) + 10 * cycle L1 + 5 * identity L1, no replay buffer.
"""

import argparse
import itertools

import torch

from . import config as config_lib
from .datasets import NaturalMangaDataset, load_coco_items, load_manga_items, manifest_identity
from .networks.cyclegan import Discriminator, GeneratorResNet
from .training import (Run, adam, add_train_args, autocast, average_gradients, broadcast_module,
                       exit_after_smoke, finished, log_every, make_loader, per_rank_batch, setup,
                       steps_per_epoch, stop_requested, teardown, to_device, memory_format)

STAGE = "without_text"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="train-without-text", description=__doc__.splitlines()[0])
    add_train_args(parser)
    args = parser.parse_args(argv)
    cfg = config_lib.config_from_args(args)
    s, t = cfg[STAGE], cfg["train"]
    ctx = setup(args, cfg)
    device = ctx.device
    batch = per_rank_batch(s["batch_size"], ctx)
    coco_dir, manga_dir = config_lib.coco_dir(cfg), config_lib.manga_dir(cfg)
    identity = {"stage": cfg[STAGE], "crop": t["crop"], "seed": t["seed"],
                "coco": manifest_identity(coco_dir), "manga": manifest_identity(manga_dir)}
    run = Run(cfg, STAGE, identity, s["keep_every"], ctx)
    if finished(run):
        teardown(ctx)
        return 0

    dataset = NaturalMangaDataset(load_coco_items(coco_dir, with_depth=False),
                                  load_manga_items(manga_dir, "train", "textfree"), t["crop"])
    ctx.print(f"natural {len(dataset.natural)}, manga text-free {len(dataset.manga)}, "
              f"{steps_per_epoch(dataset, s['batch_size'])} steps/epoch, {batch} per GPU")

    crop = t["crop"]
    comics2natural = GeneratorResNet(3, 3, s["residual_blocks"]).to(device, memory_format=memory_format(cfg))
    natural2comics = GeneratorResNet(3, 3, s["residual_blocks"]).to(device, memory_format=memory_format(cfg))
    discrim_natural = Discriminator((3, crop, crop)).to(device, memory_format=memory_format(cfg))
    discrim_comics = Discriminator((3, crop, crop)).to(device, memory_format=memory_format(cfg))
    optimizer_G = adam(itertools.chain(comics2natural.parameters(), natural2comics.parameters()), s)
    optimizer_Dn = adam(discrim_natural.parameters(), s)
    optimizer_Dc = adam(discrim_comics.parameters(), s)
    mse, l1 = torch.nn.MSELoss(), torch.nn.L1Loss()

    modules = {"comics2natural": comics2natural, "natural2comics": natural2comics,
               "discrim_natural": discrim_natural, "discrim_comics": discrim_comics}
    optimizers = {"optimizer_G": optimizer_G, "optimizer_discrim_natural": optimizer_Dn,
                  "optimizer_discrim_comics": optimizer_Dc}
    epochs_done, step = 0, 0
    state = run.load_latest(device)
    if state:
        for name, module in {**modules, **optimizers}.items():
            module.load_state_dict(state[name])
        epochs_done, step = state["epochs_done"], state["step"]
    for module in modules.values():
        broadcast_module(module, ctx)

    def snapshot():
        return {"epochs_done": epochs_done, "step": step, "stage": STAGE,
                **{name: m.state_dict() for name, m in {**modules, **optimizers}.items()}}

    valid = torch.ones((batch, *discrim_natural.output_shape), device=device)
    fake = torch.zeros_like(valid)
    while epochs_done < s["epochs"]:
        loader = make_loader(dataset, batch, t["num_workers"], t["seed"], epochs_done, ctx)
        for data in loader:
            real_natural = to_device(data["natural"], ctx, cfg)
            real_comics = to_device(data["manga"], ctx, cfg)
            natural2comics.train(), comics2natural.train()

            optimizer_G.zero_grad(set_to_none=True)
            with autocast(ctx, cfg):
                loss_identity = (l1(comics2natural(real_natural), real_natural)
                                 + l1(natural2comics(real_comics), real_comics)) / 2
                fake_comics = natural2comics(real_natural)
                fake_natural = comics2natural(real_comics)
                loss_gan_n2c = mse(discrim_comics(fake_comics), valid)
                loss_gan_c2n = mse(discrim_natural(fake_natural), valid)
                loss_gan = (loss_gan_n2c + loss_gan_c2n) / 2
                loss_cycle = (l1(comics2natural(fake_comics), real_natural)
                              + l1(natural2comics(fake_natural), real_comics)) / 2
                loss_G = (loss_gan + s["lambda_cycle"] * loss_cycle
                          + s["lambda_identity"] * loss_identity)
            loss_G.backward()
            average_gradients(comics2natural, ctx)
            average_gradients(natural2comics, ctx)
            optimizer_G.step()

            optimizer_Dn.zero_grad(set_to_none=True)
            with autocast(ctx, cfg):
                loss_Dn = (mse(discrim_natural(real_natural), valid)
                           + mse(discrim_natural(fake_natural.detach()), fake)) / 2
            loss_Dn.backward()
            average_gradients(discrim_natural, ctx)
            optimizer_Dn.step()

            optimizer_Dc.zero_grad(set_to_none=True)
            with autocast(ctx, cfg):
                loss_Dc = (mse(discrim_comics(real_comics), valid)
                           + mse(discrim_comics(fake_comics.detach()), fake)) / 2
            loss_Dc.backward()
            average_gradients(discrim_comics, ctx)
            optimizer_Dc.step()

            step += 1
            if log_every(step):
                run.log_losses(epochs_done + 1, step, {
                    "G": loss_G.item(), "gan_n2c": loss_gan_n2c.item(),
                    "gan_c2n": loss_gan_c2n.item(), "cycle": loss_cycle.item(),
                    "identity": loss_identity.item(), "D_natural": loss_Dn.item(),
                    "D_comics": loss_Dc.item()})
            if stop_requested(args, step):
                run.save_samples(f"smoke_step{step:06d}", [real_natural, fake_comics,
                                                          real_comics, fake_natural])
                exit_after_smoke(run, snapshot())
        epochs_done += 1
        n = min(t["vis_samples"], real_natural.shape[0])
        run.save_samples(f"epoch_{epochs_done:03d}",
                         [real_natural[:n], fake_comics[:n], real_comics[:n], fake_natural[:n]])
        run.save(snapshot(), epoch_complete=True, final=epochs_done == s["epochs"])
        run.log({"epoch": epochs_done, "step": step, "event": "epoch_saved"})
    ctx.print(f"Done: {run.final_path}")
    teardown(ctx)
    return 0
