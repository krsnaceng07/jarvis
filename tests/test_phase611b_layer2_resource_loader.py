"""Phase 6.11b — resource_loader + 3 stub loaders tests.

Verifies:
- skills_loader — ``loadSkills`` returns
  the expected empty shape (Phase 6.11b
  stub; full loader lands in 6.12+).
- prompt_templates — ``loadPromptTemplates``
  returns the expected empty shape.
- theme_loader — ``loadThemeFromPath`` is a
  documented stub that raises
  ``NotImplementedError``.
- resource_loader — ``DefaultResourceLoader``
  constructor + getters + ``reload()``
  end-to-end + ``extendResources()``.
  ``load_context_file_from_dir`` +
  ``load_project_context_files`` walk the
  filesystem correctly.
- ``DefaultResourceLoader._discover_system_prompt_file``
  + ``_discover_append_system_prompt_file``
  find ``SYSTEM.md`` + ``APPEND_SYSTEM.md``
  in the project's ``.jarvis/`` dir or the
  agent dir.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.agents.sessions.prompt_templates import (
    PromptArgument,
    PromptTemplate,
    loadPromptTemplates,
)
from src.agents.sessions.resource_loader import (
    CONFIG_DIR_NAME,
    AgentsFile,
    DefaultResourceLoader,
    DefaultResourceLoaderOptions,
    load_context_file_from_dir,
    load_project_context_files,
)
from src.agents.sessions.settings_manager import SettingsManager
from src.agents.sessions.skills_loader import (
    Skill,
    loadSkills,
)
from src.agents.sessions.theme_loader import (
    Theme,
    loadThemeFromPath,
)


# ============================================================================
# Skills loader (stub)
# ============================================================================


class TestSkill:
    def test_required_fields(self) -> None:
        skill = Skill(
            name="my_skill",
            description="A test skill",
            file_path="C:/skills/my_skill/SKILL.md",
        )
        assert skill.name == "my_skill"
        assert skill.description == "A test skill"
        assert skill.file_path == "C:/skills/my_skill/SKILL.md"
        assert skill.base_dir is None
        assert skill.frontmatter == {}
        assert skill.body == ""
        assert skill.source_info is None
        assert skill.disable_model_invocation is False

    def test_full_construction(self) -> None:
        skill = Skill(
            name="review",
            description="Review PR",
            file_path="C:/skills/review/SKILL.md",
            base_dir="C:/skills/review",
            frontmatter={"version": 1},
            body="# Review\n",
            disable_model_invocation=True,
        )
        assert skill.base_dir == "C:/skills/review"
        assert skill.frontmatter == {"version": 1}
        assert skill.body == "# Review\n"
        assert skill.disable_model_invocation is True


class TestLoadSkillsStub:
    def test_returns_empty_shape(self, tmp_path: Path) -> None:
        result = loadSkills(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        assert "skills" in result
        assert "diagnostics" in result
        assert result["skills"] == []
        assert result["diagnostics"] == []

    def test_ignores_skill_paths(self, tmp_path: Path) -> None:
        # Phase 6.11b stub: skill_paths is
        # accepted but ignored (the real
        # loader lands in 6.12+).
        result = loadSkills(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            skill_paths=[str(tmp_path / "skills")],
        )
        assert result["skills"] == []


# ============================================================================
# Prompt templates loader (stub)
# ============================================================================


class TestPromptTemplate:
    def test_required_fields(self) -> None:
        prompt = PromptTemplate(
            name="review-pr",
            description="Review a PR",
            file_path="C:/prompts/review-pr.md",
            body="Review this PR:",
        )
        assert prompt.name == "review-pr"
        assert prompt.arguments == []
        assert prompt.source_info is None

    def test_with_arguments(self) -> None:
        prompt = PromptTemplate(
            name="review-pr",
            description="Review a PR",
            file_path="C:/prompts/review-pr.md",
            body="Review $PR_URL",
            arguments=[
                PromptArgument(
                    name="PR_URL",
                    description="The PR URL",
                    required=True,
                ),
            ],
        )
        assert len(prompt.arguments) == 1
        assert prompt.arguments[0].name == "PR_URL"
        assert prompt.arguments[0].required is True


class TestPromptArgument:
    def test_defaults(self) -> None:
        arg = PromptArgument(name="x")
        assert arg.name == "x"
        assert arg.description == ""
        assert arg.required is False


class TestLoadPromptTemplatesStub:
    def test_returns_empty_shape(self, tmp_path: Path) -> None:
        result = loadPromptTemplates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        assert "prompts" in result
        assert "diagnostics" in result
        assert result["prompts"] == []
        assert result["diagnostics"] == []


# ============================================================================
# Theme loader (stub)
# ============================================================================


class TestTheme:
    def test_defaults(self) -> None:
        theme = Theme()
        assert theme.name is None
        assert theme.source_path is None
        assert theme.colors == {}
        assert theme.styles == {}
        assert theme.source_info is None

    def test_construction(self) -> None:
        theme = Theme(
            name="dark",
            source_path="C:/themes/dark.json",
            colors={"bg": "#000"},
            styles={"bold": {"fg": "#fff"}},
        )
        assert theme.name == "dark"
        assert theme.colors == {"bg": "#000"}
        assert theme.styles == {"bold": {"fg": "#fff"}}


class TestLoadThemeFromPathStub:
    def test_raises_not_implemented(self, tmp_path: Path) -> None:
        theme_file = tmp_path / "theme.json"
        theme_file.write_text("{}")
        with pytest.raises(NotImplementedError):
            loadThemeFromPath(str(theme_file))


# ============================================================================
# resource_loader: AGENTS.md helpers
# ============================================================================


class TestLoadContextFileFromDir:
    def test_no_file(self, tmp_path: Path) -> None:
        result = load_context_file_from_dir(str(tmp_path))
        assert result is None

    def test_agents_md(self, tmp_path: Path) -> None:
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Project context\n")
        result = load_context_file_from_dir(str(tmp_path))
        assert result is not None
        assert result.path == str(agents)
        assert "# Project context" in result.content

    def test_agents_md_uppercase(self, tmp_path: Path) -> None:
        # On Windows the filesystem is
        # case-insensitive; ``AGENTS.MD``
        # collides with ``AGENTS.md`` so the
        # candidate picker finds the
        # lowercase match first. The OpenClaw
        # source's ``existsSync`` is also
        # case-insensitive on Windows, so
        # both ports behave the same.
        if os.name == "nt":
            pytest.skip(
                "case-insensitive filesystem: AGENTS.MD collides with AGENTS.md"
            )
        agents = tmp_path / "AGENTS.MD"
        agents.write_text("# Upper\n")
        result = load_context_file_from_dir(str(tmp_path))
        assert result is not None
        assert result.path == str(agents)

    def test_claude_md(self, tmp_path: Path) -> None:
        claude = tmp_path / "CLAUDE.md"
        claude.write_text("# Claude\n")
        result = load_context_file_from_dir(str(tmp_path))
        assert result is not None
        assert result.path == str(claude)

    def test_agents_md_takes_precedence(self, tmp_path: Path) -> None:
        # ``AGENTS.md`` comes first in the
        # candidate list — should be picked
        # over CLAUDE.md when both exist.
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Agents\n")
        claude = tmp_path / "CLAUDE.md"
        claude.write_text("# Claude\n")
        result = load_context_file_from_dir(str(tmp_path))
        assert result is not None
        assert result.path == str(agents)


class TestLoadProjectContextFiles:
    def test_only_agent_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Isolate home so the ancestor walk-up
        # does not pick up the operator's real
        # ``~/.agents/skills`` install.
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        monkeypatch.setenv("HOME", str(empty_home))
        monkeypatch.setenv("USERPROFILE", str(empty_home))
        # Bound the ancestor walk-up at the
        # agent dir by creating a fake ``.git``
        # inside it.
        agent_dir = tmp_path / "agent"
        (agent_dir / ".git").mkdir(parents=True)
        agents = agent_dir / "AGENTS.md"
        agents.write_text("# Agent context\n")
        result = load_project_context_files(
            cwd=str(tmp_path), agent_dir=str(agent_dir)
        )
        assert len(result) == 1
        assert result[0].path == str(agents)
        assert "Agent context" in result[0].content

    def test_cwd_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        empty_home = tmp_path / "home"
        empty_home.mkdir()
        monkeypatch.setenv("HOME", str(empty_home))
        monkeypatch.setenv("USERPROFILE", str(empty_home))
        # Bound the ancestor walk-up at
        # ``tmp_path`` by creating a fake
        # ``.git`` inside it.
        (tmp_path / ".git").mkdir()
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# CWD context\n")
        result = load_project_context_files(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        assert len(result) == 1
        assert result[0].path == str(agents)

    def test_no_files(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        result = load_project_context_files(
            cwd=str(tmp_path), agent_dir=str(agent_dir)
        )
        assert result == []


# ============================================================================
# resource_loader: DefaultResourceLoader
# ============================================================================


def _make_loader(tmp_path: Path, **overrides) -> DefaultResourceLoader:
    """Build a DefaultResourceLoader with
    in-memory settings + a fake ``.git``
    in the cwd to bound the ancestor
    walk-up."""
    sm = overrides.pop("settings_manager", None) or SettingsManager.in_memory()
    options = DefaultResourceLoaderOptions(
        cwd=str(tmp_path),
        agent_dir=str(tmp_path / "agent"),
        settings_manager=sm,
        **overrides,
    )
    (tmp_path / ".git").mkdir(exist_ok=True)
    (tmp_path / "agent").mkdir(exist_ok=True)
    return DefaultResourceLoader(options)


class TestDefaultResourceLoader:
    def test_constructor(self, tmp_path: Path) -> None:
        sm = SettingsManager.in_memory()
        loader = DefaultResourceLoader(
            DefaultResourceLoaderOptions(
                cwd=str(tmp_path),
                agent_dir=str(tmp_path / "agent"),
                settings_manager=sm,
            )
        )
        assert loader.cwd == str(tmp_path)
        assert loader.agent_dir == str(tmp_path / "agent")
        assert loader.settings_manager is sm
        assert loader.no_extensions is False
        assert loader.no_skills is False

    def test_initial_getters(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        # Before reload, getters return the
        # initial empty state.
        ext_result = loader.get_extensions()
        assert ext_result.extensions == []
        assert ext_result.errors == []
        skills = loader.get_skills()
        assert skills["skills"] == []
        assert skills["diagnostics"] == []
        prompts = loader.get_prompts()
        assert prompts["prompts"] == []
        assert prompts["diagnostics"] == []
        themes = loader.get_themes()
        assert themes["themes"] == []
        assert themes["diagnostics"] == []
        agents_files = loader.get_agents_files()
        assert agents_files["agentsFiles"] == []
        assert loader.get_system_prompt() is None
        assert loader.get_append_system_prompt() == []

    @pytest.mark.asyncio
    async def test_reload_empty(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        await loader.reload()
        # No skills / prompts / themes are
        # registered.
        assert loader.get_skills()["skills"] == []
        assert loader.get_prompts()["prompts"] == []
        # No AGENTS.md present.
        assert loader.get_agents_files()["agentsFiles"] == []
        # No system prompt configured.
        assert loader.get_system_prompt() is None
        assert loader.get_append_system_prompt() == []

    @pytest.mark.asyncio
    async def test_reload_loads_agents_md(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Test project\n")
        await loader.reload()
        files = loader.get_agents_files()["agentsFiles"]
        assert any(f.path == str(agents) for f in files)

    @pytest.mark.asyncio
    async def test_reload_loads_agents_md_uppercase(self, tmp_path: Path) -> None:
        if os.name == "nt":
            pytest.skip(
                "case-insensitive filesystem: AGENTS.MD collides with AGENTS.md"
            )
        loader = _make_loader(tmp_path)
        agents = tmp_path / "AGENTS.MD"
        agents.write_text("# Upper\n")
        await loader.reload()
        files = loader.get_agents_files()["agentsFiles"]
        assert any(f.path == str(agents) for f in files)

    @pytest.mark.asyncio
    async def test_reload_loads_claude_md(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        claude = tmp_path / "CLAUDE.md"
        claude.write_text("# Claude\n")
        await loader.reload()
        files = loader.get_agents_files()["agentsFiles"]
        assert any(f.path == str(claude) for f in files)

    @pytest.mark.asyncio
    async def test_reload_skips_agents_files_when_disabled(
        self, tmp_path: Path
    ) -> None:
        loader = _make_loader(tmp_path, no_context_files=True)
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Project\n")
        await loader.reload()
        assert loader.get_agents_files()["agentsFiles"] == []

    @pytest.mark.asyncio
    async def test_reload_discovers_system_prompt(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        # Project-level SYSTEM.md wins.
        system_md = tmp_path / CONFIG_DIR_NAME / "SYSTEM.md"
        system_md.parent.mkdir(parents=True)
        system_md.write_text("You are JARVIS.\n")
        await loader.reload()
        assert loader.get_system_prompt() == "You are JARVIS.\n"

    @pytest.mark.asyncio
    async def test_reload_discovers_append_system_prompt(
        self, tmp_path: Path
    ) -> None:
        loader = _make_loader(tmp_path)
        append_md = tmp_path / CONFIG_DIR_NAME / "APPEND_SYSTEM.md"
        append_md.parent.mkdir(parents=True)
        append_md.write_text("Extra instructions.\n")
        await loader.reload()
        assert loader.get_append_system_prompt() == ["Extra instructions.\n"]

    @pytest.mark.asyncio
    async def test_reload_explicit_system_prompt_wins(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path, system_prompt="Explicit body")
        # Discovery should be skipped when
        # the constructor option is set.
        system_md = tmp_path / CONFIG_DIR_NAME / "SYSTEM.md"
        system_md.parent.mkdir(parents=True)
        system_md.write_text("Discovered body\n")
        await loader.reload()
        assert loader.get_system_prompt() == "Explicit body"

    def test_extend_resources_adds_paths(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        skill = tmp_path / "skill.md"
        prompt = tmp_path / "prompt.md"
        theme = tmp_path / "theme.json"
        skill.write_text("# Skill")
        prompt.write_text("# Prompt")
        theme.write_text("{}")
        loader.extend_resources(
            {
                "skillPaths": [
                    {
                        "path": str(skill),
                        "metadata": {
                            "source": "local",
                            "scope": "temporary",
                            "origin": "top-level",
                        },
                    }
                ],
                "promptPaths": [
                    {
                        "path": str(prompt),
                        "metadata": {
                            "source": "local",
                            "scope": "temporary",
                            "origin": "top-level",
                        },
                    }
                ],
                "themePaths": [
                    {
                        "path": str(theme),
                        "metadata": {
                            "source": "local",
                            "scope": "temporary",
                            "origin": "top-level",
                        },
                    }
                ],
            }
        )
        assert any(
            p.endswith("skill.md") for p in loader.additional_skill_paths
        )
        assert any(
            p.endswith("prompt.md")
            for p in loader.additional_prompt_template_paths
        )
        assert any(
            p.endswith("theme.json") for p in loader.additional_theme_paths
        )

    def test_extend_resources_empty(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path)
        # No keys at all — should not raise.
        loader.extend_resources({})
        assert loader.additional_skill_paths == []
        assert loader.additional_prompt_template_paths == []
        assert loader.additional_theme_paths == []

    @pytest.mark.asyncio
    async def test_reload_clears_extension_cache(self, tmp_path: Path) -> None:
        # The extension cache is global; this
        # test just verifies that reload()
        # doesn't raise when called twice.
        loader = _make_loader(tmp_path)
        await loader.reload()
        await loader.reload()
        # No assertion on cache state; the
        # call should simply succeed.

    @pytest.mark.asyncio
    async def test_reload_with_no_extensions(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path, no_extensions=True)
        await loader.reload()
        # Even with no extensions, the loader
        # should produce a valid empty result.
        assert loader.get_extensions().extensions == []

    @pytest.mark.asyncio
    async def test_reload_with_no_skills(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path, no_skills=True)
        await loader.reload()
        assert loader.get_skills()["skills"] == []

    @pytest.mark.asyncio
    async def test_reload_with_no_prompts(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path, no_prompt_templates=True)
        await loader.reload()
        assert loader.get_prompts()["prompts"] == []

    @pytest.mark.asyncio
    async def test_reload_with_no_themes(self, tmp_path: Path) -> None:
        loader = _make_loader(tmp_path, no_themes=True)
        await loader.reload()
        assert loader.get_themes()["themes"] == []


class TestAgentsFile:
    def test_construction(self) -> None:
        af = AgentsFile(path="/AGENTS.md", content="# Context\n")
        assert af.path == "/AGENTS.md"
        assert af.content == "# Context\n"


class TestConfigDirName:
    def test_jarvis(self) -> None:
        assert CONFIG_DIR_NAME == ".jarvis"
