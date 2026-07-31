"""Phase 6.10b — tools/ output + render + wrapper tests.

Verifies the 4 new modules in Phase 6.10b:
- private_temp_file — createPrivateTempWriteStream,
  writePrivateTempFile (owner-only, exclusive)
- output_accumulator — OutputAccumulator with
  streaming decode, bounded tail, temp-file
  spillover
- render_utils — TUI-independent helpers
  (shortenPath, str, replaceTabs, etc.)
- tool_definition_wrapper — wrapToolDefinition,
  wrapToolDefinitions,
  createToolDefinitionFromAgentTool
"""
from __future__ import annotations

import asyncio
import os
import stat
import tempfile
from pathlib import Path

import pytest

from src.agents.sessions.tools import (
    OutputAccumulator,
    OutputAccumulatorOptions,
    OutputSnapshot,
    create_private_temp_write_stream,
    write_private_temp_file,
    shorten_path,
    replace_tabs,
    normalize_display_text,
    get_text_output,
    format_session_tool_output,
    append_session_tool_truncation_warning,
    invalid_arg_text,
    wrap_tool_definition,
    wrap_tool_definitions,
    create_tool_definition_from_agent_tool,
)
from src.agents.sessions.extensions.types import (
    ToolDefinition,
    ExtensionContext,
)


# ============================================================================
# private_temp_file
# ============================================================================


class TestPrivateTempFile:
    def test_create_temp_write_stream(self, tmp_path: Path) -> None:
        # The OpenClaw source uses the system
        # temp dir; the Python port mirrors that
        # — we just check the result is a path
        # + a stream.
        path, stream = create_private_temp_write_stream("test")
        try:
            assert os.path.isabs(path)
            assert "test-" in os.path.basename(path)
            assert path.endswith(".log")
            assert stream is not None
            # Owner-only: the OpenClaw source uses
            # 0o600 mode. On Windows the mode
            # bits are advisory; we still try.
            if os.name != "nt":
                mode = stat.S_IMODE(os.stat(path).st_mode)
                assert mode & 0o777 == 0o600
        finally:
            stream.close()
            if os.path.exists(path):
                os.unlink(path)

    def test_write_temp_file(self) -> None:
        path = write_private_temp_file("test", "hello world")
        try:
            with open(path, encoding="utf-8") as f:
                assert f.read() == "hello world"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_write_temp_file_unicode(self) -> None:
        content = "日本語テスト 🎉"
        path = write_private_temp_file("test", content)
        try:
            with open(path, encoding="utf-8") as f:
                assert f.read() == content
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_unique_paths(self) -> None:
        paths = [
            create_private_temp_write_stream("test")[0] for _ in range(5)
        ]
        for p, _ in []:  # close the streams
            pass
        # All 5 paths are unique
        assert len(set(paths)) == 5
        # Clean up
        for p in paths:
            try:
                os.unlink(p)
            except (OSError, FileNotFoundError):
                pass


# ============================================================================
# OutputAccumulator
# ============================================================================


