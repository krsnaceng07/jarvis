"""Tests for the tts-local-cli speech provider port.

Covers the core helpers + the dependency-injected
``build_cli_speech_provider`` flow.

Mirrors a subset of OpenClaw's
``extensions/tts-local-cli/speech-provider.test.ts`` and
``extensions/tts-local-cli/speech-provider-stream-error.test.ts``.

The extension directory uses a hyphen (``tts-local-cli``)
which is not a valid Python identifier; the import path
reaches the module via direct ``importlib.util`` loading
to avoid the namespace collision and the
``sys.path.insert`` race that pytest triggers in
full-suite collection.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_ROOT = os.path.dirname(_THIS_DIR)
if _EXT_ROOT not in sys.path:
    sys.path.insert(0, _EXT_ROOT)


def _load_module(name: str, file_path: str):
    """Load a Python module from ``file_path`` under ``name``."""
    spec = importlib.util.spec_from_file_location(name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module {name!r} from {file_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_LIB_PATH = os.path.join(_EXT_ROOT, "lib", "speech_provider.py")
_speech_provider = _load_module("tts_local_cli_speech_provider", _LIB_PATH)

# Re-export the public surface for the test body.
AUDIO_EXTENSIONS = _speech_provider.AUDIO_EXTENSIONS
CliProviderDeps = _speech_provider.CliProviderDeps
DEFAULT_TIMEOUT_MS = _speech_provider.DEFAULT_TIMEOUT_MS
MAX_AUDIO_OUTPUT_BYTES = _speech_provider.MAX_AUDIO_OUTPUT_BYTES
MAX_CLI_STDERR_BYTES = _speech_provider.MAX_CLI_STDERR_BYTES
apply_template = _speech_provider.apply_template
build_cli_speech_provider = _speech_provider.build_cli_speech_provider
detect_format = _speech_provider.detect_format
find_audio_file = _speech_provider.find_audio_file
get_config = _speech_provider.get_config
get_file_ext = _speech_provider.get_file_ext
normalize_output_format = _speech_provider.normalize_output_format
parse_command = _speech_provider.parse_command
resolve_cli_provider_config = _speech_provider.resolve_cli_provider_config
strip_emojis = _speech_provider.strip_emojis

from jarvis_sdk.api import (  # noqa: E402
    PluginApi,
)
from jarvis_sdk.context import (  # noqa: E402
    PluginContext,
)
from jarvis_sdk.speech_provider import (  # noqa: E402
    VALID_SPEECH_OUTPUT_FORMATS,
)


# ── Test helpers ─────────────────────────────────────────


def _ctx() -> tuple[PluginApi, CliProviderDeps]:
    """Build a PluginApi + CliProviderDeps pair for testing."""
    ctx = PluginContext(plugin_id="tts-local-cli", plugin_kind="provider")
    api = PluginApi(ctx)
    return api, CliProviderDeps()


class _FakeWriter:
    """Minimal stand-in for the host's ``tempWorkspace`` write callback."""

    def __init__(self) -> None:
        self.written: list[tuple[str, bytes]] = []

    async def __call__(self, name: str, data: bytes) -> None:
        self.written.append((name, data))


# ── Helpers ──────────────────────────────────────────────


class TestStripEmojis:
    def test_removes_emoji_presentation(self) -> None:
        assert strip_emojis("hello 🌍 world") == "hello world"

    def test_collapses_whitespace(self) -> None:
        assert strip_emojis("a  b\tc") == "a b c"

    def test_returns_empty_for_empty(self) -> None:
        assert strip_emojis("") == ""

    def test_returns_empty_for_emoji_only(self) -> None:
        assert strip_emojis("🎉") == ""


class TestApplyTemplate:
    def test_substitutes_known_key(self) -> None:
        assert apply_template("{{Text}}", {"Text": "hi"}) == "hi"

    def test_case_insensitive(self) -> None:
        assert apply_template("{{text}}", {"Text": "hi"}) == "hi"
        assert apply_template("{{TEXT}}", {"Text": "hi"}) == "hi"

    def test_unknown_key_becomes_empty(self) -> None:
        assert apply_template("{{Missing}}", {"Text": "hi"}) == ""

    def test_no_template_passthrough(self) -> None:
        assert apply_template("plain text", {"Text": "hi"}) == "plain text"

    def test_mixed_template(self) -> None:
        assert (
            apply_template(
                "echo {{Text}} > {{OutputPath}}",
                {"Text": "hello", "OutputPath": "/tmp/out"},
            )
            == "echo hello > /tmp/out"
        )


