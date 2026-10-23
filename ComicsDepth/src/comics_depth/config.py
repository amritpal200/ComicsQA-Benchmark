"""TOML configuration with --set overrides and {placeholder} path expansion."""

import argparse
import copy
import hashlib
import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "configs" / "default.toml"


def parse_value(raw):
    """Parse a TOML literal (number, bool, list, quoted string); fall back to a bare string."""
    try:
        return tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        return raw


def apply_override(cfg, item):
    key, sep, raw = item.partition("=")
    if not sep:
        raise ValueError(f"override must look like section.key=value, got {item!r}")
    *parents, leaf = key.strip().split(".")
    node = cfg
    for part in parents:
        if part not in node or not isinstance(node[part], dict):
            raise KeyError(f"unknown config section in {key!r}")
        node = node[part]
    if leaf not in node:
        raise KeyError(f"unknown config key {key!r}")
    node[leaf] = parse_value(raw.strip())


def expand_paths(paths):
    expanded = dict(paths)
    for _ in range(len(expanded) + 1):
        changed = False
        for key, value in expanded.items():
            if isinstance(value, str) and "{" in value:
                new = value.format_map(expanded)
                changed |= new != value
                expanded[key] = new
        if not changed:
            return expanded
    raise ValueError(f"cyclic placeholders in [paths]: {paths}")


def load_config(path=None, overrides=()):
    with open(path or DEFAULT_CONFIG, "rb") as handle:
        cfg = tomllib.load(handle)
    for item in overrides:
        apply_override(cfg, item)
    cfg["paths"] = expand_paths(cfg["paths"])
    return cfg


def add_config_args(parser: argparse.ArgumentParser):
    parser.add_argument("--config", type=Path, default=None,
                        help=f"TOML config (default: {DEFAULT_CONFIG})")
    parser.add_argument("--set", dest="overrides", action="append", default=[],
                        metavar="SECTION.KEY=VALUE", help="override a config value (repeatable)")


def config_from_args(args):
    return load_config(args.config, args.overrides)


def section_hash(cfg, *sections):
    payload = {name: copy.deepcopy(cfg[name]) for name in sections}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(blob).hexdigest()


def root(cfg) -> Path:
    return Path(cfg["paths"]["root"])


def data_dir(cfg, name) -> Path:
    return root(cfg) / "data" / name


def manga_dir(cfg) -> Path:
    return data_dir(cfg, cfg["manga"]["name"])


def coco_dir(cfg) -> Path:
    return data_dir(cfg, cfg["coco"]["name"])


def run_dir(cfg, stage) -> Path:
    return root(cfg) / "runs" / cfg["train"]["run"] / stage
