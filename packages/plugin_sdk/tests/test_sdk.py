"""Property tests for the JARVIS plugin SDK.

Phase 1C: drives ``Result``, ``ToolDecl``, ``PluginCommandContext``, and
``CommandDecl`` through hypothesis to pin the contract. These are
not feature tests — they exist so a refactor of the SDK that breaks
the contract (e.g. flattens ``Result``, drops ``match()``, makes
``handler`` optional again) is caught before a downstream extension
inherits the bug.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest
from hypothesis import given, strategies as st

from jarvis_sdk import (
    Result,
    CommandDecl,
    Err,
    Ok,
    PluginCommandContext,
    PluginCommandResult,
    ToolDecl,
    ToolParam,
    define_plugin_entry,
)
from typing import Any
from jarvis_sdk.api import PluginApi
from jarvis_sdk.context import PluginContext
from jarvis_sdk.entry import PluginEntry

# ── Result.match() property tests ───────────────────────────────────


@given(value=st.text(min_size=1, max_size=100))
def test_ok_match_dispatches_to_ok(value: str) -> None:
    """Ok.match(ok=..., err=...) always calls the ok branch."""
    result: Result[str] = Ok(value)
    seen: list[str] = []
    out = result.match(ok=lambda v: seen.append(v) or f"got:{v}", err=lambda e, c: "err")
    assert seen == [value]
    assert out == f"got:{value}"


@given(
    error=st.text(min_size=1, max_size=100),
    code=st.sampled_from(["E_FOO", "HTTP_503", "BAD_FORMAT", "TIME_IN_PAST"]),
)
def test_err_match_dispatches_to_err(error: str, code: str) -> None:
    """Err.match(ok=..., err=...) always calls the err branch."""
    result: Result[str] = Err(error, code=code)
    out = result.match(ok=lambda v: "ok", err=lambda e, c: f"{c}:{e}")
    assert out == f"{code}:{error}"


@given(value=st.integers(min_value=-1_000_000, max_value=1_000_000))
def test_ok_is_ok_and_not_err(value: int) -> None:
    """Ok.value is preserved; is_ok=True; is_err=False."""
    r: Result[int] = Ok(value)
    assert r.value == value
    assert r.is_ok is True
    assert r.is_err is False


@given(
    error=st.text(min_size=1, max_size=50),
    code=st.text(
        alphabet=string.ascii_uppercase + string.digits + "_",
        min_size=1,
        max_size=20,
    ),
)
def test_err_is_err_and_not_ok(error: str, code: str) -> None:
    """Err.error+code are preserved; is_err=True; is_ok=False."""
    r: Result[Any] = Err(error, code=code)
    assert r.error == error
    assert r.code == code
    assert r.is_ok is False
    assert r.is_err is True


# ── ToolDecl / ToolParam property tests ─────────────────────────────


def _safe_param_name() -> st.SearchStrategy[str]:
    return st.text(
        alphabet=string.ascii_lowercase + string.digits + "_",
        min_size=1,
        max_size=20,
    ).filter(lambda s: s[0].isalpha() and not s.endswith("_"))


@given(
    name=_safe_param_name(),
    type_=st.sampled_from(["string", "integer", "number", "boolean"]),
    required=st.booleans(),
    description=st.text(max_size=200),
)
def test_tool_param_construction(name: str, type_: str, required: bool, description: str) -> None:
    """ToolParam is a frozen dataclass — fields round-trip and is not mutable.

    Note: ``type_`` is a ``str`` for property-test coverage; the SDK
    types it as a ``Literal[...]`` but the runtime field is just a
    string. Pyright complains about the widening — that's the intent.
    """
    p = ToolParam(
        name=name,
        type=type_,  # type: ignore[arg-type]
        description=description,
        required=required,
    )
    assert p.name == name
    assert p.type == type_
    assert p.description == description
    assert p.required is required
    # frozen
    with pytest.raises((AttributeError, TypeError)):
        p.name = "mutated"  # type: ignore[misc]


def test_tool_decl_round_trip() -> None:
    """ToolDecl with multiple params preserves the param list."""
    td = ToolDecl(
        name="do_thing",
        description="Does the thing.",
        parameters=[
            ToolParam(name="x", type="integer", description="x", required=True),
            ToolParam(name="y", type="string", description="y", required=False),
        ],
        returns="string",
        category="utility",
    )
    assert td.name == "do_thing"
    assert len(td.parameters) == 2
    assert td.parameters[0].name == "x"
    assert td.parameters[0].required is True
    assert td.parameters[1].name == "y"
    assert td.parameters[1].required is False
    assert td.returns == "string"
    assert td.category == "utility"


# ── CommandDecl / PluginCommandContext property tests ───────────────


def test_command_decl_requires_callable_handler() -> None:
    """CommandDecl accepts only callables as ``handler``."""
    with pytest.raises(TypeError):
        CommandDecl(name="bad", description="x", handler="not a function")  # type: ignore[arg-type]


async def _sample_command_handler(_ctx: PluginCommandContext) -> PluginCommandResult:
    return PluginCommandResult(reply_text="ok")


def test_command_decl_with_real_handler() -> None:
    """CommandDecl carries handler + default flags."""
    cmd = CommandDecl(
        name="hello",
        description="Say hello.",
        handler=_sample_command_handler,
    )
    assert cmd.name == "hello"
    assert cmd.description == "Say hello."
    assert callable(cmd.handler)
    assert cmd.accepts_args is True
    assert cmd.expose_sender_is_owner is True


def test_plugin_command_context_defaults_are_safe() -> None:
    """Default PluginCommandContext is the single-live-session shape."""
    ctx = PluginCommandContext(args="list", command_body="/reminders list")
    assert ctx.args == "list"
    assert ctx.command_body == "/reminders list"
    assert ctx.channel == "live"
    assert ctx.is_authorized_sender is True
    assert ctx.sender_is_owner is True
    assert ctx.config == {}


# ── PluginApi accumulator tests ──────────────────────────────────────


def test_plugin_api_register_command_raises_without_handler() -> None:
    """register_command(dict) without a handler must TypeError."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)
    with pytest.raises(TypeError):
        api.register_command({"name": "x", "description": "y"})