class TestParseCommand:
    def test_splits_simple(self) -> None:
        assert parse_command("echo hi") == {
            "cmd": "echo",
            "initialArgs": ["hi"],
        }

    def test_splits_with_double_quotes(self) -> None:
        assert parse_command('echo "hello world"') == {
            "cmd": "echo",
            "initialArgs": ["hello world"],
        }

    def test_splits_with_single_quotes(self) -> None:
        assert parse_command("echo 'hello world'") == {
            "cmd": "echo",
            "initialArgs": ["hello world"],
        }

    def test_handles_empty(self) -> None:
        assert parse_command("") == {"cmd": "", "initialArgs": []}

    def test_handles_only_spaces(self) -> None:
        assert parse_command("   ") == {"cmd": "", "initialArgs": []}


class TestGetConfig:
    def test_returns_none_when_command_missing(self) -> None:
        assert get_config({}) is None
        assert get_config({"command": ""}) is None
        assert get_config({"command": "  "}) is None

    def test_returns_config_for_valid_command(self) -> None:
        config = get_config(
            {
                "command": "piper",
                "args": ["--model", "en_US-amy"],
                "outputFormat": "wav",
                "timeoutMs": 30_000,
            }
        )
        assert config is not None
        assert config["command"] == "piper"
        assert config["args"] == ["--model", "en_US-amy"]
        assert config["outputFormat"] == "wav"
        assert config["timeoutMs"] == 30_000

    def test_defaults_to_mp3_format(self) -> None:
        config = get_config({"command": "piper"})
        assert config is not None
        assert config["outputFormat"] == "mp3"

    def test_defaults_timeout(self) -> None:
        config = get_config({"command": "piper"})
        assert config is not None
        assert config["timeoutMs"] == DEFAULT_TIMEOUT_MS


class TestNormalizeOutputFormat:
    def test_lowercases_known(self) -> None:
        assert normalize_output_format("MP3") == "mp3"
        assert normalize_output_format("Opus") == "opus"
        assert normalize_output_format("WAV") == "wav"

    def test_falls_back_to_mp3_for_unknown(self) -> None:
        assert normalize_output_format("flac") == "mp3"
        assert normalize_output_format("") == "mp3"
        assert normalize_output_format(None) == "mp3"  # type: ignore[arg-type]


class TestGetFileExt:
    def test_returns_canonical_extension(self) -> None:
        assert get_file_ext("mp3") == ".mp3"
        assert get_file_ext("opus") == ".opus"
        assert get_file_ext("wav") == ".wav"
        assert get_file_ext("unknown") == ".mp3"


class TestDetectFormat:
    def test_detects_known_extensions(self) -> None:
        assert detect_format("/tmp/speech.mp3") == "mp3"
        assert detect_format("/tmp/speech.opus") == "opus"
        assert detect_format("/tmp/speech.ogg") == "opus"
        assert detect_format("/tmp/speech.wav") == "wav"
        assert detect_format("/tmp/speech.m4a") == "mp3"

    def test_returns_none_for_unknown(self) -> None:
        assert detect_format("/tmp/speech.txt") is None
        assert detect_format("/tmp/speech") is None


class TestResolveCliProviderConfig:
    def test_returns_empty_for_no_providers(self) -> None:
        assert resolve_cli_provider_config({}) == {}
        assert resolve_cli_provider_config({"providers": None}) == {}

    def test_returns_tts_local_cli_block(self) -> None:
        raw = {
            "providers": {
                "tts-local-cli": {"command": "piper", "args": []},
                "other": {"command": "x"},
            }
        }
        result = resolve_cli_provider_config(raw)
        assert result == {"command": "piper", "args": []}

    def test_falls_back_to_cli_alias(self) -> None:
        raw = {"providers": {"cli": {"command": "espeak"}}}
        assert resolve_cli_provider_config(raw) == {"command": "espeak"}

    def test_prefers_tts_local_cli_over_cli(self) -> None:
        raw = {
            "providers": {
                "tts-local-cli": {"command": "piper"},
                "cli": {"command": "espeak"},
            }
        }
        assert resolve_cli_provider_config(raw) == {"command": "piper"}


