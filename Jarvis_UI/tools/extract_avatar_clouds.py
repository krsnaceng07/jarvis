"""Bake the two hologram busts from the approved reference art.

Both characters are extracted from the owner-approved storyboards so the
dashboard and onboarding show the same silhouettes the owner signed off on:

* male   <- 46s cell of ``reference/male_timeline.png`` (5 x 5 storyboard)
* female <- 42s cell of ``reference/holographic_woman_timeline.png`` (5 x 7)

The renderer consumes a flat Float32 stream of ``x y z r g b`` per particle.
Brightness drives depth (bright cores sit closer to camera) and the colour ramp
is normalized to the HUD cyan so both characters read as one material.
"""

from __future__ import annotations

import struct
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
PREVIEW_DIR = Path(tempfile.gettempdir()) / 'jarvis_ui_previews'
PUBLIC = ROOT / "public"
# The owner-approved storyboards, vendored so both bakes are reproducible.
MALE_TIMELINE = ROOT / "reference" / "male_timeline.png"
FEMALE_TIMELINE = ROOT / "reference" / "holographic_woman_timeline.png"

DEEP = np.array([0.004, 0.020, 0.060])
MID = np.array([0.030, 0.170, 0.520])
BRIGHT = np.array([0.620, 0.850, 1.000])


def colour_ramp(intensity: np.ndarray) -> np.ndarray:
    t = np.clip(intensity, 0.0, 1.0)[:, None]
    low = DEEP + (MID - DEEP) * np.clip(t / 0.62, 0.0, 1.0)
    high = MID + (BRIGHT - MID) * np.clip((t - 0.62) / 0.38, 0.0, 1.0)
    return np.where(t < 0.62, low, high)