def test_plugin_api_register_command_accepts_dict_with_handler() -> None:
    """register_command(dict) with handler succeeds and stores a CommandDecl."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)
    api.register_command(
        {
            "name": "x",
            "description": "y",
            "handler": _sample_command_handler,
        }
    )
    assert len(api.commands) == 1
    assert api.commands[0].name == "x"
    assert callable(api.commands[0].handler)


def test_plugin_api_grouped_facades_present() -> None:
    """PluginApi exposes session, agent, run_context, lifecycle (mirror OpenClaw)."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)
    assert api.session is not None
    assert api.agent is not None
    assert api.run_context is not None
    assert api.lifecycle is not None


def test_plugin_api_register_context_engine_round_trips_read_back() -> None:
    """PluginApi keeps the new context-engine registration contract stable."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)

    def factory(ctx: object | None = None):
        return {"ok": True}

    api.register_context_engine(
        {
            "id": "lossless-claw",
            "factory": factory,
            "info": {"id": "lossless-claw", "name": "Lossless Claw"},
        }
    )

    assert len(api.context_engines) == 1
    engine = api.context_engines[0]
    assert engine["id"] == "lossless-claw"
    assert engine["factory"] is factory
    assert engine["_owner_id"] == "t"


def test_plugin_api_register_compaction_provider_round_trips_read_back() -> None:
    """PluginApi exposes the compaction-provider registration contract."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)

    async def compact(_params: dict[str, object]) -> dict[str, object]:
        return {"ok": True}

    api.register_compaction_provider(
        {
            "id": "lossless-compact",
            "compact": compact,
            "meta": {"name": "Lossless compact"},
        }
    )

    assert len(api.compaction_providers) == 1
    provider = api.compaction_providers[0]
    assert provider["id"] == "lossless-compact"
    assert provider["compact"] is compact
    assert provider["_owner_id"] == "t"


