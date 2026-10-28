import femalePortraitUrl from '../../assets/female.png';
import malePortraitUrl from '../../assets/male.png';

export const PARTICLE_COUNT = 60_000;
export const MORPH_DURATION = 2.0;
export const SCAN_DELAY = 1.0;
export const SCAN_DURATION = 1.0;
export const SCAN_TOP = 0.88;
export const SCAN_BOTTOM = -0.78;
export const LUMINANCE_THRESHOLD = 0.05;
export const LUMINANCE_EXPONENT = 1.3;
export const MALE_LUMINANCE_EXPONENT = 0.75;
export const FEMALE_CHEST_EDGE_Y = 850;
export const FEMALE_CHEST_FADE_PX = 40;
export const BURST_STRENGTH = 1.25;
export const SWIRL_STRENGTH = 2.5;
export const SWIRL_BIAS = 1.2;
export const DIAGONAL_STREAK_WIDTH = 0.11;
export const STREAK_BRIGHTNESS = 1.75;
export const PARTICLE_SIZE_MIN = 0.6;
export const PARTICLE_SIZE_MAX = 1.6;
export const IDLE_JITTER = 0.003;
export const SCAN_BAND_WIDTH = 0.06;
export const FEMALE_OPACITY = 0.24;
export const MALE_OPACITY = 0.18;

const FEMALE_COLOR_GAIN = [0.52, 0.86, 1.15] as const;
const MALE_COLOR_GAIN = [0.42, 0.76, 1.24] as const;
const PORTRAIT_BOUNDS_PERCENTILE = 0.01;
const SOURCE_MOUTH = {
  female: [0.637, 0.552],
  male: [0.601, 0.522],
} as const;

export interface ParticleMorphData {
  femalePositions: Float32Array;
  malePositions: Float32Array;
  femaleColors: Float32Array;
  maleColors: Float32Array;
  femaleMouth: readonly [number, number];
  maleMouth: readonly [number, number];
  seeds: Float32Array;
  sizes: Float32Array;
  count: number;
}

interface SampledPortrait {
  positions: Float32Array;
  colors: Float32Array;
  frame: PortraitFrame;
}

interface PortraitFrame {
  centerX: number;
  centerY: number;
  height: number;
}

type PortraitGender = 'female' | 'male';

function mulberry32(seed: number): () => number {
  let value = seed >>> 0;
  return () => {
    value = (value + 0x6d2b79f5) >>> 0;
    let result = Math.imul(value ^ (value >>> 15), 1 | value);
    result = (result + Math.imul(result ^ (result >>> 7), 61 | result)) ^ result;
    return ((result ^ (result >>> 14)) >>> 0) / 4294967296;
  };
}

function loadImageData(url: string): Promise<ImageData> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      if (!context) {
        reject(new Error('Could not create a 2D context for the portrait image'));
        return;
      }
      context.drawImage(image, 0, 0);
      resolve(context.getImageData(0, 0, canvas.width, canvas.height));
    };
    image.onerror = () => reject(new Error(`Could not load portrait source: ${url}`));
    image.src = url;
  });
}

function luminanceAt(data: Uint8ClampedArray, pixel: number): number {
  const offset = pixel * 4;
  return (0.2126 * data[offset] + 0.7152 * data[offset + 1] + 0.0722 * data[offset + 2]) / 255;
}

function particleWeight(gender: PortraitGender, luminance: number, y: number, height: number): number {
  if (luminance <= LUMINANCE_THRESHOLD) return 0;
  // The male source is dimmer, so retain more of its face midtones without changing the female portrait.
  const exponent = gender === 'male' ? MALE_LUMINANCE_EXPONENT : LUMINANCE_EXPONENT;
  let weight = luminance ** exponent;
  if (gender === 'female') {
    const scale = height / 1024;
    const fadeStart = (FEMALE_CHEST_EDGE_Y - FEMALE_CHEST_FADE_PX) * scale;
    const fadeEnd = FEMALE_CHEST_EDGE_Y * scale;
    if (y >= fadeEnd) return 0;
    if (y > fadeStart) weight *= (fadeEnd - y) / (fadeEnd - fadeStart);
  }
  return weight;
}

function histogramPercentile(histogram: Uint32Array, total: number, percentile: number): number {
  const target = Math.floor((total - 1) * percentile);
  let cumulative = 0;
  for (let coordinate = 0; coordinate < histogram.length; coordinate += 1) {
    cumulative += histogram[coordinate];
    if (cumulative > target) return coordinate;
  }
  return histogram.length - 1;
}

