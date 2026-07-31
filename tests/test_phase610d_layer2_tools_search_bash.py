"""Phase 6.10d — tools/ search + bash tests.

Verifies the 5 search + bash modules:
- bash_operations — the Protocol interface
- bash — execute_bash, create_bash_tool_definition,
  resolve_bash_timeout_ms, create_local_bash_operations
- find — find_files, create_find_tool_definition
- grep — grep_files, create_grep_tool_definition
- ls — list_directory, create_ls_tool_definition
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

from src.agents.sessions.tools import (
    BashOperations,
    FindOperations,
    GrepOperations,
    LsOperations,
    create_bash_tool,
    create_bash_tool_definition,
    create_find_tool,
    create_find_tool_definition,
    create_grep_tool,
    create_grep_tool_definition,
    create_ls_tool,
    create_ls_tool_definition,
    create_local_bash_operations,
    execute_bash,
    find_files,
    grep_files,
    list_directory,
    resolve_bash_timeout_ms,
    DEFAULT_BASH_TIMEOUT_MS,
    DEFAULT_IGNORE_PATTERNS,
    FIND_DEFAULT_LIMIT,
    GREP_DEFAULT_LIMIT,
    LS_DEFAULT_LIMIT,
    DEFAULT_CONTEXT,
)


# ============================================================================
# bash_operations
# ============================================================================


class TestBashOperations:
    def test_protocol_runtime_checkable(self) -> None:
        # Any class with an async ``exec`` method
        # satisfies the protocol.
        class _FakeOps:
            async def exec(
                self,
                command: str,
                cwd: str,
                options: dict,
            ) -> dict:
                return {"exitCode": 0}

        ops = _FakeOps()
        assert isinstance(ops, BashOperations)


# ============================================================================
# bash: resolve_bash_timeout_ms
# ============================================================================


class TestResolveBashTimeoutMs:
    def test_undefined_returns_none(self) -> None:
        assert resolve_bash_timeout_ms(None) is None

    def test_positive_seconds(self) -> None:
        assert resolve_bash_timeout_ms(5) == 5000

    def test_float_seconds(self) -> None:
        assert resolve_bash_timeout_ms(0.5) == 500

    def test_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            resolve_bash_timeout_ms(0)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            resolve_bash_timeout_ms(-1)

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            resolve_bash_timeout_ms("not a number")

    def test_bool_raises(self) -> None:
        # Booleans are not valid timeouts
        with pytest.raises(ValueError, match="positive"):
            resolve_bash_timeout_ms(True)

    def test_default_constant(self) -> None:
        assert DEFAULT_BASH_TIMEOUT_MS == 30 * 60 * 1000


# ============================================================================
# bash: create_local_bash_operations
# ============================================================================


class TestCreateLocalBashOperations:
    def test_returns_bash_operations(self) -> None:
        ops = create_local_bash_operations()
        assert isinstance(ops, BashOperations)

    @pytest.mark.asyncio
    async def test_exec_runs_command(self, tmp_path: Path) -> None:
        ops = create_local_bash_operations()
        if sys.platform == "win32":
            command = "echo hello"
        else:
            command = "echo hello"
        received: list[bytes] = []

        def _on_data(data: bytes) -> None:
            received.append(data)

        result = await ops.exec(
            command,
            str(tmp_path),
            {"onData": _on_data},
        )
        assert "exitCode" in result
        # The onData callback should have
        # received at least one chunk.
        assert b"".join(received).decode("utf-8", errors="replace").strip() == "hello"

    @pytest.mark.asyncio
    async def test_exec_invalid_cwd_raises(self) -> None:
        ops = create_local_bash_operations()
        with pytest.raises(FileNotFoundError, match="does not exist"):
            await ops.exec(
                "echo hello",
                "/nonexistent/path",
                {"onData": lambda d: None},
            )


# ============================================================================
# bash: execute_bash
# ============================================================================


class TestExecuteBash:
    @pytest.mark.asyncio
    async def test_basic(self, tmp_path: Path) -> None:
        result = await execute_bash(
            command="echo hello",
            cwd=str(tmp_path),
        )
        assert "exitCode" in result
        assert "hello" in result["output"]

    @pytest.mark.asyncio
    async def test_invalid_cwd_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            await execute_bash(
                command="echo hello",
                cwd="/nonexistent/path",
            )


# ============================================================================
# bash: create_bash_tool_definition
# ============================================================================


class TestCreateBashTool:
    @pytest.mark.asyncio
    async def test_factory(self) -> None:
        tool = await create_bash_tool_definition()
        assert tool["name"] == "bash"
        assert callable(tool["execute"])

    @pytest.mark.asyncio
    async def test_execute(self, tmp_path: Path) -> None:
        tool = await create_bash_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1",
            {"command": "echo hi"},
            None,
            None,
            None,
        )
        assert "hi" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_missing_command(self) -> None:
        tool = await create_bash_tool_definition()
        with pytest.raises(ValueError, match="command is required"):
            await tool["execute"]("c1", {}, None, None, None)

    @pytest.mark.asyncio
    async def test_alias(self) -> None:
        tool = await create_bash_tool()
        assert tool["name"] == "bash"


# ============================================================================
# find
# ============================================================================


class TestFindFiles:
    def test_basic(self, tmp_path: Path) -> None:
        # Create some files
        (tmp_path / "a.py").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "c.py").write_text("c")
        result = asyncio.run(
            find_files("*.py", cwd=str(tmp_path))
        )
        # At least the .py files should be found
        paths = result["paths"]
        assert any(p.endswith("a.py") for p in paths)
        assert any(p.endswith("c.py") for p in paths)

    def test_recursive_glob(self, tmp_path: Path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "deep.py").write_text("x")
        result = asyncio.run(
            find_files("**/*.py", cwd=str(tmp_path))
        )
        paths = result["paths"]
        assert any("deep.py" in p for p in paths)

    def test_respects_default_ignore(self, tmp_path: Path) -> None:
        # Create a file in .git (should be ignored)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.py").write_text("x")
        # Create a non-ignored file
        (tmp_path / "main.py").write_text("x")
        result = asyncio.run(find_files("*.py", cwd=str(tmp_path)))
        paths = result["paths"]
        assert not any(".git" in p for p in paths)
        assert any("main.py" in p for p in paths)

    def test_limit(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text("x")
        result = asyncio.run(
            find_files("*.py", cwd=str(tmp_path), limit=2)
        )
        assert result["resultLimitReached"] == 2
        assert len(result["paths"]) <= 2


class TestCreateFindTool:
    @pytest.mark.asyncio
    async def test_factory(self) -> None:
        tool = await create_find_tool_definition()
        assert tool["name"] == "find"
        assert callable(tool["execute"])

    @pytest.mark.asyncio
    async def test_execute(self, tmp_path: Path) -> None:
        (tmp_path / "x.py").write_text("x")
        tool = await create_find_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1", {"pattern": "*.py"}, None, None, None
        )
        assert "x.py" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_no_match(self, tmp_path: Path) -> None:
        tool = await create_find_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1", {"pattern": "*.zzz"}, None, None, None
        )
        assert "no matches" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_missing_pattern(self) -> None:
        tool = await create_find_tool_definition()
        with pytest.raises(ValueError, match="pattern is required"):
            await tool["execute"]("c1", {}, None, None, None)

    @pytest.mark.asyncio
    async def test_alias(self) -> None:
        tool = await create_find_tool()
        assert tool["name"] == "find"


# ============================================================================
# grep
# ============================================================================


class TestGrepFiles:
    def test_basic_regex(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("hello world\nfoo bar\n")
        (tmp_path / "b.py").write_text("hello python\nbaz qux\n")
        result = asyncio.run(
            grep_files("hello", cwd=str(tmp_path))
        )
        assert len(result["matches"]) == 2

    def test_literal(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("foo.bar\nfoo+bar\n")
        result = asyncio.run(
            grep_files(
                "foo.bar", cwd=str(tmp_path), literal=True
            )
        )
        # Literal "foo.bar" should match the
        # first line, NOT regex "foo<any>bar".
        assert len(result["matches"]) == 1
        assert result["matches"][0]["line"] == 1

    def test_ignore_case(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("Hello\nhello\nHELLO\n")
        result = asyncio.run(
            grep_files(
                "hello", cwd=str(tmp_path), ignore_case=True
            )
        )
        assert len(result["matches"]) == 3

    def test_context(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text(
            "line 1\nline 2\nhello\nline 4\nline 5\n"
        )
        result = asyncio.run(
            grep_files("hello", cwd=str(tmp_path), context=1)
        )
        assert len(result["matches"]) == 1
        assert "context" in result["matches"][0]
        # Context includes the match line
        # plus 1 line on each side
        assert len(result["matches"][0]["context"]) == 3

    def test_glob_filter(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("hello\n")
        (tmp_path / "b.txt").write_text("hello\n")
        result = asyncio.run(
            grep_files("hello", cwd=str(tmp_path), glob="*.py")
        )
        assert len(result["matches"]) == 1
        assert result["matches"][0]["path"].endswith(".py")

    def test_limit(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.py").write_text("hello\n")
        result = asyncio.run(
            grep_files("hello", cwd=str(tmp_path), limit=2)
        )
        assert result["matchLimitReached"] == 2

    def test_line_truncation(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("hello " + "x" * 1000 + "\n")
        result = asyncio.run(grep_files("hello", cwd=str(tmp_path)))
        assert result["linesTruncated"] is True
        # Line was truncated to a reasonable length
        assert len(result["matches"][0]["text"]) < 1000


class TestCreateGrepTool:
    @pytest.mark.asyncio
    async def test_factory(self) -> None:
        tool = await create_grep_tool_definition()
        assert tool["name"] == "grep"
        assert callable(tool["execute"])

    @pytest.mark.asyncio
    async def test_execute(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("hello world\n")
        tool = await create_grep_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1", {"pattern": "hello"}, None, None, None
        )
        assert "hello" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_no_match(self, tmp_path: Path) -> None:
        tool = await create_grep_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1", {"pattern": "nothing"}, None, None, None
        )
        assert "no matches" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_missing_pattern(self) -> None:
        tool = await create_grep_tool_definition()
        with pytest.raises(ValueError, match="pattern is required"):
            await tool["execute"]("c1", {}, None, None, None)

    @pytest.mark.asyncio
    async def test_alias(self) -> None:
        tool = await create_grep_tool()
        assert tool["name"] == "grep"


# ============================================================================
# ls
# ============================================================================


class TestListDirectory:
    def test_basic(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = asyncio.run(list_directory(str(tmp_path), cwd=str(tmp_path)))
        entries = result["entries"]
        assert any(e == "a.txt" for e in entries)
        assert any(e == "b.txt" for e in entries)

    def test_sorted_alphabetically(self, tmp_path: Path) -> None:
        (tmp_path / "z.txt").write_text("z")
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "m.txt").write_text("m")
        result = asyncio.run(list_directory(str(tmp_path), cwd=str(tmp_path)))
        entries = result["entries"]
        # Case-insensitive sort
        assert entries == sorted(entries, key=lambda e: e.lower())

    def test_directories_marked(self, tmp_path: Path) -> None:
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("x")
        result = asyncio.run(list_directory(str(tmp_path), cwd=str(tmp_path)))
        entries = result["entries"]
        assert "subdir/" in entries
        assert "file.txt" in entries

    def test_limit(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x")
        result = asyncio.run(
            list_directory(str(tmp_path), cwd=str(tmp_path), limit=2)
        )
        assert result["entryLimitReached"] == 2
        assert len(result["entries"]) <= 2

    def test_not_directory_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            asyncio.run(list_directory(str(f), cwd=str(tmp_path)))

    def test_empty_directory(self, tmp_path: Path) -> None:
        sub = tmp_path / "empty"
        sub.mkdir()
        result = asyncio.run(list_directory(str(sub), cwd=str(tmp_path)))
        assert result["entries"] == []


class TestCreateLsTool:
    @pytest.mark.asyncio
    async def test_factory(self) -> None:
        tool = await create_ls_tool_definition()
        assert tool["name"] == "ls"
        assert callable(tool["execute"])

    @pytest.mark.asyncio
    async def test_execute(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        tool = await create_ls_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1", {"path": str(tmp_path)}, None, None, None
        )
        assert "a.txt" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_execute_empty(self, tmp_path: Path) -> None:
        sub = tmp_path / "empty"
        sub.mkdir()
        tool = await create_ls_tool_definition(cwd=str(tmp_path))
        result = await tool["execute"](
            "c1", {"path": str(sub)}, None, None, None
        )
        assert "empty" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_alias(self) -> None:
        tool = await create_ls_tool()
        assert tool["name"] == "ls"
