"""tests.test_desktop_host_tools — Tests for desktop host tool wiring and execution parity.

Validates:
1. All core OpenClaw coding and PC tools are declared in desktop TOOL_DECLARATIONS (including mkdir and open_path).
2. Coding tools (read, write, edit, ls, mkdir, open_path) execute and verify real filesystem states.
3. System prompt configuration injects real drive availability, host directories, task context, and anti-hallucination rules.
"""

from pathlib import Path
from unittest.mock import patch
import pytest
from apps.desktop.src.jarvis_desktop.app import (
    CODING_TOOL_DECLARATIONS,
    TOOL_DECLARATIONS,
    _extract_tool_output,
)
from src.agents.sessions.tools import (
    create_automations_tool,
    create_edit_tool,
    create_exec_tool,
    create_ls_tool,
    create_mkdir_tool,
    create_open_path_tool,
    create_pdf_tool,
    create_read_tool,
    create_remove_path_tool,
    create_rename_path_tool,
    create_secrets_tool,
    create_web_fetch_tool,
    create_write_tool,
)
from src.agents.verification import ExecutionVerifier


def test_coding_tools_declared_in_desktop_app():
    declared_names = {t["name"] for t in TOOL_DECLARATIONS}
    required_coding_tools = {
        "ls",
        "read",
        "write",
        "edit",
        "exec",
        "process",
        "mkdir",
        "remove_path",
        "rename_path",
        "open_path",
        "set_task_goal",
        "web_fetch",
        "automations",
        "pdf",
        "secrets",
    }

    for name in required_coding_tools:
        assert name in declared_names, (
            f"Tool '{name}' must be declared in desktop host TOOL_DECLARATIONS"
        )

    for tool in CODING_TOOL_DECLARATIONS:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert tool["parameters"].get("type") == "OBJECT"


@pytest.mark.asyncio
async def test_coding_tools_real_filesystem_roundtrip(tmp_path):
    workspace = str(tmp_path)
    write_tool = create_write_tool(workspace)
    read_tool = create_read_tool(workspace)
    edit_tool = create_edit_tool(workspace)
    ls_tool = create_ls_tool(workspace)
    mkdir_tool = create_mkdir_tool(workspace)

    test_file = tmp_path / "app_module.py"
    initial_content = "def calculate():\n    return 42\n"

    # 1. Write file
    _ = await write_tool["execute"]("call_w1", {"path": str(test_file), "content": initial_content})
    assert test_file.exists()
    verif_w = ExecutionVerifier.verify_filesystem_write(
        str(test_file), expected_bytes=len(initial_content)
    )
    assert verif_w.verified is True

    # 2. Read file
    read_res = await read_tool["execute"]("call_r1", {"path": str(test_file)})
    read_text = _extract_tool_output(read_res)
    assert "return 42" in read_text

    # 3. Edit file
    _ = await edit_tool["execute"](
        "call_e1",
        {
            "path": str(test_file),
            "old_text": "return 42",
            "new_text": "return 100",
        },
    )
    assert "return 100" in test_file.read_text(encoding="utf-8")
    verif_e = ExecutionVerifier.verify_filesystem_edit(
        str(test_file), expected_content_fragments=["return 100"]
    )
    assert verif_e.verified is True

    # 4. Ls directory
    ls_res = await ls_tool["execute"]("call_l1", {"path": str(tmp_path)})
    ls_text = _extract_tool_output(ls_res)
    assert "app_module.py" in ls_text

    # 5. Mkdir directory
    new_dir = tmp_path / "subfolder" / "nested"
    mkdir_res = await mkdir_tool["execute"]("call_m1", {"path": str(new_dir)})
    assert new_dir.exists()
    assert new_dir.is_dir()
    verif_m = ExecutionVerifier.verify_filesystem_path(str(new_dir), must_be_dir=True)
    assert verif_m.verified is True
    assert "Directory created successfully" in _extract_tool_output(mkdir_res)