class TestOutputAccumulator:
    def test_basic_append(self) -> None:
        acc = OutputAccumulator()
        text = acc.append(b"hello world")
        assert text == "hello world"
        snap = acc.snapshot()
        assert snap.content == "hello world"
        assert snap.fullOutputPath is None

    def test_streaming_decode_multibyte(self) -> None:
        # Split a multi-byte UTF-8 character
        # across append() calls — the
        # incremental decoder should reassemble.
        acc = OutputAccumulator()
        # "日" is 3 bytes in UTF-8: 0xE6 0x97 0xA5
        acc.append(b"\xE6\x97")
        text = acc.append(b"\xA5")
        assert text == "日"

    def test_line_counting(self) -> None:
        acc = OutputAccumulator()
        acc.append(b"line 1\nline 2\nline 3")
        snap = acc.snapshot()
        # 3 lines (the last has no trailing \n)
        assert snap.truncation["totalLines"] == 3

    def test_bounded_tail_truncates(self) -> None:
        acc = OutputAccumulator(
            OutputAccumulatorOptions(maxLines=2, maxBytes=1000)
        )
        # 10 lines, only 2 are kept in display
        acc.append(b"\n".join(f"line {i}".encode() for i in range(10)))
        snap = acc.snapshot()
        assert snap.truncation["truncated"] is True
        assert snap.truncation["truncatedBy"] == "lines"
        # Display should only have the last 2 lines
        assert "line 8" in snap.content
        assert "line 9" in snap.content
        assert "line 0" not in snap.content

    def test_bounded_bytes_truncates(self) -> None:
        acc = OutputAccumulator(
            OutputAccumulatorOptions(maxBytes=10, maxLines=10000)
        )
        acc.append(b"a" * 100)
        snap = acc.snapshot()
        assert snap.truncation["truncated"] is True
        assert snap.truncation["truncatedBy"] == "bytes"
        # Display content should be bounded
        assert len(snap.content.encode("utf-8")) <= 10

    def test_finish_returns_remaining(self) -> None:
        acc = OutputAccumulator()
        acc.append(b"hello ")
        text = acc.finish()
        assert text == ""
        # The accumulated text is in the snapshot
        snap = acc.snapshot()
        assert "hello" in snap.content

    def test_append_after_finish_raises(self) -> None:
        acc = OutputAccumulator()
        acc.finish()
        with pytest.raises(RuntimeError, match="finished"):
            acc.append(b"more")

    def test_temp_file_creates_when_overflow(self) -> None:
        acc = OutputAccumulator(
            OutputAccumulatorOptions(
                maxBytes=10, maxLines=10000, tempFilePrefix="test-out"
            )
        )
        acc.append(b"a" * 100)
        snap = acc.snapshot(persist_if_truncated=True)
        assert snap.fullOutputPath is not None
        assert "test-out-" in snap.fullOutputPath
        # Clean up: close the file handle before
        # unlinking (Windows holds an exclusive
        # lock until close).
        path = snap.fullOutputPath
        assert path is not None
        asyncio.run(acc.close_temp_file())
        if os.path.exists(path):
            os.unlink(path)

    def test_get_last_line_bytes(self) -> None:
        acc = OutputAccumulator()
        acc.append(b"complete line\nincomplete")
        last = acc.get_last_line_bytes()
        # "incomplete" is 10 chars
        assert last == len("incomplete")

    def test_transform_decoded_text(self) -> None:
        acc = OutputAccumulator(
            OutputAccumulatorOptions(
                transformDecodedText=lambda s: s.replace("foo", "bar")
            )
        )
        text = acc.append(b"foo bar")
        assert text == "bar bar"
        snap = acc.snapshot()
        assert "bar bar" in snap.content

    def test_close_temp_file_async(self) -> None:
        acc = OutputAccumulator(
            OutputAccumulatorOptions(
                maxBytes=5, maxLines=100, tempFilePrefix="close-test"
            )
        )
        acc.append(b"x" * 50)
        snap = acc.snapshot(persist_if_truncated=True)
        path = snap.fullOutputPath
        assert path is not None
        try:
            asyncio.run(acc.close_temp_file())
            # The file should still exist
            # (close just closes the stream; the
            # file remains on disk).
            assert os.path.exists(path)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_snapshot_no_truncation(self) -> None:
        acc = OutputAccumulator(
            OutputAccumulatorOptions(maxLines=100, maxBytes=10000)
        )
        acc.append(b"a\nb\nc")
        snap = acc.snapshot()
        assert snap.truncation["truncated"] is False
        assert snap.truncation["truncatedBy"] is None


# ============================================================================
# render_utils
# ============================================================================


