from pathlib import Path

from src.bootstrap import seed_workspace


def test_new_workspace_seeds_openclaw_root_contract(tmp_path: Path) -> None:
    result = seed_workspace(tmp_path)

    for filename in ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "BOOTSTRAP.md"):
        path = tmp_path / filename
        assert path.exists()
        assert "seeded by src.bootstrap" in path.read_text(encoding="utf-8")
    assert str(tmp_path / "BOOTSTRAP.md") in result.root_seeded


def test_workspace_bootstrap_does_not_overwrite_or_recreate(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# User policy\n", encoding="utf-8")
    (tmp_path / "BOOTSTRAP.md").unlink()

    result = seed_workspace(tmp_path)

    assert agents.read_text(encoding="utf-8") == "# User policy\n"
    assert not (tmp_path / "BOOTSTRAP.md").exists()
    assert str(agents) in result.root_skipped


def test_bootstrap_can_be_skipped_for_first_run(tmp_path: Path) -> None:
    result = seed_workspace(tmp_path, skip_bootstrap=True)

    assert not (tmp_path / "BOOTSTRAP.md").exists()
    assert str(tmp_path / "AGENTS.md") in result.root_seeded
    assert str(tmp_path / "BOOTSTRAP.md") not in result.root_seeded


def test_bootstrap_cleans_up_after_workspace_is_configured(tmp_path: Path) -> None:
    seed_workspace(tmp_path)
    (tmp_path / "IDENTITY.md").write_text("# Identity\n\nConfigured\n", encoding="utf-8")

    result = seed_workspace(tmp_path)

    assert not (tmp_path / "BOOTSTRAP.md").exists()
    assert getattr(result, "root_removed", [])