def trim_outliers(
    px: np.ndarray,
    py: np.ndarray,
    value: np.ndarray,
    *,
    keep: float = 0.995,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drop connector traces and caption specks that sit outside the bust.

    The reference art has HUD traces entering the bust bounding box; without
    this the fitted bust shrinks to leave room for pixels nobody can see.
    """
    x_lo, x_hi = np.quantile(px, [1 - keep, keep])
    y_lo, y_hi = np.quantile(py, [1 - keep, keep])
    inside = (px >= x_lo) & (px <= x_hi) & (py >= y_lo) & (py <= y_hi)
    return px[inside], py[inside], value[inside]


def soft_mask(mask: np.ndarray, radius: float = 5.0) -> np.ndarray:
    """Feather the silhouette so the bust does not end on a hard cut line.

    The reference bust fades into the card instead of stopping at a contour;
    without this the shoulders read as a solid shelf.
    """
    image = Image.fromarray((mask * 255).astype(np.uint8))
    blurred = np.asarray(image.filter(ImageFilter.GaussianBlur(radius)), dtype=np.float32) / 255.0
    return np.clip(blurred * 1.7, 0.0, 1.0)


def sample_stratified(
    mask: np.ndarray,
    intensity: np.ndarray,
    *,
    cell: int = 2,
    jitter: float = 0.22,
    seed: int = 1,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Stratified sampling: an even sub-pixel grid inside the mask.

    Multinomial sampling leaves Poisson density noise, which reads as confetti
    once the bust is downscaled to the card. The reference art is a smooth
    luminous field, so every masked pixel is split into ``cell x cell`` slots
    with sub-slot jitter; brightness stays in the colour, coverage stays even.
    """
    ys, xs = np.where(mask)
    feather = soft_mask(mask)
    base = intensity[ys, xs] * np.clip(feather[ys, xs], 0.0, 1.0)

    rng = np.random.default_rng(seed)
    offsets = (np.arange(cell) + 0.5) / cell
    px: list[np.ndarray] = []
    py: list[np.ndarray] = []
    value: list[np.ndarray] = []
    for oy in offsets:
        for ox in offsets:
            px.append(xs + ox + rng.uniform(-jitter, jitter, xs.size) / cell)
            py.append(ys + oy + rng.uniform(-jitter, jitter, ys.size) / cell)
            value.append(base)
    return trim_outliers(np.concatenate(px), np.concatenate(py), np.concatenate(value))


def finish_cloud(
    px: np.ndarray,
    py: np.ndarray,
    value: np.ndarray,
    *,
    height: float,
    depth: tuple[float, float],
    fade_bottom: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    x0, x1 = px.min(), px.max()
    y0, y1 = py.min(), py.max()

    nx = (px - x0) / max(1.0, x1 - x0)
    ny = (py - y0) / max(1.0, y1 - y0)

    # Preserve the reference silhouette aspect: only the height is normalized,
    # width follows the source pixels.
    aspect = max(0.1, (x1 - x0) / max(1.0, y1 - y0))
    width = height * aspect

    world_x = (nx - 0.5) * width
    world_y = (0.5 - ny) * height + 0.08
    world_z = depth[0] + np.clip(value, 0.0, 1.0) ** 1.4 * (depth[1] - depth[0])

    color = colour_ramp(value)

    if fade_bottom > 0.0:
        # Additive blending makes dim particles disappear; use that instead of
        # an extra alpha channel so the binary format stays a simple 6 floats.
        edge = np.clip((ny - (1.0 - fade_bottom)) / fade_bottom, 0.0, 1.0)
        color = color * (1.0 - edge[:, None] * 0.92)

    cloud = np.concatenate(
        (world_x[:, None], world_y[:, None], world_z[:, None], color), axis=1
    ).astype(np.float32)

    rng = np.random.default_rng(seed)
    return cloud[rng.permutation(cloud.shape[0])]


def anatomical_male_depth(nx: np.ndarray, ny: np.ndarray, value: np.ndarray) -> np.ndarray:
    """True 3D anatomical relief for the male holographic bust.

    Instead of deriving depth purely from brightness (which flattens the face and
    causes neck tendons to jut out in front of the jaw), this models real human
    cranial and facial topography:
    * Cranial ellipsoid curving back to ears and temples
    * Nose bridge and tip projecting forward
    * Brow ridge framing sunken eye sockets
    * Defined lips and chin point
    * Recessed neck positioned naturally behind the jawline
    * Natural clavicle and upper chest curvature
    * Subtle surface micro-relief from local luminance
    """
    head_r_x, head_r_y, head_r_z = 0.28, 0.32, 0.26
    dy_head = (ny - 0.16) / head_r_y
    dx_head = nx / head_r_x
    r2 = dx_head**2 + dy_head**2
    in_head = ny > -0.15
    z_skull = np.where(in_head, np.sqrt(np.maximum(0.0, 1.0 - r2)) * head_r_z, 0.0)

    z_nose = (
        0.08 * np.exp(-(nx / 0.035)**2 - ((ny - 0.075) / 0.075)**2)
        + 0.12 * np.exp(-(nx / 0.04)**2 - ((ny - 0.02) / 0.035)**2)
    )
    z_brow = 0.045 * np.exp(-(nx / 0.15)**2 - ((ny - 0.16) / 0.035)**2)
    z_eyes = -0.055 * np.exp(-((np.abs(nx) - 0.09) / 0.04)**2 - ((ny - 0.12) / 0.035)**2)
    z_lips = 0.055 * np.exp(-(nx / 0.06)**2 - ((ny - (-0.03)) / 0.025)**2)
    z_chin = 0.065 * np.exp(-(nx / 0.055)**2 - ((ny - (-0.09)) / 0.04)**2)

    in_neck = (ny <= -0.12) & (ny > -0.28)
    neck_nx = np.clip(nx / 0.14, -1.0, 1.0)
    z_neck = np.where(in_neck, 0.06 + np.sqrt(np.maximum(0.0, 1.0 - neck_nx**2)) * 0.06, 0.0)

    in_torso = ny <= -0.28
    torso_nx = np.clip(np.abs(nx) / 0.48, 0.0, 1.0)
    z_torso = np.where(in_torso, 0.06 + (1.0 - torso_nx) * 0.10 + 0.03 * np.exp(-((ny - (-0.35)) / 0.08)**2), 0.0)

    z_base = np.where(in_head, z_skull, np.where(in_neck, z_neck, z_torso))
    z = z_base + z_nose + z_brow + z_eyes + z_lips + z_chin + (value - 0.2) * 0.04
    return np.clip(z, 0.02, 0.65).astype(np.float32)


def extract_male(target_count: int = 38000) -> np.ndarray:
    image = Image.open(MALE_TIMELINE).convert("RGB")
    # 5 x 5 storyboard, 2 seconds per cell. Row 4 / column 3 is the 46s frame:
    # the settled portrait with the clearest male facial landmarks.
    cell_w = image.size[0] / 5
    cell_h = image.size[1] / 5
    cell = image.crop((int(cell_w * 3), int(cell_h * 4), int(cell_w * 4), int(cell_h * 5)))

    # Exact bust crop inside the cell: perfectly centered 180x180 square covering
    # the hair crown down to the chest fade, excluding HUD labels and outer rings.
    crop = cell.crop((65, 18, 245, 198))
    data = np.asarray(crop, dtype=np.float32) / 255.0

    red, green, blue = data[..., 0], data[..., 1], data[..., 2]
    lum = data.mean(axis=2)
    blue_score = blue - (red + green) / 2.0

    # Mask foreground holographic material and reject dark background noise
    mask = (lum > 0.06) & ((blue_score > 0.01) | (lum > 0.18))
    gy, gx = np.gradient(lum)
    mag = np.hypot(gy, gx)

    # Local maxima detection for constellation nodes
    padded = np.pad(lum, 1, mode="edge")
    is_max = np.ones_like(lum, dtype=bool)
    for dy in [-1, 0, 1]:
        for dx in [-1, 0, 1]:
            if dy == 0 and dx == 0:
                continue
            is_max &= (lum >= padded[1 + dy : 1 + dy + lum.shape[0], 1 + dx : 1 + dx + lum.shape[1]])

    rng = np.random.default_rng(123)
    all_px, all_py, all_val = [], [], []

    # 1. Landmark & constellation nodes (bright facial and hair vertices)
    node_ys, node_xs = np.where(is_max & (lum > 0.18))
    all_px.append(node_xs.astype(np.float32))
    all_py.append(node_ys.astype(np.float32))
    all_val.append(np.clip(lum[node_ys, node_xs] * 1.30, 0.0, 1.0))

    # 2. Continuous ridge & contour filaments (dense sub-sampling along facial & hair ridges)
    ridge_ys, ridge_xs = np.where((mag > 0.07) & mask)
    for ox, oy in [(-0.25, -0.25), (0.25, 0.25), (-0.25, 0.25), (0.25, -0.25)]:
        jx = ox + rng.uniform(-0.12, 0.12, ridge_xs.size)
        jy = oy + rng.uniform(-0.12, 0.12, ridge_ys.size)
        all_px.append(ridge_xs + jx)
        all_py.append(ridge_ys + jy)
        all_val.append(np.clip(lum[ridge_ys, ridge_xs] * 1.15, 0.0, 1.0))

    # 3. Stratified volume fill with luminance-adaptive sampling density
    vol_ys, vol_xs = np.where(mask)
    for ox in [-0.25, 0.25]:
        for oy in [-0.25, 0.25]:
            p_keep = np.clip(lum[vol_ys, vol_xs] / 0.14, 0.30, 1.0)
            kept = rng.uniform(0.0, 1.0, vol_xs.size) < p_keep
            all_px.append(vol_xs[kept] + ox + rng.uniform(-0.15, 0.15, kept.sum()))
            all_py.append(vol_ys[kept] + oy + rng.uniform(-0.15, 0.15, kept.sum()))
            all_val.append(lum[vol_ys[kept], vol_xs[kept]])

    px = np.concatenate(all_px).astype(np.float32)
    py = np.concatenate(all_py).astype(np.float32)
    val = np.concatenate(all_val).astype(np.float32)

    # Subsample to exact target particle count
    if px.size > target_count:
        # Keep more of the eye, nose and mouth filaments at dashboard scale.
        face_detail = (py >= 45.0) & (py <= 112.0) & (np.abs(px - 90.0) <= 36.0)
        priority = np.where(face_detail, 2.0, 1.0)
        idx = rng.choice(px.size, target_count, replace=False, p=priority / priority.sum())
        px, py, val = px[idx], py[idx], val[idx]

    height = 2.40
    aspect = 1.0
    width = height * aspect

    nx = (px - 90.0) / 180.0
    ny = (90.0 - py) / 180.0

    world_x = nx * width
    world_y = ny * height + 0.08
    world_z = anatomical_male_depth(nx, ny, val)

    # Smooth chest fade at the base so the bust doesn't end abruptly
    fade_mask = np.clip((-ny - 0.30) / 0.20, 0.0, 1.0)
    color = colour_ramp(val) * (1.0 - fade_mask[:, None] * 0.90)

    cloud = np.concatenate(
        (world_x[:, None], world_y[:, None], world_z[:, None], color), axis=1
    ).astype(np.float32)
    order = rng.permutation(cloud.shape[0])
    print(f"male extracted={px.size} particles (target={target_count})")
    return cloud[order]


def extract_female() -> np.ndarray:
    image = Image.open(FEMALE_TIMELINE).convert("RGB")
    # Storyboard grid: 5 columns x 7 rows of 2-second frames. Row 4 / column 1 is
    # the 42s frame, the cleanest fully stabilised portrait of the character.
    cell_w = image.size[0] / 5
    cell_h = image.size[1] / 7
    cell = image.crop((int(cell_w), int(cell_h * 4), int(cell_w * 2), int(cell_h * 5)))

    # Bust crop inside the cell: hair left edge through the chest cut.
    crop = cell.crop((118, 26, 252, 146))
    data = np.asarray(crop).astype(np.float32) / 255.0

    red, green, blue = data[..., 0], data[..., 1], data[..., 2]
    lum = data.mean(axis=2)
    blue_score = blue - (red + green) / 2.0

    # Ring arcs and tick marks behind the character are dimmer than the bust.
    mask = (blue_score > 0.05) & (lum > 0.22)

    px, py, value = sample_stratified(mask, lum, cell=2, seed=31)
    print(f"female pixels={mask.sum()} samples={px.size}")

    return finish_cloud(
        px,
        py,
        np.clip((value - 0.12) * 1.4, 0.0, 1.0),
        height=2.44,
        depth=(0.02, 0.66),
        fade_bottom=0.22,
        seed=32,
    )


def write_bin(points: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<%df" % points.size, *points.ravel().tolist()))
    print(f"{path.name}: {points.shape[0]} particles, {path.stat().st_size} bytes")


def write_preview(points: np.ndarray, path: Path, size: int = 720) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    xmin, xmax = float(points[:, 0].min()), float(points[:, 0].max())
    ymin, ymax = float(points[:, 1].min()), float(points[:, 1].max())
    span = max(1e-6, xmax - xmin)
    height_span = max(1e-6, ymax - ymin)
    # Aspect-correct preview: the reference silhouettes are not square.
    width_px = max(1, int(size * span / height_span))
    canvas = np.zeros((size, width_px, 3), dtype=np.float32)
    px = ((points[:, 0] - xmin) / span * (width_px - 1)).astype(int)
    py = ((ymax - points[:, 1]) / height_span * (size - 1)).astype(int)
    keep = (px >= 0) & (px < width_px) & (py >= 0) & (py < size)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx = np.clip(px[keep] + dx, 0, width_px - 1)
            cy = np.clip(py[keep] + dy, 0, size - 1)
            weight = 0.26 if (dx or dy) else 1.0
            np.add.at(canvas, (cy, cx), points[keep, 3:6] * weight)
    canvas = np.clip(canvas, 0.0, 1.0)
    Image.fromarray((canvas * 255).astype(np.uint8)).save(path)
    print(f"preview: {path} ({width_px}x{size})")


if __name__ == "__main__":
    male = extract_male()
    female = extract_female()
    write_bin(male, PUBLIC / "avatar_male.bin")
    write_bin(female, PUBLIC / "avatar_female.bin")
    write_preview(male, PREVIEW_DIR / "avatar_male_preview.png")
    write_preview(female, PREVIEW_DIR / "avatar_female_preview.png")