class TestRenderUtils:
    def test_shorten_path_under_home(self) -> None:
        home = os.path.expanduser("~")
        # Use ``os.path.join`` so the path uses
        # the host's separator (Windows uses
        # ``\\``, POSIX uses ``/``).
        result = shorten_path(os.path.join(home, "foo"))
        assert result == "~" + os.sep + "foo"

    def test_shorten_path_at_home(self) -> None:
        home = os.path.expanduser("~")
        assert shorten_path(home) == "~"

    def test_shorten_path_outside_home(self) -> None:
        # On Windows ``/etc/hosts`` realpath is
        # ``C:\\etc\\hosts``. We pass the
        # realpath-form to make the test
        # platform-agnostic.
        outside = os.path.realpath("/etc/hosts")
        assert shorten_path(outside) == outside

    def test_shorten_path_non_string(self) -> None:
        assert shorten_path(None) == ""
        assert shorten_path(42) == ""

    def test_str_helper_string(self) -> None:
        from src.agents.sessions.tools import render_str
        assert render_str("hello") == "hello"

    def test_str_helper_none(self) -> None:
        from src.agents.sessions.tools import render_str
        assert render_str(None) == ""

    def test_str_helper_other(self) -> None:
        from src.agents.sessions.tools import render_str
        assert render_str(42) is None
        assert render_str([1, 2]) is None

    def test_replace_tabs(self) -> None:
        assert replace_tabs("a\tb\tc") == "a   b   c"
        assert replace_tabs("no tabs") == "no tabs"

    def test_normalize_display_text_strips_cr(self) -> None:
        assert normalize_display_text("a\rb\r\rc") == "abc"

    def test_get_text_output_empty(self) -> None:
        assert get_text_output(None) == ""
        assert get_text_output({}) == ""

    def test_get_text_output_text_blocks(self) -> None:
        result = {
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
            ]
        }
        assert get_text_output(result) == "hello\nworld"

    def test_format_session_tool_output_empty(self) -> None:
        assert format_session_tool_output(
            {"content": []}, {"expanded": True}
        ) == ""

    def test_format_session_tool_output_collapsed(self) -> None:
        result = {
            "content": [
                {"type": "text", "text": "\n".join(f"line {i}" for i in range(10))}
            ]
        }
        text = format_session_tool_output(
            result, {"expanded": False}, collapsed_line_limit=3
        )
        assert "line 0" in text
        assert "line 2" in text
        assert "line 3" not in text
        assert "7 more lines" in text
        assert "<keyhint:app.tools.expand>" in text

    def test_format_session_tool_output_expanded(self) -> None:
        result = {
            "content": [
                {"type": "text", "text": "\n".join(f"line {i}" for i in range(5))}
            ]
        }
        text = format_session_tool_output(
            result, {"expanded": True}
        )
        for i in range(5):
            assert f"line {i}" in text

    def test_append_session_tool_truncation_warning_no_warnings(self) -> None:
        assert (
            append_session_tool_truncation_warning("hello", {}) == "hello"
        )

    def test_append_session_tool_truncation_warning_with_limit(self) -> None:
        result = append_session_tool_truncation_warning(
            "hello", {"limit": {"count": 100, "noun": "match"}}
        )
        assert "[Truncated:" in result
        assert "100 match limit" in result

    def test_append_session_tool_truncation_warning_with_truncation(self) -> None:
        result = append_session_tool_truncation_warning(
            "hello",
            {
                "truncation": {
                    "truncated": True,
                    "maxBytes": 51200,
                }
            },
        )
        assert "[Truncated:" in result
        assert "50.0KB" in result

    def test_invalid_arg_text(self) -> None:
        assert invalid_arg_text() == "[invalid arg]"


# ============================================================================
# tool_definition_wrapper
# ============================================================================


