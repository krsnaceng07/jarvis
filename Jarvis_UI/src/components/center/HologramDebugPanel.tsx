import React, { useEffect, useState } from 'react';

import { hologramDebug } from './hologramDebug';
import { HOLOGRAM_CYCLE_SECONDS, sampleHologramTimeline } from './hologramTimeline';

/**
 * Dev-only calibration strip (`?holo=debug` in a dev build). Production never
 * mounts it, so the reference composition stays clean.
 */
export const HologramDebugPanel: React.FC = () => {
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!hologramDebug.enabled) return;
    const id = window.setInterval(() => setTick((n) => n + 1), 150);
    return () => window.clearInterval(id);
  }, []);

  if (!hologramDebug.enabled || !hologramDebug.panel) return null;

  const phase = sampleHologramTimeline(hologramDebug.time);
  const elapsed = hologramDebug.time.toFixed(2);

  return (
    <div className="fixed bottom-3 left-3 z-50 w-[176px] space-y-1.5 rounded border border-[#1c4650] bg-[#03080c]/95 p-2 font-mono text-[9px] text-slate-300 shadow-[0_0_18px_rgba(0,0,0,0.6)]">
      <div className="flex items-center justify-between text-[8px] uppercase tracking-[0.18em] text-cyan-300">
        <span>holo debug</span>
        <span className="text-slate-500">{elapsed}s</span>
      </div>

      <div className="text-[8px] uppercase tracking-[0.16em] text-slate-500">
        {phase.phase}
      </div>

      <label className="block">
        <span className="flex justify-between text-slate-400">
          <span>timeline</span>
          <span>{elapsed}s</span>
        </span>
        <input
          type="range"
          min={0}
          max={HOLOGRAM_CYCLE_SECONDS}
          step={0.02}
          value={hologramDebug.time}
          onChange={(event) => {
            hologramDebug.time = Number(event.target.value);
            hologramDebug.paused = true;
          }}
          className="w-full accent-cyan-400"
        />
      </label>

      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => {
            hologramDebug.paused = !hologramDebug.paused;
          }}
          className="flex-1 rounded border border-[#1c4650] px-1 py-0.5 text-[8px] uppercase tracking-[0.12em] hover:text-cyan-200"
        >
          {hologramDebug.paused ? 'play' : 'pause'}
        </button>
        <button
          type="button"
          onClick={() => {
            hologramDebug.dispersion = null;
            hologramDebug.turbulence = null;
            hologramDebug.brightness = null;
            hologramDebug.speech = null;
          }}
          className="flex-1 rounded border border-[#1c4650] px-1 py-0.5 text-[8px] uppercase tracking-[0.12em] hover:text-cyan-200"
        >
          auto
        </button>
      </div>

      <label className="block">
        <span className="flex justify-between text-slate-400">
          <span>dispersion</span>
          <span>{hologramDebug.dispersion === null ? 'auto' : hologramDebug.dispersion.toFixed(2)}</span>
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={hologramDebug.dispersion ?? 0}
          onChange={(event) => {
            hologramDebug.dispersion = Number(event.target.value);
          }}
          className="w-full accent-cyan-400"
        />
      </label>

      <label className="block">
        <span className="flex justify-between text-slate-400">
          <span>turbulence</span>
          <span>{hologramDebug.turbulence === null ? 'auto' : `${hologramDebug.turbulence.toFixed(2)}x`}</span>
        </span>
        <input
          type="range"
          min={0}
          max={2}
          step={0.05}
          value={hologramDebug.turbulence ?? 1}
          onChange={(event) => {
            hologramDebug.turbulence = Number(event.target.value);
          }}
          className="w-full accent-cyan-400"
        />
      </label>

      <label className="block">
        <span className="flex justify-between text-slate-400">
          <span>speech</span>
          <span>{hologramDebug.speech === null ? 'live' : hologramDebug.speech.toFixed(2)}</span>
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.02}
          value={hologramDebug.speech ?? 0}
          onChange={(event) => {
            hologramDebug.speech = Number(event.target.value);
          }}
          className="w-full accent-cyan-400"
        />
      </label>

      <label className="block">
        <span className="flex justify-between text-slate-400">
          <span>brightness</span>
          <span>{hologramDebug.brightness === null ? 'auto' : `${hologramDebug.brightness.toFixed(2)}x`}</span>
        </span>
        <input
          type="range"
          min={0.4}
          max={1.8}
          step={0.05}
          value={hologramDebug.brightness ?? 1}
          onChange={(event) => {
            hologramDebug.brightness = Number(event.target.value);
          }}
          className="w-full accent-cyan-400"
        />
      </label>
    </div>
  );
};
