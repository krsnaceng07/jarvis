"""Phase 5.21 — TTS Local CLI entry point tests.

Covers the full ``register(api)`` flow for the
tts-local-cli plugin:
- ``register(api)`` calls ``api.registerSpeechProvider``
  with a descriptor built by ``build_cli_speech_provider``
- the descriptor exposes the standard speech-provider
  surface (``id``, ``name``, ``description``, ``binary``,
  ``default_voice``, ``synthesize``, ``stream_synthesize``,
  ``is_available``)
- the CLI command builder matches the OpenClaw source
  for espeak / say / spd-say
- the synthesize handler returns a structured result
  dict (the host routes through the voice service)
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# Load the extension's ``plugin.py`` via
# ``importlib.util.spec_from_file_location`` so the
# import doesn't depend on ``sys.path`` ordering. The
# OpenClaw naming pattern has every extension ship a
# top-level ``plugin.py``, so any extension root on
# ``sys.path`` would resolve ``plugin`` to the wrong
# file when other tests in the same suite have added
# their own extension roots to ``sys.path``.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_EXT_PARENT = os.path.dirname(_THIS_DIR)  # tests/extensions/
_TESTS_PARENT = os.path.dirname(_EXT_PARENT)  # tests/
_PROJECT_ROOT = os.path.dirname(_TESTS_PARENT)  # project root
_EXT_ROOT = os.path.join(_PROJECT_ROOT, "extensions", "tts-local-cli")
_PLUGIN_PATH = os.path.join(_EXT_ROOT, "plugin.py")
_SPEC = importlib.util.spec_from_file_location(
    "_tts_local_cli_plugin_under_test", _PLUGIN_PATH
)
_plugin = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("_tts_local_cli_plugin_under_test", _plugin)
_SPEC.loader.exec_module(_plugin)

TTSLocalCLIPlugin = _plugin.TTSLocalCLIPlugin
build_cli_speech_provider = _plugin.build_cli_speech_provider
entry = _plugin.entry
tts_local_cli_plugin = _plugin.tts_local_cli_plugin
_build_cli_command = _plugin._build_cli_command
_cli_synthesize = _plugin._cli_synthesize
_cli_stream_synthesize = _plugin._cli_stream_synthesize
_resolve_cli_binary = _plugin._resolve_cli_binary
_default_voice_for_binary = _plugin._default_voice_for_binary


# ── Plugin descriptor ──────────────────────────────────────


class TestPluginDescriptor:
    def test_descriptor_metadata(self) -> None:
        assert tts_local_cli_plugin.id == "tts-local-cli"
        assert tts_local_cli_plugin.kind == "infra"
        assert tts_local_cli_plugin.version == "0.1.0"
        assert "TTS" in tts_local_cli_plugin.description.upper()

    def test_init_is_noop(self) -> None:
        assert tts_local_cli_plugin.init({}) is None

    def test_entry_is_plugin(self) -> None:
        assert entry is tts_local_cli_plugin


# ── CLI binary detection ───────────────────────────────────


class TestCliBinaryDetection:
    def test_returns_string_when_found(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None
        )
        assert _resolve_cli_binary() == "/usr/bin/espeak"

    def test_returns_none_when_none_found(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        assert _resolve_cli_binary() is None

    def test_candidate_order_is_espeak_first(self, monkeypatch) -> None:
        """The candidate order is espeak → espeak-ng → say → spd-say."""
        calls: list[str] = []

        def _fake_which(name: str) -> Optional[str]:
            calls.append(name)
            return None

        monkeypatch.setattr("shutil.which", _fake_which)
        _resolve_cli_binary()
        assert calls == ["espeak", "espeak-ng", "say", "spd-say"]


# ── Default voice resolution ──────────────────────────────


class TestDefaultVoice:
    def test_espeak_default_voice(self) -> None:
        assert _default_voice_for_binary("/usr/bin/espeak") == "en"

    def test_espeak_ng_default_voice(self) -> None:
        assert _default_voice_for_binary("/usr/local/bin/espeak-ng") == "en"

    def test_say_default_voice(self) -> None:
        assert _default_voice_for_binary("/usr/bin/say") == "Alex"

    def test_spd_say_default_voice(self) -> None:
        assert _default_voice_for_binary("/usr/bin/spd-say") == "system"

    def test_unknown_binary_default_voice(self) -> None:
        assert _default_voice_for_binary("/usr/bin/custom-tts") is None

    def test_no_binary_default_voice(self) -> None:
        assert _default_voice_for_binary(None) is None


# ── Speech provider factory ──────────────────────────────


class TestSpeechProviderFactory:
    def test_returns_standard_surface(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None
        )
        provider = build_cli_speech_provider()
        assert provider["id"] == "tts-local-cli"
        assert provider["name"] == "Local CLI TTS"
        assert "espeak" in provider["description"].lower() or "tts" in provider["description"].lower()
        assert provider["binary"] == "/usr/bin/espeak"
        assert provider["default_voice"] == "en"
        assert provider["is_available"] is True
        assert callable(provider["synthesize"])
        assert callable(provider["stream_synthesize"])

    def test_unavailable_when_no_binary(self, monkeypatch) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        provider = build_cli_speech_provider()
        assert provider["binary"] is None
        assert provider["default_voice"] is None
        assert provider["is_available"] is False


# ── CLI command builder ───────────────────────────────────


class TestBuildCliCommand:
    def test_espeak_command_shape(self) -> None:
        cmd = _build_cli_command(
            "/usr/bin/espeak",
            "Hello, world!",
            "en",
            output_path="/tmp/out.wav",
        )
        assert cmd[0] == "/usr/bin/espeak"
        assert "-w" in cmd
        assert "/tmp/out.wav" in cmd
        assert "-v" in cmd
        assert "en" in cmd
        assert "Hello, world!" in cmd

    def test_say_command_shape(self) -> None:
        cmd = _build_cli_command(
            "/usr/bin/say", "Hello", "Alex", output_path="/tmp/out.aiff"
        )
        assert cmd[0] == "/usr/bin/say"
        assert "-o" in cmd
        assert "/tmp/out.aiff" in cmd
        assert "-v" in cmd
        assert "Alex" in cmd
        assert "Hello" in cmd

    def test_spd_say_command_shape(self) -> None:
        cmd = _build_cli_command(
            "/usr/bin/spd-say", "Hello", "system", output_path="/tmp/out.wav"
        )
        assert cmd[0] == "/usr/bin/spd-say"
        assert "-w" in cmd
        assert "/tmp/out.wav" in cmd
        assert "Hello" in cmd

    def test_espeak_with_rate_and_pitch(self) -> None:
        cmd = _build_cli_command(
            "/usr/bin/espeak",
            "Hello",
            "en",
            rate=180,
            pitch=50,
            output_path="/tmp/out.wav",
        )
        assert "-s" in cmd
        assert "180" in cmd
        assert "-p" in cmd
        assert "50" in cmd

    def test_missing_binary_raises(self) -> None:
        with pytest.raises(RuntimeError, match="binary is not available"):
            _build_cli_command(None, "Hello", None, output_path="/tmp/out.wav")

    def test_missing_output_path_raises(self) -> None:
        with pytest.raises(ValueError, match="requires an output path"):
            _build_cli_command(
                "/usr/bin/espeak", "Hello", "en", output_path=None
            )

    def test_unsupported_format_raises(self) -> None:
        with pytest.raises(ValueError, match="only wav"):
            _build_cli_command(
                "/usr/bin/espeak", "Hello", "en",
                fmt="mp3", output_path="/tmp/out.mp3",
            )


# ── Synthesize handler ─────────────────────────────────────


class TestSynthesizeHandler:
    def test_returns_no_local_cli_when_binary_missing(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        result = _cli_synthesize("Hello", output_path="/tmp/out.wav")
        assert result["ok"] is False
        assert result["reason"] == "no_local_tts_cli"
        assert result["text"] == "Hello"

    def test_returns_missing_output_path(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None
        )
        result = _cli_synthesize("Hello")
        assert result["ok"] is False
        assert result["reason"] == "missing_output_path"

    def test_returns_subprocess_result(
        self, monkeypatch, tmp_path
    ) -> None:
        """The handler delegates to ``subprocess.run`` and
        returns the captured stdout / stderr / returncode."""
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None
        )
        captured: dict = {}

        class _FakeResult:
            returncode = 0
            stdout = "ok"
            stderr = ""

        def _fake_run(command, **_kwargs):
            captured["command"] = command
            return _FakeResult()

        monkeypatch.setattr("subprocess.run", _fake_run)
        output_path = str(tmp_path / "out.wav")
        result = _cli_synthesize(
            "Hello", voice="en", output_path=output_path
        )
        assert result["ok"] is True
        assert result["returncode"] == 0
        assert result["stdout"] == "ok"
        assert result["output_path"] == output_path
        # The command shape is the espeak one.
        assert captured["command"][0] == "/usr/bin/espeak"
        assert "-w" in captured["command"]
        assert "Hello" in captured["command"]

    def test_returns_failure_on_nonzero_returncode(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None
        )

        class _FakeResult:
            returncode = 1
            stdout = ""
            stderr = "espeak: error"

        monkeypatch.setattr(
            "subprocess.run",
            lambda _command, **_kwargs: _FakeResult(),
        )
        output_path = str(tmp_path / "out.wav")
        result = _cli_synthesize("Hello", output_path=output_path)
        assert result["ok"] is False
        assert result["returncode"] == 1
        assert "espeak: error" in result["stderr"]


# ── Stream synthesize (stub) ──────────────────────────────


class TestStreamSynthesize:
    def test_stream_synthesize_returns_empty_when_no_binary(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda _name: None)
        chunks = list(_cli_stream_synthesize("Hello"))
        assert chunks == []

    def test_stream_synthesize_returns_stub_when_binary_available(
        self, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/espeak" if name == "espeak" else None
        )
        chunks = list(_cli_stream_synthesize("Hello"))
        # The in-port stub yields a single empty bytes
        # chunk (the real streaming synthesis lands in
        # a follow-up phase).
        assert chunks == [b""]


# ── register(api) flow ──────────────────────────────────────


class TestRegisterApi:
    def test_register_calls_register_speech_provider(self) -> None:
        api = _RecordingApi()
        tts_local_cli_plugin.register(api)
        assert len(api.providers) == 1
        provider = api.providers[0]
        assert provider["id"] == "tts-local-cli"
        assert callable(provider["synthesize"])


class _RecordingApi:
    """Minimal API surface for the register() flow tests."""

    def __init__(self) -> None:
        self.providers: list[dict] = []
        self.plugin_config: dict = {}

    def register_speech_provider(self, provider: dict) -> None:
        self.providers.append(provider)
