# Third-party code and method

## ComicsDepth (method reference, no code copied verbatim)
Bhattacharjee, Everaert, Salzmann, Süsstrunk. *Estimating Image Depth in the Comics Domain*, WACV 2022.
Repository https://github.com/IVRL/ComicsDepth, inspected at commit `fd0cc3c` (2026-10-23).
LICENSE file: CC0-1.0; README states CC BY-NC 4.0. Treat as non-commercial research use.

The architectures, losses and hyperparameters were reconstructed from these upstream files:

| Upstream file | Here |
|---|---|
| `datasets_preparation.py --coco17_depth` | `coco_depth.py` |
| `datasets_preparation.py --crop_frames`, `comics2textareas.py` (U-Net text areas, `generate_dcm_without_text_areas`) | `manga_prep.py` (MAGI-3 boxes instead of a U-Net) |
| `cyclegan_natural_comics_without_text_train.py` | `train_without_text.py` |
| `cyclegan_natural_comics_add_text_train.py` | `train_add_text.py` |
| `depth_add_text_ignoretext_train.py` | `train_depth.py` |
| inline `GeneratorResNet`/`Discriminator` (missing `models/models.py`) | `networks/cyclegan.py` |
| `evaluation.py` (`evalulate_image`) | `ordering.py` |

## MiDaS v2.1
`src/comics_depth/networks/midas_v21.py` is adapted from https://github.com/isl-org/MiDaS
(commit `454597711a62`, `midas/midas_net.py`, `midas/blocks.py`).

MIT License, Copyright (c) 2019 Intel ISL (Intel Intelligent Systems Lab).
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions: The above copyright notice and this
permission notice shall be included in all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

Weights: `midas_v21_384.pt` from the MiDaS v2_1 release (downloaded by `scripts/download_weights.sh`).

## Depth Anything V2 (optional baseline)
`depth-anything/Depth-Anything-V2-Large-hf` via transformers; the Large weights are CC BY-NC 4.0.
