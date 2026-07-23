"""Tests for memory_core.dreaming_command — Phase 4.4i.

Mirrors the TypeScript ``test_dreaming-command.test.ts`` patterns.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from extensions.memory_core import dreaming_command as dc


# ── Test helpers ──────────────────────────────────────────────────────


class _RuntimeConfig:
    def __init__(self, config: dict) -> None:
        self._config = config

    def current(self) -> dict:
        return self._config


class _Api:
    """Minimal plugin API stub for the command handler."""

    def __init__(self, config: dict) -> None:
        self.runtime = SimpleNamespace(config=_RuntimeConfig(config))


def _ctx(args: str = "", sender_is_owner: bool = False, gateway_scopes: list[str] | None = None) -> dict:
    return {
        "args": args,
        "senderIsOwner": sender_is_owner,
        "gatewayClientScopes": gateway_scopes,
    }


# ── Config helpers ───────────────────────────────────────────────────


def test_resolve_dreaming_plugin_config_valid() -> None:
    """``memory-core`` plugin config is extracted."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {
                    "config": {"dreaming": {"enabled": True, "frequency": "0 4 * * *"}}
                }
            }
        }
    }
    result = dc.resolve_dreaming_plugin_config(cfg)
    assert result == {"dreaming": {"enabled": True, "frequency": "0 4 * * *"}}


def test_resolve_dreaming_plugin_config_empty() -> None:
    """Missing plugin entries → empty dict."""
    assert dc.resolve_dreaming_plugin_config({}) == {}
    assert dc.resolve_dreaming_plugin_config({"plugins": {}}) == {}
    assert dc.resolve_dreaming_plugin_config({"plugins": {"entries": {}}}) == {}


def test_update_dreaming_enabled_in_config_enables() -> None:
    """``enabled=True`` is set in the dreaming config."""
    cfg = {"plugins": {"entries": {"memory-core": {"config": {"dreaming": {"enabled": False}}}}}}
    result = dc.update_dreaming_enabled_in_config(cfg, enabled=True)
    dreaming = result["plugins"]["entries"]["memory-core"]["config"]["dreaming"]
    assert dreaming["enabled"] is True


def test_update_dreaming_enabled_in_config_disables() -> None:
    """``enabled=False`` is set in the dreaming config."""
    cfg = {"plugins": {"entries": {"memory-core": {"config": {"dreaming": {"enabled": True, "frequency": "0 4 * * *"}}}}}}
    result = dc.update_dreaming_enabled_in_config(cfg, enabled=False)
    dreaming = result["plugins"]["entries"]["memory-core"]["config"]["dreaming"]
    assert dreaming["enabled"] is False
    # Other fields preserved
    assert dreaming["frequency"] == "0 4 * * *"


def test_update_dreaming_enabled_in_config_creates_plugin_entry() -> None:
    """Missing ``memory-core`` entry is created."""
    cfg = {"plugins": {"entries": {}}}
    result = dc.update_dreaming_enabled_in_config(cfg, enabled=True)
    assert "memory-core" in result["plugins"]["entries"]
    assert result["plugins"]["entries"]["memory-core"]["config"]["dreaming"]["enabled"] is True


def test_update_dreaming_enabled_in_config_pure() -> None:
    """Input is not mutated."""
    cfg = {"plugins": {"entries": {"memory-core": {"config": {"dreaming": {"enabled": False}}}}}}
    dc.update_dreaming_enabled_in_config(cfg, enabled=True)
    # Original still has enabled=False
    assert cfg["plugins"]["entries"]["memory-core"]["config"]["dreaming"]["enabled"] is False


# ── Status formatting ───────────────────────────────────────────────


def test_format_status_enabled() -> None:
    """Enabled status block includes on + timezone + cadence + policy."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {
                    "config": {
                        "dreaming": {
                            "enabled": True,
                            "frequency": "0 4 * * *",
                            "timezone": "Asia/Kathmandu",
                        },
                        "deep": {"minScore": 0.9, "minRecallCount": 4, "minUniqueQueries": 5},
                    }
                }
            }
        }
    }
    text = dc.format_status(cfg)
    assert "Dreaming status:" in text
    assert "- enabled: on (Asia/Kathmandu)" in text
    assert "- sweep cadence: 0 4 * * *" in text
    assert "score>=0.9" in text
    assert "recalls>=4" in text
    assert "uniqueQueries>=5" in text


def test_format_status_disabled_no_timezone() -> None:
    """Disabled status without timezone omits the timezone suffix."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {
                    "config": {"dreaming": {"enabled": False, "frequency": "0 3 * * *"}}
                }
            }
        }
    }
    text = dc.format_status(cfg)
    assert "- enabled: off" in text
    assert "(Asia/Kathmandu)" not in text


