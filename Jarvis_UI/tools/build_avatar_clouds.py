"""Bake holographic bust point clouds for the character switcher.

The renderer only needs a flat Float32 stream of ``x y z r g b`` per particle.
Both characters are generated in the same world space so the WebGL framing
math stays identical: the male cloud is a 2.5D relief of the supplied render,
the female cloud is a procedural bust (head, neck, shoulders, long hair)
sampled on its visible front surface.

Run from ``Jarvis_UI``:
    python tools/build_avatar_clouds.py
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

# Female bust extents in renderer world units (y up, z toward camera).
X_MIN, X_MAX = -1.50, 1.50
Y_MIN, Y_MAX = -1.12, 1.30
Z_START, Z_END = 1.05, -0.30
STEP = 0.0095


def smooth_min(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1.0 - h) + a * h - k * h * (1.0 - h)


def ellipsoid(
    x: np.ndarray, y: np.ndarray, z: np.ndarray,
    cx: float, cy: float, cz: float,
    rx: float, ry: float, rz: float,
) -> np.ndarray:
    scaled = np.stack(((x - cx) / rx, (y - cy) / ry, (z - cz) / rz), axis=-1)
    k = np.linalg.norm(scaled, axis=-1)
    return (k - 1.0) * min(rx, ry, rz)


def capsule(
    x: np.ndarray, y: np.ndarray, z: np.ndarray,
    ax: float, ay: float, az: float,
    bx: float, by: float, bz: float,
    radius: float,
) -> np.ndarray:
    abx, aby, abz = bx - ax, by - ay, bz - az
    apx, apy, apz = x - ax, y - ay, z - az
    denom = abx * abx + aby * aby + abz * abz
    t = np.clip((apx * abx + apy * aby + apz * abz) / denom, 0.0, 1.0)
    qx = apx - abx * t
    qy = apy - aby * t
    qz = apz - abz * t
    return np.sqrt(qx * qx + qy * qy + qz * qz) - radius


def rounded_box(
    x: np.ndarray, y: np.ndarray, z: np.ndarray,
    cx: float, cy: float, cz: float,
    hx: float, hy: float, hz: float,
    rounding: float,
) -> np.ndarray:
    qx = np.abs(x - cx) - hx + rounding
    qy = np.abs(y - cy) - hy + rounding
    qz = np.abs(z - cz) - hz + rounding
    outside = np.sqrt(
        np.maximum(qx, 0.0) ** 2
        + np.maximum(qy, 0.0) ** 2
        + np.maximum(qz, 0.0) ** 2
    )
    inside = np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0.0)
    return outside + inside - rounding


def body_sdf(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Face, neck and shoulders (the skin surface)."""
    skull = ellipsoid(x, y, z, 0.0, 0.80, 0.06, 0.335, 0.40, 0.36)
    jaw = ellipsoid(x, y, z, 0.0, 0.52, 0.10, 0.245, 0.25, 0.31)
    head = smooth_min(skull, jaw, 0.12)

    cheek_l = ellipsoid(x, y, z, -0.185, 0.60, 0.24, 0.125, 0.115, 0.135)
    cheek_r = ellipsoid(x, y, z, 0.185, 0.60, 0.24, 0.125, 0.115, 0.135)
    head = smooth_min(head, cheek_l, 0.08)
    head = smooth_min(head, cheek_r, 0.08)

    chin = ellipsoid(x, y, z, 0.0, 0.415, 0.27, 0.105, 0.095, 0.105)
    head = smooth_min(head, chin, 0.06)

    brow = capsule(x, y, z, -0.155, 0.775, 0.335, 0.155, 0.775, 0.335, 0.036)
    head = smooth_min(head, brow, 0.04)

    bridge = capsule(x, y, z, 0.0, 0.745, 0.345, 0.0, 0.605, 0.405, 0.042)
    nose_tip = ellipsoid(x, y, z, 0.0, 0.575, 0.42, 0.062, 0.05, 0.065)
    head = smooth_min(head, bridge, 0.025)
    head = smooth_min(head, nose_tip, 0.02)

    lips = ellipsoid(x, y, z, 0.0, 0.485, 0.375, 0.095, 0.042, 0.055)
    head = smooth_min(head, lips, 0.015)

    socket_l = ellipsoid(x, y, z, -0.125, 0.675, 0.385, 0.078, 0.052, 0.075)
    socket_r = ellipsoid(x, y, z, 0.125, 0.675, 0.385, 0.078, 0.052, 0.075)
    head = np.maximum(head, -socket_l)
    head = np.maximum(head, -socket_r)

    neck = capsule(x, y, z, 0.0, 0.52, 0.02, 0.0, 0.20, 0.0, 0.128)

    torso = rounded_box(x, y, z, 0.0, -0.76, 0.0, 0.84, 0.44, 0.27, 0.24)
    shoulder_l = capsule(x, y, z, -0.10, 0.04, 0.0, -1.23, -0.58, 0.0, 0.205)
    shoulder_r = capsule(x, y, z, 0.10, 0.04, 0.0, 1.23, -0.58, 0.0, 0.205)
    torso = smooth_min(torso, shoulder_l, 0.20)
    torso = smooth_min(torso, shoulder_r, 0.20)

    clavicle = capsule(x, y, z, -0.40, -0.03, 0.215, 0.40, -0.03, 0.215, 0.04)
    torso = smooth_min(torso, clavicle, 0.06)

    body = smooth_min(head, neck, 0.08)
    body = smooth_min(body, torso, 0.09)
    return body


