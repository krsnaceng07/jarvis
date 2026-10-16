"""tests.test_tool_calling_parity — Tests for OpenClaw -> JARVIS tool calling parity.

Verifies:
1. Schema normalization (uppercase Gemini Live schema -> lowercase JSON schema).
2. Argument preparation and edit alias normalization (old_text/oldText, new_text/newText).
3. ToolSchemaRegistry: validation, type coercion, and missing required argument rejection.
4. Output truncation protecting context window (32 KB limit).
5. Execution timeout resolution across read-only, coding, exec, and plugin tools.
6. Batch parallelizability evaluation (read-only tools parallel, mutating sequential).
7. Desktop host _execute_tool integration: validation error returns structured observation,
   timeout error handling, and parallel batch dispatch.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.desktop.src.jarvis_desktop.tool_pipeline import (
    MAX_TOOL_OUTPUT_CHARS,
    ToolSchemaRegistry,
    is_batch_parallelizable,
    normalize_tool_parameter_schema,
    prepare_tool_arguments,
    resolve_tool_timeout,
    truncate_output,
)


# ── 1. Schema Normalization Tests ────────────────────────────────────────────


def test_normalize_tool_parameter_schema_uppercase_types():
    raw = {
        "type": "OBJECT",
        "properties": {
            "path": {"type": "STRING", "description": "File path"},
            "limit": {"type": "INTEGER", "description": "Max entries"},
            "recursive": {"type": "BOOLEAN"},
            "items": {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": ["path"],
    }
    normalized = normalize_tool_parameter_schema(raw)

    assert normalized["type"] == "object"
    assert normalized["properties"]["path"]["type"] == "string"
    assert normalized["properties"]["limit"]["type"] == "integer"
    assert normalized["properties"]["recursive"]["type"] == "boolean"
    assert normalized["properties"]["items"]["type"] == "array"
    assert normalized["properties"]["items"]["items"]["type"] == "string"
    assert normalized["required"] == ["path"]


def test_normalize_tool_parameter_schema_nested_objects():
    raw = {
        "type": "OBJECT",
        "properties": {
            "config": {
                "type": "OBJECT",
                "properties": {
                    "enabled": {"type": "BOOLEAN"},
                    "timeout": {"type": "NUMBER"},
                },
            }
        },
    }
    normalized = normalize_tool_parameter_schema(raw)
    assert normalized["type"] == "object"
    assert normalized["properties"]["config"]["type"] == "object"
    assert normalized["properties"]["config"]["properties"]["enabled"]["type"] == "boolean"
    assert normalized["properties"]["config"]["properties"]["timeout"]["type"] == "number"


# ── 2. Argument Preparation & Aliases ────────────────────────────────────────


def test_prepare_tool_arguments_edit_aliases():
    # snake_case -> camelCase
    args1 = {"path": "test.txt", "old_text": "hello", "new_text": "world"}
    prep1 = prepare_tool_arguments("edit", args1)
    assert prep1["oldText"] == "hello"
    assert prep1["newText"] == "world"

    # camelCase -> snake_case
    args2 = {"path": "test.txt", "oldText": "foo", "newText": "bar"}
    prep2 = prepare_tool_arguments("edit", args2)
    assert prep2["old_text"] == "foo"
    assert prep2["new_text"] == "bar"

    # Non-edit tools pass through
    args3 = {"path": "dir", "limit": 10}
    prep3 = prepare_tool_arguments("ls", args3)
    assert prep3 == args3


# ── 3. ToolSchemaRegistry: Validation & Coercion ─────────────────────────────


def test_tool_schema_registry_validation_success():
    registry = ToolSchemaRegistry()
    registry.register_declaration({
        "name": "write",
        "description": "Write a file",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING"},
                "content": {"type": "STRING"},
            },
            "required": ["path", "content"],
        },
    })

    args, err = registry.validate_and_coerce("write", {"path": "file.txt", "content": "abc"})
    assert err is None
    assert args["path"] == "file.txt"
    assert args["content"] == "abc"


def test_tool_schema_registry_coercion():
    registry = ToolSchemaRegistry()
    registry.register_declaration({
        "name": "ls",
        "description": "List dir",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING"},
                "limit": {"type": "INTEGER"},
            },
        },
    })

    # String number "50" coerced to integer 50
    args, err = registry.validate_and_coerce("ls", {"path": "C:\\", "limit": "50"})
    assert err is None
    assert args["limit"] == 50
    assert isinstance(args["limit"], int)


def test_tool_schema_registry_missing_required_fails():
    registry = ToolSchemaRegistry()
    registry.register_declaration({
        "name": "write",
        "description": "Write a file",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING"},
                "content": {"type": "STRING"},
            },
            "required": ["path", "content"],
        },
    })

    # Missing "content"
    args, err = registry.validate_and_coerce("write", {"path": "file.txt"})
    assert err is not None
    assert "content" in err.lower() or "missing" in err.lower() or "required" in err.lower()


def test_tool_schema_registry_unregistered_tool_passes_through():
    registry = ToolSchemaRegistry()
    raw_args = {"custom_param": 42}
    args, err = registry.validate_and_coerce("unknown_tool", raw_args)
    assert err is None
    assert args == raw_args


# ── 4. Output Truncation ─────────────────────────────────────────────────────


def test_truncate_output_short():
    short = "Short output 123"
    assert truncate_output(short, max_chars=100) == short


def test_truncate_output_exceeds_budget():
    large = "x" * (MAX_TOOL_OUTPUT_CHARS + 5000)
    truncated = truncate_output(large)
    assert len(truncated) <= MAX_TOOL_OUTPUT_CHARS
    assert "[Truncated: output exceeded" in truncated


# ── 5. Execution Timeout Resolution ──────────────────────────────────────────


def test_resolve_tool_timeout():
    # Read-only tools
    assert resolve_tool_timeout("ls", {}) == 15.0
    assert resolve_tool_timeout("read", {"path": "a.txt"}) == 15.0

    # Coding mutating tools
    assert resolve_tool_timeout("write", {}) == 30.0
    assert resolve_tool_timeout("mkdir", {}) == 30.0
    assert resolve_tool_timeout("edit", {}) == 30.0

    # Exec tool default & custom timeout_ms
    assert resolve_tool_timeout("exec", {}) == 45.0
    assert resolve_tool_timeout("exec", {"timeout_ms": 20000}) == 20.0
    # Clamped lower to 5s
    assert resolve_tool_timeout("exec", {"timeout_ms": 1000}) == 5.0
    # Clamped upper to 300s
    assert resolve_tool_timeout("exec", {"timeout_ms": 600000}) == 300.0

    # Plugins
    assert resolve_tool_timeout("weather_get", {}) == 60.0


# ── 6. Batch Parallelizability ───────────────────────────────────────────────


def test_is_batch_parallelizable():
    fc_ls = SimpleNamespace(name="ls")
    fc_read = SimpleNamespace(name="read")
    fc_write = SimpleNamespace(name="write")

    # Single call is never parallelized
    assert not is_batch_parallelizable([fc_ls])

    # Multiple read-only calls CAN be parallelized
    assert is_batch_parallelizable([fc_ls, fc_read])

    # Mixed read and mutating CANNOT be parallelized
    assert not is_batch_parallelizable([fc_ls, fc_write])

    # Dict format support
    assert is_batch_parallelizable([{"name": "ls"}, {"name": "read"}])
    assert not is_batch_parallelizable([{"name": "ls"}, {"name": "write"}])


# ── 7. Desktop Host _execute_tool Integration ────────────────────────────────


@pytest.mark.asyncio
async def test_execute_tool_validation_error_returns_observation():
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    live = JarvisLive(mock_ui)

    # Call "write" without required "content" argument
    fc = SimpleNamespace(id="call_1", name="write", args={"path": "some/path.txt"})
    resp = await live._execute_tool(fc)

    assert resp.name == "write"
    # Must return validation error observation without throwing an unhandled exception
    assert "Tool argument validation failed" in resp.response["result"]
    assert resp.response.get("error") is True


@pytest.mark.asyncio
async def test_execute_tool_timeout_handling():
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    live = JarvisLive(mock_ui)

    # Mock tool execution that takes too long
    async def slow_execute(call_id, args):
        await asyncio.sleep(2.0)
        return {"output": "done"}

    live._coding_tools["ls"] = {"execute": slow_execute}

    with patch(
        "apps.desktop.src.jarvis_desktop.app.resolve_tool_timeout", return_value=0.05
    ):
        fc = SimpleNamespace(id="call_2", name="ls", args={"path": "C:\\"})
        resp = await live._execute_tool(fc)

        assert resp.name == "ls"
        assert "timed out after 0.05s" in resp.response["result"]
        assert resp.response.get("error") is True


@pytest.mark.asyncio
async def test_execute_tool_coerces_arguments_successfully(tmp_path):
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    live = JarvisLive(mock_ui)

    # Call "ls" with string limit "10"
    fc = SimpleNamespace(id="call_3", name="ls", args={"path": str(tmp_path), "limit": "10"})
    resp = await live._execute_tool(fc)

    assert resp.name == "ls"
    assert "Verified" in resp.response["result"]
