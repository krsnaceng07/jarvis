"""Property tests for the JARVIS plugin SDK.

Phase 1C: drives ``Result``, ``ToolDecl``, ``PluginCommandContext``, and
``CommandDecl`` through hypothesis to pin the contract. These are
not feature tests — they exist so a refactor of the SDK that breaks
the contract (e.g. flattens ``Result``, drops ``match()``, makes
``handler`` optional again) is caught before a downstream extension
inherits the bug.
"""
from __future__ import annotations

import string

import pytest
from hypothesis import given, strategies as st

from jarvis_sdk import (
    CommandDecl,
    Err,
    Ok,
    PluginCommandContext,
    PluginCommandResult,
    Result,
    ToolDecl,
    ToolParam,
    define_plugin_entry,
)
from jarvis_sdk.api import PluginApi
from jarvis_sdk.context import PluginContext
from jarvis_sdk.entry import PluginEntry
from jarvis_sdk.result import ResultNone


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
    r: Result = Err(error, code=code)
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
def test_tool_param_construction(
    name: str, type_: str, required: bool, description: str
) -> None:
    """ToolParam is a frozen dataclass — fields round-trip and is not mutable.

    Note: ``type_`` is a ``str`` for property-test coverage; the SDK
    types it as a ``Literal[...]`` but the runtime field is just a
    string. Pyright complains about the widening — that's the intent.
    """
    p = ToolParam(
        name=name, type=type_, description=description, required=required  # type: ignore[arg-type]
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
