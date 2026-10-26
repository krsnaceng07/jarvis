/**
 * Speech envelope that drives the hologram jaw.
 *
 * The gateway already streams real `audio_level` packets for the assistant's
 * playback chunks (~35fps, 0..1 RMS). Those packets are the primary source.
 * When the UI reports `speaking` but no packets arrive for a full second (for
 * example a text-only bridge), the envelope falls back to a syllable-shaped
 * curve so the mouth follows the real utterance instead of freezing shut.
 */
export const SPEECH_PACKET_TIMEOUT = 1.0;

export class SpeechEnvelope {
  private target = 0;
  private level = 0;
  private lastPacketAt = Number.NEGATIVE_INFINITY;

  noteAudioLevel(value: number, time: number): void {
    this.target = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
    this.lastPacketAt = time;
  }

  getLevel(): number {
    return this.level;
  }

  update(dt: number, time: number, speaking: boolean): number {
    const live = time - this.lastPacketAt < SPEECH_PACKET_TIMEOUT;
    const fallback = 0.38 + 0.3 * Math.sin(time * 9.3) * Math.sin(time * 4.1) + 0.12 * Math.sin(time * 17);
    const desired = speaking ? (live ? this.target : Math.min(1, Math.max(0, fallback))) : 0;

    // Fast attack, slower release: a jaw snaps open on the syllable and eases shut.
    const response = desired > this.level ? 30 : 8;
    this.level += (desired - this.level) * (1 - Math.exp(-dt * response));
    return this.level;
  }
}
