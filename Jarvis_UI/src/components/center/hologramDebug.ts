/**
 * Dev-only calibration state. The renderer reads this object every frame, so the
 * debug panel can scrub and override without re-mounting the WebGL scene.
 * Disabled entirely outside `?holo=debug` in a dev build.
 */
export interface HologramDebugState {
  enabled: boolean;
  panel: boolean;
  paused: boolean;
  time: number;
  dispersion: number | null;
  turbulence: number | null;
  brightness: number | null;
  speech: number | null;
  /** Sprite size / opacity overrides so capture tooling can sweep calibration. */
  size: number | null;
  opacity: number | null;
  /** Hide rings/embers so captures can be measured against the bust alone. */
  hud: boolean | null;
  /**
   * One-shot: the next rendered frame is dumped to `window.__jarvisFrame` as
   * raw RGBA. Canvas pixels bypass the screenshot path entirely, and
   * `toDataURL` returns empty for dim additive frames, so raw readback it is.
   */
  capture: boolean;
}

const params = typeof window === 'undefined' ? null : new URLSearchParams(window.location.search);

export const hologramDebug: HologramDebugState = {
  enabled: Boolean(params?.has('holo')) && import.meta.env.DEV,
  panel: true,
  paused: false,
  time: 0,
  dispersion: null,
  turbulence: null,
  brightness: null,
  speech: null,
  size: null,
  opacity: null,
  hud: null,
  capture: false,
};

// Capture tooling drives the same object; exposing it keeps frame comparison
// deterministic instead of hoping a screenshot lands mid-dispersion.
if (hologramDebug.enabled && typeof window !== 'undefined') {
  (window as unknown as { __jarvisHologram?: HologramDebugState }).__jarvisHologram = hologramDebug;
}
