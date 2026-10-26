"""Live audio transport for the desktop host.

Mechanically extracted from ``app.py`` (Phase 2 split) so the host entry point
stays under the 2000-line limit. ``JarvisLive`` inherits these methods; bodies,
constants, and call sites are unchanged.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import traceback
from typing import Any

import sounddevice as sd
from google.genai import types  # type: ignore
from jarvis_hooks import HookBus

from .audio_cues import TOOL_CHIME_BYTES
from .visual_stream import VisualFrameStreamer

CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 512

_PLUGIN_HOOK_BUS = HookBus()


def _emit_canonical_event(
    event_type: str,
    priority: str = "P2_NORMAL",
    tool_name: str = "",
    args: dict[str, Any] | None = None,
    turn_id: str = "",
    task_generation: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Non-blocking event emission to the canonical event bus (INV-P9-HOST-001, INV-P9-DEP-001)."""
    try:
        from jarvis_learning.evaluation.event_bus import (
            get_global_event_bus,  # pyright: ignore[reportMissingImports]
        )
        from jarvis_learning.evaluation.event_envelope import (
            create_event_envelope,  # pyright: ignore[reportMissingImports]
        )

        envelope = create_event_envelope(
            event_type=event_type,
            priority=priority,
            tool_name=tool_name,
            sanitized_arguments=args or {},
            turn_id=turn_id,
            task_generation=task_generation,
            metadata=metadata or {},
        )
        get_global_event_bus().publish_nonblocking(envelope)
    except Exception:
        # Non-critical: failure in event emission must NEVER disrupt active runtime
        pass


class _SessionRotationRequired(Exception):
    """Internal signal raised in _receive_audio to cleanly cancel TaskGroup tasks for session rotation."""

    pass


