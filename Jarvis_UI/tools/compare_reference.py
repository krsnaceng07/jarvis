"""Compare rendered HUD regions against the reference screenshot.

The vision preview of a 1536x831 dark screenshot is unreliable, so fidelity is
checked numerically: region brightness and colour balance against the approved
reference, plus a per-region report.

Usage:
    python tools/compare_reference.py reference.png rendered.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

REGIONS: dict[str, tuple[int, int, int, int]] = {
    "top bar": (0, 0, 1536, 37),
    "left rail": (10, 37, 286, 824),
    "module cards": (310, 100, 480, 350),
    "hologram card": (679, 68, 1020, 408),
    "visual hub": (297, 425, 1047, 809),
    "right panel": (1057, 37, 1526, 824),
    "whole page": (0, 0, 1536, 831),
}


def load(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("rendered", type=Path)
    args = parser.parse_args()

    ref = load(args.reference)
    got = load(args.rendered)
    if ref.shape != got.shape:
        raise SystemExit(f"size mismatch: {ref.shape} vs {got.shape}")

    print(f"{'region':16}{'ref':>7}{'mine':>7}{'delta':>9}{'ref rgb':>22}{'mine rgb':>22}")
    for name, (x0, y0, x1, y1) in REGIONS.items():
        a = ref[y0:y1, x0:x1]
        b = got[y0:y1, x0:x1]
        print(
            f"{name:16}{a.mean():7.3f}{b.mean():7.3f}{b.mean() - a.mean():+9.3f}"
            f"{str(np.round(a.reshape(-1, 3).mean(axis=0), 3)):>22}"
            f"{str(np.round(b.reshape(-1, 3).mean(axis=0), 3)):>22}"
        )


if __name__ == "__main__":
    main()