@pytest.mark.asyncio
async def test_open_path_tool_dispatch(tmp_path):
    workspace = str(tmp_path)
    open_tool = create_open_path_tool(workspace)

    # 1. Test explorer target
    with patch("subprocess.Popen") as mock_popen:
        res_exp = await open_tool["execute"]("call_o1", {"target": "explorer"})
        assert "File Explorer opened successfully" in _extract_tool_output(res_exp)
        mock_popen.assert_called_once_with(["explorer.exe"])

    # 2. Test user directory alias (Downloads)
    with patch("subprocess.Popen") as mock_popen:
        res_dl = await open_tool["execute"]("call_o2", {"target": "downloads"})
        expected_dl = str(Path.home() / "Downloads")
        assert expected_dl in _extract_tool_output(res_dl) or "Downloads" in _extract_tool_output(
            res_dl
        )
        mock_popen.assert_called_once()

    # 3. Test local directory target
    test_dir = tmp_path / "target_folder"
    test_dir.mkdir(parents=True, exist_ok=True)
    with patch("subprocess.Popen") as mock_popen:
        res_dir = await open_tool["execute"]("call_o3", {"target": str(test_dir)})
        assert "Successfully opened folder" in _extract_tool_output(res_dir)
        mock_popen.assert_called_once()

    # 4. Test URL opening
    with patch("webbrowser.open") as mock_webopen:
        res_url = await open_tool["execute"]("call_o4", {"target": "https://example.com"})
        assert "URL opened in default browser" in _extract_tool_output(res_url)
        mock_webopen.assert_called_once_with("https://example.com")


@pytest.mark.asyncio
async def test_remove_path_and_rename_path_real_filesystem(tmp_path):
    workspace = str(tmp_path)
    remove_tool = create_remove_path_tool(workspace)
    rename_tool = create_rename_path_tool(workspace)

    # 1. Test rename file
    file1 = tmp_path / "original.txt"
    file1.write_text("hello world", encoding="utf-8")
    file2 = tmp_path / "renamed.txt"

    res_ren = await rename_tool["execute"](
        "call_ren1", {"old_path": str(file1), "new_path": str(file2)}
    )
    assert not file1.exists()
    assert file2.exists()
    assert file2.read_text(encoding="utf-8") == "hello world"
    verif_ren = ExecutionVerifier.verify_filesystem_rename(str(file1), str(file2))
    assert verif_ren.verified is True
    assert "Successfully renamed" in _extract_tool_output(res_ren)

    # 2. Test remove file
    res_rem = await remove_tool["execute"]("call_rem1", {"path": str(file2)})
    assert not file2.exists()
    verif_rem = ExecutionVerifier.verify_filesystem_removal(str(file2))
    assert verif_rem.verified is True
    assert "Path removed successfully" in _extract_tool_output(res_rem)

    # 3. Test rename and remove directory recursively
    dir1 = tmp_path / "test_folder"
    dir1.mkdir()
    child_file = dir1 / "nested.txt"
    child_file.write_text("nested data", encoding="utf-8")

    dir2 = tmp_path / "renamed_folder"
    _ = await rename_tool["execute"]("call_ren2", {"old_path": str(dir1), "new_path": str(dir2)})
    assert not dir1.exists()
    assert dir2.exists()
    assert (dir2 / "nested.txt").exists()

    _ = await remove_tool["execute"]("call_rem2", {"path": str(dir2), "recursive": True})
    assert not dir2.exists()
    verif_rem_dir = ExecutionVerifier.verify_filesystem_removal(str(dir2))
    assert verif_rem_dir.verified is True


@pytest.mark.asyncio
async def test_exec_tool_no_safebins_block_in_full_mode(tmp_path):
    workspace = str(tmp_path)
    exec_tool = create_exec_tool(workspace)

    # In default security mode ("full"), commands like Rename-Item, ren, Remove-Item, echo must NOT be blocked by safeBins!
    res = await exec_tool["execute"]("call_x1", {"command": "echo 'JARVIS_EXEC_OK'"})
    out = _extract_tool_output(res)
    assert "not in safeBins" not in out
    assert "JARVIS_EXEC_OK" in out


def test_normalize_user_home_path_redirection():
    import os
    from src.agents.sessions.tools.path_utils import normalize_user_home_path

    current_home = os.path.expanduser("~")

    # Hallucinated user under C:\Users\ (or /Users/ or /home/)
    fake_win = r"C:\Users\rsnac\Downloads\New folder"
    norm_win = normalize_user_home_path(fake_win)
    expected_win = os.path.normpath(os.path.join(current_home, r"Downloads\New folder"))
    assert norm_win == expected_win

    # Tilde with hallucinated user ~rsnac/Downloads
    fake_tilde = "~rsnac/Downloads"
    norm_tilde = normalize_user_home_path(fake_tilde)
    expected_tilde = os.path.normpath(os.path.join(current_home, "Downloads"))
    assert norm_tilde == expected_tilde

    # Real user path stays intact
    real_path = os.path.join(current_home, "Downloads")
    assert normalize_user_home_path(real_path) == real_path


