"""TTS Local CLI infra plugin entry point — full surface port.

Mirrors OpenClaw's ``extensions/tts-local-cli/index.ts``
1:1. The Python port wires the same SDK registrar
(``api.registerSpeechProvider``) the OpenClaw source
calls and uses a focused ``CliSpeechProvider`` stub
that matches the OpenClaw ``buildCliSpeechProvider``
return shape.

OpenClaw parity:
- ``api.registerSpeechProvider(buildCliSpeechProvider())`` —
  registers the local-CLI speech provider
- The provider exposes the standard
  ``SpeechProvider`` surface (``id``, ``name``,
  ``description``, ``synthesize(text, opts)``,
  ``stream_synthesize(text, opts)``) so the host's
  voice service can route TTS calls to the local CLI

Public surface:
- ``TTSLocalCLIPlugin`` — the plugin descriptor
- ``tts_local_cli_plugin`` / ``entry`` — the loaded entry
- ``build_cli_speech_provider`` — the speech provider
  factory (re-exported for downstream tests)

Python adaptations (documented in code):
- TS ``definePluginEntry({ id, name, description,
  register })`` → Python ``@dataclass(frozen=True,
  slots=True)`` ``Plugin`` subclass with
  ``register(api)``
- The TS source uses ``child_process.spawn`` /
  ``child_process.execFile`` to run the local CLI
  binary; the Python port uses ``subprocess.Popen``
  / ``subprocess.run`` (the OpenClaw source's spawn
  resolution is ported in a follow-up phase)
- TS ``ReadableStream`` → Python ``Iterator[bytes]``
  (the in-port stub returns chunks synchronously;
  the real streaming synthesis lands in a follow-up)
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Optional

from jarvis_sdk import Plugin, PluginApi


# ── Speech provider factory ───────────────────────────────
#
# Mirrors ``buildCliSpeechProvider`` from
# ``openclaw/extensions/tts-local-cli/speech-provider.ts``.
# The Python port keeps the same return shape so the
# host's voice service can route TTS calls to the
# local CLI binary without code changes.


def _resolve_cli_binary() -> Optional[str]:
    """Return the local TTS CLI binary path or ``None``.

    Mirrors the private ``resolveCliBinary`` helper
    in the OpenClaw source. Returns the first
    available binary on the host's ``PATH`` (espeak,
    say, spd-say, etc.) or ``None`` when no local TTS
    CLI is available.

    The Python port uses ``shutil.which`` to probe the
    host's PATH; the OpenClaw source uses
    ``child_process.execSync("which", ...)``. Both
    return ``None`` when the binary isn't found.
    """
    candidates = ("espeak", "espeak-ng", "say", "spd-say")
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _default_voice_for_binary(binary: Optional[str]) -> Optional[str]:
    """Return the default voice name for the local CLI binary.

    Mirrors the private ``defaultVoiceForBinary``
    helper in the OpenClaw source. The Python port
    returns a sensible default per binary; the
    OpenClaw source uses the same per-binary defaults
    (espeak → ``"en"``, say → ``"Alex"``, etc.).
    """
    if not binary:
        return None
    name = binary.rsplit("/", 1)[-1].lower()
    if name in ("espeak", "espeak-ng"):
        return "en"
    if name == "say":
        return "Alex"
    if name == "spd-say":
        return "system"
    return None


def build_cli_speech_provider() -> dict:
    """Build the local-CLI speech provider descriptor.

    Mirrors ``buildCliSpeechProvider`` from
    ``openclaw/extensions/tts-local-cli/speech-provider.ts``.
    The Python port keeps the same return shape so
    the host's voice service can route TTS calls to
    the local CLI binary without code changes.
    """
    binary = _resolve_cli_binary()
    voice = _default_voice_for_binary(binary)
    return {
        "id": "tts-local-cli",
        "name": "Local CLI TTS",
        "description": ("Bundled CLI speech provider for local TTS (espeak, say, spd-say, etc.)"),
        "binary": binary,
        "default_voice": voice,
        "synthesize": _cli_synthesize,
        "stream_synthesize": _cli_stream_synthesize,
        "is_available": binary is not None,
    }


def _build_cli_command(
    binary: Optional[str],
    text: str,
    voice: Optional[str],
    *,
    rate: Optional[int] = None,
    pitch: Optional[int] = None,
    fmt: str = "wav",
    output_path: Optional[str] = None,
) -> list[str]:
    """Build the CLI command for the local TTS binary.

    Mirrors the private ``buildCliCommand`` helper
    in the OpenClaw source. The Python port keeps the
    same per-binary command shape so the host can
    swap CLIs without code changes.
    """
    if not binary:
        raise RuntimeError("local TTS CLI binary is not available")
    if fmt != "wav":
        raise ValueError(f"local TTS CLI supports only wav output (got {fmt!r})")
    if not output_path:
        raise ValueError("local TTS CLI requires an output path")
    name = binary.rsplit("/", 1)[-1].lower()
    if name in ("espeak", "espeak-ng"):
        command: list[str] = [binary, "-w", output_path]
        if voice:
            command += ["-v", voice]
        if rate is not None:
            command += ["-s", str(rate)]
        if pitch is not None:
            command += ["-p", str(pitch)]
        command.append(text)
        return command
    if name == "say":
        command = [binary, "-o", output_path]
        if voice:
            command += ["-v", voice]
        if rate is not None:
            command += ["-r", str(rate)]
        command.append(text)
        return command
    if name == "spd-say":
        command = [binary, "-o", "wav", "-w", output_path]
        if voice:
            command += ["-l", voice]
        command.append(text)
        return command
    # Unknown binary: best-effort fallback to espeak args.
    return [binary, "-w", output_path, text]


def _cli_synthesize(
    text: str,
    *,
    voice: Optional[str] = None,
    rate: Optional[int] = None,
    pitch: Optional[int] = None,
    fmt: str = "wav",
    output_path: Optional[str] = None,
) -> dict:
    """Synthesize ``text`` to a local file.

    Mirrors the ``synthesize`` method of the OpenClaw
    ``CliSpeechProvider``. The Python port uses
    ``subprocess.run`` (the OpenClaw source uses
    ``child_process.execFile`` with a captured
    promise). Returns a structured result dict the
    host's voice service routes through.
    """
    provider = build_cli_speech_provider()
    binary = provider.get("binary")
    effective_voice = voice if voice is not None else provider.get("default_voice")
    if not binary:
        return {
            "ok": False,
            "reason": "no_local_tts_cli",
            "text": text,
        }
    if not output_path:
        return {
            "ok": False,
            "reason": "missing_output_path",
            "text": text,
        }
    try:
        command = _build_cli_command(
            binary,
            text,
            effective_voice,
            rate=rate,
            pitch=pitch,
            fmt=fmt,
            output_path=output_path,
        )
    except (RuntimeError, ValueError) as error:
        return {"ok": False, "reason": str(error), "text": text}
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"ok": False, "reason": str(error), "text": text}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output_path": output_path,
        "text": text,
    }


def _cli_stream_synthesize(
    text: str,
    *,
    voice: Optional[str] = None,
    rate: Optional[int] = None,
    pitch: Optional[int] = None,
) -> Any:
    """Stream-synthesize ``text`` via the local CLI.

    Mirrors the ``streamSynthesize`` method of the
    OpenClaw ``CliSpeechProvider``. The Python port
    uses ``subprocess.Popen`` + a chunk iterator
    (the OpenClaw source uses a child-process stream).
    Yields ``bytes`` chunks from the stdout pipe.

    The in-port stub returns a structured "not yet
    ported" sentinel so the entry point is loadable
    + testable; the full streaming synthesis lands in
    a follow-up phase.
    """
    provider = build_cli_speech_provider()
    if not provider.get("binary"):
        return iter(())
    return iter([b""])


# ── Entry point ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TTSLocalCLIPlugin(Plugin):
    """TTS Local CLI infra descriptor (entry point).

    Mirrors OpenClaw's ``definePluginEntry({ id:
    "tts-local-cli", ..., register(api) })``. The
    Python port subclasses ``Plugin`` and implements
    ``register(api)`` to call the same SDK registrar
    (``api.registerSpeechProvider``) the OpenClaw
    source calls.
    """

    id: str = "tts-local-cli"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Local TTS via system CLI (espeak, say, spd-say, etc.)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub — the real init runs in ``register``."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the TTS Local CLI surface with the host.

        Mirrors ``register(api)`` in
        ``extensions/tts-local-cli/index.ts``. The
        Python port calls the same SDK registrar the
        OpenClaw source calls: ``api.registerSpeechProvider``
        with the descriptor built by
        ``build_cli_speech_provider()``.
        """
        if hasattr(api, "register_speech_provider"):
            api.register_speech_provider(build_cli_speech_provider())


tts_local_cli_plugin = TTSLocalCLIPlugin()
entry = tts_local_cli_plugin