def test_format_status_uses_default_promotion_policy() -> None:
    """Default policy is used when no deep config is present."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {
                    "config": {"dreaming": {"enabled": True, "frequency": "0 3 * * *"}}
                }
            }
        }
    }
    text = dc.format_status(cfg)
    assert "score>=0.8" in text
    assert "recalls>=3" in text
    assert "uniqueQueries>=3" in text


# ── Permission check ─────────────────────────────────────────────────


def test_lacks_admin_or_owner_channel_owner_allowed() -> None:
    """Channel owner is allowed to mutate."""
    assert dc._lacks_admin_or_owner_for_dreaming_mutation(None, True) is False


def test_lacks_admin_or_owner_channel_non_owner_denied() -> None:
    """Non-owner channel caller is denied."""
    assert dc._lacks_admin_or_owner_for_dreaming_mutation(None, False) is True
    assert dc._lacks_admin_or_owner_for_dreaming_mutation(None, None) is True


def test_lacks_admin_or_owner_gateway_admin_allowed() -> None:
    """Gateway client with ``operator.admin`` scope is allowed."""
    assert dc._lacks_admin_or_owner_for_dreaming_mutation(["operator.admin"], False) is False


def test_lacks_admin_or_owner_gateway_no_admin_denied() -> None:
    """Gateway client without ``operator.admin`` is denied."""
    assert dc._lacks_admin_or_owner_for_dreaming_mutation(["operator.read"], False) is True
    assert dc._lacks_admin_or_owner_for_dreaming_mutation([], False) is True


# ── handle_dreaming_command dispatch ─────────────────────────────────


def test_handle_dreaming_command_no_args() -> None:
    """Empty args → usage + status."""
    api = _Api({})
    result = asyncio.run(dc.handle_dreaming_command(api, _ctx(args="")))
    assert "Usage: /dreaming status" in result["text"]
    assert "Phases:" in result["text"]
    assert "Dreaming status:" in result["text"]


def test_handle_dreaming_command_help() -> None:
    """``help`` / ``options`` / ``phases`` → usage + status."""
    for token in ("help", "options", "phases"):
        api = _Api({})
        result = asyncio.run(dc.handle_dreaming_command(api, _ctx(args=token)))
        assert "Usage:" in result["text"], token


def test_handle_dreaming_command_status() -> None:
    """``status`` → just the status block."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {
                    "config": {"dreaming": {"enabled": True, "frequency": "0 4 * * *"}}
                }
            }
        }
    }
    api = _Api(cfg)
    result = asyncio.run(dc.handle_dreaming_command(api, _ctx(args="status")))
    assert "Dreaming status:" in result["text"]
    assert "Usage:" not in result["text"]


def test_handle_dreaming_command_on_owner() -> None:
    """``on`` from channel owner → enabled + status."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {"config": {"dreaming": {"enabled": False}}}
            }
        }
    }
    api = _Api(cfg)
    result = asyncio.run(
        dc.handle_dreaming_command(api, _ctx(args="on", sender_is_owner=True))
    )
    assert "Dreaming enabled." in result["text"]
    assert "- enabled: on" in result["text"]


def test_handle_dreaming_command_off_gateway_admin() -> None:
    """``off`` from gateway client with ``operator.admin`` → disabled + status."""
    cfg = {
        "plugins": {
            "entries": {
                "memory-core": {"config": {"dreaming": {"enabled": True}}}
            }
        }
    }
    api = _Api(cfg)
    result = asyncio.run(
        dc.handle_dreaming_command(
            api, _ctx(args="off", gateway_scopes=["operator.admin"])
        )
    )
    assert "Dreaming disabled." in result["text"]
    assert "- enabled: off" in result["text"]


def test_handle_dreaming_command_on_denied() -> None:
    """``on`` from non-owner / non-admin → permission error."""
    api = _Api({})
    result = asyncio.run(
        dc.handle_dreaming_command(api, _ctx(args="on", sender_is_owner=False))
    )
    assert "⚠️" in result["text"]
    assert "owner" in result["text"] or "admin" in result["text"]


def test_handle_dreaming_command_off_denied_gateway() -> None:
    """``off`` from gateway client without admin scope → permission error."""
    api = _Api({})
    result = asyncio.run(
        dc.handle_dreaming_command(
            api, _ctx(args="off", gateway_scopes=["operator.read"])
        )
    )
    assert "⚠️" in result["text"]


def test_handle_dreaming_command_unknown_token() -> None:
    """Unknown token → usage + status (graceful fallback)."""
    api = _Api({})
    result = asyncio.run(
        dc.handle_dreaming_command(api, _ctx(args="bogus"))
    )
    assert "Usage:" in result["text"]
    assert "Dreaming status:" in result["text"]


def test_handle_dreaming_command_extra_args_ignored() -> None:
    """Extra whitespace-separated tokens after the first are ignored."""
    api = _Api({})
    result = asyncio.run(
        dc.handle_dreaming_command(api, _ctx(args="status --verbose"))
    )
    assert "Dreaming status:" in result["text"]