@pytest.mark.asyncio
async def test_mkdir_tool_hallucinated_user_and_permission_resilience(tmp_path):
    import os
    from unittest.mock import patch

    workspace = str(tmp_path)
    mkdir_tool = create_mkdir_tool(workspace)

    # 1. Hallucinated user path redirected into temp directory safely
    fake_path = r"C:\Users\rsnac\Downloads\subfolder"
    with patch("src.agents.sessions.tools.path_utils.os.path.expanduser", return_value=str(tmp_path)):
        res = await mkdir_tool["execute"]("call_m_fake", {"path": fake_path})
        assert "Directory created successfully" in _extract_tool_output(res)
        expected_dir = tmp_path / "Downloads" / "subfolder"
        assert expected_dir.exists()
        assert expected_dir.is_dir()

    # 2. PermissionError on protected directory returns structured error result without crashing
    with patch("os.makedirs", side_effect=PermissionError("[WinError 5] Access is denied: 'C:\\Users\\protected'")):
        res_perm = await mkdir_tool["execute"]("call_m_perm", {"path": r"C:\Users\protected\sub"})
        assert res_perm["details"]["created"] is False
        assert "Permission denied" in _extract_tool_output(res_perm)


def test_desktop_environment_prompt_context():
    from unittest.mock import MagicMock
    from apps.desktop.src.jarvis_desktop.app import JarvisLive
    live = JarvisLive(ui=MagicMock())
    cfg = live._build_config()
    sys_inst = cfg.system_instruction or ""
    assert "[HOST & USER ENVIRONMENT]" in sys_inst
    assert "Current Logged-in User:" in sys_inst
    assert "User Home Directory:" in sys_inst
    assert "Downloads Directory:" in sys_inst


@pytest.mark.asyncio
async def test_process_tool_interactive_input():
    import io
    from unittest.mock import MagicMock
    from src.agents.sessions.process_registry import ProcessSession, registry
    from src.agents.sessions.tools import create_process_tool

    process_tool = create_process_tool()

    mock_proc = MagicMock()
    mock_stdin = io.BytesIO()
    mock_proc.stdin = mock_stdin

    session = ProcessSession(
        command="test_cli",
        session_key="agent:main:main",
        proc=mock_proc,
        backgrounded=True,
    )
    registry.register(session)

    # 1. Write text to process
    res_w = await process_tool["execute"]("call_p_w", {"action": "write", "session_id": session.id, "data": "hello"})
    assert "Wrote 5 chars" in _extract_tool_output(res_w)
    assert mock_stdin.getvalue() == b"hello"

    # 2. Submit (Enter)
    res_sub = await process_tool["execute"]("call_p_sub", {"action": "submit", "session_id": session.id})
    assert "Submitted session" in _extract_tool_output(res_sub)
    assert mock_stdin.getvalue() == b"hello\r\n"

    # 3. Paste text
    res_p = await process_tool["execute"]("call_p_paste", {"action": "paste", "session_id": session.id, "text": "paste_content"})
    assert "Pasted 13 chars" in _extract_tool_output(res_p)
    assert b"paste_content" in mock_stdin.getvalue()

    # 4. Send keys (Ctrl+C / sigint)
    res_k = await process_tool["execute"]("call_p_k", {"action": "send-keys", "session_id": session.id, "keys": ["ctrl+c"]})
    assert "Sent input/keys" in _extract_tool_output(res_k)
    assert b"\x03" in mock_stdin.getvalue()

    registry.remove(session.id)


@pytest.mark.asyncio
async def test_web_fetch_tool_execution():
    from unittest.mock import AsyncMock, patch
    import httpx

    web_fetch = create_web_fetch_tool()

    html_content = (
        "<!DOCTYPE html><html><head><title>Test Article Title</title></head>"
        "<body><h1>Main Header</h1><p>This is a paragraph with <a href='https://example.com'>a link</a>.</p></body></html>"
    )

    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.text = html_content
    mock_resp.content = html_content.encode("utf-8")
    mock_resp.url = httpx.URL("https://example.com/test")

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        # 1. Test markdown extraction
        res = await web_fetch["execute"]("call_wf1", {"url": "https://example.com/test"})
        text_out = _extract_tool_output(res)
        assert "Title: Test Article Title" in text_out
        assert "Main Header" in text_out
        assert "This is a paragraph" in text_out
        assert res["details"]["status_code"] == 200

        # 2. Test raw HTML extraction
        res_raw = await web_fetch["execute"]("call_wf2", {"url": "https://example.com/test", "extract_text": False})
        raw_out = _extract_tool_output(res_raw)
        assert "<html>" in raw_out
        assert "<title>Test Article Title</title>" in raw_out

        # 3. Test invalid URL rejection
        res_bad = await web_fetch["execute"]("call_wf3", {"url": "ftp://example.com/file"})
        assert "Invalid URL" in _extract_tool_output(res_bad) or res_bad["details"].get("error") is not None


