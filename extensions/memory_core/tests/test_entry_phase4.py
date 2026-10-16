"""Tests for memory_core.__init__ Phase 4.4k wiring.

Verifies the entry point wires the dreaming pipeline correctly:
- Plugin entry metadata is correct (id, kind, version, etc.)
- _configure_dreaming_state wires the host's keyed store factory
- /dreaming command handler routes through dreaming_command.handle_dreaming_command
- _register calls dreaming_module.register_short_term_promotion_dreaming
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


from extensions.memory_core import dreaming_state
import extensions.memory_core as memory_core_module


# ── Test helpers ──────────────────────────────────────────────────────


def _make_api_with_state() -> SimpleNamespace:
    """Build a minimal PluginApi stub with a working state factory."""

    def _open_keyed(options: dict) -> object:
        return SimpleNamespace(entries=lambda: [], delete=lambda k: None, write=lambda k, v: None)

    state = SimpleNamespace(open_keyed_store=_open_keyed)
    runtime = SimpleNamespace(state=state)
    return SimpleNamespace(runtime=runtime)


# ── _configure_dreaming_state ────────────────────────────────────────


def test_configure_dreaming_state_with_state() -> None:
    """When host.state.open_keyed_store is available, factory is wired."""
    api = _make_api_with_state()
    dreaming_state._configured_open_keyed_store = None
    memory_core_module._configure_dreaming_state(api)
    assert dreaming_state._configured_open_keyed_store is not None


def test_configure_dreaming_state_without_runtime() -> None:
    """No ``runtime`` attribute → no-op (factory stays unchanged)."""
    api = SimpleNamespace(runtime=None)
    dreaming_state._configured_open_keyed_store = None
    memory_core_module._configure_dreaming_state(api)
    assert dreaming_state._configured_open_keyed_store is None


def test_configure_dreaming_state_without_state() -> None:
    """No ``state`` attribute → no-op."""
    api = SimpleNamespace(runtime=SimpleNamespace(state=None))
    dreaming_state._configured_open_keyed_store = None
    memory_core_module._configure_dreaming_state(api)
    assert dreaming_state._configured_open_keyed_store is None


def test_configure_dreaming_state_without_open_keyed() -> None:
    """``state`` exists but no ``open_keyed_store`` method → no-op."""
    api = SimpleNamespace(runtime=SimpleNamespace(state=SimpleNamespace(other=lambda: None)))
    dreaming_state._configured_open_keyed_store = None
    memory_core_module._configure_dreaming_state(api)
    assert dreaming_state._configured_open_keyed_store is None


# ── /dreaming command handler ───────────────────────────────────────


def test_dreaming_command_handler_status() -> None:
    """``/dreaming status`` returns the status block."""
    ctx = SimpleNamespace(args="status", sender_is_owner=False, gateway_client_scopes=None)
    result = memory_core_module._dreaming_command_handler(ctx)
    text = getattr(result, "reply_text", "") or result.get("reply_text", "")
    assert "Dreaming status:" in text


def test_dreaming_command_handler_no_args() -> None:
    """``/dreaming`` (no args) returns usage + status."""
    ctx = SimpleNamespace(args="", sender_is_owner=False, gateway_client_scopes=None)
    result = memory_core_module._dreaming_command_handler(ctx)
    text = getattr(result, "reply_text", "") or result.get("reply_text", "")
    assert "Usage:" in text
    assert "Dreaming status:" in text


def test_dreaming_command_handler_help() -> None:
    """``/dreaming help`` returns usage."""
    ctx = SimpleNamespace(args="help", sender_is_owner=False, gateway_client_scopes=None)
    result = memory_core_module._dreaming_command_handler(ctx)
    text = getattr(result, "reply_text", "") or result.get("reply_text", "")
    assert "Usage:" in text


# ── API proxy ────────────────────────────────────────────────────────


def test_get_dreaming_api_proxy_exposes_runtime_config() -> None:
    """The proxy object exposes ``runtime.config.current()``."""
    proxy = memory_core_module._get_dreaming_api_proxy()
    assert hasattr(proxy, "runtime")
    assert hasattr(proxy.runtime, "config")
    assert callable(proxy.runtime.config.current)
    # current() should not raise
    config = proxy.runtime.config.current()
    assert isinstance(config, dict)


# ── Plugin entry metadata ───────────────────────────────────────────


def test_plugin_entry_metadata() -> None:
    """The exported entry has the expected metadata."""
    e = memory_core_module.entry
    assert e.id == "memory_core"
    assert e.kind == "memory"
    assert e.name == "Memory (Core)"
    assert callable(e.register)
    # Version was bumped to 0.3.0 for Phase 4.4
    assert e.version == "0.3.0"
    assert e.activation == "on_startup"


def test_plugin_entry_calls_dreaming_cron_registration() -> None:
    """Calling ``entry.register`` calls ``register_short_term_promotion_dreaming``."""
    api = _make_api_with_state()
    # Stub the registration paths so the test doesn't depend on the rest of the SDK
    api.register_tool = lambda plugin, opts: None  # type: ignore[method-assign]
    api.register_memory_capability = lambda cap: None  # type: ignore[method-assign]
    api.register_command = lambda cmd: None  # type: ignore[method-assign]
    api.register_doctor_contract = lambda contract: None  # type: ignore[method-assign]

    with patch(
        "extensions.memory_core.dreaming_module.register_short_term_promotion_dreaming"
    ) as mock_cron:
        mock_cron.return_value = None
        memory_core_module.entry.register(api)
    mock_cron.assert_called_once_with(api)
