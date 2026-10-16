"""Contract tests for the generic provider/channel SDK seams.

Mirrors OpenClaw's ``src/plugin-sdk/`` parity: closed channel-action
vocabulary, typed presentation actions (no raw-string inference),
static channel capabilities, provider route-resolution union, stream
wrapper composition, and honest ``not_implemented`` defaults so the
existing stub extensions keep loading unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

from jarvis_sdk import (
    ApprovalAction,
    CHANNEL_MESSAGE_ACTION_NAMES,
    ChannelCapabilities,
    ChannelPlugin,
    CommandAction,
    IncompatibleResolution,
    IndeterminateResolution,
    Ok,
    ProviderModelRouteCandidate,
    ProviderPlugin,
    Result,
    RoutesResolution,
    SelectAction,
    TextAction,
    UrlAction,
    action_kind,
    compose_provider_stream_wrappers,
    is_known_message_action,
    validate_action,
)
from jarvis_sdk.api import PluginApi
from jarvis_sdk.context import PluginContext


# ── Closed action vocabulary ──────────────────────────────────────


def test_closed_vocabulary_matches_openclaw_count() -> None:
    """The closed list tracks OpenClaw's 57 message-action names."""
    assert len(CHANNEL_MESSAGE_ACTION_NAMES) == 57
    assert len(set(CHANNEL_MESSAGE_ACTION_NAMES)) == 57


def test_is_known_message_action() -> None:
    assert is_known_message_action("send") is True
    assert is_known_message_action("thread-reply") is True
    assert is_known_message_action("/start") is False
    assert is_known_message_action("") is False


def test_action_kinds_stay_distinguishable() -> None:
    """Approval/command/url/select/text never collapse to one string shape."""
    actions = [
        TextAction(text="hi"),
        CommandAction(command="/start", label="Start"),
        ApprovalAction(approval_id="a1", label="Deploy?"),
        UrlAction(url="https://example.com", label="Open"),
        SelectAction(options=("a", "b"), label="Pick"),
    ]
    assert [action_kind(a) for a in actions] == [
        "text",
        "command",
        "approval",
        "url",
        "select",
    ]


@pytest.mark.parametrize(
    "action",
    [
        TextAction(text="ok"),
        CommandAction(command="/x"),
        ApprovalAction(approval_id="a"),
        UrlAction(url="https://example.com"),
        SelectAction(options=("a",)),
    ],
)
def test_validate_action_accepts_well_formed(action: Any) -> None:
    assert validate_action(action) is action


@pytest.mark.parametrize(
    "action",
    [
        CommandAction(command=""),
        ApprovalAction(approval_id=""),
        UrlAction(url=""),
        SelectAction(options=()),
    ],
)
def test_validate_action_rejects_empty_payload(action: Any) -> None:
    with pytest.raises(ValueError):
        validate_action(action)


# ── Channel capabilities + defaults ───────────────────────────────


def test_channel_capabilities_default_absent() -> None:
    """A minimal channel honestly reports no optional capabilities."""
    caps = ChannelCapabilities()
    assert caps.chat_types == ()
    assert caps.polls is False
    assert caps.media is False
    assert caps.native_commands is False


class _MinimalChannel(ChannelPlugin):
    id = "test-channel"
    kind = "channel"
    version = "0.1.0"
    description = "test"

    def init(self, ctx: Any) -> None:
        return None

    async def send(self, target: str, message: Any) -> Result[None]:
        return Ok(None)

    async def listen(self, callback: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_channel_send_typed_text_delegates_to_send() -> None:
    ch = _MinimalChannel()
    out = await ch.send_typed("t", TextAction(text="hi"))
    assert out.is_ok


@pytest.mark.asyncio
async def test_channel_send_typed_other_kinds_are_honest() -> None:
    """Non-text actions are not guessed into a rendering by default."""
    ch = _MinimalChannel()
    out = await ch.send_typed("t", CommandAction(command="/x"))
    assert out.is_err
    assert out.code == "not_implemented"


def test_channel_normalize_inbound_keeps_raw() -> None:
    ch = _MinimalChannel()
    event = ch.normalize_inbound({"chat": 1})
    assert event["raw"] == {"chat": 1}


def test_channel_doctor_contract_default_skipped() -> None:
    assert _MinimalChannel().doctor_contract() == {"status": "not_implemented"}


# ── Provider route union + defaults ───────────────────────────────


def test_route_resolutions_are_distinct_kinds() -> None:
    routes = RoutesResolution(
        routes=(ProviderModelRouteCandidate(api="openai", base_url="https://x"),),
        default_runtime_id="openclaw",
    )
    assert routes.kind == "routes"
    assert IndeterminateResolution().kind == "indeterminate"
    assert IncompatibleResolution(code="c", message="m").kind == "incompatible"


class _MinimalProvider(ProviderPlugin):
    id = "test-provider"
    kind = "provider"
    version = "0.1.0"
    description = "test"

    def init(self, ctx: Any) -> None:
        return None

    async def complete(self, messages: list[dict[str, Any]], **kwargs: Any) -> Result[str]:
        return Ok("done")

    def list_models(self) -> list[str]:
        return ["m1"]


@pytest.mark.asyncio
async def test_provider_defaults_are_honest() -> None:
    """Optional seams default to Err/empty so stubs keep loading."""
    p = _MinimalProvider()
    assert [r async for r in p.astream([])][0].code == "not_implemented"
    out = await p.complete_with_tools([], [])
    assert out.is_err and out.code == "not_implemented"
    assert p.list_models_detail() == []
    assert p.resolve_auth({}).code == "not_implemented"
    assert p.build_catalog().code == "not_implemented"


# ── Stream wrapper composition ────────────────────────────────────


def test_compose_wrappers_apply_left_to_right_and_skip_falsey() -> None:
    def add_a(fn: Any) -> Any:
        return lambda: (fn() if callable(fn) else fn) + "a"

    def add_b(fn: Any) -> Any:
        return lambda: (fn() if callable(fn) else fn) + "b"

    composed = compose_provider_stream_wrappers(lambda: "", add_a, None, False, add_b)
    assert composed is not None
    assert composed() == "ab"


def test_compose_with_no_base_and_no_wrappers_returns_none() -> None:
    assert compose_provider_stream_wrappers(None) is None


# ── Manifest metadata passthrough ─────────────────────────────────


def test_manifest_passthrough_readback() -> None:
    ctx = PluginContext(plugin_id="p", plugin_kind="channel")
    api = PluginApi(ctx)
    api.set_manifest(
        {
            "id": "p",
            "channels": ["telegram"],
            "providers": ["openai"],
            "cliCommands": ["login"],
            "doctorContract": {"migrations": []},
        }
    )
    assert api.manifest_channels == ["telegram"]
    assert api.manifest_providers == ["openai"]
    assert api.manifest_cli_commands == ["login"]
    assert api.manifest_doctor_contract == {"migrations": []}


def test_manifest_passthrough_absent_yields_empty() -> None:
    ctx = PluginContext(plugin_id="p", plugin_kind="tool")
    api = PluginApi(ctx)
    api.set_manifest({"id": "p"})
    assert api.manifest_channels == []
    assert api.manifest_providers == []
    assert api.manifest_cli_commands == []
    assert api.manifest_doctor_contract is None