def hair_sdf(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Long hair shell that frames the face and falls over the shoulders."""
    cap = ellipsoid(x, y, z, 0.0, 0.82, -0.01, 0.405, 0.465, 0.40)
    back = ellipsoid(x, y, z, 0.0, 0.18, -0.26, 0.46, 0.62, 0.14)
    fall_l = capsule(x, y, z, -0.35, 0.72, 0.0, -0.47, -0.52, 0.05, 0.145)
    fall_r = capsule(x, y, z, 0.35, 0.72, 0.0, 0.47, -0.52, 0.05, 0.145)
    inner_l = capsule(x, y, z, -0.28, 0.60, -0.09, -0.38, -0.70, -0.02, 0.115)
    inner_r = capsule(x, y, z, 0.28, 0.60, -0.09, 0.38, -0.70, -0.02, 0.115)

    hair = smooth_min(cap, back, 0.10)
    hair = smooth_min(hair, fall_l, 0.07)
    hair = smooth_min(hair, fall_r, 0.07)
    hair = smooth_min(hair, inner_l, 0.05)
    hair = smooth_min(hair, inner_r, 0.05)

    angle = np.arctan2(x + 1e-6, z + 1e-6)
    hair = hair + 0.010 * np.sin(angle * 24.0 + y * 3.6)

    face_window = ellipsoid(x, y, z, 0.0, 0.64, 0.44, 0.275, 0.35, 0.30)
    return np.maximum(hair, -face_window)


def combined_sdf(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    return np.minimum(
        body_sdf(x, y, z),
        hair_sdf(x, y, z),
    )


def front_surface() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    xs = np.arange(X_MIN, X_MAX, STEP)
    ys = np.arange(Y_MIN, Y_MAX, STEP)
    gx, gy = np.meshgrid(xs, ys)
    flat_x = gx.ravel()
    flat_y = gy.ravel()

    hit_z = np.full(flat_x.shape, np.nan)
    for z in np.arange(Z_START, Z_END, -0.007):
        values = combined_sdf(flat_x, flat_y, np.full_like(flat_x, z))
        newly_inside = (values <= 0.0) & np.isnan(hit_z)
        hit_z[newly_inside] = z
        if np.all(~np.isnan(hit_z)):
            break

    valid = ~np.isnan(hit_z)
    x = flat_x[valid]
    y = flat_y[valid]
    z = hit_z[valid]
    is_hair = hair_sdf(x, y, z) < body_sdf(x, y, z)
    return x, y, z, is_hair


def normals(x: np.ndarray, y: np.ndarray, z: np.ndarray, eps: float = 0.005) -> np.ndarray:
    dx = combined_sdf(x + eps, y, z) - combined_sdf(x - eps, y, z)
    dy = combined_sdf(x, y + eps, z) - combined_sdf(x, y - eps, z)
    dz = combined_sdf(x, y, z + eps) - combined_sdf(x, y, z - eps)
    n = np.stack((dx, dy, dz), axis=-1)
    return n / (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9)


def build_female(target: int = 24000, seed: int = 7) -> np.ndarray:
    x, y, z, is_hair = front_surface()
    rng = np.random.default_rng(seed)

    keep = min(target, x.size)
    idx = rng.choice(x.size, size=keep, replace=False)
    x, y, z, is_hair = x[idx], y[idx], z[idx], is_hair[idx]

    x = x + rng.normal(0.0, STEP * 0.32, x.size)
    y = y + rng.normal(0.0, STEP * 0.32, y.size)
    z = z + rng.normal(0.0, 0.0035, z.size)

    n = normals(x, y, z)
    light = np.array([-0.42, 0.55, 0.72], dtype=np.float64)
    light /= np.linalg.norm(light)
    lambert = np.clip(n @ light, 0.0, 1.0)
    rim = np.power(1.0 - np.abs(n[:, 2]), 2.6)

    shade = np.clip(0.28 + 0.80 * np.power(lambert, 1.3) + 0.45 * rim, 0.0, 1.22)
    shade = np.where(is_hair, shade * 0.80, shade)

    deep = np.array([0.008, 0.205, 0.360])
    mid = np.array([0.055, 0.690, 0.880])
    bright = np.array([0.800, 0.975, 1.000])

    t = np.clip(shade, 0.0, 1.0)
    color = np.where(
        t[:, None] < 0.55,
        deep + (mid - deep) * (t[:, None] / 0.55),
        mid + (bright - mid) * ((t[:, None] - 0.55) / 0.45),
    )
    color = np.clip(color, 0.0, 1.0)

    cloud = np.concatenate((x[:, None], y[:, None], z[:, None], color), axis=1)
    order = rng.permutation(cloud.shape[0])
    return cloud[order].astype(np.float32)


def write_bin(points: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(struct.pack("<%df" % points.size, *points.ravel().tolist()))
    print(f"{path.name}: {points.shape[0]} particles, {path.stat().st_size} bytes")


def write_preview(points: np.ndarray, path: Path, size: int = 720) -> None:
    from PIL import Image

    canvas = np.zeros((size, size, 3), dtype=np.float32)
    px = ((points[:, 0] - X_MIN) / (X_MAX - X_MIN) * (size - 1)).astype(int)
    py = ((Y_MAX - points[:, 1]) / (Y_MAX - Y_MIN) * (size - 1)).astype(int)
    keep = (px >= 0) & (px < size) & (py >= 0) & (py < size)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            cx = np.clip(px[keep] + dx, 0, size - 1)
            cy = np.clip(py[keep] + dy, 0, size - 1)
            weight = 0.30 if (dx or dy) else 1.0
            canvas[cy, cx] += points[keep, 3:6] * weight
    canvas = np.clip(canvas, 0.0, 1.0)
    Image.fromarray((canvas * 255).astype(np.uint8)).save(path)
    print(f"preview: {path}")


def ascii_preview(points: np.ndarray, cols: int = 60, rows: int = 34) -> None:
    img = np.zeros((rows, cols), dtype=np.float32)
    px = ((points[:, 0] - X_MIN) / (X_MAX - X_MIN) * (cols - 1)).astype(int)
    py = ((Y_MAX - points[:, 1]) / (Y_MAX - Y_MIN) * (rows - 1)).astype(int)
    np.add.at(img, (py, px), 1.0)
    chars = " .:-=+*#%@"
    peak = max(1.0, np.percentile(img, 99))
    for row in img:
        print("".join(chars[min(9, int(v / peak * 9.99))] for v in row))


if __name__ == "__main__":
    female = build_female()
    write_bin(female, PUBLIC / "avatar_female.bin")
    write_preview(female, ROOT / "avatar_female_preview.png")
    ascii_preview(female)
