import type { CharacterAppearance } from '../../types/modules';

/** One baked bust: anchor points, per-point colour, and per-point dispersion target. */
export interface AvatarCloud {
  positions: Float32Array;
  colors: Float32Array;
  scatter: Float32Array;
  count: number;
  min: readonly [number, number, number];
  max: readonly [number, number, number];
}

export const CLOUD_URLS: Record<CharacterAppearance, string> = {
  male: '/avatar_male.bin',
  female: '/avatar_female.bin',
};

/** Small deterministic PRNG so every session disperses the same cloud the same way. */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Scatter amplitudes are the full-breakup curve from the reference: at peak the
 * particles leave the bust entirely and fill the HUD, then converge back.
 */
const SCATTER_MIN = 0.12;
const SCATTER_RANGE = 1.05;
const SCATTER_SWIRL = 0.32;
const SCATTER_DEPTH = 0.7;

export function buildCloud(data: Float32Array, seed = 0x5f3759df): AvatarCloud {
  const count = Math.floor(data.length / 6);
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const scatter = new Float32Array(count * 3);

  let cx = 0;
  let cy = 0;
  let cz = 0;
  let minX = Infinity;
  let minY = Infinity;
  let minZ = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let maxZ = -Infinity;

  for (let i = 0; i < count; i += 1) {
    const s = i * 6;
    const d = i * 3;
    const x = data[s];
    const y = data[s + 1];
    const z = data[s + 2];

    positions[d] = x;
    positions[d + 1] = y;
    positions[d + 2] = z;

    colors[d] = data[s + 3];
    colors[d + 1] = data[s + 4];
    colors[d + 2] = data[s + 5];

    cx += x;
    cy += y;
    cz += z;

    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    minZ = Math.min(minZ, z);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
    maxZ = Math.max(maxZ, z);
  }

  const inv = count > 0 ? 1 / count : 0;
  cx *= inv;
  cy *= inv;
  cz *= inv;

  const rand = mulberry32(seed);
  for (let i = 0; i < count; i += 1) {
    const d = i * 3;
    const dx = positions[d] - cx;
    const dy = positions[d + 1] - cy;
    const dz = positions[d + 2] - cz;
    const len = Math.hypot(dx, dy, dz) || 1;
    const nx = dx / len;
    const ny = dy / len;
    const nz = dz / len;

    // Radial push plus an in-plane swirl keeps the cloud volumetric instead of
    // letting it grow into a hollow sphere.
    const magnitude = SCATTER_MIN + Math.pow(rand(), 1.45) * SCATTER_RANGE;
    const swirl = (rand() - 0.5) * 2 * SCATTER_SWIRL * magnitude;
    const rise = ny > 0.2 ? rand() * 0.12 : 0;

    scatter[d] = nx * magnitude - ny * swirl;
    scatter[d + 1] = ny * magnitude + nx * swirl + rise;
    scatter[d + 2] = nz * magnitude * SCATTER_DEPTH;
  }

  return {
    positions,
    colors,
    scatter,
    count,
    min: [minX, minY, minZ],
    max: [maxX, maxY, maxZ],
  };
}

export interface FaceAnchors {
  x: number;
  headY: number;
  mouthY: number;
}

/**
 * Derive the face rig from the baked cloud instead of hard-coding offsets. The
 * brightest cluster in the upper half is the face; it anchors the mouth and the
 * neck pivot, so both characters share one shader rig.
 */
export function computeFaceAnchors(cloud: AvatarCloud): FaceAnchors {
  const top = cloud.max[1];
  const bottom = cloud.min[1];
  const height = Math.max(0.001, top - bottom);
  const band = bottom + height * 0.55;

  let sum = 0;
  let weightedX = 0;
  let weightedY = 0;

  for (let i = 0; i < cloud.count; i += 1) {
    const d = i * 3;
    const y = cloud.positions[d + 1];
    if (y < band) continue;
    const luminance = (cloud.colors[d] + cloud.colors[d + 1] + cloud.colors[d + 2]) / 3;
    const weight = luminance ** 3;
    sum += weight;
    weightedX += cloud.positions[d] * weight;
    weightedY += y * weight;
  }

  if (sum <= 0) {
    return { x: 0, headY: band, mouthY: band + height * 0.08 };
  }

  const faceX = weightedX / sum;
  const eyeY = weightedY / sum;
  const headHeight = Math.max(height * 0.2, 2 * (top - eyeY));

  return {
    x: faceX,
    headY: top - headHeight,
    // 30% of head height below the eye line lands on the mouth/lower jaw for both
    // busts; the shader deforms a soft ellipse around this point.
    mouthY: eyeY - 0.3 * headHeight,
  };
}