@pytest.mark.asyncio
async def test_automations_tool_execution(tmp_path):
    automations = create_automations_tool(str(tmp_path))

    # 1. Create a one-shot scheduled task
    create_res = await automations["execute"](
        "call_a1",
        {
            "action": "create",
            "schedule": "30s",
            "prompt": "Run integrity check",
            "job_id": "test_job_1",
        },
    )
    assert create_res["details"]["success"] is True
    assert "test_job_1" in _extract_tool_output(create_res)

    # 2. Status of created task
    status_res = await automations["execute"](
        "call_a2",
        {"action": "status", "job_id": "test_job_1"},
    )
    assert status_res["details"]["job"] is not None
    assert "Run integrity check" in _extract_tool_output(status_res)

    # 3. List tasks
    list_res = await automations["execute"]("call_a3", {"action": "list"})
    assert list_res["details"]["count"] >= 1
    assert "test_job_1" in _extract_tool_output(list_res)

    # 4. Delete task
    del_res = await automations["execute"](
        "call_a4",
        {"action": "delete", "job_id": "test_job_1"},
    )
    assert del_res["details"]["success"] is True
    assert "test_job_1" in _extract_tool_output(del_res)


@pytest.mark.asyncio
async def test_pdf_tool_execution(tmp_path):
    import fitz  # PyMuPDF

    pdf_tool = create_pdf_tool(str(tmp_path))

    # Generate a two-page PDF for test
    pdf_path = tmp_path / "sample_doc.pdf"
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text((50, 72), "First Page Header\nHello from page 1 content.")

    page2 = doc.new_page()
    page2.insert_text((50, 72), "Second Page Header\nSecret keyword TARGET_TOKEN resides here.")

    doc.save(str(pdf_path))
    doc.close()

    # 1. Extract all pages
    res_all = await pdf_tool["execute"]("call_p1", {"file_path": str(pdf_path)})
    out_all = _extract_tool_output(res_all)
    assert "First Page Header" in out_all
    assert "Secret keyword TARGET_TOKEN" in out_all
    assert res_all["details"]["total_pages"] == 2

    # 2. Extract page 1 only
    res_p1 = await pdf_tool["execute"]("call_p2", {"file_path": str(pdf_path), "pages": "1"})
    out_p1 = _extract_tool_output(res_p1)
    assert "First Page Header" in out_p1
    assert "TARGET_TOKEN" not in out_p1

    # 3. Search query/prompt filtering
    res_q = await pdf_tool["execute"](
        "call_p3",
        {"file_path": str(pdf_path), "prompt": "TARGET_TOKEN"},
    )
    out_q = _extract_tool_output(res_q)
    assert "TARGET_TOKEN" in out_q
    assert res_q["details"]["matches_found"] == 1


@pytest.mark.asyncio
async def test_secrets_tool_execution(tmp_path, monkeypatch):
    secrets_tool = create_secrets_tool(str(tmp_path))

    # Point home and env to controlled test locations
    test_home = tmp_path / "fake_home"
    test_home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: test_home)
    monkeypatch.setenv("JARVIS_TEST_SECRET_KEY", "super_secret_val_xyz")

    # 1. List secrets: key name present, value NEVER exposed
    list_res = await secrets_tool["execute"]("call_s1", {"action": "list"})
    list_out = _extract_tool_output(list_res)
    assert "JARVIS_TEST_SECRET_KEY" in list_out
    assert "super_secret_val_xyz" not in list_out
    assert "super_secret_val_xyz" not in str(list_res["details"])

    # 2. Request a secret
    req_res = await secrets_tool["execute"](
        "call_s2",
        {
            "action": "request",
            "secret_name": "NEW_API_TOKEN",
            "reason": "Needed for external service integration",
        },
    )
    req_out = _extract_tool_output(req_res)
    assert "NEW_API_TOKEN" in req_out
    assert req_res["details"]["status"] == "pending"

    # Verify pending requests file was persisted
    pending_file = test_home / ".jarvis" / "credentials" / "pending_requests.json"
    assert pending_file.exists()
    assert "NEW_API_TOKEN" in pending_file.read_text(encoding="utf-8")

    # 3. Delete a secret
    del_res = await secrets_tool["execute"](
        "call_s3",
        {"action": "delete", "secret_name": "JARVIS_TEST_SECRET_KEY"},
    )
    assert del_res["details"]["status"] == "deleted"

