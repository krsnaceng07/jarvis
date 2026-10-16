"""Tests for file-transfer operations, policies, tools, and CLI."""

from __future__ import annotations

import base64
from pathlib import Path
import pytest

from extensions.file_transfer.src.cli import handle_file_transfer_cli, repair_file_transfer_config
from extensions.file_transfer.src.operations import (
    fetch_dir,
    fetch_file,
    is_binary_bytes,
    list_dir,
    write_file,
)
from extensions.file_transfer.src.policy import (
    LiteralGrant,
    NodePolicyConfig,
    check_path_policy,
    is_path_contained_in,
)
from extensions.file_transfer.src.tools import (
    execute_dir_fetch_tool,
    execute_dir_list_tool,
    execute_file_fetch_tool,
    execute_file_write_tool,
)


def test_is_binary_bytes() -> None:
    assert not is_binary_bytes(b"hello world UTF-8 text")
    assert is_binary_bytes(b"hello\x00world")
    assert is_binary_bytes(b"\xff\xfe\xfd")


def test_path_containment(tmp_path: Path) -> None:
    child = tmp_path / "sub" / "file.txt"
    assert is_path_contained_in(str(child), str(tmp_path))
    assert not is_path_contained_in(str(tmp_path), str(child))


def test_check_path_policy(tmp_path: Path) -> None:
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    denied_file = allowed_dir / "secret.key"

    policy = NodePolicyConfig(
        allow_read_paths=[str(allowed_dir)],
        deny_paths=[str(denied_file)],
    )

    allowed, reason = check_path_policy(
        "node-1", "read", str(allowed_dir / "doc.txt"), policy=policy
    )
    assert allowed
    assert reason is None

    allowed, reason = check_path_policy("node-1", "read", str(denied_file), policy=policy)
    assert not allowed
    assert "denied root" in (reason or "")

    # Test literal grant override
    grant = LiteralGrant(
        node_id="node-1",
        command="file.fetch",
        requested_path=str(denied_file),
        canonical_path=str(denied_file.resolve()),
    )
    allowed, _ = check_path_policy(
        "node-1", "read", str(denied_file), policy=policy, grants=[grant]
    )
    assert not allowed  # Deny path takes precedence over grants


def test_fetch_and_write_file_text_and_binary(tmp_path: Path) -> None:
    text_file = tmp_path / "sample.txt"
    write_res = write_file(str(text_file), "hello jarvis transfer", overwrite=True)
    assert write_res["bytesWritten"] == len("hello jarvis transfer")

    fetch_res = fetch_file(str(text_file))
    assert fetch_res["content"] == "hello jarvis transfer"
    assert fetch_res["isText"] is True
    assert fetch_res["bytes"] == len("hello jarvis transfer")

    # Binary file
    bin_file = tmp_path / "data.bin"
    raw_bin = b"\x00\x01\x02\x03\x04"
    write_file(str(bin_file), base64.b64encode(raw_bin).decode("ascii"), is_base64=True)
    fetch_bin = fetch_file(str(bin_file))
    assert fetch_bin["isText"] is False
    assert base64.b64decode(fetch_bin["content"]) == raw_bin


def test_list_and_fetch_dir(tmp_path: Path) -> None:
    subdir = tmp_path / "folder"
    subdir.mkdir()
    (subdir / "a.txt").write_text("aaa")
    (subdir / "b.txt").write_text("bbb")

    listing = list_dir(str(subdir))
    assert listing["count"] == 2

    archive = fetch_dir(str(subdir))
    assert len(archive) > 0


@pytest.mark.asyncio
async def test_tools_execution(tmp_path: Path) -> None:
    target = tmp_path / "tool_test.txt"
    write_out = await execute_file_write_tool({"path": str(target), "content": "tool content"})
    assert "Successfully wrote" in write_out["content"][0]["text"]

    fetch_out = await execute_file_fetch_tool({"path": str(target)})
    assert fetch_out["content"][0]["text"] == "tool content"

    list_out = await execute_dir_list_tool({"path": str(tmp_path)})
    assert "Found" in list_out["content"][0]["text"]

    fetch_dir_out = await execute_dir_fetch_tool({"path": str(tmp_path)})
    assert "Archive generated" in fetch_dir_out["content"][0]["text"]


def test_cli_and_doctor() -> None:
    cfg = {"nodes": {"node-1": {}}, "literalGrants": []}
    cli_out = handle_file_transfer_cli(["status"], cfg)
    assert "Configured nodes: 1" in cli_out

    repaired, repairs = repair_file_transfer_config({})
    assert repaired["policyVersion"] == 2
    assert "Set file-transfer policyVersion to 2" in repairs
