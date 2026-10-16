"""tests.test_drive_and_fs_parity — Tests for real PC drive discovery and truthfulness.

Validates:
1. Dynamic drive discovery via Win32 API / fallback.
2. Accurate detection of available vs non-available logical drives.
3. ls tool listing drives with path="drives".
4. Truthful failure (FileNotFoundError) when accessing non-existent drives (e.g. D:\\).
"""

import sys
import pytest
from src.agents.sessions.tools.path_utils import (
    discover_system_drives,
    is_drive_available,
)
from src.agents.sessions.tools.ls import create_ls_tool


def test_discover_system_drives_returns_real_drives():
    drives = discover_system_drives()
    assert isinstance(drives, list)
    assert len(drives) >= 1
    for drive in drives:
        assert drive.endswith("\\") or drive.endswith("/")
        assert len(drive) == 3 or drive.startswith("/")

    if sys.platform == "win32":
        # On this system, C:\ and E:\ exist
        assert "C:\\" in drives
        assert "E:\\" in drives
        assert "D:\\" not in drives


def test_is_drive_available():
    if sys.platform == "win32":
        assert is_drive_available("C:\\") is True
        assert is_drive_available("C:/Windows") is True
        assert is_drive_available("E:\\jarvis") is True
        assert is_drive_available("D:\\") is False
        assert is_drive_available("D:/nonexistent") is False
        assert is_drive_available("Z:\\never_exists") is False
    else:
        assert is_drive_available("/tmp") is True


@pytest.mark.asyncio
async def test_ls_tool_list_drives():
    ls = create_ls_tool(cwd="E:/jarvis" if sys.platform == "win32" else "/tmp")
    result = await ls["execute"]("call_drives_1", {"path": "drives"})
    assert "content" in result
    text = result["content"][0]["text"]
    if sys.platform == "win32":
        assert "C:\\" in text
        assert "E:\\" in text
        assert "D:\\" not in text


@pytest.mark.asyncio
async def test_ls_tool_rejects_missing_drive_with_truthful_error():
    if sys.platform != "win32":
        pytest.skip("Windows-specific drive letter test")

    ls = create_ls_tool(cwd="E:/jarvis")
    with pytest.raises(FileNotFoundError) as exc_info:
        await ls["execute"]("call_d_missing", {"path": "D:\\"})

    err_msg = str(exc_info.value)
    assert "Drive not found: 'D:\\'" in err_msg
    assert "This PC only has drives:" in err_msg
    assert "C:\\" in err_msg
    assert "E:\\" in err_msg


@pytest.mark.asyncio
async def test_ls_tool_lists_valid_directory(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    f1 = sub / "test1.txt"
    f1.write_text("hello", encoding="utf-8")
    f2 = sub / "test2.py"
    f2.write_text("print(1)", encoding="utf-8")

    ls = create_ls_tool(cwd=str(tmp_path))
    result = await ls["execute"]("call_valid_dir", {"path": str(sub)})
    assert "content" in result
    text = result["content"][0]["text"]
    assert "test1.txt" in text
    assert "test2.py" in text
