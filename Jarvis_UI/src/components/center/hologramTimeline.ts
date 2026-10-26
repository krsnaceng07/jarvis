import type { AssistantState } from '../../types/assistant';

/**
 * The reference storyboard is a one-way reveal: loose cloud -> scan sweep ->
 * stable portrait. It then holds that portrait for the whole onboarding step.
 *
 * Running that dissolve on a loop (the previous 12s cycle) read as a broken
 * hologram instead of a character, so the reveal now plays once on mount and
 * once per character switch, and never during idle.
 */
export const REVEAL_SECONDS = 3.4;
export const DISSOLVE_SECONDS = 0.9;
export const HOLOGRAM_CYCLE_SECONDS = REVEAL_SECONDS;

/** Scan plane travel, in bust-local units (bust spans roughly -1.25..1.25). */
export const BAND_START_Y = -1.55;
export const BAND_END_Y = 1.55;
const BAND_SWEEP_START = 0.55;
const BAND_SWEEP_END = 2.95;

export type HologramPhaseName = 'materialising' | 'settling' | 'idle';

export interface HologramSample {
  phase: HologramPhaseName;
  /** 0..1 through the reveal. */
  progress: number;
  /** 0 = fully formed, 1 = fully broken apart. */
  scatter: number;
  turbulence: number;
  brightness: number;
  bandY: number;
  bandStrength: number;
  /** Whether the scan gate is still deciding which particles exist. */
  bandActive: boolean;
}

/**
 * Live energy per assistant state. Kept as shimmer only: the character identity
 * never breaks down because JARVIS is thinking or running a tool.
 */
const STATE_ENERGY: Record<AssistantState, number> = {
  idle: 0,
  listening: 0.3,
  transcribing: 0.45,
  thinking: 0.7,
  speaking: 0.5,
  tool_running: 0.85,
  waiting_for_permission: 0.15,
  cancelling: 0.55,
  cancelled: 0.25,
  disconnected: 0.1,
  error: 0.9,
};

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function smootherstep(t: number): number {
  return t * t * t * (t * (t * 6 - 15) + 10);
}

export function normalizeCycleTime(time: number): number {
  const cycle = time % HOLOGRAM_CYCLE_SECONDS;
  return cycle < 0 ? cycle + HOLOGRAM_CYCLE_SECONDS : cycle;
}

/**
 * Deterministic frame sample. Same (seconds, state) always yields the same
 * numbers, which is what the debug scrubber and the comparison captures use.
 */
export function sampleHologramTimeline(
  seconds: number,
  state: AssistantState = 'idle',
): HologramSample {
  const t = Math.max(0, seconds);
  const energy = STATE_ENERGY[state];

  if (t >= REVEAL_SECONDS) {
    return {
      phase: 'idle',
      progress: 1,
      scatter: 0,
      turbulence: 0.32 + energy * 0.5,
      brightness: 1 + energy * 0.05,
      bandY: BAND_END_Y,
      bandStrength: 0,
      bandActive: false,
    };
  }

  const sweep = clamp01((t - BAND_SWEEP_START) / (BAND_SWEEP_END - BAND_SWEEP_START));
  const bandY = lerp(BAND_START_Y, BAND_END_Y, smootherstep(sweep));

  // The band fades in just before it enters the bust and out after it leaves.
  const rampIn = clamp01((t - (BAND_SWEEP_START - 0.25)) / 0.25);
  const rampOut = clamp01((REVEAL_SECONDS - t) / (REVEAL_SECONDS - BAND_SWEEP_END));
  const bandStrength = Math.min(rampIn, rampOut);

  // Scatter stays fully broken while the band does the per-particle forming;
  // dimming it early would let the head assemble before the scan reaches it.
  const scatter = t < BAND_SWEEP_END ? 1 : 1 - smootherstep((t - BAND_SWEEP_END) / (REVEAL_SECONDS - BAND_SWEEP_END));

  const haze = 1 - sweep;
  const turbulence = lerp(1.55, 0.32, smootherstep(clamp01(t / BAND_SWEEP_END))) + energy * 0.4;
  const brightness = lerp(0.82, 1.02, smootherstep(clamp01(t / (REVEAL_SECONDS * 0.85)))) + energy * 0.04;

  return {
    phase: t < BAND_SWEEP_END ? 'materialising' : 'settling',
    progress: clamp01(t / REVEAL_SECONDS),
    scatter,
    turbulence: turbulence + haze * 0.15,
    brightness,
    bandY,
    bandStrength,
    bandActive: true,
  };
}

/** Dissolve curve used when switching characters: the bust breaks apart first. */
export function sampleDissolve(seconds: number): { progress: number; scatter: number; brightness: number } {
  const progress = clamp01(seconds / DISSOLVE_SECONDS);
  const eased = smootherstep(progress);
  return { progress, scatter: eased, brightness: 1 - 0.42 * eased };
}
