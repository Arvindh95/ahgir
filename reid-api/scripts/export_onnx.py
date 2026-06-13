"""One-shot OSNet → ONNX export.

Run this BEFORE deploying the reid-api service. It writes the model into
../models/osnet_ain_x1_0.onnx which docker-compose mounts into the container.

Why kept in this repo: deploys are reproducible — anyone setting up a new VPS
runs the same script and gets bit-identical weights. The torchreid dependency
is intentionally NOT in reid-api/requirements.txt because we only need it
once at export time; the runtime container ships only onnxruntime.

torchreid is NOT a PyPI package at the version we need (PyPI 'torchreid' stops
at 0.2.5 and lacks osnet_ain). Install it from KaiyangZhou's deep-person-reid
source, and note torch.onnx.export needs the `onnx` package too. The simplest
reproducible path is a throwaway container (no host pollution):

    docker run --rm -v "$PWD/reid-api:/work" -w /work python:3.11-slim bash -c '
      apt-get update -qq && apt-get install -y -qq libgl1 libglib2.0-0 gcc g++ git
      pip install "numpy<2" Cython onnx
      pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cpu
      git clone --depth 1 https://github.com/KaiyangZhou/deep-person-reid.git /tmp/dpr
      grep -vE "tb-nightly|flake8|yapf|isort" /tmp/dpr/requirements.txt > /tmp/req.txt
      pip install -r /tmp/req.txt tensorboard
      pip install --no-build-isolation -e /tmp/dpr
      python scripts/export_onnx.py'

Then `docker compose restart reid-api`.
"""
from __future__ import annotations

import argparse
import os
import sys

DEFAULT_OUT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "models", "osnet_ain_x1_0.onnx")
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output ONNX path.")
    parser.add_argument(
        "--model",
        default="osnet_ain_x1_0",
        help="torchreid model name. osnet_ain_x1_0 is the default we ship.",
    )
    args = parser.parse_args()

    try:
        import torch
        import torchreid
    except ImportError as exc:
        print(
            "torch / torchreid not installed. Install with:\n"
            "    pip install torch==2.1.2 torchvision==0.16.2 torchreid==1.4.0\n"
            f"Underlying error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(f"Building {args.model} with ImageNet-pretrained weights …")
    model = torchreid.models.build_model(
        name=args.model,
        num_classes=1000,  # ignored for embedding extraction
        loss="softmax",
        pretrained=True,
    )
    model.eval()

    # Dummy NCHW input matching reid-api/app.py preprocessing geometry.
    dummy = torch.randn(1, 3, 256, 128)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        args.out,
        input_names=["input"],
        output_names=["embedding"],
        opset_version=14,
        dynamic_axes={"input": {0: "batch"}, "embedding": {0: "batch"}},
    )
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