# ── find_audio_file (filesystem-backed) ─────────────────


class TestFindAudioFile:
    def test_prefers_file_matching_base_name(self, tmp_path) -> None:
        (tmp_path / "speech-001.mp3").write_bytes(b"hi")
        (tmp_path / "other.wav").write_bytes(b"other")
        result = find_audio_file(str(tmp_path), "speech")
        assert result == str(tmp_path / "speech-001.mp3")

    def test_falls_back_to_any_audio_file(self, tmp_path) -> None:
        (tmp_path / "random.wav").write_bytes(b"hi")
        result = find_audio_file(str(tmp_path), "speech")
        assert result == str(tmp_path / "random.wav")

    def test_returns_none_when_no_audio(self, tmp_path) -> None:
        (tmp_path / "text.txt").write_bytes(b"hi")
        assert find_audio_file(str(tmp_path), "speech") is None

    def test_returns_none_for_missing_dir(self) -> None:
        assert find_audio_file("/nonexistent/path", "speech") is None


# ── build_cli_speech_provider (DI flow) ─────────────────


class TestBuildCliSpeechProvider:
    def test_returns_provider_with_id_and_label(self) -> None:
        provider = build_cli_speech_provider()
        assert provider["id"] == "tts-local-cli"
        assert provider["label"] == "Local CLI"

    def test_registers_via_sdk(self) -> None:
        api, _ = _ctx()
        provider = build_cli_speech_provider()
        api.register_speech_provider(provider)
        assert len(api.speech_providers) == 1
        assert api.speech_providers[0]["id"] == "tts-local-cli"

    def test_synthesize_raises_when_run_command_not_wired(self, tmp_path) -> None:
        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": _FakeWriter()}

        deps = CliProviderDeps(
            run_command=None,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        with pytest.raises(RuntimeError, match="run_command"):
            asyncio.run(
                provider["synthesize"](
                    {
                        "text": "hello",
                        "providerConfig": {"command": "piper"},
                    }
                )
            )

    def test_synthesize_raises_when_temp_workspace_not_wired(self) -> None:
        deps = CliProviderDeps(
            run_command=lambda cmd, opts: asyncio.sleep(0),
            temp_workspace=None,
        )
        provider = build_cli_speech_provider(deps=deps)
        with pytest.raises(RuntimeError, match="temp_workspace"):
            asyncio.run(
                provider["synthesize"](
                    {
                        "text": "hello",
                        "providerConfig": {"command": "piper"},
                    }
                )
            )

    def test_synthesize_raises_when_not_configured(self) -> None:
        writer = _FakeWriter()

        async def temp_workspace(opts):
            return {"dir": str(opts.get("dir", "/tmp")), "write": writer}

        deps = CliProviderDeps(
            run_command=lambda cmd, opts: asyncio.sleep(0),
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        with pytest.raises(RuntimeError, match="not configured"):
            asyncio.run(
                provider["synthesize"](
                    {
                        "text": "hello",
                        "providerConfig": {},
                    }
                )
            )

    def test_synthesize_returns_audio_on_stdout(self, tmp_path) -> None:
        writer = _FakeWriter()
        captured: list[list[str]] = []

        async def run_command(cmd, opts):
            captured.append(cmd)
            return {
                "code": 0,
                "stdout": b"FAKE_WAV_DATA",
                "stderr": b"",
                "termination": "exit",
            }

        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": writer}

        deps = CliProviderDeps(
            run_command=run_command,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        result = asyncio.run(
            provider["synthesize"](
                {
                    "text": "hello world",
                    "providerConfig": {
                        "command": "piper",
                        "args": ["--output", "{{OutputPath}}"],
                        "outputFormat": "wav",
                    },
                }
            )
        )
        assert result["audio"] == b"FAKE_WAV_DATA"
        assert result["format"] == "wav"
        # Command was constructed from the configured
        # command + args + template substitution.
        assert captured[0][0] == "piper"
        assert captured[0][1:] == [
            "--output",
            str(tmp_path / "speech.wav"),
        ]

    def test_synthesize_raises_on_nonzero_exit(self, tmp_path) -> None:
        async def run_command(cmd, opts):
            return {
                "code": 1,
                "stdout": b"",
                "stderr": b"something went wrong",
                "termination": "exit",
            }

        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": _FakeWriter()}

        deps = CliProviderDeps(
            run_command=run_command,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        with pytest.raises(RuntimeError, match="exit 1"):
            asyncio.run(
                provider["synthesize"](
                    {
                        "text": "hello",
                        "providerConfig": {"command": "piper"},
                    }
                )
            )

    def test_synthesize_raises_on_timeout(self, tmp_path) -> None:
        async def run_command(cmd, opts):
            return {
                "code": None,
                "stdout": b"",
                "stderr": b"",
                "termination": "timeout",
            }

        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": _FakeWriter()}

        deps = CliProviderDeps(
            run_command=run_command,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        with pytest.raises(TimeoutError, match="timed out"):
            asyncio.run(
                provider["synthesize"](
                    {
                        "text": "hello",
                        "providerConfig": {"command": "piper"},
                    }
                )
            )

    def test_synthesize_reads_file_from_workspace(self, tmp_path) -> None:
        # Pretend the CLI wrote a file in the workspace.
        audio_path = tmp_path / "speech.wav"
        audio_path.write_bytes(b"WAV_FROM_FILE")
        captured: list[list[str]] = []

        async def run_command(cmd, opts):
            captured.append(cmd)
            return {
                "code": 0,
                "stdout": b"",
                "stderr": b"",
                "termination": "exit",
            }

        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": _FakeWriter()}

        deps = CliProviderDeps(
            run_command=run_command,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        result = asyncio.run(
            provider["synthesize"](
                {
                    "text": "hello",
                    "providerConfig": {"command": "piper"},
                }
            )
        )
        assert result["audio"] == b"WAV_FROM_FILE"
        assert result["format"] == "wav"
        assert result["sourcePath"] == str(audio_path)

    def test_synthesize_raises_on_empty_text_after_strip(self, tmp_path) -> None:
        async def run_command(cmd, opts):
            return {
                "code": 0,
                "stdout": b"",
                "stderr": b"",
                "termination": "exit",
            }

        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": _FakeWriter()}

        deps = CliProviderDeps(
            run_command=run_command,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        with pytest.raises(ValueError, match="text is required"):
            asyncio.run(
                provider["synthesize"](
                    {
                        "text": "",
                        "providerConfig": {"command": "piper"},
                    }
                )
            )

    def test_synthesize_strips_emoji_before_running(self, tmp_path) -> None:
        captured_inputs: list[str] = []

        async def run_command(cmd, opts):
            captured_inputs.append(opts.get("input", ""))
            return {
                "code": 0,
                "stdout": b"OK",
                "stderr": b"",
                "termination": "exit",
            }

        async def temp_workspace(opts):
            return {"dir": str(tmp_path), "write": _FakeWriter()}

        deps = CliProviderDeps(
            run_command=run_command,
            temp_workspace=temp_workspace,
        )
        provider = build_cli_speech_provider(deps=deps)
        asyncio.run(
            provider["synthesize"](
                {
                    "text": "hello 🌍 world",
                    "providerConfig": {"command": "piper"},
                }
            )
        )
        assert captured_inputs[0] == "hello world"


# ── Output format membership set ───────────────────────


def test_output_format_membership_set() -> None:
    assert VALID_SPEECH_OUTPUT_FORMATS == frozenset({"mp3", "opus", "wav"})


def test_audio_extensions_set() -> None:
    assert ".wav" in AUDIO_EXTENSIONS
    assert ".mp3" in AUDIO_EXTENSIONS
    assert ".opus" in AUDIO_EXTENSIONS


def test_max_bytes_constants() -> None:
    assert MAX_AUDIO_OUTPUT_BYTES == 50 * 1024 * 1024
    assert MAX_CLI_STDERR_BYTES == 1024 * 1024


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
