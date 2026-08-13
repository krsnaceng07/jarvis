from __future__ import annotations

import os
from pathlib import Path

from src.agents.embedded_agent_runner.sandbox_materialize import materialize_skill_entries


def test_materialize_copies_files(tmp_path: Path) -> None:
    # create a fake workspace
    src = tmp_path / "workspace"
    src.mkdir()
    a = src / "skills" / "s1.py"
    a.parent.mkdir()
    a.write_text("print('hello')")

    entries = [{"skill": {"filePath": str(a.relative_to(src))}}]
    tmpdir, new_entries = materialize_skill_entries(entries, str(src))
    try:
        assert os.path.isdir(tmpdir)
        new_path = new_entries[0]["skill"]["filePath"]
        assert os.path.exists(new_path)
        assert "hello" in open(new_path, "r", encoding="utf-8").read()
    finally:
        # cleanup
        import shutil

        shutil.rmtree(tmpdir, ignore_errors=True)