def test_plugin_api_register_operation_domains_round_trip() -> None:
    """PluginApi exposes the operation-domain OpenClaw registrar names."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)

    async def catalog_handler(_ctx: object) -> dict[str, object]:
        return {"ok": True}

    api.register_session_catalog({"id": "catalog-a", "handler": catalog_handler})
    api.register_cli_backend({"id": "cli-a", "handler": lambda *_args, **_kwargs: None})
    api.register_text_transform({"id": "transform-a", "handler": lambda value: value})
    api.register_session_extension({"id": "ext-a", "handler": lambda *_args, **_kwargs: None})
    api.register_codex_app_server_extension_factory(
        {"id": "codex-a", "factory": lambda *_args, **_kwargs: None}
    )
    api.register_interactive_handler(
        {"id": "interactive-a", "handler": lambda *_args, **_kwargs: None}
    )

    assert len(api.session_catalogs) == 1
    assert len(api.cli_backends) == 1
    assert len(api.text_transforms) == 1
    assert len(api.session_extensions) == 1
    assert len(api.codex_app_server_extension_factories) == 1
    assert len(api.interactive_handlers) == 1


def test_plugin_api_remaining_openclaw_registrars_exist() -> None:
    """The capability/host-side OpenClaw registrar names survive at the API boundary."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)

    api.register_runtime_lifecycle({"id": "lifecycle-a", "start": lambda *_args, **_kwargs: None})
    api.register_control_ui_descriptor({"id": "ui-a", "label": "UI A"})
    api.register_tool_metadata({"id": "tool-meta-a", "label": "Tool meta"})
    api.register_trusted_tool_policy({"id": "trusted-policy-a", "allow": True})
    api.register_session_scheduler_job({"id": "job-a", "run": lambda *_args, **_kwargs: None})
    api.register_session_action({"id": "action-a", "run": lambda *_args, **_kwargs: None})
    api.register_agent_event_subscription(
        {"id": "subscription-a", "run": lambda *_args, **_kwargs: None}
    )
    api.register_memory_embedding_provider({"id": "memory-embed-a", "provider": object()})
    api.register_conversation_binding_resolved_handler(
        {"id": "binding-a", "handler": lambda *_args, **_kwargs: None}
    )

    assert len(api.runtime_lifecycles) == 1
    assert len(api.control_ui_descriptors) == 1
    assert len(api.tool_metadata) == 1
    assert len(api.trusted_tool_policies) == 1
    assert len(api.session_scheduler_jobs) == 1
    assert len(api.session_actions) == 1
    assert len(api.agent_event_subscriptions) == 1
    assert len(api.memory_embedding_providers) == 1
    assert len(api.conversation_binding_resolved_handlers) == 1


def test_plugin_api_memory_host_registrars_round_trip() -> None:
    """The host-side memory API contract for OpenClaw is a real PluginApi readback."""
    ctx = PluginContext(plugin_id="memory-plugin", plugin_kind="memory")
    api = PluginApi(ctx)

    def builder(_params: object) -> list[str]:
        return ["memory-builder"]

    async def preparer(_params: object) -> list[str]:
        return ["memory-preparer"]

    def resolver(_params: dict[str, object] | None = None) -> dict[str, object]:
        return {"ok": True}

    api.register_memory_capability(
        {"id": "memory-slot", "promptBuilder": builder, "runtime": object()}
    )
    api.register_memory_prompt_section(builder)
    api.register_memory_prompt_supplement(builder)
    api.register_memory_prompt_preparation(preparer)
    api.register_memory_corpus_supplement({"id": "wiki", "body": "memory"})
    api.register_memory_flush_plan(resolver)
    api.register_memory_runtime(object())

    assert api.memory_capability is not None
    assert len(api.memory_prompt_sections) == 1
    assert len(api.memory_prompt_supplements) == 1
    assert len(api.memory_prompt_preparations) == 1
    assert len(api.memory_corpus_supplements) == 1
    assert len(api.memory_flush_plans) == 1
    assert len(api.memory_runtimes) == 1


