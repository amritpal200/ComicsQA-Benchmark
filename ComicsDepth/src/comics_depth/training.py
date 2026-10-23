"""Shared training utilities: device and multi-GPU setup, run identity, checkpoints, logging.

Multi-GPU (torchrun, one process per GPU) is plain data parallelism: each rank gets
batch_size / world_size samples and gradients are averaged across ranks before every optimizer
step, which equals one optimizer step on the full batch (CycleGANs use InstanceNorm, which is
per sample; MiDaS BatchNorm is converted to SyncBatchNorm). Models are not wrapped in
DistributedDataParallel because the CycleGAN generators run several forwards per step.
Only rank 0 writes files.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.distributed as dist
from torch.utils.data import DataLoader, DistributedSampler

from . import config as config_lib
from .io_utils import append_jsonl, atomic_write_json, run_metadata


@dataclass
class Context:
    device: torch.device
    rank: int = 0
    world: int = 1

    @property
    def main(self):
        return self.rank == 0

    @property
    def distributed(self):
        return self.world > 1

    def barrier(self):
        if self.distributed:
            dist.barrier()

    def print(self, *args, **kwargs):
        if self.main:
            print(*args, **kwargs, flush=True)


def add_train_args(parser: argparse.ArgumentParser):
    config_lib.add_config_args(parser)
    parser.add_argument("--max-steps", type=int, default=0,
                        help="stop after N optimizer steps (smoke test); 0 = full schedule")
    parser.add_argument("--device", default="cuda", help="cuda (default) or cpu for tiny tests")


def setup(args, cfg) -> Context:
    world = int(os.environ.get("WORLD_SIZE", "1"))
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA is not available; pass --gpu N or --gpus N,M to scripts/run.sh")
    if cfg["train"]["allow_tf32"]:
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
    torch.backends.cudnn.benchmark = True
    torch.manual_seed(cfg["train"]["seed"])  # identical initial weights on every rank
    if world == 1:
        return Context(torch.device(args.device))
    local_rank = int(os.environ["LOCAL_RANK"])
    if args.device == "cuda":
        torch.cuda.set_device(local_rank)
        dist.init_process_group("nccl", device_id=torch.device("cuda", local_rank))
        device = torch.device("cuda", local_rank)
    else:  # CPU (gloo) only for tests of the multi-process logic
        dist.init_process_group("gloo")
        device = torch.device("cpu")
    ctx = Context(device, dist.get_rank(), dist.get_world_size())
    ctx.print(f"data parallel on {ctx.world} GPUs")
    return ctx


def teardown(ctx: Context):
    if ctx.distributed and dist.is_initialized():
        dist.barrier()
        dist.destroy_process_group()


def autocast(ctx: Context, cfg):
    """bf16 autocast on CUDA when train.amp = "bf16" (no-op on CPU or with "none")."""
    mode = cfg["train"]["amp"]
    if mode not in ("none", "bf16"):
        raise SystemExit(f"train.amp must be 'none' or 'bf16', got {mode!r}")
    return torch.autocast("cuda", dtype=torch.bfloat16,
                          enabled=mode == "bf16" and ctx.device.type == "cuda")


def memory_format(cfg):
    return torch.channels_last if cfg["train"]["channels_last"] else torch.contiguous_format


def to_device(tensor, ctx: Context, cfg):
    tensor = tensor.to(ctx.device, non_blocking=True)
    if tensor.dim() == 4:
        tensor = tensor.contiguous(memory_format=memory_format(cfg))
    return tensor


def per_rank_batch(batch_size, ctx: Context):
    if batch_size % ctx.world:
        raise SystemExit(f"batch_size {batch_size} is not divisible by {ctx.world} GPUs")
    return batch_size // ctx.world


def make_loader(dataset, batch_size, num_workers, seed, epoch, ctx: Context):
    # The generator seeds the workers' Python `random` (pairing and crops); include the rank.
    generator = torch.Generator().manual_seed(seed * 1000003 + epoch * 101 + ctx.rank)
    sampler = None
    if ctx.distributed:
        sampler = DistributedSampler(dataset, num_replicas=ctx.world, rank=ctx.rank,
                                     shuffle=True, seed=seed, drop_last=True)
        sampler.set_epoch(epoch)
    return DataLoader(dataset, batch_size=batch_size, shuffle=sampler is None, sampler=sampler,
                      drop_last=True, num_workers=num_workers, generator=generator,
                      pin_memory=ctx.device.type == "cuda", persistent_workers=False)


def steps_per_epoch(dataset, batch_size):
    return len(dataset) // batch_size


def broadcast_module(module, ctx: Context):
    if ctx.distributed:
        for tensor in module.state_dict().values():
            dist.broadcast(tensor, src=0)


def average_gradients(module, ctx: Context):
    """All-reduce (mean) the gradients of one module in a single flat buffer."""
    if not ctx.distributed:
        return
    grads = [p.grad for p in module.parameters() if p.grad is not None]
    if not grads:
        return
    flat = torch._utils._flatten_dense_tensors(grads)
    dist.all_reduce(flat)
    flat /= ctx.world
    for grad, reduced in zip(grads, torch._utils._unflatten_dense_tensors(flat, grads)):
        grad.copy_(reduced)


def mean_across_ranks(values: dict, ctx: Context):
    """Average logged scalars over ranks (every rank must call this at the same step)."""
    if not ctx.distributed:
        return {k: float(v) for k, v in values.items()}
    keys = sorted(values)
    tensor = torch.tensor([float(values[k]) for k in keys], device=ctx.device)
    dist.all_reduce(tensor)
    tensor /= ctx.world
    return dict(zip(keys, tensor.tolist()))


def require_file(path, hint):
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Missing {path}: {hint}")
    return path


def adam(params, section):
    return torch.optim.Adam(params, lr=section["lr"], betas=tuple(section["betas"]))


class Run:
    """One training stage in {root}/runs/<run>/<stage>/.

    Files: run.json (identity + metadata), metrics.jsonl, latest.pth, epoch_XXX.pth (every
    keep_every epochs, hard links), final.pth when the schedule completes, samples/*.png.
    Resuming requires an identical identity (stage config + inputs). The GPU count is not part
    of the identity: the global batch size is."""

    def __init__(self, cfg, stage, identity, keep_every, ctx: Context = None):
        self.ctx = ctx or Context(torch.device("cpu"))
        self.dir = config_lib.run_dir(cfg, stage)
        self.stage = stage
        self.keep_every = keep_every
        self.identity = json.loads(json.dumps(identity, sort_keys=True, default=str))
        info_path = self.dir / "run.json"
        if self.ctx.main:
            self.dir.mkdir(parents=True, exist_ok=True)
            if info_path.exists():
                self._check(info_path)
            else:
                atomic_write_json(info_path, {"stage": stage, "identity": self.identity,
                                              "created": {**run_metadata(), "world_size": self.ctx.world}})
        self.ctx.barrier()
        if not self.ctx.main:
            self._check(info_path)

    def _check(self, info_path):
        with open(info_path) as handle:
            saved = json.load(handle)
        if saved["identity"] != self.identity:
            raise SystemExit(
                f"{info_path} was created with a different config/inputs.\n"
                f"Use a new run name (--set train.run=...) instead of resuming.\n"
                f"saved:   {json.dumps(saved['identity'], sort_keys=True)[:2000]}\n"
                f"current: {json.dumps(self.identity, sort_keys=True)[:2000]}")

    @property
    def final_path(self):
        return self.dir / "final.pth"

    def load_latest(self, map_location):
        path = self.dir / "latest.pth"
        if not path.exists():
            return None
        state = torch.load(path, map_location=map_location, weights_only=False)
        self.ctx.print(f"Resuming {self.stage} from {path}: {state['epochs_done']} epochs done, "
                       f"step {state['step']}")
        return state

    def save(self, state, epoch_complete, final=False):
        if self.ctx.main:
            latest = self.dir / "latest.pth"
            tmp = self.dir / f".latest.pth.tmp-{os.getpid()}"
            torch.save(state, tmp)
            os.replace(tmp, latest)
            epochs = state["epochs_done"]
            links = []
            if epoch_complete and self.keep_every and epochs % self.keep_every == 0:
                links.append(self.dir / f"epoch_{epochs:03d}.pth")
            if final:
                links.append(self.final_path)
            for link in links:
                if link.exists():
                    link.unlink()
                os.link(latest, link)
        self.ctx.barrier()

    def log(self, record):
        if not self.ctx.main:
            return
        record = {"time": round(time.time(), 1), **record}
        append_jsonl(self.dir / "metrics.jsonl", record)
        print(" ".join(f"{k}={v:.5g}" if isinstance(v, float) else f"{k}={v}"
                       for k, v in record.items() if k != "time"), flush=True)

    def log_losses(self, epoch, step, losses: dict):
        """Rank-averaged losses (call on every rank)."""
        self.log({"epoch": epoch, "step": step, **mean_across_ranks(losses, self.ctx)})

    def save_samples(self, name, rows):
        """rows: list of (B, C, H, W) tensors in [0, 1]; each becomes one row of the grid."""
        if not self.ctx.main:
            return
        from torchvision.utils import save_image
        rows = [r.detach().float().cpu() for r in rows]
        rows = [r.expand(-1, 3, -1, -1) if r.shape[1] == 1 else r for r in rows]
        grid = torch.cat(rows, dim=0)
        (self.dir / "samples").mkdir(exist_ok=True)
        save_image(grid, self.dir / "samples" / f"{name}.png", nrow=rows[0].shape[0])


def finished(run: Run):
    if run.final_path.exists():
        run.ctx.print(f"{run.stage} already complete: {run.final_path}")
        return True
    return False


def log_every(step):
    return step <= 10 or step % 50 == 0


def stop_requested(args, step):
    return bool(args.max_steps) and step >= args.max_steps


def exit_after_smoke(run, state):
    run.save(state, epoch_complete=False)
    run.ctx.print(f"Stopped after --max-steps={state['step']} (smoke test); "
                  f"latest.pth saved in {run.dir}")
    teardown(run.ctx)
    sys.exit(0)
