"""Command dispatcher: python -m comics_depth <command> [options]."""

import importlib
import sys

COMMANDS = {
    "verify-weights": "comics_depth.verify_weights",
    "prepare-coco": "comics_depth.coco_depth",
    "prepare-manga": "comics_depth.manga_prep",
    "train-without-text": "comics_depth.train_without_text",
    "train-add-text": "comics_depth.train_add_text",
    "train-depth": "comics_depth.train_depth",
    "predict": "comics_depth.predict",
    "preview": "comics_depth.preview",
    "evaluate": "comics_depth.evaluate",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print("usage: python -m comics_depth <command> [options]")
        print("commands: " + ", ".join(COMMANDS))
        return 2
    module = importlib.import_module(COMMANDS[argv[0]])
    return module.main(argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main())
