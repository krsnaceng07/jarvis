import { describe, expect, it } from 'vitest';

import { buildCloud, computeFaceAnchors } from '../components/center/hologramCloud';
import { SpeechEnvelope } from '../components/center/hologramSpeech';
import {
  BAND_END_Y,
  BAND_START_Y,
  DISSOLVE_SECONDS,
  REVEAL_SECONDS,
  sampleDissolve,
  sampleHologramTimeline,
} from '../components/center/hologramTimeline';

describe('Hologram reveal timeline', () => {
  it('starts fully broken apart and ends with a formed portrait', () => {
    const start = sampleHologramTimeline(0);
    expect(start.scatter).toBeCloseTo(1, 5);
    expect(start.bandActive).toBe(true);

    const end = sampleHologramTimeline(REVEAL_SECONDS);
    expect(end.scatter).toBe(0);
    expect(end.bandActive).toBe(false);
    expect(end.phase).toBe('idle');
  });

  it('sweeps the scan band upward once and never back down', () => {
    let previous = -Infinity;
    for (let t = 0; t <= REVEAL_SECONDS; t += 0.02) {
      const sample = sampleHologramTimeline(t);
      expect(sample.bandY).toBeGreaterThanOrEqual(previous - 1e-9);
      previous = sample.bandY;
    }
    expect(sampleHologramTimeline(0.4).bandY).toBeCloseTo(BAND_START_Y, 1);
    expect(sampleHologramTimeline(3.3).bandY).toBeGreaterThan(BAND_END_Y - 0.2);
  });

  it('holds the formed portrait instead of looping the dissolve', () => {
    for (const t of [REVEAL_SECONDS, 12, 60, 600]) {
      const sample = sampleHologramTimeline(t);
      expect(sample.scatter).toBe(0);
      expect(sample.bandStrength).toBe(0);
      expect(sample.bandActive).toBe(false);
    }
  });

  it('is deterministic for the debug scrubber', () => {
    for (const t of [0.1, 0.8, 1.9, 2.7, 3.3]) {
      const first = sampleHologramTimeline(t, 'listening');
      const second = sampleHologramTimeline(t, 'listening');
      expect(second).toEqual(first);
    }
  });

  it('moves continuously with no per-frame jumps', () => {
    let previous = sampleHologramTimeline(0, 'idle');
    for (let t = 0.016; t <= REVEAL_SECONDS; t += 0.016) {
      const sample = sampleHologramTimeline(t, 'idle');
      expect(Math.abs(sample.bandY - previous.bandY)).toBeLessThan(0.05);
      expect(Math.abs(sample.scatter - previous.scatter)).toBeLessThan(0.09);
      expect(Math.abs(sample.brightness - previous.brightness)).toBeLessThan(0.05);
      expect(Math.abs(sample.bandStrength - previous.bandStrength)).toBeLessThan(0.08);
      previous = sample;
    }
  });

  it('reacts to live assistant states without dissolving the identity', () => {
    const idle = sampleHologramTimeline(REVEAL_SECONDS + 1, 'idle');
    const thinking = sampleHologramTimeline(REVEAL_SECONDS + 1, 'thinking');
    const tool = sampleHologramTimeline(REVEAL_SECONDS + 1, 'tool_running');

    expect(thinking.turbulence).toBeGreaterThan(idle.turbulence);
    expect(tool.turbulence).toBeGreaterThan(thinking.turbulence);
    expect(tool.scatter).toBe(0);
  });

  it('dissolves forward in one smooth pass when switching characters', () => {
    const start = sampleDissolve(0);
    expect(start.scatter).toBe(0);
    expect(start.progress).toBe(0);

    const end = sampleDissolve(DISSOLVE_SECONDS);
    expect(end.scatter).toBeCloseTo(1, 5);
    expect(end.progress).toBe(1);
    expect(end.brightness).toBeLessThan(0.7);

    let previous = -1;
    for (let t = 0; t <= DISSOLVE_SECONDS; t += 0.01) {
      const sample = sampleDissolve(t).scatter;
      expect(sample).toBeGreaterThanOrEqual(previous - 1e-9);
      previous = sample;
    }
  });
});