class TestToolDefinitionWrapper:
    @pytest.mark.asyncio
    async def test_wrap_basic(self) -> None:
        async def _execute(
            tool_call_id: str,
            params: dict,
            signal: object,
            on_update: object,
            ctx: object,
        ) -> dict:
            return {"content": "ok"}

        definition: ToolDefinition = {
            "name": "t",
            "label": "T",
            "description": "d",
            "execute": _execute,
        }
        wrapped = wrap_tool_definition(definition)
        assert wrapped["name"] == "t"
        assert wrapped["label"] == "T"
        assert wrapped["description"] == "d"
        # Call the execute closure
        result = await wrapped["execute"]("c1", {"x": 1}, None, None)
        assert result == {"content": "ok"}

    @pytest.mark.asyncio
    async def test_wrap_with_ctx_factory(self) -> None:
        seen_ctx: list[object] = []

        def _ctx_factory() -> ExtensionContext:
            ctx = {"cwd": "/test"}
            seen_ctx.append(ctx)
            return ctx  # type: ignore[return-value]

        async def _execute(
            tool_call_id: str,
            params: dict,
            signal: object,
            on_update: object,
            ctx: object,
        ) -> dict:
            return {"ctx": ctx}

        definition: ToolDefinition = {
            "name": "t",
            "label": "T",
            "description": "d",
            "execute": _execute,
        }
        wrapped = wrap_tool_definition(definition, _ctx_factory)
        result = await wrapped["execute"]("c1", {}, None, None)
        assert result == {"ctx": {"cwd": "/test"}}
        assert len(seen_ctx) == 1

    @pytest.mark.asyncio
    async def test_wrap_no_execute_raises(self) -> None:
        definition: ToolDefinition = {
            "name": "t",
            "label": "T",
            "description": "d",
        }
        wrapped = wrap_tool_definition(definition)
        with pytest.raises(RuntimeError, match="no execute"):
            await wrapped["execute"]("c1", {}, None, None)

    def test_wrap_with_optional_fields(self) -> None:
        async def _execute(*args: object, **kwargs: object) -> dict:
            return {}

        definition: ToolDefinition = {
            "name": "t",
            "label": "T",
            "description": "d",
            "execute": _execute,
            "parameters": {"type": "object"},
            "outputSchema": {"type": "object"},
            "hideFromChannelProgress": True,
            "executionMode": "sequential",
        }
        wrapped = wrap_tool_definition(definition)
        assert wrapped["parameters"] == {"type": "object"}
        assert wrapped["outputSchema"] == {"type": "object"}
        assert wrapped["hideFromChannelProgress"] is True
        assert wrapped["executionMode"] == "sequential"

    def test_wrap_definitions(self) -> None:
        async def _e(*a: object, **k: object) -> dict:
            return {}

        definitions: list[ToolDefinition] = [
            {"name": "a", "label": "A", "description": "a", "execute": _e},
            {"name": "b", "label": "B", "description": "b", "execute": _e},
        ]
        wrapped = wrap_tool_definitions(definitions)
        assert len(wrapped) == 2
        assert wrapped[0]["name"] == "a"
        assert wrapped[1]["name"] == "b"

    @pytest.mark.asyncio
    async def test_create_from_agent_tool(self) -> None:
        async def _agent_execute(
            tool_call_id: str,
            params: dict,
            signal: object,
            on_update: object,
        ) -> dict:
            return {"content": "agent result"}

        agent_tool = {
            "name": "t",
            "label": "T",
            "description": "d",
            "execute": _agent_execute,
            "parameters": {"type": "object"},
        }
        definition = create_tool_definition_from_agent_tool(agent_tool)
        assert definition["name"] == "t"
        assert definition["label"] == "T"
        assert definition["description"] == "d"
        # The definition's execute accepts 5 args
        # (matches the ToolDefinition contract).
        result = await definition["execute"]("c1", {}, None, None, None)
        assert result == {"content": "agent result"}

    def test_create_from_agent_tool_no_execute_raises(self) -> None:
        with pytest.raises(RuntimeError, match="no execute"):
            create_tool_definition_from_agent_tool({"name": "t"})
