# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#   "torch==2.9.0+cu126", "torchvision==0.24.0+cu126", "transformers==5.16.1", "pillow>=11,<13",
# ]
# [tool.uv.sources]
# torch = { index = "pytorch-cu126" }
# torchvision = { index = "pytorch-cu126" }
# [[tool.uv.index]]
# name = "pytorch-cu126"
# url = "https://download.pytorch.org/whl/cu126"
# explicit = true
# ///
"""run_ocr.py with the CUDA 12.6 build of torch 2.9.0, for GPUs older than sm_70 (e.g. TITAN Xp, Pascal),
which the CUDA 12.8 build no longer supports. Same arguments and output as run_ocr.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_ocr  # noqa: E402

if __name__ == '__main__':
    try:
        sys.exit(run_ocr.main())
    except Exception as exc:
        run_ocr.log(f'FATAL {type(exc).__name__}: {exc}')
        sys.exit(1)