describe('Hologram avatar cloud', () => {
  const synthetic = new Float32Array([
    -1, -0.5, 0, 0.1, 0.4, 0.8,
    0, 0.5, 0.2, 0.2, 0.5, 0.9,
    1, -0.2, 0.4, 0.3, 0.6, 1,
  ]);

  it('builds anchors, colours and bounds from the baked buffer', () => {
    const cloud = buildCloud(synthetic, 7);
    expect(cloud.count).toBe(3);
    const anchors = Array.from(cloud.positions).map((value) => Number(value.toFixed(5)));
    expect(anchors).toEqual([-1, -0.5, 0, 0, 0.5, 0.2, 1, -0.2, 0.4]);
    expect(cloud.min[0]).toBe(-1);
    expect(cloud.max[1]).toBe(0.5);
  });

  it('keeps dispersion offsets bounded and deterministic', () => {
    const first = buildCloud(synthetic, 7);
    const second = buildCloud(synthetic, 7);

    expect(Array.from(first.scatter)).toEqual(Array.from(second.scatter));
    for (let i = 0; i < first.count; i += 1) {
      const magnitude = Math.hypot(
        first.scatter[i * 3],
        first.scatter[i * 3 + 1],
        first.scatter[i * 3 + 2],
      );
      expect(magnitude).toBeGreaterThan(0.1);
      expect(magnitude).toBeLessThan(2.0);
    }
  });
});

describe('Hologram face rig', () => {
  // Tall bright head over dim shoulders, enough to exercise the anchor math.
  const head = new Float32Array([
    0, 1.0, 0.5, 0.9, 0.95, 1.0,
    -0.1, 0.55, 0.5, 0.9, 0.95, 1.0,
    0.1, 0.55, 0.5, 0.9, 0.95, 1.0,
    0, 0.5, 0.5, 0.85, 0.92, 1.0,
    -0.9, -0.8, 0.1, 0.2, 0.5, 0.8,
    0.9, -0.8, 0.1, 0.2, 0.5, 0.8,
  ]);

  it('places the mouth below the bright face cluster', () => {
    const cloud = buildCloud(head, 3);
    const anchors = computeFaceAnchors(cloud);

    expect(anchors.mouthY).toBeLessThan(anchors.headY + 1.2);
    expect(anchors.mouthY).toBeGreaterThan(cloud.min[1]);
    expect(anchors.mouthY).toBeLessThan(cloud.max[1]);
    expect(anchors.headY).toBeLessThan(anchors.mouthY);
    expect(Math.abs(anchors.x)).toBeLessThan(0.2);
  });
});

describe('Speech envelope', () => {
  it('stays shut when the assistant is not speaking', () => {
    const envelope = new SpeechEnvelope();
    envelope.noteAudioLevel(0.9, 0);
    for (let i = 0; i < 90; i += 1) envelope.update(1 / 60, i / 60, false);
    expect(envelope.getLevel()).toBeLessThan(0.02);
  });

  it('follows live audio packets while speaking', () => {
    const envelope = new SpeechEnvelope();
    for (let i = 0; i < 60; i += 1) {
      const t = i / 60;
      envelope.noteAudioLevel(0.8, t);
      envelope.update(1 / 60, t, true);
    }
    expect(envelope.getLevel()).toBeGreaterThan(0.6);
  });

  it('falls back to a moving envelope when the bridge sends no packets', () => {
    const envelope = new SpeechEnvelope();
    const samples: number[] = [];
    for (let i = 0; i < 240; i += 1) {
      const t = i / 60 + 2;
      samples.push(envelope.update(1 / 60, t, true));
    }
    const tail = samples.slice(120);
    expect(Math.max(...tail)).toBeGreaterThan(0.25);
    expect(new Set(tail.map((value) => value.toFixed(2))).size).toBeGreaterThan(8);
  });
});
