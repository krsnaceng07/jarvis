"""Offline prediction of the hologram shader, so framing can be tuned fast.

Mirrors the constants in ``src/components/center/ThreeHologram.tsx`` (fov,
camera distance, sprite falloff, additive blending) and rasterizes the baked
cloud at the real card size. Tuning in the browser costs a capture cycle per
change; this is one second per iteration.

Usage:
    python tools/preview_avatar_render.py public/avatar_male.bin out.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

# Kept in sync with ThreeHologram.tsx.
CAMERA_FOV = 35.0
CAMERA_Z = 3.4
SPRITE_STOPS = ((0.0, 1.0), (0.35, 0.85), (0.7, 0.22), (1.0, 0.0))


def load_cloud(path: Path) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.float32)
    return raw.reshape(-1, 6)


def sprite_kernel(radius: int) -> np.ndarray:
    span = np.arange(-radius, radius + 1, dtype=np.float32) / max(1.0, radius)
    y, x = np.meshgrid(span, span, indexing="ij")
    r = np.sqrt(x * x + y * y)
    stops = np.array(SPRITE_STOPS, dtype=np.float32)
    return np.interp(r, stops[:, 0], stops[:, 1], left=1.0, right=0.0)


def render(
    cloud: np.ndarray,
    *,
    width: int,
    height: int,
    margin: float,
    radius: int,
    opacity: float,
    centre_y: float,
    scale_mult: float = 1.0,
) -> np.ndarray:
    x, y = cloud[:, 0], cloud[:, 1]
    span_x = max(1e-6, float(x.max() - x.min()))
    span_y = max(1e-6, float(y.max() - y.min()))

    visible_h = 2.0 * CAMERA_Z * np.tan(np.radians(CAMERA_FOV) / 2.0)
    visible_w = visible_h * (width / height)
    scale = (
        min(visible_w / (span_x * margin), visible_h / (span_y * margin))
        * scale_mult
    )

    # group.position in the shader lifts the bust off the card centre so the
    # status row and TERMINATE button keep the bottom third clear.
    world_x = (x - (x.min() + x.max()) / 2.0) * scale
    world_y = (y - (y.min() + y.max()) / 2.0) * scale
    px = (0.5 + world_x / visible_w) * width
    py = (0.5 - (world_y / visible_h) - centre_y) * height

    canvas = np.zeros((height, width, 3), dtype=np.float32)
    kernel = sprite_kernel(radius)
    keep = (px > -radius) & (px < width + radius) & (py > -radius) & (py < height + radius)

    base_x = np.rint(px[keep]).astype(int)
    base_y = np.rint(py[keep]).astype(int)
    colours = cloud[keep, 3:6] * opacity

    for dy in range(-radius, radius + 1):
        cy = base_y + dy
        ok_y = (cy >= 0) & (cy < height)
        for dx in range(-radius, radius + 1):
            cx = base_x + dx
            ok = ok_y & (cx >= 0) & (cx < width)
            weight = kernel[dy + radius, dx + radius]
            if weight <= 0.0 or not ok.any():
                continue
            np.add.at(
                canvas,
                (cy[ok], cx[ok]),
                colours[ok] * weight,
            )

    return np.clip(canvas, 0.0, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cloud", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--width", type=int, default=341)
    parser.add_argument("--height", type=int, default=340)
    parser.add_argument("--margin", type=float, default=1.55)
    parser.add_argument("--radius", type=int, default=2)
    parser.add_argument("--opacity", type=float, default=0.42)
    parser.add_argument("--centre-y", type=float, default=0.10)
    parser.add_argument("--scale-mult", type=float, default=1.0)
    parser.add_argument("--zoom", type=int, default=2)
    args = parser.parse_args()

    cloud = load_cloud(args.cloud)
    image = render(
        cloud,
        width=args.width,
        height=args.height,
        margin=args.margin,
        radius=args.radius,
        opacity=args.opacity,
        centre_y=args.centre_y,
        scale_mult=args.scale_mult,
    )
    out = Image.fromarray((image * 255).astype(np.uint8))
    if args.zoom != 1:
        out = out.resize((out.width * args.zoom, out.height * args.zoom), Image.LANCZOS)
    out.save(args.output)
    print(f"{args.output} ({out.width}x{out.height})")


if __name__ == "__main__":
    main()
