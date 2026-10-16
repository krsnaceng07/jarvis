"""Tests for the foundational logbook port.

Covers the SDK surface additions (registerService,
registerGatewayMethod, registerNodeInvokePolicy,
session.controls.registerControlUiDescriptor,
api.plugin_config) plus the ported types and config
modules.

Mirrors a subset of OpenClaw's
``extensions/logbook/src/config.test.ts`` and
``extensions/logbook/src/types.test.ts``.
"""
from __future__ import annotations

import pytest

from extensions.logbook.src.logbook_config import (
    parse_model_ref,
    resolve_logbook_config,
)
from extensions.logbook.src.logbook_types import (
    LogbookCard,
    LogbookFrame,
    VALID_LOGBOOK_BATCH_STATUSES,
)
from packages.plugin_sdk.src.jarvis_sdk.api import (
    PluginApi,
    PluginControlUiDescriptor,
)
from packages.plugin_sdk.src.jarvis_sdk.context import PluginContext


# ── SDK surface ────────────────────────────────────────────


class TestPluginSdkSurfaceAdditions:
    def test_session_controls_register_descriptor(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        api.session.controls.register_control_ui_descriptor(
            {
                "surface": "tab",
                "id": "logbook",
                "label": "Logbook",
                "description": "Day as a timeline.",
                "icon": "sun",
                "group": "control",
                "requiredScopes": ["operator.write"],
            }
        )
        descriptors = api.session.controls._descriptors
        assert len(descriptors) == 1
        assert descriptors[0].id == "logbook"
        assert isinstance(descriptors[0], PluginControlUiDescriptor)

    def test_session_controls_rejects_blank_id(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        with pytest.raises(ValueError, match="non-empty 'id'"):
            api.session.controls.register_control_ui_descriptor({"id": ""})

    def test_register_service_basic(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)

        async def start(service_ctx):
            return None

        def stop():
            return None

        api.register_service(
            {"id": "logbook", "start": start, "stop": stop}
        )
        assert len(api.services) == 1
        assert api.services[0]["id"] == "logbook"
        assert api.services[0]["_owner_id"] == "t"

    def test_register_service_rejects_duplicate_id(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        api.register_service({"id": "logbook", "start": lambda c: None})
        with pytest.raises(RuntimeError, match="already registered"):
            api.register_service({"id": "logbook", "start": lambda c: None})

    def test_register_service_rejects_non_callable_start(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        with pytest.raises(ValueError, match="callable 'start'"):
            api.register_service({"id": "logbook", "start": "nope"})

    def test_register_gateway_method(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)

        async def handler(params_and_respond):
            return None

        api.register_gateway_method(
            "logbook.status", handler, {"scope": "operator.read"}
        )
        assert len(api.gateway_methods) == 1
        method = api.gateway_methods[0]
        assert method["method"] == "logbook.status"
        assert method["opts"]["scope"] == "operator.read"

    def test_register_gateway_method_rejects_duplicate(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        api.register_gateway_method("m1", lambda r: None)
        with pytest.raises(RuntimeError, match="already registered"):
            api.register_gateway_method("m1", lambda r: None)

    def test_register_node_invoke_policy(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)

        async def handle(policy_ctx):
            return {"ok": True}

        api.register_node_invoke_policy(
            {
                "commands": ["logbook.snapshot"],
                "defaultPlatforms": ["macos"],
                "handle": handle,
            }
        )
        assert len(api.node_invoke_policies) == 1
        assert api.node_invoke_policies[0]["policy"]["commands"] == [
            "logbook.snapshot"
        ]

    def test_register_node_invoke_policy_rejects_empty_commands(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        with pytest.raises(ValueError, match="non-empty 'commands'"):
            api.register_node_invoke_policy(
                {"commands": [], "handle": lambda c: None}
            )

    def test_plugin_config_property_round_trips(self) -> None:
        ctx = PluginContext(plugin_id="t", plugin_kind="infra")
        api = PluginApi(ctx)
        assert api.plugin_config is None
        api.set_plugin_config({"captureEnabled": False})
        assert api.plugin_config == {"captureEnabled": False}


# ── Types ──────────────────────────────────────────────────


class TestLogbookTypes:
    def test_batch_status_membership_set(self) -> None:
        assert VALID_LOGBOOK_BATCH_STATUSES == frozenset(
            {"pending", "running", "done", "error"}
        )

    def test_frame_construction(self) -> None:
        frame: LogbookFrame = {
            "id": 1,
            "capturedAtMs": 1_700_000_000_000,
            "day": "2026-01-01",
            "path": "/tmp/frame.jpg",
            "screenIndex": 0,
            "byteSize": 1024,
            "idle": False,
        }
        assert frame["id"] == 1
        assert frame["idle"] is False

    def test_card_construction(self) -> None:
        card: LogbookCard = {
            "id": 1,
            "day": "2026-01-01",
            "startMs": 1_700_000_000_000,
            "endMs": 1_700_000_360_000,
            "title": "Coding",
            "summary": "Wrote code.",
            "detail": "Long detail.",
            "category": "coding",
            "distractions": [],
        }
        assert card["category"] == "coding"


# ── Config ────────────────────────────────────────────────


class TestLogbookConfig:
    def test_resolve_empty_uses_defaults(self) -> None:
        config = resolve_logbook_config(None)
        assert config["captureEnabled"] is True
        assert config["captureIntervalSeconds"] == 30
        assert config["analysisIntervalMinutes"] == 15
        assert config["screenIndex"] == 0
        assert config["maxWidth"] == 1440
        assert config["retentionDays"] == 14
        assert "nodeId" not in config
        assert "visionModel" not in config

    def test_resolve_object_uses_values(self) -> None:
        config = resolve_logbook_config(
            {
                "captureEnabled": False,
                "captureIntervalSeconds": 60,
                "analysisIntervalMinutes": 30,
                "screenIndex": 2,
                "maxWidth": 1920,
                "retentionDays": 30,
                "nodeId": "node-1",
                "visionModel": "openai/gpt-4o",
            }
        )
        assert config["captureEnabled"] is False
        assert config["captureIntervalSeconds"] == 60
        assert config["analysisIntervalMinutes"] == 30
        assert config["screenIndex"] == 2
        assert config["maxWidth"] == 1920
        assert config["retentionDays"] == 30
        assert config["nodeId"] == "node-1"
        assert config["visionModel"] == "openai/gpt-4o"

    def test_clamps_capture_interval(self) -> None:
        too_low = resolve_logbook_config({"captureIntervalSeconds": 1})
        too_high = resolve_logbook_config({"captureIntervalSeconds": 9999})
        assert too_low["captureIntervalSeconds"] == 5
        assert too_high["captureIntervalSeconds"] == 600

    def test_clamps_analysis_interval(self) -> None:
        too_low = resolve_logbook_config({"analysisIntervalMinutes": 0})
        too_high = resolve_logbook_config({"analysisIntervalMinutes": 999})
        assert too_low["analysisIntervalMinutes"] == 3
        assert too_high["analysisIntervalMinutes"] == 120

    def test_clamps_screen_index(self) -> None:
        assert resolve_logbook_config({"screenIndex": -1})["screenIndex"] == 0
        assert (
            resolve_logbook_config({"screenIndex": 100})["screenIndex"] == 16
        )

    def test_clamps_max_width(self) -> None:
        assert (
            resolve_logbook_config({"maxWidth": 100})["maxWidth"] == 480
        )
        assert (
            resolve_logbook_config({"maxWidth": 9999})["maxWidth"] == 3840
        )

    def test_clamps_retention_days(self) -> None:
        assert (
            resolve_logbook_config({"retentionDays": 0})["retentionDays"] == 1
        )
        assert (
            resolve_logbook_config({"retentionDays": 9999})["retentionDays"]
            == 365
        )

    def test_blank_optional_strings_omitted(self) -> None:
        config = resolve_logbook_config({"nodeId": "  ", "visionModel": ""})
        assert "nodeId" not in config
        assert "visionModel" not in config

    def test_parse_model_ref_splits_on_first_slash(self) -> None:
        # Model ids may contain slashes; the split is on
        # the FIRST slash.
        assert parse_model_ref("openai/gpt-4o") == {
            "provider": "openai",
            "model": "gpt-4o",
        }
        assert parse_model_ref("anthropic/claude/sonnet-4-6") == {
            "provider": "anthropic",
            "model": "claude/sonnet-4-6",
        }

    def test_parse_model_ref_rejects_invalid(self) -> None:
        assert parse_model_ref("") is None
        assert parse_model_ref("noprovider/") is None
        assert parse_model_ref("/nomodel") is None
        assert parse_model_ref("nope") is None
        assert parse_model_ref(123) is None  # type: ignore[arg-type]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
