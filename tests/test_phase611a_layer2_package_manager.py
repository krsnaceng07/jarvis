"""Phase 6.11a — package_manager + supporting helpers tests.

Verifies the package manager pipeline:
- path_utils — canonicalize_path, is_local_path, to_posix_path
- ignore_rules — add_ignore_rules, IgnoreMatcher, is_path_within_root,
  is_real_path_within_root
- git — parse_git_url, GitSource
- package_manager — DefaultPackageManager
  (local resolution + auto-discovery +
  pattern application + dedupe)

Test contracts mirror OpenClaw 1:1:
- ``parse_git_url`` strips the trailing ``.git`` suffix from the path
  (matches ``normalizeGitPath`` in the OpenClaw source) and splits the
  optional ``@ref`` suffix into :attr:`GitSource.ref`. The full
  ``user/repo`` path is preserved.
- ``is_local_path`` mirrors OpenClaw's ``isLocalPath``: it rejects every
  explicit URL scheme (``http:`` / ``https:`` / ``ssh:`` / ``npm:`` /
  ``git:`` / ``github:``) and treats everything else (including the
  ``git@host:user/repo`` SSH short form) as local.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from src.agents.sessions.git import GitSource, parse_git_url
from src.agents.sessions.ignore_rules import (
    IgnoreMatcher,
    add_ignore_rules,
    is_path_within_root,
)
from src.agents.sessions.package_manager import (
    CONFIG_DIR_NAME_PRIMARY,
    DefaultPackageManager,
    PathMetadata,
    ResolvedPaths,
    _apply_patterns,
    _has_glob_pattern,
    _is_override_pattern,
    _is_pattern,
    _resource_precedence_rank,
    _resolve_extension_entries,
    _split_patterns,
    canonicalize_path,
    is_local_path,
    to_posix_path,
)
from src.agents.sessions.settings_manager import SettingsManager


# ============================================================================
# path_utils
# ============================================================================


class TestCanonicalizePath:
    def test_resolves_symlinks(self, tmp_path: Path) -> None:
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        try:
            os.symlink(str(real), str(link), target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlink not supported on this platform")
        result = canonicalize_path(str(link))
        assert os.path.normpath(result) == os.path.normpath(str(real))

    def test_normalizes_nonexistent(self) -> None:
        result = canonicalize_path("/nonexistent/foo/bar")
        assert os.path.isabs(result)


class TestIsLocalPath:
    def test_npm_is_not_local(self) -> None:
        assert is_local_path("npm:foo") is False
        assert is_local_path("npm:foo@1.0.0") is False

    def test_https_is_not_local(self) -> None:
        # Mirrors OpenClaw's isLocalPath
        # (rejects the ``https:`` prefix).
        assert is_local_path("https://github.com/foo/bar.git") is False

    def test_http_is_not_local(self) -> None:
        assert is_local_path("http://github.com/foo/bar.git") is False

    def test_ssh_scheme_is_not_local(self) -> None:
        assert is_local_path("ssh://git@github.com/foo/bar.git") is False

    def test_ssh_short_form_is_local(self) -> None:
        # OpenClaw treats ``git@host:user/repo``
        # as local — the prefix is ``git@``,
        # not ``git:``. The Python port mirrors
        # that.
        assert is_local_path("git@github.com:foo/bar.git") is True

    def test_github_shorthand_is_not_local(self) -> None:
        assert is_local_path("github:foo/bar") is False

    def test_absolute_is_local(self) -> None:
        assert is_local_path("/foo/bar") is True
        # Windows-style absolute paths are
        # local too.
        if os.name == "nt":
            assert is_local_path("C:\\foo\\bar") is True

    def test_relative_is_local(self) -> None:
        assert is_local_path("foo/bar") is True
        assert is_local_path("./foo") is True

    def test_tilde_is_local(self) -> None:
        assert is_local_path("~/foo") is True

    def test_file_url_is_local(self) -> None:
        assert is_local_path("file:///foo/bar") is True

    def test_empty(self) -> None:
        assert is_local_path("") is False


class TestToPosixPath:
    def test_unix_path(self) -> None:
        assert to_posix_path("a/b/c") == "a/b/c"

    def test_windows_path(self) -> None:
        result = to_posix_path("a\\b\\c")
        assert "\\" not in result
        assert result == "a/b/c"

    def test_empty(self) -> None:
        assert to_posix_path("") == ""


# ============================================================================
# ignore_rules
# ============================================================================


class TestAddIgnoreRules:
    def test_creates_matcher(self, tmp_path: Path) -> None:
        matcher = add_ignore_rules(str(tmp_path), str(tmp_path))
        assert isinstance(matcher, IgnoreMatcher)

    def test_ignores_node_modules(self, tmp_path: Path) -> None:
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "foo.js").write_text("x")
        matcher = add_ignore_rules(str(tmp_path), str(tmp_path))
        assert matcher.ignores("node_modules") is True
        assert matcher.ignores("node_modules/foo.js") is True

    def test_ignores_pycache(self, tmp_path: Path) -> None:
        (tmp_path / "__pycache__").mkdir()
        matcher = add_ignore_rules(str(tmp_path), str(tmp_path))
        assert matcher.ignores("__pycache__") is True

    def test_does_not_ignore_normal(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("x")
        matcher = add_ignore_rules(str(tmp_path), str(tmp_path))
        assert matcher.ignores("src") is False
        assert matcher.ignores("src/main.py") is False

    def test_glob_pattern(self, tmp_path: Path) -> None:
        (tmp_path / "foo.pyc").write_text("x")
        matcher = add_ignore_rules(str(tmp_path), str(tmp_path))
        assert matcher.ignores("foo.pyc") is True


class TestIsPathWithinRoot:
    def test_inside(self, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        assert is_path_within_root(str(tmp_path), str(sub)) is True

    def test_outside(self, tmp_path: Path) -> None:
        other = tmp_path.parent / "other"
        assert is_path_within_root(str(tmp_path), str(other)) is False

    def test_equal(self, tmp_path: Path) -> None:
        assert is_path_within_root(str(tmp_path), str(tmp_path)) is True


# ============================================================================
# git
# ============================================================================


class TestParseGitUrl:
    """Mirrors OpenClaw's ``parseGitUrl``.

    The path is returned WITHOUT the trailing
    ``.git`` suffix (the OpenClaw source
    strips it via ``normalizeGitPath``).
    The full ``user/repo`` path is preserved.
    An optional ``@ref`` suffix is split out
    into ``ref``.
    """

    def test_https(self) -> None:
        result = parse_git_url("https://github.com/foo/bar.git")
        assert result is not None
        assert result.host == "github.com"
        assert result.path == "foo/bar"
        assert result.ref is None

    def test_ssh(self) -> None:
        result = parse_git_url("ssh://git@github.com/foo/bar.git")
        assert result is not None
        assert result.host == "github.com"
        assert result.path == "foo/bar"
        assert result.ref is None

    def test_ssh_short(self) -> None:
        result = parse_git_url("git@github.com:foo/bar.git")
        assert result is not None
        assert result.host == "github.com"
        assert result.path == "foo/bar"
        assert result.ref is None

    def test_with_ref(self) -> None:
        result = parse_git_url("https://github.com/foo/bar@main")
        assert result is not None
        assert result.ref == "main"
        assert result.path == "foo/bar"

    def test_ssh_short_with_ref(self) -> None:
        result = parse_git_url("git@github.com:foo/bar.git@v1.0.0")
        assert result is not None
        assert result.host == "github.com"
        assert result.path == "foo/bar"
        assert result.ref == "v1.0.0"

    def test_not_git(self) -> None:
        assert parse_git_url("npm:foo") is None
        assert parse_git_url("file:///foo/bar") is None
        assert parse_git_url("~/foo") is None
        assert parse_git_url("/absolute/path") is None
        assert parse_git_url("relative/path") is None
        assert parse_git_url("") is None

    def test_git_protocol(self) -> None:
        result = parse_git_url("git://github.com/foo/bar.git")
        assert result is not None
        assert result.host == "github.com"
        assert result.path == "foo/bar"

    def test_git_source_dataclass(self) -> None:
        src = GitSource(host="github.com", path="foo/bar", ref="main")
        assert src.host == "github.com"
        assert src.path == "foo/bar"
        assert src.ref == "main"


# ============================================================================
# package_manager: helpers
# ============================================================================


class TestParseNpmSpec:
    """``_parse_npm_spec`` is a method on
    :class:`DefaultPackageManager`; the tests
    build a throwaway instance + call it."""

    @staticmethod
    def _make_pm(tmp_path: Path) -> DefaultPackageManager:
        sm = SettingsManager.in_memory()
        return DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )

    def test_simple(self, tmp_path: Path) -> None:
        pm = self._make_pm(tmp_path)
        result = pm._parse_npm_spec("foo")
        assert result["name"] == "foo"
        assert "version" not in result

    def test_with_version(self, tmp_path: Path) -> None:
        pm = self._make_pm(tmp_path)
        result = pm._parse_npm_spec("foo@1.0.0")
        assert result["name"] == "foo"
        assert result["version"] == "1.0.0"

    def test_scoped(self, tmp_path: Path) -> None:
        pm = self._make_pm(tmp_path)
        result = pm._parse_npm_spec("@scope/foo")
        assert result["name"] == "@scope/foo"

    def test_scoped_with_version(self, tmp_path: Path) -> None:
        pm = self._make_pm(tmp_path)
        result = pm._parse_npm_spec("@scope/foo@1.0.0")
        assert result["name"] == "@scope/foo"
        assert result["version"] == "1.0.0"


class TestPatternHelpers:
    def test_is_pattern(self) -> None:
        assert _is_pattern("foo") is False
        assert _is_pattern("*.js") is True
        assert _is_pattern("!foo") is True
        assert _is_pattern("+foo") is True
        assert _is_pattern("-foo") is True
        assert _is_pattern("foo?bar") is True

    def test_is_override_pattern(self) -> None:
        assert _is_override_pattern("!foo") is True
        assert _is_override_pattern("+foo") is True
        assert _is_override_pattern("-foo") is True
        assert _is_override_pattern("foo") is False
        assert _is_override_pattern("*.js") is False

    def test_has_glob_pattern(self) -> None:
        assert _has_glob_pattern("*.js") is True
        assert _has_glob_pattern("foo?bar") is True
        assert _has_glob_pattern("foo") is False

    def test_split_patterns(self) -> None:
        plain, patterns = _split_patterns(
            ["a", "b", "*.js", "!c", "+d"]
        )
        assert plain == ["a", "b"]
        assert patterns == ["*.js", "!c", "+d"]


class TestApplyPatterns:
    def test_no_patterns_returns_all(self) -> None:
        result = _apply_patterns(["a", "b", "c"], [], "/")
        assert result == {"a", "b", "c"}

    def test_includes_filter(self) -> None:
        result = _apply_patterns(
            ["a.js", "b.py", "c.js"], ["*.js"], "/"
        )
        assert "a.js" in result
        assert "c.js" in result
        assert "b.py" not in result

    def test_excludes_filter(self) -> None:
        # ``*.js`` includes only the .js files;
        # ``!b.js`` excludes b.js.
        result = _apply_patterns(
            ["a.js", "b.js", "c.py"],
            ["*.js", "!b.js"],
            "/",
        )
        assert "a.js" in result
        assert "b.js" not in result
        assert "c.py" not in result

    def test_excludes_filter_wildcard_include(self) -> None:
        # ``*`` includes every file; ``!b.js``
        # excludes only b.js.
        result = _apply_patterns(
            ["a.js", "b.js", "c.py"],
            ["*", "!b.js"],
            "/",
        )
        assert "a.js" in result
        assert "b.js" not in result
        assert "c.py" in result

    def test_force_include(self) -> None:
        # ``!b.js`` excludes b.js, but ``+b.js``
        # force-includes it back.
        result = _apply_patterns(
            ["a.js", "b.js"],
            ["!b.js", "+b.js"],
            "/",
        )
        assert result == {"a.js", "b.js"}

    def test_force_exclude(self) -> None:
        # ``*.js`` includes a.js + b.js, but
        # ``-b.js`` force-excludes b.js.
        result = _apply_patterns(
            ["a.js", "b.js"],
            ["*.js", "-b.js"],
            "/",
        )
        assert result == {"a.js"}


class TestResourcePrecedenceRank:
    def test_project_local(self) -> None:
        m = PathMetadata(source="local", scope="project", origin="top-level")
        assert _resource_precedence_rank(m) == 0

    def test_project_auto(self) -> None:
        m = PathMetadata(source="auto", scope="project", origin="top-level")
        assert _resource_precedence_rank(m) == 1

    def test_user_local(self) -> None:
        m = PathMetadata(source="local", scope="user", origin="top-level")
        assert _resource_precedence_rank(m) == 2

    def test_user_auto(self) -> None:
        m = PathMetadata(source="auto", scope="user", origin="top-level")
        assert _resource_precedence_rank(m) == 3

    def test_package(self) -> None:
        m = PathMetadata(
            source="npm:foo", scope="user", origin="package"
        )
        assert _resource_precedence_rank(m) == 4


# ============================================================================
# package_manager: DefaultPackageManager
# ============================================================================


def _make_settings_manager(tmp_path: Path) -> SettingsManager:
    """Build a SettingsManager with in-memory
    storage for tests."""
    return SettingsManager.in_memory()


class TestDefaultPackageManagerLocal:
    def test_resolve_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Isolate the home dir so the auto-discovery
        # path doesn't pick up the operator's
        # real ``~/.agents/skills`` install.
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        monkeypatch.setenv("HOME", str(empty_home))
        monkeypatch.setenv("USERPROFILE", str(empty_home))
        # Bound the ancestor walk-up at ``tmp_path``
        # by creating a fake ``.git`` directory;
        # otherwise the walk would climb out of the
        # test dir + discover the operator's real
        # ``~/.agents/skills/`` install.
        (tmp_path / ".git").mkdir()
        sm = _make_settings_manager(tmp_path)
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        assert isinstance(result, ResolvedPaths)
        assert result.extensions == []
        assert result.skills == []
        assert result.prompts == []
        assert result.themes == []


class TestDefaultPackageManagerLocalSettings:
    def test_resolve_local_skills(self, tmp_path: Path) -> None:
        sm = _make_settings_manager(tmp_path)
        # Create a skill in the project skills dir
        project_dir = tmp_path / CONFIG_DIR_NAME_PRIMARY
        skills_dir = project_dir / "skills"
        skills_dir.mkdir(parents=True)
        skill = skills_dir / "test.md"
        skill.write_text("# Test skill\n")
        sm.set_project_skill_paths([str(skill)])
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        # The local entry from project_settings
        # should resolve the skill.
        paths = [r.path for r in result.skills]
        assert any(str(skill) in p for p in paths)


class TestDefaultPackageManagerAutoDiscovery:
    def test_auto_skills_in_project(self, tmp_path: Path) -> None:
        sm = _make_settings_manager(tmp_path)
        # Create a SKILL.md in the project
        # skills dir.
        project_dir = tmp_path / CONFIG_DIR_NAME_PRIMARY
        skills_dir = project_dir / "skills"
        skill_dir = skills_dir / "my_skill"
        skill_dir.mkdir(parents=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text("# My skill\n")
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        paths = [r.path for r in result.skills]
        assert any("SKILL.md" in p for p in paths)

    def test_auto_prompts_in_project_alias_dir(self, tmp_path: Path) -> None:
        sm = _make_settings_manager(tmp_path)
        project_dir = tmp_path / ".openclaw"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)
        prompt = prompts_dir / "alias.md"
        prompt.write_text("Alias prompt\n")
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        paths = [r.path for r in result.prompts]
        assert str(prompt) in paths

    def test_auto_prompts_in_project(self, tmp_path: Path) -> None:
        sm = _make_settings_manager(tmp_path)
        # Create a .md file in the project
        # prompts dir.
        project_dir = tmp_path / CONFIG_DIR_NAME_PRIMARY
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)
        prompt = prompts_dir / "test.md"
        prompt.write_text("Test prompt\n")
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        paths = [r.path for r in result.prompts]
        assert any("test.md" in p for p in paths)

    def test_auto_themes_in_project(self, tmp_path: Path) -> None:
        sm = _make_settings_manager(tmp_path)
        project_dir = tmp_path / CONFIG_DIR_NAME_PRIMARY
        themes_dir = project_dir / "themes"
        themes_dir.mkdir(parents=True)
        theme = themes_dir / "my_theme.json"
        theme.write_text("{}")
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        paths = [r.path for r in result.themes]
        assert any("my_theme.json" in p for p in paths)

    def test_auto_extensions_in_project(self, tmp_path: Path) -> None:
        sm = _make_settings_manager(tmp_path)
        # ``_collect_auto_extension_entries``
        # discovers ``.ts`` / ``.js`` files in
        # the project's extensions dir.
        project_dir = tmp_path / CONFIG_DIR_NAME_PRIMARY
        ext_dir = project_dir / "extensions"
        ext_dir.mkdir(parents=True)
        ext_file = ext_dir / "my_ext.ts"
        ext_file.write_text("// my ext\n")
        pm = DefaultPackageManager(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            settings_manager=sm,
        )
        result = asyncio.run(pm.resolve())
        paths = [r.path for r in result.extensions]
        assert any("my_ext.ts" in p for p in paths)


class TestResolveExtensionEntries:
    def test_index_ts(self, tmp_path: Path) -> None:
        ext = tmp_path / "ext"
        ext.mkdir()
        (ext / "index.ts").write_text("// ext")
        result = _resolve_extension_entries(str(ext))
        assert result == [str(ext / "index.ts")]

    def test_index_js(self, tmp_path: Path) -> None:
        ext = tmp_path / "ext"
        ext.mkdir()
        (ext / "index.js").write_text("// ext")
        result = _resolve_extension_entries(str(ext))
        assert result == [str(ext / "index.js")]

    def test_package_json_manifest(self, tmp_path: Path) -> None:
        ext = tmp_path / "ext"
        ext.mkdir()
        (ext / "package.json").write_text(
            json.dumps({"openclaw": {"extensions": ["./src/main.ts"]}})
        )
        (ext / "src").mkdir()
        (ext / "src" / "main.ts").write_text("// main")
        result = _resolve_extension_entries(str(ext))
        assert result == [str(ext / "src" / "main.ts")]

    def test_no_entry(self, tmp_path: Path) -> None:
        ext = tmp_path / "ext"
        ext.mkdir()
        result = _resolve_extension_entries(str(ext))
        assert result is None