function samplePortrait(image: ImageData, gender: PortraitGender, seed: number): SampledPortrait {
  const { data, width, height } = image;
  const candidates = new Uint32Array(width * height);
  const xHistogram = new Uint32Array(width);
  const yHistogram = new Uint32Array(height);
  let candidateCount = 0;
  let maxWeight = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const pixel = y * width + x;
      const weight = particleWeight(gender, luminanceAt(data, pixel), y, height);
      if (weight <= 0) continue;
      candidates[candidateCount] = pixel;
      candidateCount += 1;
      xHistogram[x] += 1;
      yHistogram[y] += 1;
      maxWeight = Math.max(maxWeight, weight);
    }
  }
  if (candidateCount === 0 || maxWeight === 0) {
    throw new Error(`The ${gender} portrait has no pixels above the luminance threshold`);
  }

  const random = mulberry32(seed);
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const colors = new Float32Array(PARTICLE_COUNT * 3);
  const gains = gender === 'female' ? FEMALE_COLOR_GAIN : MALE_COLOR_GAIN;
  let written = 0;
  let attempts = 0;
  const attemptLimit = PARTICLE_COUNT * 160;
  while (written < PARTICLE_COUNT && attempts < attemptLimit) {
    attempts += 1;
    const pixel = candidates[Math.floor(random() * candidateCount)];
    const y = Math.floor(pixel / width);
    const x = pixel - y * width;
    const luminance = luminanceAt(data, pixel);
    const weight = particleWeight(gender, luminance, y, height);
    if (random() * maxWeight > weight) continue;

    const source = pixel * 4;
    const target = written * 3;
    positions[target] = (x / (width - 1)) * 2 - 1;
    positions[target + 1] = 1 - (y / (height - 1)) * 2;
    positions[target + 2] = (random() - 0.5) * 0.1;
    colors[target] = Math.min(1, (data[source] / 255) * gains[0]);
    colors[target + 1] = Math.min(1, (data[source + 1] / 255) * gains[1]);
    colors[target + 2] = Math.min(1, (data[source + 2] / 255) * gains[2]);
    written += 1;
  }
  if (written !== PARTICLE_COUNT) {
    throw new Error(`Could only sample ${written} of ${PARTICLE_COUNT} ${gender} particles`);
  }

  const xLow = histogramPercentile(xHistogram, candidateCount, PORTRAIT_BOUNDS_PERCENTILE);
  const xHigh = histogramPercentile(xHistogram, candidateCount, 1 - PORTRAIT_BOUNDS_PERCENTILE);
  const yLow = histogramPercentile(yHistogram, candidateCount, PORTRAIT_BOUNDS_PERCENTILE);
  const yHigh = histogramPercentile(yHistogram, candidateCount, 1 - PORTRAIT_BOUNDS_PERCENTILE);
  return {
    positions,
    colors,
    frame: {
      centerX: ((xLow + xHigh) / (width - 1)) - 1,
      centerY: 1 - ((yLow + yHigh) / (height - 1)),
      height: 2 * (yHigh - yLow) / (height - 1),
    },
  };
}

function alignPortrait(portrait: SampledPortrait, scale: number): void {
  for (let index = 0; index < PARTICLE_COUNT; index += 1) {
    const offset = index * 3;
    portrait.positions[offset] = (portrait.positions[offset] - portrait.frame.centerX) * scale;
    portrait.positions[offset + 1] = (portrait.positions[offset + 1] - portrait.frame.centerY) * scale;
  }
}

function mouthAnchor(gender: PortraitGender, frame: PortraitFrame, scale: number): readonly [number, number] {
  const [xFraction, yFraction] = SOURCE_MOUTH[gender];
  const sourceX = xFraction * 2 - 1;
  const sourceY = 1 - yFraction * 2;
  return [(sourceX - frame.centerX) * scale, (sourceY - frame.centerY) * scale];
}

function pairPortraits(female: SampledPortrait, male: SampledPortrait): ParticleMorphData {
  const maleScale = female.frame.height / male.frame.height;
  alignPortrait(female, 1);
  alignPortrait(male, maleScale);

  const permutation = new Uint32Array(PARTICLE_COUNT);
  for (let i = 0; i < PARTICLE_COUNT; i += 1) permutation[i] = i;
  const random = mulberry32(0xc001d00d);
  for (let i = PARTICLE_COUNT - 1; i > 0; i -= 1) {
    const swap = Math.floor(random() * (i + 1));
    [permutation[i], permutation[swap]] = [permutation[swap], permutation[i]];
  }

  const femalePositions = new Float32Array(PARTICLE_COUNT * 3);
  const malePositions = new Float32Array(PARTICLE_COUNT * 3);
  const femaleColors = new Float32Array(PARTICLE_COUNT * 3);
  const maleColors = new Float32Array(PARTICLE_COUNT * 3);
  const seeds = new Float32Array(PARTICLE_COUNT);
  const sizes = new Float32Array(PARTICLE_COUNT);
  for (let i = 0; i < PARTICLE_COUNT; i += 1) {
    const from = permutation[i] * 3;
    const to = i * 3;
    femalePositions.set(female.positions.subarray(from, from + 3), to);
    malePositions.set(male.positions.subarray(from, from + 3), to);
    femaleColors.set(female.colors.subarray(from, from + 3), to);
    maleColors.set(male.colors.subarray(from, from + 3), to);
    seeds[i] = random();
    sizes[i] = PARTICLE_SIZE_MIN + random() * (PARTICLE_SIZE_MAX - PARTICLE_SIZE_MIN);
  }
  return {
    femalePositions,
    malePositions,
    femaleColors,
    maleColors,
    femaleMouth: mouthAnchor('female', female.frame, 1),
    maleMouth: mouthAnchor('male', male.frame, maleScale),
    seeds,
    sizes,
    count: PARTICLE_COUNT,
  };
}

let particleDataPromise: Promise<ParticleMorphData> | null = null;

export function loadParticlePortraitData(): Promise<ParticleMorphData> {
  if (!particleDataPromise) {
    particleDataPromise = Promise.all([loadImageData(femalePortraitUrl), loadImageData(malePortraitUrl)])
      .then(([femaleImage, maleImage]) =>
        pairPortraits(
          samplePortrait(femaleImage, 'female', 0x51ed270b),
          samplePortrait(maleImage, 'male', 0x2545f491),
        ),
      )
      .catch((error: unknown) => {
        particleDataPromise = null;
        throw error;
      });
  }
  return particleDataPromise;
}

