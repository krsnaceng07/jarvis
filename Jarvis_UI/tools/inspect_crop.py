"""Crop + brighten a screenshot region so dark HUD detail survives inspection.

The plain captures are very dark; downscaled previews of them lose all text, so
verification crops are level-stretched and upscaled before being looked at.

Usage:
    python tools/inspect_crop.py shot.png 700,240 310x170 --out crop.png --scale 3
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("origin", help="x,y")
    parser.add_argument("size", help="widthxheight")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--gain", type=float, default=2.6)
    parser.add_argument("--raw", action="store_true", help="skip the level stretch")
    args = parser.parse_args()

    x, y = (int(v) for v in args.origin.split(","))
    w, h = (int(v) for v in args.size.lower().split("x"))

    image = Image.open(args.image).convert("RGB").crop((x, y, x + w, y + h))
    if not args.raw:
        data = np.asarray(image, dtype=np.float32) / 255.0
        data = np.clip(data * args.gain, 0.0, 1.0)
        image = Image.fromarray((data * 255).astype(np.uint8))
    if args.scale != 1:
        image = image.resize((image.width * args.scale, image.height * args.scale), Image.LANCZOS)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out)
    print(f"{args.out} ({image.width}x{image.height})")


if __name__ == "__main__":
    main()
