import os
import pytest

from src.agents.sessions.tools.apply_patch import apply_patch, parse_patch_text


@pytest.fixture
def temp_workspace(tmp_path):
    os.chdir(tmp_path)
    return tmp_path


def test_parse_patch_text_add_file():
    patch_text = """*** Begin Patch
*** Add File: test.txt
+line 1
+line 2
*** End Patch
"""
    parsed = parse_patch_text(patch_text)
    assert len(parsed["hunks"]) == 1
    hunk = parsed["hunks"][0]
    assert hunk["kind"] == "add"
    assert hunk["path"] == "test.txt"
    assert hunk["contents"] == "line 1\nline 2\n"


def test_parse_patch_text_delete_file():
    patch_text = """*** Begin Patch
*** Delete File: old.txt
*** End Patch
"""
    parsed = parse_patch_text(patch_text)
    assert len(parsed["hunks"]) == 1
    hunk = parsed["hunks"][0]
    assert hunk["kind"] == "delete"
    assert hunk["path"] == "old.txt"


def test_parse_patch_text_update_file():
    patch_text = """*** Begin Patch
*** Update File: src/main.py
@@ optional context
-old line
+new line
*** End Patch
"""
    parsed = parse_patch_text(patch_text)
    assert len(parsed["hunks"]) == 1
    hunk = parsed["hunks"][0]
    assert hunk["kind"] == "update"
    assert hunk["path"] == "src/main.py"
    assert len(hunk["chunks"]) == 1
    chunk = hunk["chunks"][0]
    assert chunk["changeContext"] == "optional context"
    assert chunk["oldLines"] == ["old line"]
    assert chunk["newLines"] == ["new line"]


@pytest.mark.asyncio
async def test_apply_patch_execution(temp_workspace):
    # Setup initial files
    (temp_workspace / "old.txt").write_text("to delete", encoding="utf-8")
    src_dir = temp_workspace / "src"
    src_dir.mkdir()
    (src_dir / "main.py").write_text("hello world\nold line\ngoodbye\n", encoding="utf-8")

    patch_text = """*** Begin Patch
*** Add File: new.txt
+new file line 1
+new file line 2
*** Delete File: old.txt
*** Update File: src/main.py
@@
-old line
+new line
*** End Patch
"""
    
    summary = await apply_patch(patch_text, cwd=str(temp_workspace))
    
    assert summary["addedFiles"] == 1
    assert summary["deletedFiles"] == 1
    assert summary["updatedFiles"] == 1
    
    assert (temp_workspace / "new.txt").exists()
    assert (temp_workspace / "new.txt").read_text(encoding="utf-8") == "new file line 1\nnew file line 2\n"
    
    assert not (temp_workspace / "old.txt").exists()
    
    assert (temp_workspace / "src" / "main.py").read_text(encoding="utf-8") == "hello world\nnew line\ngoodbye\n"


@pytest.mark.asyncio
async def test_apply_patch_workspace_only(temp_workspace):
    patch_text = """*** Begin Patch
*** Add File: ../out_of_bounds.txt
+line 1
*** End Patch
"""
    
    with pytest.raises(ValueError, match="escapes workspace"):
        await apply_patch(patch_text, cwd=str(temp_workspace), workspace_only=True)