def test_plugin_api_remaining_network_registrars_exist() -> None:
    """The network/host side of the OpenClaw registrar vocabulary is callable on PluginApi."""
    ctx = PluginContext(plugin_id="n", plugin_kind="tool")
    api = PluginApi(ctx)

    api.register_hosted_media_resolver(
        {"id": "media-resolver-a", "resolve": lambda *_args, **_kwargs: None}
    )
    api.register_mcp_server_connection_resolver(
        {"id": "mcp-a", "resolve": lambda *_args, **_kwargs: None}
    )
    api.register_reload({"id": "reload-a", "handler": lambda *_args, **_kwargs: None})
    api.register_node_host_command({"id": "node-a", "handler": lambda *_args, **_kwargs: None})
    api.register_security_audit_collector(
        {"id": "audit-a", "collect": lambda *_args, **_kwargs: None}
    )

    assert len(api.hosted_media_resolvers) == 1
    assert len(api.mcp_server_connection_resolvers) == 1
    assert len(api.reload_handlers) == 1
    assert len(api.node_host_commands) == 1
    assert len(api.security_audit_collectors) == 1


def test_plugin_api_openclaw_compatibility_aliases_round_trip() -> None:
    """Compatibility aliases preserve their OpenClaw registry contracts."""
    ctx = PluginContext(plugin_id="t", plugin_kind="tool")
    api = PluginApi(ctx)

    api.register_http_route(
        {"path": "/health", "handler": lambda *_args, **_kwargs: {"status": "ok"}}
    )
    api.register_text_transforms({"id": "transform-a", "handler": lambda value: value})
    api.register_typed_hook({"name": "validate", "handler": lambda *_args, **_kwargs: None})
    api.register_model_catalog_provider({"provider": "model-catalog"}, {"id": "catalog-a"})
    api.register_agent_tool_result_middleware(
        {"id": "middleware-a", "handler": lambda *_args, **_kwargs: None}
    )

    assert len(api.http_handlers) == 1
    assert len(api.text_transforms) == 1
    assert len(api.hooks) == 1
    assert len(api.model_catalog_providers) == 1
    assert len(api.agent_tool_result_middlewares) == 1


def test_plugin_api_has_expected_openclaw_registrar_equivalents() -> None:
    """PluginApi exposes the same OpenClaw registrar names as the registrar composer."""
    api_text = Path("packages/plugin_sdk/src/jarvis_sdk/api.py").read_text(encoding="utf-8")
    api_names = set(re.findall(r"def\s+(register_[A-Za-z0-9_]+)\(", api_text))

    def snake_to_camel(name: str) -> str:
        parts = name.split("_")
        return parts[0] + "".join(p.title() for p in parts[1:])

    api_camel = {snake_to_camel(name) for name in api_names}

    registrar_paths = [
        Path("packages/plugin_sdk/src/jarvis_sdk/plugin_registry_registrars.py"),
        Path("src/plugins/registrars.py"),
    ]
    sdk_only_extras = {
        "registerCron",
        "registerDoctorContract",
        "registerHttpHandler",
        "registerSkill",
        "registerTextTransform",
    }

    for path in registrar_paths:
        registrar_text = path.read_text(encoding="utf-8")
        registrar_names = {
            match.group(1) for match in re.finditer(r'"(register[A-Za-z0-9_]+)"', registrar_text)
        }
        missing = sorted(registrar_names - api_camel)
        extra = sorted(api_camel - registrar_names - sdk_only_extras)
        assert not missing, f"Missing PluginApi aliases for {path}: {missing}"
        assert not extra, f"Unexpected API names not in {path}: {extra}"


# ── define_plugin_entry property tests ───────────────────────────────


def test_define_plugin_entry_returns_plugin_entry() -> None:
    """define_plugin_entry returns a PluginEntry (mirrors OpenClaw)."""

    def reg(_api: PluginApi) -> None:
        return None

    entry = define_plugin_entry(
        id="t",
        kind="tool",
        name="T",
        description="d",
        register=reg,
        version="0.1.0",
    )
    assert isinstance(entry, PluginEntry)
    assert entry.id == "t"
    assert entry.kind == "tool"
    assert entry.name == "T"
    assert entry.description == "d"
    assert entry.version == "0.1.0"
    assert entry.register is reg