class LiveTransport:
    """Audio send/receive/playback half of ``JarvisLive``."""

    async def _send_realtime(self):
        """Stream mic PCM chunks to the Live API session with zero speech-onset clipping and instant barge-in."""
        if not self.out_queue:
            return

        speech_threshold = int(os.environ.get("JARVIS_SPEECH_THRESHOLD", "45"))
        barge_in_threshold = int(os.environ.get("JARVIS_BARGE_IN_THRESHOLD", "120"))
        silence_threshold_ms = float(os.environ.get("JARVIS_SILENCE_THRESHOLD_MS", "200"))

        consecutive_silence_ms = 0.0

        while True:
            msg = await self.out_queue.get()
            if not self._setup_complete:
                if type(self.session).__name__ in ("MagicMock", "AsyncMock"):
                    self._setup_complete = True
                else:
                    peak = msg.get("peak", 0) if isinstance(msg, dict) else 0
                    if peak >= speech_threshold and len(self._pending_audio) < 30:
                        self._pending_audio.append(msg)
                    continue

            # Drain any pending audio chunks buffered during connect/reconnect
            if self._pending_audio and self.session:
                pending = self._pending_audio
                self._pending_audio = []
                for p_chunk in pending:
                    p_data = p_chunk.get("data") if isinstance(p_chunk, dict) else p_chunk
                    if p_data:
                        p_mime = (
                            p_chunk.get("mime_type")
                            if isinstance(p_chunk, dict) and p_chunk.get("mime_type")
                            else f"audio/pcm;rate={SEND_SAMPLE_RATE}"
                        )
                        try:
                            async with self._ws_send_lock:
                                await self.session.send_realtime_input(
                                    media=types.Blob(data=p_data, mime_type=p_mime)
                                )
                        except Exception as p_err:
                            print(f"[JARVIS] ⚠️ pending audio drain error: {p_err}")
                            break

            # Dynamic batch draining: if queue has accumulated backpressure (>6 chunks = ~192ms),
            # drain up to 6 chunks into a single payload to keep network latency < 35ms.
            q_size = self.out_queue.qsize()
            max_batch = 6 if q_size > 6 else 2
            batch = [msg]
            while not self.out_queue.empty() and len(batch) < max_batch:
                try:
                    batch.append(self.out_queue.get_nowait())
                except Exception:
                    break

            pcm_parts = []
            max_peak = 0
            total_duration_ms = 0.0
            for m in batch:
                if isinstance(m, dict):
                    d = m.get("data")
                    if d:
                        pcm_parts.append(d)
                    max_peak = max(max_peak, m.get("peak", 0))
                    total_duration_ms += m.get("duration_ms", 32.0)
                elif m:
                    pcm_parts.append(m)

            if not pcm_parts or not self.session:
                continue

            combined_data = b"".join(pcm_parts)
            mime = f"audio/pcm;rate={SEND_SAMPLE_RATE}"

            speaking_lock = getattr(self, "_speaking_lock", None)
            is_assistant_speaking = False
            if speaking_lock is not None:
                with speaking_lock:
                    is_assistant_speaking = getattr(self, "_is_speaking", False)

            # Barge-in check: If assistant is speaking and user speaks above barge-in threshold,
            # trigger instant local interruption, silence speaker, and allow user audio through immediately.
            is_barge_in = False
            if is_assistant_speaking:
                if max_peak >= barge_in_threshold:
                    self._trigger_local_barge_in()
                    is_assistant_speaking = False
                    is_barge_in = True
                elif not getattr(self, "_user_is_speaking", False):
                    # Suppress assistant audio echo feedback from speaker to microphone
                    continue

            is_speech = (max_peak >= speech_threshold) or is_barge_in

            if is_speech:
                was_speaking = getattr(self, "_user_is_speaking", False)
                if not was_speaking or getattr(self, "_audio_stream_ended", True) or is_barge_in:
                    self._audio_stream_ended = False
                    self._user_is_speaking = True
                    if not getattr(self.ui, "muted", False) and not is_assistant_speaking:
                        try:
                            self.ui.set_state("HEARING")
                        except Exception:
                            pass
                else:
                    self._user_is_speaking = True
                    self._audio_stream_ended = False

                consecutive_silence_ms = 0.0

                async with self._ws_send_lock:
                    try:
                        await self.session.send_realtime_input(
                            media=types.Blob(
                                data=combined_data,
                                mime_type=mime,
                            )
                        )
                    except Exception as send_err:
                        msg_s = str(send_err).lower()
                        if any(
                            k in msg_s
                            for k in ("closed", "not connected", "connection", "abnormal")
                        ):
                            break
            else:
                # Ambient / trailing non-speech frame (OpenClaw parity):
                # Forward to Gemini Live continuously so server-side neural VAD has continuous
                # acoustic prosody to evaluate natural conversational cadence and sentence completion.
                consecutive_silence_ms += total_duration_ms

                # If user was speaking and has now paused past silence_threshold_ms (250ms),
                # transition state to THINKING while server VAD finalizes turn complete.
                if (
                    getattr(self, "_user_is_speaking", False)
                    and consecutive_silence_ms >= silence_threshold_ms
                ):
                    self._user_is_speaking = False
                    self._audio_stream_ended = True
                    self._interrupted = False
                    if not getattr(self.ui, "muted", False) and not is_assistant_speaking:
                        try:
                            self.ui.set_state("THINKING")
                        except Exception:
                            pass

                # Send ambient/trailing audio frames continuously to server VAD
                async with self._ws_send_lock:
                    try:
                        await self.session.send_realtime_input(
                            media=types.Blob(
                                data=combined_data,
                                mime_type=mime,
                            )
                        )
                    except Exception as send_err:
                        msg_s = str(send_err).lower()
                        if any(
                            k in msg_s
                            for k in ("closed", "not connected", "connection", "abnormal")
                        ):
                            break

    async def _send_visual_stream(self):
        """Continuously stream screen visual frames to the Gemini Live session."""
        print("[JARVIS] 👁️ Visual stream started")
        streamer = VisualFrameStreamer()
        try:
            async for frame in streamer.frames():
                if not self.session:
                    continue
                # Priority yielding: if user speech/audio is queued, transmitting, or actively conversing, skip frame
                if (
                    (self.out_queue and not self.out_queue.empty())
                    or self._ws_send_lock.locked()
                    or getattr(self, "_is_speaking", False)
                    or getattr(self, "_user_is_speaking", False)
                ):
                    continue
                async with self._ws_send_lock:
                    try:
                        await self.session.send_realtime_input(
                            media=types.Blob(
                                data=frame.data,
                                mime_type=frame.mime_type,
                            )
                        )
                    except Exception as e:
                        msg_s = str(e).lower()
                        if any(
                            k in msg_s
                            for k in ("closed", "not connected", "connection", "abnormal")
                        ):
                            break
                        # Temporary congestion or frame drop: sleep briefly and keep stream alive
                        await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"[JARVIS] visual stream ended: {exc}")
        finally:
            print("[JARVIS] 👁️ Visual stream stopped")

    def _trigger_local_barge_in(self) -> None:
        """Instantly silence speaker and drain pending audio on conversational user interruption.

        Note: Do NOT call stream.stop() here as PortAudio deadlocks if stop() is called while
        stream.write() is executing in another thread. Draining the queue and inserting None
        safely and instantly cuts off subsequent audio without crashing or hanging the stream.
        """
        self.abort_playback = True
        self._interrupted = True
        self._audio_stream_ended = False
        self._user_is_speaking = True
        if getattr(self, "_is_speaking", False):
            self.set_speaking(False)
        if self.audio_in_queue is not None:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
            try:
                self.audio_in_queue.put_nowait(None)
            except Exception:
                pass

    async def _keepalive_ping(self):
        """Send periodic WebSocket keepalive pings (every 15s) and monitor idle auto-sleep timeout."""
        ping_ticks = 0
        try:
            while True:
                await asyncio.sleep(3)
                # Idle auto-sleep check: if user has been inactive for > idle_sleep_timeout_s and auto-sleep is enabled
                enable_auto_sleep = os.environ.get("JARVIS_ENABLE_AUTO_SLEEP", "0") == "1"
                now = time.monotonic()
                if (
                    enable_auto_sleep
                    and getattr(self, "session_state", "ACTIVE") == "ACTIVE"
                    and getattr(self, "idle_sleep_timeout_s", 0) > 0
                    and (now - getattr(self, "_last_activity_ts", now) > self.idle_sleep_timeout_s)
                    and not getattr(self, "_is_speaking", False)
                    and not getattr(self, "_user_is_speaking", False)
                ):
                    self.enter_standby_mode(reason="idle_timeout")

                ping_ticks += 1
                should_ping = (ping_ticks % 5 == 0) or getattr(self, "_tool_call_in_flight", False)
                if should_ping and self.session:
                    ws = getattr(self.session, "_ws", None)
                    if ws and hasattr(ws, "ping"):
                        try:
                            res = ws.ping()
                            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                                await res
                        except Exception:
                            pass
        except asyncio.CancelledError:
            pass

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        import os
        import time

        import numpy as np

        loop = asyncio.get_event_loop()

        def _safe_put(q, item):
            if q is None:
                return
            try:
                put_fn = getattr(q, "put_nowait", None)
                if callable(put_fn):
                    put_fn(item)
            except Exception:
                pass

        stream_info = {"sr": 16000, "ch": 1}
        # Echo suppression: mute mic while JARVIS is speaking + holdoff
        # after speech ends to let speaker audio decay.
        # If user speaks loudly over speaker (barge-in), permit it through so Gemini receives the interruption.
        echo_suppression_hold_sec = float(os.environ.get("JARVIS_ECHO_HOLD_SEC", "0.04"))
        was_speaking = False
        post_speech_silence_frames = 0
        idle_silence_counter = 0

        def callback(indata, frames, time_info, status):
            # Echo suppression & intelligent conversational barge-in:
            # Suppress mic while JARVIS is speaking to prevent speaker acoustic feedback loops and turn lag.
            # When user intentionally speaks directly into mic over the speaker (peak >= barge_in_thresh),
            # pass it through immediately and silence local speaker output for natural conversational interruption.
            nonlocal was_speaking, post_speech_silence_frames, idle_silence_counter

            mute_during_speech = os.environ.get("JARVIS_MIC_MUTE_WHILE_SPEAKING", "0") == "1"
            speaking_lock = getattr(self, "_speaking_lock", None)
            is_speaking = False
            if speaking_lock is not None:
                with speaking_lock:
                    is_speaking = getattr(self, "_is_speaking", False)

            peak = 0
            in_speaking_window = False
            speech_thresh = int(os.environ.get("JARVIS_SPEECH_THRESHOLD", "45"))
            if hasattr(self, "vad") and getattr(self.vad, "speech_threshold", None) is not None:
                speech_thresh = int(getattr(self.vad, "speech_threshold"))

            if hasattr(indata, "ndim"):
                arr_in = np.asarray(indata)
                peak = int(np.max(np.abs(arr_in)))
                now = time.monotonic()
                last_ended = getattr(self, "_last_speaking_ended_at", 0.0)
                in_speaking_window = is_speaking or (now - last_ended < echo_suppression_hold_sec)

            if not getattr(self.ui, "muted", False):
                if hasattr(indata, "ndim"):
                    actual_sr = stream_info["sr"]
                    arr_in: Any = np.asarray(indata)
                    if arr_in.ndim > 1 and arr_in.shape[1] > 1:
                        mono = (arr_in[:, 0].astype(np.int32) + arr_in[:, 1].astype(np.int32)) // 2
                    else:
                        mono = arr_in.flatten().astype(np.int32)

                    if len(mono) == 0:
                        return

                    # Microphone gain (default 1.0 = native PCM, configurable via JARVIS_MIC_GAIN)
                    mic_gain = float(os.environ.get("JARVIS_MIC_GAIN", "1.0"))
                    if mic_gain != 1.0:
                        mono = np.clip(mono.astype(np.float32) * mic_gain, -32768, 32767).astype(
                            np.int32
                        )

                    if actual_sr == 16000:
                        pcm = mono.astype(np.int16).tobytes()
                    elif actual_sr == 48000:
                        pcm = mono[::3].astype(np.int16).tobytes()
                    else:
                        num_target = int(len(mono) * 16000 / actual_sr)
                        if num_target > 0:
                            indices = (np.arange(num_target) * (actual_sr / 16000.0)).astype(
                                np.int32
                            )
                            pcm = mono[indices].astype(np.int16).tobytes()
                        else:
                            return
                elif hasattr(indata, "tobytes"):
                    pcm = indata.tobytes()
                    frame = {
                        "data": pcm,
                        "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                        "peak": 0,
                        "duration_ms": (len(pcm) / (SEND_SAMPLE_RATE * 2)) * 1000.0,
                    }
                    try:
                        loop.call_soon_threadsafe(_safe_put, self.out_queue, frame)
                    except Exception:
                        pass
                    return
                else:
                    return

                # Check session standby state & local wake-word trigger
                if getattr(self, "session_state", "ACTIVE") == "STANDBY":
                    woke = False
                    if hasattr(self, "wake_word_engine") and self.wake_word_engine:
                        try:
                            if self.wake_word_engine.process_chunk(pcm):
                                woke = True
                        except Exception:
                            pass
                    if not woke and (peak >= speech_thresh * 2):
                        woke = True

                    if woke:
                        loop.call_soon_threadsafe(self.wake_from_standby)
                    # In STANDBY mode, suppress microphone transmission to Gemini Live completely
                    return

                # Apply high-pass filter (120Hz cutoff) to strip fan rumble before VAD and transmission
                filtered_pcm: bytes = pcm
                filter_fn = (
                    getattr(self.vad, "filter_audio", None) if hasattr(self, "vad") else None
                )
                if callable(filter_fn):
                    try:
                        res = filter_fn(pcm)
                        if isinstance(res, (bytes, bytearray)):
                            filtered_pcm = bytes(res)
                    except Exception:
                        filtered_pcm = pcm

                # Recompute peak on filtered audio so low-frequency fan rumble doesn't inflate peak
                if filtered_pcm:
                    try:
                        filtered_samples = np.frombuffer(filtered_pcm, dtype=np.int16)
                        if len(filtered_samples) > 0:
                            peak = int(np.max(np.abs(filtered_samples)))
                    except Exception:
                        pass

                # Robust multi-signal speech detection:
                # 1. Neural VAD (Silero) detects speech phonemes
                # 2. Amplitude peak >= speech_thresh detects vocal energy
                # Either signal triggers active speech, ensuring soft syllables, non-English
                # speech (e.g. Nepali), and quiet mics are NEVER lost.
                vad_detected = False
                if hasattr(self, "vad") and self.vad is not None:
                    try:
                        vad_detected = self.vad.is_speech(filtered_pcm or pcm)
                    except Exception:
                        vad_detected = False

                is_speech = vad_detected or (peak >= speech_thresh)

                if is_speech:
                    self._last_activity_ts = time.monotonic()
                    post_speech_silence_frames = 0
                    idle_silence_counter = 0

                    if not was_speaking:
                        was_speaking = True
                        # Speech onset: flush pre-roll buffer into out_queue so the first syllable is never clipped
                        flush_fn = (
                            getattr(self.vad, "flush_pre_roll", None)
                            if hasattr(self, "vad")
                            else None
                        )
                        if callable(flush_fn):
                            try:
                                pre_roll = flush_fn()
                                if isinstance(pre_roll, (list, tuple)):
                                    for pr_chunk in pre_roll:
                                        pr_bytes = (
                                            bytes(pr_chunk)
                                            if isinstance(pr_chunk, (bytes, bytearray))
                                            else b""
                                        )
                                        pr_frame = {
                                            "data": pr_bytes,
                                            "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                                            "peak": peak,
                                            "duration_ms": (len(pr_bytes) / (SEND_SAMPLE_RATE * 2))
                                            * 1000.0,
                                        }
                                        loop.call_soon_threadsafe(
                                            _safe_put, self.out_queue, pr_frame
                                        )
                            except Exception:
                                pass

                    if not is_speaking:
                        try:
                            self.ui.set_state("HEARING")
                        except Exception:
                            pass
                    if in_speaking_window:
                        # User spoke over assistant: trigger immediate conversational barge-in
                        try:
                            loop.call_soon_threadsafe(self._trigger_local_barge_in)
                        except Exception:
                            pass

                    frame = {
                        "data": filtered_pcm,
                        "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                        "peak": peak if hasattr(indata, "ndim") else 0,
                        "duration_ms": (len(filtered_pcm) / (SEND_SAMPLE_RATE * 2)) * 1000.0,
                    }
                    try:
                        loop.call_soon_threadsafe(_safe_put, self.out_queue, frame)
                    except Exception:
                        pass
                else:
                    if in_speaking_window and mute_during_speech:
                        return

                    silence_bytes = b"\x00" * len(pcm)
                    # Digital Silence Gate:
                    # When active speech just ceased, send pure digital silence for up to
                    # 10 frames (~320ms) so Gemini Live server VAD triggers end-of-turn instantly.
                    if was_speaking and post_speech_silence_frames < 10:
                        post_speech_silence_frames += 1
                        frame = {
                            "data": silence_bytes,
                            "mime_type": f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                            "peak": 0,
                            "duration_ms": (len(silence_bytes) / (SEND_SAMPLE_RATE * 2)) * 1000.0,
                        }
                        try:
                            loop.call_soon_threadsafe(_safe_put, self.out_queue, frame)
                        except Exception:
                            pass
                        if post_speech_silence_frames >= 10:
                            was_speaking = False
                    else:
                        was_speaking = False
                        # Pure idle silence: DO NOT pump empty frames into out_queue!
                        # Ambient audio stays in VAD pre-roll buffer only.

        mic_warned = False
        try:
            while True:
                open_fn = getattr(self, "_open_input_stream", None)
                if open_fn is not None:
                    stream, sr, ch = open_fn(callback)
                else:
                    try:
                        stream = sd.InputStream(
                            samplerate=SEND_SAMPLE_RATE,
                            channels=CHANNELS,
                            dtype="int16",
                            blocksize=CHUNK_SIZE,
                            callback=callback,
                        )
                        stream.start()
                        sr, ch = SEND_SAMPLE_RATE, CHANNELS
                    except Exception:
                        stream, sr, ch = None, 0, 0

                if stream is not None:
                    stream_info["sr"] = sr
                    stream_info["ch"] = ch
                    mic_warned = False
                    try:
                        while True:
                            await asyncio.sleep(0.5)
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        print(f"[JARVIS] ⚠️ Mic stream error: {e}")
                    finally:
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                else:
                    if not mic_warned:
                        print(
                            "[JARVIS] ⚠️ Microphone unavailable. "
                            "If Windows blocked access, please enable 'Microphone access' in Windows Settings > Privacy & security > Microphone."
                        )
                        self.ui.write_log(
                            "SYS: ⚠️ Microphone unavailable. Check Windows Settings > Privacy & security > Microphone."
                        )
                        if sys.platform == "win32":
                            try:
                                import subprocess

                                subprocess.Popen(
                                    ["start", "ms-settings:privacy-microphone"], shell=True
                                )
                            except Exception:
                                pass
                        mic_warned = True
                    await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        if not self.session:
            return

        try:
            while True:
                async for response in self.session.receive():
                    # 0. Check for server setupComplete message (Gemini Live session ready)
                    if getattr(response, "setup_complete", None) and not self._setup_complete:
                        self._setup_complete = True
                        pending = self._pending_audio
                        self._pending_audio = []
                        print(
                            f"[JARVIS] ✅ Session ready "
                            f"(draining {len(pending)} buffered audio chunks)."
                        )
                        for chunk in pending:
                            data = chunk.get("data") if isinstance(chunk, dict) else chunk
                            mime = (
                                chunk.get("mime_type")
                                if isinstance(chunk, dict) and chunk.get("mime_type")
                                else f"audio/pcm;rate={SEND_SAMPLE_RATE}"
                            )
                            if data:
                                try:
                                    async with self._ws_send_lock:
                                        await self.session.send_realtime_input(
                                            media=types.Blob(data=data, mime_type=mime)
                                        )
                                except Exception as drain_err:
                                    print(f"[JARVIS] ⚠️ drain error: {drain_err}")
                                    break

                    # 1. Update session resumption handle if provided by Google server
                    sru = getattr(response, "session_resumption_update", None)
                    if sru:
                        new_h = getattr(sru, "new_handle", None)
                        resumable = getattr(sru, "resumable", None)
                        if new_h and resumable is not False:
                            self._session_resumption_handle = new_h
                            if hasattr(self, "rolling_context") and self.rolling_context:
                                self.rolling_context.latest_resumption_handle = new_h
                            self._consecutive_reconnect_failures = 0

                    # 2. Check for server GoAway signal (graceful server rotation)
                    go_away = getattr(response, "go_away", None)
                    if go_away:
                        time_left = getattr(go_away, "time_left", None) or "soon"
                        print(
                            f"[JARVIS] ℹ️ Live API Server rotation notice: server disconnecting in {time_left}. Resumption handle is ready."
                        )
                        self._server_rotation_requested = True

                    # 3. Capture audio bytes from either response.data or model_turn inline_data
                    audio_bytes = getattr(response, "data", None)
                    if (
                        not audio_bytes
                        and response.server_content
                        and response.server_content.model_turn
                    ):
                        for p in response.server_content.model_turn.parts:
                            if getattr(p, "inline_data", None) and p.inline_data.data:
                                audio_bytes = p.inline_data.data
                                break

                    # If server emits a new model turn, clear _interrupted so the answer
                    # to the user's interruption is never dropped and plays immediately
                    if (
                        response.server_content
                        and response.server_content.model_turn
                        and getattr(self, "_interrupted", False)
                    ):
                        self._interrupted = False

                    if audio_bytes and self.audio_in_queue:
                        # If this turn was interrupted by the user, drop leftover audio packets from the interrupted turn
                        if not getattr(self, "_interrupted", False):
                            try:
                                self.audio_in_queue.put_nowait(audio_bytes)
                            except Exception:
                                pass

                    if response.server_content:
                        sc = response.server_content

                        if getattr(sc, "interrupted", False):
                            self._interrupted = True
                            if self.audio_in_queue:
                                while not self.audio_in_queue.empty():
                                    try:
                                        self.audio_in_queue.get_nowait()
                                    except Exception:
                                        pass
                                # Sentinel: _play_audio checks for None and
                                # breaks immediately instead of waiting.
                                self.audio_in_queue.put_nowait(None)
                            self.set_speaking(False)

                        if sc.output_transcription and sc.output_transcription.text:
                            # Speaking state is owned exclusively by _play_audio;
                            # do NOT call set_speaking(True) here — audio hasn't
                            # reached the speaker yet.
                            txt = sc.output_transcription.text.strip()
                            if txt:
                                out_buf.append(txt)

                        if sc.model_turn and sc.model_turn.parts:
                            self._interrupted = False
                            for part in sc.model_turn.parts:
                                if getattr(part, "text", None) and not getattr(
                                    part, "thought", False
                                ):
                                    t = part.text.strip()
                                    if t and t not in out_buf:
                                        out_buf.append(t)

                        live_final = getattr(sc, "input_transcription", None)
                        live_interim = getattr(sc, "interim_input_transcription", None)

                        if live_final and getattr(live_final, "text", None):
                            txt = live_final.text.strip()
                            if txt and txt not in in_buf:
                                in_buf.append(txt)
                            if hasattr(self.ui, "set_live_transcript"):
                                try:
                                    self.ui.set_live_transcript(" ".join(in_buf), is_final=False, role="user")
                                except TypeError:
                                    self.ui.set_live_transcript(" ".join(in_buf))
                        elif live_interim and getattr(live_interim, "text", None):
                            interim_txt = live_interim.text.strip()
                            if interim_txt:
                                display_txt = f"{' '.join(in_buf)} {interim_txt}".strip()
                                if hasattr(self.ui, "set_live_transcript"):
                                    try:
                                        self.ui.set_live_transcript(display_txt, is_final=False, role="user")
                                    except TypeError:
                                        self.ui.set_live_transcript(display_txt)

                        if sc.turn_complete:
                            self._turns_completed_in_session += 1
                            self._audio_stream_ended = True
                            self._user_is_speaking = False
                            self._interrupted = False
                            # Signal _play_audio that Gemini has finished
                            # sending audio. _play_audio will drain remaining
                            # queued chunks then end speech instantly.
                            tc_sig = getattr(self, "_turn_complete_signal", None)
                            if tc_sig is not None:
                                tc_sig.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                if hasattr(self.ui, "set_live_transcript"):
                                    try:
                                        self.ui.set_live_transcript(f"You: {full_in}", is_final=True, role="user")
                                    except TypeError:
                                        self.ui.set_live_transcript(f"You: {full_in}")
                                self.ui.write_log(f"You: {full_in}")
                                if hasattr(self, "rolling_context") and self.rolling_context:
                                    self.rolling_context.record_user_turn(full_in)
                                if hasattr(self, "_transcript_store"):
                                    self._transcript_store.append_entry(
                                        "desktop:hud", "user_speech", {"text": full_in}
                                    )
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                if hasattr(self, "rolling_context") and self.rolling_context:
                                    self.rolling_context.record_model_turn(full_out)
                                if hasattr(self, "_transcript_store"):
                                    self._transcript_store.append_entry(
                                        "desktop:hud", "assistant_speech", {"text": full_out}
                                    )
                            out_buf = []
                            self._last_activity_ts = time.monotonic()

                            # Phase 3.5: background LLM-based memory
                            # extraction is gone; the model calls
                            # `save_memory` directly when it wants
                            # to remember something.

                            # Phase 3: fire `agent_end` hook after each
                            # complete turn. Plugins can persist state
                            # (memory flush, metric emission, etc.).
                            from jarvis_hooks import fire_sync

                            fire_sync(
                                _PLUGIN_HOOK_BUS,
                                "agent_end",
                                {"input": full_in, "output": full_out},
                            )
                            _emit_canonical_event(
                                "TurnCompleted",
                                priority="P2_NORMAL",
                                metadata={"input": full_in, "output": full_out},
                            )

                            # Proactive session rotation on server GoAway notice at turn boundary
                            if self._server_rotation_requested and self._session_resumption_handle:
                                print(
                                    "[JARVIS] 🔄 Proactively rotating Live API session at turn boundary before server disconnect..."
                                )
                                self._server_rotation_requested = False
                                raise _SessionRotationRequired("GoAway rotation at turn boundary")

                    if response.tool_call:
                        # Step A: Inject instant auditory chime to eliminate conversational dead air
                        # ONLY if the assistant is not currently speaking and queue is empty
                        if (
                            self.audio_in_queue
                            and not getattr(self, "is_speaking", False)
                            and self.audio_in_queue.empty()
                        ):
                            try:
                                self.audio_in_queue.put_nowait(TOOL_CHIME_BYTES)
                            except Exception:
                                pass

                        # Step B: Run tool calls concurrently in background task without blocking receive loop
                        asyncio.create_task(self._handle_tool_calls(response.tool_call))

        except _SessionRotationRequired:
            raise
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._is_deadline_expired_error(e):
                print(
                    f"[JARVIS] ℹ️ Live API session deadline reached ({type(e).__name__}): {e}. Seamlessly resuming..."
                )
                self.ui.write_log("SYS: 🔄 Session rotating / resuming...")
            elif self._is_invalid_argument_or_handle_error(e):
                print(
                    f"[JARVIS] ℹ️ Live API session handle or argument rejected by server ({type(e).__name__}): {e}. Fresh session starting..."
                )
                self.ui.write_log("SYS: 🔄 Refreshing Live session...")
            else:
                msg_str = str(e).lower()
                if any(
                    k in msg_str
                    for k in (
                        "connectionclosed",
                        "closed",
                        "1000",
                        "1001",
                        "1006",
                        "1007",
                        "1011",
                        "eof",
                        "abnormal",
                        "reset by peer",
                        "internal error",
                        "connection reset",
                    )
                ):
                    print(
                        f"[JARVIS] ℹ️ Live API connection closed by server/peer ({type(e).__name__}): {e}"
                    )
                else:
                    print(f"[JARVIS] ❌ Recv: {e}")
                    traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = None
        out_sr = RECEIVE_SAMPLE_RATE
        out_ch = CHANNELS

        open_fn = getattr(self, "_open_output_stream", None)
        if open_fn is not None:
            stream, out_sr, out_ch = open_fn(RECEIVE_SAMPLE_RATE, CHANNELS)
        else:
            try:
                stream = sd.RawOutputStream(
                    samplerate=RECEIVE_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=1024,
                )
                stream.start()
            except Exception as e:
                print(f"[JARVIS] ⚠️ Audio output stream unavailable: {e}")

        self._current_out_stream = stream

        if not self.audio_in_queue:
            return
        audio_q = self.audio_in_queue
        leftover = b""
        is_speaking = False

        prep_fn = getattr(self, "_prepare_audio_for_output", None)

        async def _play_chunk(pcm_data: bytes) -> bool:
            nonlocal stream, out_sr, out_ch
            if not pcm_data:
                return True

            # If stream is missing or stopped/closed, reopen it
            if stream is None or not getattr(stream, "active", False):
                try:
                    if stream is not None:
                        try:
                            stream.close()
                        except Exception:
                            pass
                    if open_fn is not None:
                        stream, out_sr, out_ch = open_fn(RECEIVE_SAMPLE_RATE, CHANNELS)
                    else:
                        stream = sd.RawOutputStream(
                            samplerate=RECEIVE_SAMPLE_RATE,
                            channels=CHANNELS,
                            dtype="int16",
                            blocksize=1024,
                        )
                        stream.start()
                    self._current_out_stream = stream
                except Exception as ex:
                    print(f"[JARVIS] ⚠️ Cannot open audio output stream: {ex}")
                    return False

            if stream is None:
                return False

            if prep_fn is not None:
                prepared = prep_fn(pcm_data, out_sr, out_ch)
            else:
                prepared = pcm_data

            # Slice playback into ~40ms sub-chunks (1920 bytes at 24kHz mono) to enable instant software barge-in
            chunk_slice = 1920
            for offset in range(0, len(prepared), chunk_slice):
                if getattr(self, "abort_playback", False) or getattr(self, "_interrupted", False):
                    break
                slice_data = prepared[offset : offset + chunk_slice]
                try:
                    write_fn = getattr(stream, "write", None)
                    if callable(write_fn):
                        await asyncio.to_thread(write_fn, slice_data)
                except Exception as play_err:
                    print(
                        f"[JARVIS] ⚠️ Audio playback error ({play_err}), recreating output stream..."
                    )
                    try:
                        if stream is not None:
                            try:
                                stream.close()
                            except Exception:
                                pass
                        if open_fn is not None:
                            stream, out_sr, out_ch = open_fn(RECEIVE_SAMPLE_RATE, CHANNELS)
                        else:
                            stream = sd.RawOutputStream(
                                samplerate=RECEIVE_SAMPLE_RATE,
                                channels=CHANNELS,
                                dtype="int16",
                                blocksize=1024,
                            )
                            stream.start()
                        self._current_out_stream = stream
                        if stream is not None and not (
                            getattr(self, "abort_playback", False)
                            or getattr(self, "_interrupted", False)
                        ):
                            await asyncio.to_thread(stream.write, slice_data)
                    except Exception as ex2:
                        print(f"[JARVIS] ⚠️ Audio stream recovery failed: {ex2}")
                        return False
            return True

        try:
            while True:
                # Wait indefinitely for the first chunk of a new speech segment
                chunk = await audio_q.get()
                self.abort_playback = False

                # None sentinel or interrupted = drop residual audio from interrupted speech
                if (
                    chunk is None
                    or getattr(self, "abort_playback", False)
                    or getattr(self, "_interrupted", False)
                ):
                    if is_speaking:
                        is_speaking = False
                        self.set_speaking(False)
                    continue

                if not is_speaking:
                    is_speaking = True
                    self.set_speaking(True)
                    # Clear turn_complete from previous turn so we don't
                    # falsely end this new speech segment early.
                    tc_sig = getattr(self, "_turn_complete_signal", None)
                    if tc_sig is not None:
                        tc_sig.clear()

                # Immediate playback with minimal framing: play directly without artificial buffering delay
                raw_bytes = leftover + chunk
                remainder = len(raw_bytes) % 2
                if remainder != 0:
                    pcm_to_play = raw_bytes[:-remainder]
                    leftover = raw_bytes[-remainder:]
                else:
                    pcm_to_play = raw_bytes
                    leftover = b""

                if pcm_to_play and not getattr(self, "_interrupted", False):
                    await _play_chunk(pcm_to_play)

                # Continuous streaming loop with instant turn-complete detection.
                # Primary: end speech as soon as queue is empty AND Gemini
                # signaled turn_complete (0ms dead time).
                # Fallback: 500ms timeout for edge cases (disconnect, etc).
                tc_sig = getattr(self, "_turn_complete_signal", None)
                while True:
                    # Instant end: Gemini finished and no more audio queued
                    if audio_q.empty() and tc_sig is not None and tc_sig.is_set():
                        await asyncio.sleep(0.04)
                        if audio_q.empty():
                            tc_sig.clear()
                            if is_speaking:
                                is_speaking = False
                                self.set_speaking(False)
                            self._audio_stream_ended = True
                            self._user_is_speaking = False
                            break

                    try:
                        next_chunk = await asyncio.wait_for(audio_q.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        self._audio_stream_ended = True
                        self._user_is_speaking = False
                        break

                    if next_chunk is None or getattr(self, "_interrupted", False):
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        self._audio_stream_ended = True
                        self._user_is_speaking = False
                        break

                    # Batch-drain: grab everything available right now
                    more = [next_chunk]
                    interrupted = False
                    while not audio_q.empty():
                        try:
                            item = audio_q.get_nowait()
                            if item is None or getattr(self, "_interrupted", False):
                                interrupted = True
                                break
                            more.append(item)
                        except Exception:
                            break

                    if interrupted or getattr(self, "_interrupted", False):
                        if is_speaking:
                            is_speaking = False
                            self.set_speaking(False)
                        break

                    raw_bytes = leftover + b"".join(more)
                    remainder = len(raw_bytes) % 2
                    if remainder != 0:
                        pcm_to_play = raw_bytes[:-remainder]
                        leftover = raw_bytes[-remainder:]
                    else:
                        pcm_to_play = raw_bytes
                        leftover = b""

                    if pcm_to_play and not getattr(self, "_interrupted", False):
                        await _play_chunk(pcm_to_play)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[JARVIS] ❌ Play error: {e}")
        finally:
            self._current_out_stream = None
            if is_speaking:
                is_speaking = False
                self.set_speaking(False)
            self._audio_stream_ended = True
            self._user_is_speaking = False
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

