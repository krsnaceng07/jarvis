"""Reference-versus-render comparison for the hologram characters.

Builds a labelled sheet from the storyboard frames and the phase captures taken
by ``capture_hologram_phases.py``, and prints luminance metrics per pair.

Usage: python tools/compare_hologram.py [phase_dir] [male|female]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
PHASE_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\kcs23\AppData\Local\Temp\opencode\ui"
)
CHARACTER = sys.argv[2] if len(sys.argv) > 2 else "female"

# Storyboard cell -> capture phase. Cell index is row-major at 2 seconds/frame.
SHEETS = {
    "female": {
        "path": ROOT / "reference" / "holographic_woman_timeline.png",
        "cols": 5,
        "rows": 7,
        "inset": (118, 26, 252, 146),
        "pairs": [
            ("reference 42s (stable)", (4, 1), "holo_stable.png"),
            ("reference 24s (dispersed)", (2, 2), "holo_scattered.png"),
            ("reference 64s (reforming)", (6, 2), "holo_scan_mid.png"),
        ],
    },
    "male": {
        "path": ROOT / "reference" / "male_timeline.png",
        "cols": 5,
        "rows": 5,
        "inset": (75, 18, 245, 205),
        "pairs": [
            ("reference 42s (stable)", (4, 1), "holo_stable.png"),
            ("reference 24s (dispersed)", (2, 2), "holo_scattered.png"),
            ("reference 26s (reforming)", (2, 3), "holo_scan_mid.png"),
        ],
    },
}
SHEET = SHEETS[CHARACTER]
OUT = PHASE_DIR / f"hologram_comparison_{CHARACTER}.png"


def storyboard_cell(row: int, col: int) -> Image.Image:
    src = Image.open(SHEET["path"]).convert("RGB")
    cw, ch = src.size[0] / SHEET["cols"], src.size[1] / SHEET["rows"]
    cell = src.crop((int(col * cw), int(row * ch), int((col + 1) * cw), int((row + 1) * ch)))
    return cell.crop(SHEET["inset"])


def bust_crop(path: Path, pad: float = 0.04) -> Image.Image:
    image = Image.open(path).convert("RGB")
    data = np.asarray(image).astype(np.float32)
    height, width, _ = data.shape
    # Ignore the mode chip that floats over the card corner.
    data[: int(height * 0.12), : int(width * 0.35)] = 0
    mask = data.max(axis=2) > 45
    rows, cols = np.nonzero(mask)
    if rows.size == 0:
        return image
    x_pad = int((cols.max() - cols.min()) * pad)
    y_pad = int((rows.max() - rows.min()) * pad)
    box = (
        max(0, int(cols.min()) - x_pad),
        max(0, int(rows.min()) - y_pad),
        min(width, int(cols.max()) + x_pad),
        min(height, int(rows.max()) + y_pad),
    )
    return image.crop(box)


def metrics(image: Image.Image) -> tuple[float, float, float]:
    data = np.asarray(image.convert("RGB")).astype(np.float32)
    peak = data.max(axis=2)
    lit = peak > 50
    return (
        float(data.mean()),
        float(np.percentile(peak[lit], 99)) if lit.any() else 0.0,
        float(lit.mean() * 100),
    )


def normalized_luma(image: Image.Image, size: tuple[int, int] = (180, 200)) -> np.ndarray:
    luma = np.asarray(image.convert("L").resize(size, Image.LANCZOS)).astype(np.float32)
    luma -= luma.min()
    peak = float(luma.max()) or 1.0
    return luma / peak


def similarity(left: Image.Image, right: Image.Image) -> tuple[float, float]:
    """Return (normalized cross-correlation, silhouette IoU) after size normalization."""
    a = normalized_luma(left)
    b = normalized_luma(right)
    a_centred = a - a.mean()
    b_centred = b - b.mean()
    denominator = float(np.sqrt((a_centred**2).sum() * (b_centred**2).sum())) or 1.0
    ncc = float((a_centred * b_centred).sum() / denominator)
    a_mask = a > 0.28
    b_mask = b > 0.28
    union = float((a_mask | b_mask).sum()) or 1.0
    return ncc, float((a_mask & b_mask).sum() / union)


def main() -> None:
    rows: list[tuple[str, Image.Image, Image.Image]] = []
    for label, (row, col), render in SHEET["pairs"]:
        render_path = PHASE_DIR / render
        if not render_path.exists():
            print(f"missing {render_path}, skipping")
            continue
        rows.append((label, storyboard_cell(row, col), bust_crop(render_path)))

    if not rows:
        raise SystemExit("no captures found")

    tile_h = 420
    tiles = []
    for label, reference, render in rows:
        ref_tile = reference.resize((int(reference.width * tile_h / reference.height), tile_h), Image.LANCZOS)
        ren_tile = render.resize((int(render.width * tile_h / render.height), tile_h), Image.LANCZOS)
        tiles.append((label, ref_tile, ren_tile))

    width = max(ref.width + ren.width + 24 for _, ref, ren in tiles)
    height = len(tiles) * (tile_h + 30)
    sheet = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)

    y = 0
    for label, ref, ren in tiles:
        draw.text((6, y + 4), label, fill=(120, 220, 235))
        sheet.paste(ref, (0, y + 26))
        sheet.paste(ren, (ref.width + 24, y + 26))
        y += tile_h + 30

    sheet.save(OUT)
    print(f"comparison: {OUT} ({sheet.width}x{sheet.height})")

    for label, reference, render in rows:
        ref_mean, ref_p99, ref_lit = metrics(reference)
        ren_mean, ren_p99, ren_lit = metrics(render)
        ncc, iou = similarity(reference, render)
        print(
            f"{label:28s} ref mean={ref_mean:6.1f} p99={ref_p99:5.1f} lit={ref_lit:5.1f}% | "
            f"render mean={ren_mean:6.1f} p99={ren_p99:5.1f} lit={ren_lit:5.1f}% | "
            f"ncc={ncc:+.3f} iou={iou:.3f}"
        )


if __name__ == "__main__":
    main()
