"""TTS Local CLI speech provider.

Mirrors OpenClaw's ``extensions/tts-local-cli/speech-provider.ts``.

The provider shells out to a user-configured CLI (e.g.
``say``, ``piper``, ``espeak``, ``mimic3``) to do TTS. The
provider parses the configured command + args, applies
``{{Text}}`` / ``{{OutputPath}}`` / ``{{OutputDir}}`` /
``{{OutputBase}}`` template substitutions, and reads the
synthesized audio from the temp workspace (or stdout
when the CLI writes to stdout).

Public surface (mirrors the TS source):
- ``build_cli_speech_provider()`` — the registered
  ``SpeechProviderPlugin`` descriptor
- ``resolve_cli_provider_config(raw_config)`` — extract
  the per-provider config from the host config
- ``get_config(cfg)`` — parse + validate a per-provider
  config
- ``parse_command(cmd_str)`` — split a shell-style
  command string into ``{cmd, initial_args}``
- ``apply_template(value, ctx)`` — substitute ``{{Key}}``
  tokens (case-insensitive key)
- ``strip_emojis(text)`` — drop Emoji_Presentation /
  Extended_Pictographic runes and collapse whitespace
- ``find_audio_file(dir, base_name)`` — locate the
  synthesized audio file in the temp workspace
- ``detect_format(file_path)`` — return the format for a
  given audio file extension
- ``get_file_ext(format)`` — return the canonical
  extension for a format

Python adaptations (documented in code):
- TS ``Buffer`` → Python ``bytes``
- TS ``runCommandBuffered`` / ``runFfmpeg`` /
  ``tempWorkspace`` are injected via the
  ``RunCommandFn`` / ``RunFfmpegFn`` / ``TempWorkspaceFn``
  callables on the provider (production wiring is the
  responsibility of the host when the corresponding
  ``openclaw/plugin-sdk/*`` modules are ported)
- TS ``as const`` array of formats → Python
  ``frozenset`` membership constant
- The directory is named ``lib/`` (not ``src/``) to
  avoid the namespace collision with the JARVIS root
  ``src/`` package
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TypedDict, Union

from jarvis_sdk.speech_provider import (
    SpeechOutputFormat,
    SpeechProviderPlugin,
    SpeechSynthesisRequest,
    SpeechSynthesisResult,
    SpeechTelephonySynthesisRequest,
    VALID_SPEECH_OUTPUT_FORMATS,
)


# ── Public constants ─────────────────────────────────────


VALID_OUTPUT_FORMATS: frozenset[str] = VALID_SPEECH_OUTPUT_FORMATS
AUDIO_EXTENSIONS: frozenset[str] = frozenset({".wav", ".mp3", ".opus", ".ogg", ".m4a"})
DEFAULT_TIMEOUT_MS = 120_000
MAX_AUDIO_OUTPUT_BYTES = 50 * 1024 * 1024
MAX_CLI_STDERR_BYTES = 1024 * 1024


# ── Type aliases (mirrors the TS source) ────────────────


class CliConfig(TypedDict, total=False):
    command: str
    args: list[str]
    outputFormat: SpeechOutputFormat
    timeoutMs: int
    cwd: str
    env: dict[str, str]


class RunCommandResult(TypedDict, total=False):
    code: int
    stdout: bytes
    stderr: bytes
    termination: str
    errorStream: str
    outputLimitStream: str
    error: dict[str, Any]


class TempWorkspace(TypedDict, total=False):
    dir: str
    write: Callable[[str, bytes], Awaitable[None]]


# Callable signatures for the host-supplied primitives.
RunCommandFn = Callable[
    [list[str], dict[str, Any]],
    Awaitable[RunCommandResult],
]
RunFfmpegFn = Callable[[list[str]], Awaitable[None]]
TempWorkspaceFn = Callable[
    [dict[str, Any]],
    Awaitable[TempWorkspace],
]


# ── Helpers ─────────────────────────────────────────────


def as_object(value: object) -> Optional[dict[str, Any]]:
    """Return ``value`` as a dict, or ``None`` for non-object input.

    Mirrors the private ``asObject`` helper.
    """
    if not isinstance(value, dict):
        return None
    return value


def as_string_array(value: object) -> Optional[list[str]]:
    """Return ``value`` as a list of strings, or ``None`` otherwise."""
    if not isinstance(value, list):
        return None
    if not all(isinstance(v, str) for v in value):
        return None
    return value  # type: ignore[return-value]


def as_record(value: object) -> Optional[dict[str, str]]:
    """Coerce a dict to ``dict[str, str]``, dropping non-string values."""
    obj = as_object(value)
    if obj is None:
        return None
    result: dict[str, str] = {}
    for k, v in obj.items():
        if isinstance(v, str):
            result[k] = v
    return result or None


def normalize_output_format(value: object) -> SpeechOutputFormat:
    """Return a canonical output format, defaulting to ``"mp3"`` for unknown input."""
    if not isinstance(value, str):
        return "mp3"
    lower = value.strip().lower()
    if lower in VALID_OUTPUT_FORMATS:
        return lower  # type: ignore[return-value]
    return "mp3"


def resolve_cli_provider_config(
    raw_config: dict[str, Any],
) -> dict[str, Any]:
    """Extract the ``tts-local-cli`` (or ``cli``) block from the host config."""
    providers = as_object(raw_config.get("providers")) or {}
    cli = as_object(providers.get("tts-local-cli")) or as_object(providers.get("cli"))
    return cli or {}


def get_config(cfg: dict[str, Any]) -> Optional[CliConfig]:
    """Parse + validate the per-provider config.

    Returns ``None`` when the ``command`` field is missing
    or empty (the provider is not configured).
    """
    command = cfg.get("command") if isinstance(cfg.get("command"), str) else ""
    command = command.strip() if isinstance(command, str) else ""
    if not command:
        return None
    return {
        "command": command,
        "args": as_string_array(cfg.get("args")) or [],
        "outputFormat": normalize_output_format(cfg.get("outputFormat")),
        "timeoutMs": cfg.get("timeoutMs")
        if isinstance(cfg.get("timeoutMs"), (int, float))
        else DEFAULT_TIMEOUT_MS,
        **({"cwd": cfg["cwd"]} if isinstance(cfg.get("cwd"), str) else {}),
        **({"env": as_record(cfg["env"]) or {}} if as_record(cfg.get("env")) else {}),
    }


# ── Text + format helpers ──────────────────────────────


_EMOJI_PATTERN = re.compile(
    r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF]"
    r"|[\u2700-\u27BF\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF]",
    flags=re.UNICODE,
)


def strip_emojis(text: str) -> str:
    """Drop Emoji_Presentation / Extended_Pictographic runes and collapse whitespace.

    Mirrors the private ``stripEmojis`` helper.
    """
    if not isinstance(text, str):
        return ""
    no_emoji = _EMOJI_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", no_emoji).strip()


_TEMPLATE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def apply_template(value: str, ctx: dict[str, Optional[str]]) -> str:
    """Substitute ``{{Key}}`` tokens (case-insensitive) from ``ctx``.

    Mirrors the private ``applyTemplate`` helper. The
    look-up is case-insensitive on the first letter
    (``Text`` -> ``text`` -> ``Text`` ...).
    """
    if not isinstance(value, str):
        return ""

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        normalized = key[0].upper() + key[1:].lower()
        if normalized in ctx:
            return str(ctx[normalized] or "")
        if key in ctx:
            return str(ctx[key] or "")
        return ""

    return _TEMPLATE_PATTERN.sub(_replace, value)


def parse_command(cmd_str: str) -> dict[str, Any]:
    """Split a shell-style command string into ``{cmd, initial_args}``.

    Mirrors the private ``parseCommand`` helper. Supports
    both ``"`` and ``'`` quoting. Empty input returns
    ``{"cmd": "", "initialArgs": []}``.
    """
    parts: list[str] = []
    current = ""
    in_quote = False
    quote_char = ""
    for ch in (cmd_str or "").strip():
        if in_quote:
            if ch == quote_char:
                in_quote = False
            else:
                current += ch
        elif ch in ('"', "'"):
            in_quote = True
            quote_char = ch
        elif ch in (" ", "\t"):
            if current:
                parts.append(current)
                current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return {
        "cmd": parts[0] if parts else "",
        "initialArgs": parts[1:] if len(parts) > 1 else [],
    }


# ── Audio file helpers ──────────────────────────────────


def get_file_ext(format: str) -> str:
    """Return the canonical extension for a given format."""
    if format == "opus":
        return ".opus"
    if format == "wav":
        return ".wav"
    return ".mp3"


def detect_format(file_path: str) -> Optional[SpeechOutputFormat]:
    """Detect the format for a given audio file path."""
    if not isinstance(file_path, str):
        return None
    ext = os.path.splitext(file_path)[1].lower()
    if ext in (".opus", ".ogg"):
        return "opus"
    if ext == ".wav":
        return "wav"
    if ext in (".mp3", ".m4a"):
        return "mp3"
    return None


def find_audio_file(dir_path: str, base_name: str) -> Optional[str]:
    """Locate the synthesized audio file in a temp workspace.

    Mirrors the private ``findAudioFile`` helper. Prefers
    a file whose name starts with (or contains)
    ``base_name``; falls back to the first audio file
    found.
    """
    if not isinstance(dir_path, str) or not os.path.isdir(dir_path):
        return None
    entries = sorted(os.listdir(dir_path))
    primary: list[str] = []
    fallback: list[str] = []
    for entry in entries:
        ext = os.path.splitext(entry)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            continue
        path = os.path.join(dir_path, entry)
        if entry.startswith(base_name) or base_name in entry:
            primary.append(path)
        else:
            fallback.append(path)
    if primary:
        return primary[0]
    if fallback:
        return fallback[0]
    return None


def read_audio_file(file_path: str) -> bytes:
    """Read an audio file with a max-byte safety cap.

    Mirrors the private ``readAudioFile`` helper.
    Production wiring should enforce the cap via the
    host's security-runtime; this port uses a simple
    byte-length check.
    """
    with open(file_path, "rb") as handle:
        data = handle.read(MAX_AUDIO_OUTPUT_BYTES + 1)
    if len(data) > MAX_AUDIO_OUTPUT_BYTES:
        raise ValueError(f"audio file {file_path} exceeds {MAX_AUDIO_OUTPUT_BYTES} bytes")
    return data


# ── Public surface: build_cli_speech_provider ──────────


@dataclass
class CliProviderDeps:
    """Dependency-injection bag for the CLI provider.

    Mirrors the OpenClaw host-supplied primitives that
    ``speech-provider.ts`` pulls from the plugin SDK.
    Production wiring is the responsibility of the host
    when the corresponding modules are ported.
    """

    run_command: Optional[RunCommandFn] = None
    run_ffmpeg: Optional[RunFfmpegFn] = None
    temp_workspace: Optional[TempWorkspaceFn] = None
    now_ms_fn: Callable[[], int] = lambda: int(__import__("time").time() * 1000)


async def _run_cli_synthesize(
    config: CliConfig,
    request: Union[SpeechSynthesisRequest, SpeechTelephonySynthesisRequest],
    text: str,
    *,
    deps: CliProviderDeps,
) -> SpeechSynthesisResult:
    """Run the configured CLI to synthesize audio.

    Mirrors the private ``runCli`` helper. The host-supplied
    ``run_command`` callable is used to spawn the CLI;
    a missing callable raises a clear error.
    """
    if deps.run_command is None:
        raise RuntimeError("tts-local-cli: run_command dependency is not wired")
    clean_text = strip_emojis(text)
    if not clean_text:
        raise ValueError("CLI TTS: text is empty after removing emojis")
    output_format = request.get("outputFormat") or config.get("outputFormat")
    output_ext = get_file_ext(output_format or "wav")
    file_prefix = "speech"
    output_dir = "."
    ctx: dict[str, Optional[str]] = {
        "Text": clean_text,
        "OutputPath": os.path.join(output_dir, f"{file_prefix}{output_ext}"),
        "OutputDir": output_dir,
        "OutputBase": file_prefix,
    }
    parsed = parse_command(config["command"])
    if not parsed["cmd"]:
        raise ValueError("CLI TTS: invalid command")
    base_args = list(parsed["initialArgs"]) + list(config.get("args") or [])
    args = [apply_template(a, ctx) for a in base_args]
    # If a {{text}} placeholder is in the args, the CLI
    # takes the text via arg; otherwise it's piped via
    # stdin.
    has_text_placeholder = any(
        bool(_TEMPLATE_PATTERN.search(a)) and "text" in a.lower() for a in base_args
    )
    input_data = "" if has_text_placeholder else clean_text
    result = await deps.run_command(
        [parsed["cmd"], *args],
        {
            "cwd": config.get("cwd"),
            "env": config.get("env") or {},
            "input": input_data,
            "maxOutputBytes": {
                "stdout": MAX_AUDIO_OUTPUT_BYTES,
                "stderr": MAX_CLI_STDERR_BYTES,
            },
            "timeoutMs": config.get("timeoutMs") or DEFAULT_TIMEOUT_MS,
        },
    )
    if result.get("termination") == "timeout":
        raise TimeoutError(
            f"CLI TTS timed out after {config.get('timeoutMs') or DEFAULT_TIMEOUT_MS}ms"
        )
    if result.get("termination") == "output-limit":
        stream = result.get("outputLimitStream") or "stdout"
        max_bytes = MAX_CLI_STDERR_BYTES if stream == "stderr" else MAX_AUDIO_OUTPUT_BYTES
        raise ValueError(f"CLI TTS {stream} exceeded {max_bytes} bytes")
    code = result.get("code")
    if code is not None and code != 0:
        stderr_text = (result.get("stderr") or b"").decode("utf8", errors="replace")
        raise RuntimeError(f"CLI TTS exit {code}: {stderr_text}")
    if result.get("termination") not in ("exit", "error"):
        err = result.get("error") or {}
        raise RuntimeError(f"CLI TTS failed: {err.get('message') or result.get('termination')}")
    if result.get("termination") == "error" and code not in (0, None):
        err = result.get("error") or {}
        raise RuntimeError(f"CLI TTS failed: {err.get('message') or result.get('termination')}")

    # Try to find the audio file in the workspace.
    audio_file = find_audio_file(output_dir, file_prefix)
    if audio_file is not None:
        fmt = detect_format(audio_file)
        if fmt is None:
            raise ValueError(f"CLI TTS: unknown format for {audio_file}")
        return {
            "audio": read_audio_file(audio_file),
            "format": fmt,
            "sourcePath": audio_file,
        }
    stdout = result.get("stdout") or b""
    if stdout:
        # Assume WAV for stdout output; callers can
        # convert if they need MP3.
        return {"audio": stdout, "format": "wav"}
    err = result.get("error") or {}
    raise RuntimeError(f"CLI TTS failed: {err.get('message') or result.get('termination')}")


def build_cli_speech_provider(
    *,
    deps: Optional[CliProviderDeps] = None,
) -> SpeechProviderPlugin:
    """Build the registered CLI speech provider.

    Mirrors ``buildCliSpeechProvider`` in OpenClaw. The
    returned ``SpeechProviderPlugin`` exposes:
    - ``id``: ``"tts-local-cli"``
    - ``aliases``: ``["cli"]`` (TS uses a string-array
      field; the Python port exposes it as a read-only
      list)
    - ``label``: ``"Local CLI"``
    - ``synthesize(request)``: synthesize audio from the
      request's text via the configured CLI

    The host wires the underlying primitives
    (``run_command`` / ``temp_workspace`` / ``ffmpeg``)
    via ``deps``. When the host does not supply them, the
    synthesize calls raise a clear "dependency is not
    wired" error.
    """
    effective_deps = deps or CliProviderDeps()

    async def synthesize(
        request: SpeechSynthesisRequest,
    ) -> SpeechSynthesisResult:
        if effective_deps.temp_workspace is None:
            raise RuntimeError("tts-local-cli: temp_workspace dependency is not wired")
        if effective_deps.run_command is None:
            raise RuntimeError("tts-local-cli: run_command dependency is not wired")
        # The TS source pulls the per-provider config
        # from the request's providerConfig. The Python
        # port accepts it directly via ``request["providerConfig"]``
        # (a dict matching the OpenClaw shape); the host
        # adapter is responsible for populating it.
        provider_config: dict[str, Any] = (
            request.get("providerConfig") or {}  # type: ignore[typeddict-item]
        )
        config = get_config(provider_config)
        if config is None:
            raise RuntimeError("CLI TTS not configured")
        text = request.get("text") or ""
        if not text:
            raise ValueError("CLI TTS: text is required")
        # Use a host-supplied temp workspace (the TS
        # version uses ``tempWorkspace({rootDir: ...})``).
        workspace = await effective_deps.temp_workspace({"prefix": "openclaw-cli-tts-"})
        output_dir = workspace.get("dir") or "."
        # Update ctx with the actual output dir.
        file_prefix = "speech"
        output_format = request.get("outputFormat") or config.get("outputFormat")
        output_ext = get_file_ext(output_format or "wav")
        # The actual synthesis is delegated to the lower
        # level helper. We pass output_dir via the deps
        # closure by setting env-style options; the
        # simplest path is to call _run_cli_synthesize
        # with the resolved context, so we inline a
        # small loop here.
        clean_text = strip_emojis(text)
        if not clean_text:
            raise ValueError("CLI TTS: text is empty after removing emojis")
        ctx: dict[str, Optional[str]] = {
            "Text": clean_text,
            "OutputPath": os.path.join(output_dir, f"{file_prefix}{output_ext}"),
            "OutputDir": output_dir,
            "OutputBase": file_prefix,
        }
        parsed = parse_command(config["command"])
        if not parsed["cmd"]:
            raise ValueError("CLI TTS: invalid command")
        base_args = list(parsed["initialArgs"]) + list(config.get("args") or [])
        args = [apply_template(a, ctx) for a in base_args]
        has_text_placeholder = any(
            bool(_TEMPLATE_PATTERN.search(a)) and "text" in a.lower() for a in base_args
        )
        input_data = "" if has_text_placeholder else clean_text
        result = await effective_deps.run_command(
            [parsed["cmd"], *args],
            {
                "cwd": config.get("cwd"),
                "env": config.get("env") or {},
                "input": input_data,
                "maxOutputBytes": {
                    "stdout": MAX_AUDIO_OUTPUT_BYTES,
                    "stderr": MAX_CLI_STDERR_BYTES,
                },
                "timeoutMs": config.get("timeoutMs") or DEFAULT_TIMEOUT_MS,
            },
        )
        if result.get("termination") == "timeout":
            raise TimeoutError(
                f"CLI TTS timed out after {config.get('timeoutMs') or DEFAULT_TIMEOUT_MS}ms"
            )
        if result.get("termination") == "output-limit":
            stream = result.get("outputLimitStream") or "stdout"
            max_bytes = MAX_CLI_STDERR_BYTES if stream == "stderr" else MAX_AUDIO_OUTPUT_BYTES
            raise ValueError(f"CLI TTS {stream} exceeded {max_bytes} bytes")
        code = result.get("code")
        if code is not None and code != 0:
            stderr_text = (result.get("stderr") or b"").decode("utf8", errors="replace")
            raise RuntimeError(f"CLI TTS exit {code}: {stderr_text}")
        if result.get("termination") not in ("exit", "error"):
            err = result.get("error") or {}
            raise RuntimeError(f"CLI TTS failed: {err.get('message') or result.get('termination')}")
        if result.get("termination") == "error" and code not in (
            0,
            None,
        ):
            err = result.get("error") or {}
            raise RuntimeError(f"CLI TTS failed: {err.get('message') or result.get('termination')}")
        # Look for the synthesized file in the workspace
        # (the workspace-write callback is what would
        # create it via the host's ``run_command``).
        audio_file = find_audio_file(output_dir, file_prefix)
        if audio_file is not None:
            fmt = detect_format(audio_file)
            if fmt is None:
                raise ValueError(f"CLI TTS: unknown format for {audio_file}")
            return {
                "audio": read_audio_file(audio_file),
                "format": fmt,
                "sourcePath": audio_file,
            }
        stdout = result.get("stdout") or b""
        if stdout:
            return {"audio": stdout, "format": "wav"}
        err = result.get("error") or {}
        raise RuntimeError(f"CLI TTS failed: {err.get('message') or result.get('termination')}")

    return {
        "id": "tts-local-cli",
        "label": "Local CLI",
        "description": "Bundled CLI speech provider for local TTS",
        "defaultFormat": "mp3",
        "synthesize": synthesize,
        "metadata": {
            "aliases": ["cli"],
            "autoSelectOrder": 1000,
        },
    }


__all__ = [
    "AUDIO_EXTENSIONS",
    "CliConfig",
    "CliProviderDeps",
    "DEFAULT_TIMEOUT_MS",
    "MAX_AUDIO_OUTPUT_BYTES",
    "MAX_CLI_STDERR_BYTES",
    "RunCommandFn",
    "RunCommandResult",
    "RunFfmpegFn",
    "TempWorkspace",
    "TempWorkspaceFn",
    "VALID_OUTPUT_FORMATS",
    "apply_template",
    "build_cli_speech_provider",
    "detect_format",
    "find_audio_file",
    "get_config",
    "get_file_ext",
    "normalize_output_format",
    "parse_command",
    "read_audio_file",
    "resolve_cli_provider_config",
    "strip_emojis",
]
