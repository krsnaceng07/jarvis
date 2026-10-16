"""Phase 6.13b — frontmatter + prompt_templates + system_prompt tests.

Verifies the public surface of:

- :func:`parse_frontmatter` /
  :func:`strip_frontmatter` from
  :mod:`jarvis.agents.sessions.frontmatter`
- :func:`load_prompt_templates` /
  :func:`expand_prompt_template` from
  :mod:`jarvis.agents.sessions.prompt_templates`
- :func:`build_system_prompt` from
  :mod:`jarvis.agents.sessions.system_prompt`
"""
from __future__ import annotations

import textwrap
from pathlib import Path


from src.agents.sessions.frontmatter import (
    parse_frontmatter,
    strip_frontmatter,
)
from src.agents.sessions.prompt_templates import (
    PromptTemplate,
    expand_prompt_template,
    load_prompt_templates,
)
from src.agents.sessions.system_prompt import (
    DEFAULT_TOOLS,
    build_system_prompt,
)


# ============================================================================
# frontmatter
# ============================================================================


class TestParseFrontmatter:
    def test_no_frontmatter(self) -> None:
        result = parse_frontmatter("hello world")
        assert result["frontmatter"] == {}
        assert result["body"] == "hello world"

    def test_basic_frontmatter(self) -> None:
        content = textwrap.dedent("""\
            ---
            name: foo
            description: bar
            ---
            body content
        """)
        result = parse_frontmatter(content)
        assert result["frontmatter"].get("name") == "foo"
        assert result["frontmatter"].get("description") == "bar"
        assert "body content" in result["body"]

    def test_with_argument_hint(self) -> None:
        content = textwrap.dedent("""\
            ---
            description: Review a PR
            argument-hint: "[PR number]"
            ---
            Review PR $1
        """)
        result = parse_frontmatter(content)
        assert result["frontmatter"].get("argument-hint") == "[PR number]"

    def test_crlf(self) -> None:
        content = "---\r\nname: foo\r\n---\r\nbody\r\n"
        result = parse_frontmatter(content)
        assert result["frontmatter"].get("name") == "foo"

    def test_no_body(self) -> None:
        content = "---\nname: foo\n---\n"
        result = parse_frontmatter(content)
        assert result["frontmatter"].get("name") == "foo"
        assert result["body"] == ""


class TestStripFrontmatter:
    def test_strips(self) -> None:
        content = "---\nname: foo\n---\nhello\n"
        assert strip_frontmatter(content) == "hello"

    def test_no_frontmatter(self) -> None:
        assert strip_frontmatter("hello world") == "hello world"


# ============================================================================
# prompt_templates
# ============================================================================


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestLoadPromptTemplates:
    def test_empty(self, tmp_path: Path) -> None:
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        assert result["prompts"] == []
        assert result["diagnostics"] == []

    def test_loads_project_default(
        self, tmp_path: Path
    ) -> None:
        # .jarvis/prompts/review.md
        _write_md(
            tmp_path / ".jarvis" / "prompts" / "review.md",
            textwrap.dedent("""\
                ---
                description: Review the current changes
                ---
                Review the diff for $1.
            """),
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        names = [t.name for t in result["prompts"]]
        assert "review" in names
        review = next(
            t for t in result["prompts"] if t.name == "review"
        )
        assert review.description == "Review the current changes"
        assert "$1" in review.body
        # Source is project.
        assert review.source_info is not None
        assert review.source_info.get("scope") == "project"

    def test_loads_global_default(
        self, tmp_path: Path
    ) -> None:
        _write_md(
            tmp_path / "agent" / "prompts" / "ship.md",
            textwrap.dedent("""\
                ---
                description: Ship the current branch
                ---
                Ship it.
            """),
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
        )
        names = [t.name for t in result["prompts"]]
        assert "ship" in names
        ship = next(
            t for t in result["prompts"] if t.name == "ship"
        )
        assert ship.source_info is not None
        assert ship.source_info.get("scope") == "user"

    def test_loads_explicit_paths(
        self, tmp_path: Path
    ) -> None:
        _write_md(
            tmp_path / "custom" / "extra.md",
            textwrap.dedent("""\
                ---
                description: Extra
                ---
                Extra body
            """),
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            prompt_paths=[
                str(tmp_path / "custom" / "extra.md"),
            ],
            include_defaults=False,
        )
        names = [t.name for t in result["prompts"]]
        assert "extra" in names

    def test_loads_explicit_dir(
        self, tmp_path: Path
    ) -> None:
        _write_md(
            tmp_path / "more" / "a.md",
            "---\ndescription: A\n---\nA body",
        )
        _write_md(
            tmp_path / "more" / "b.md",
            "---\ndescription: B\n---\nB body",
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            prompt_paths=[str(tmp_path / "more")],
            include_defaults=False,
        )
        names = {t.name for t in result["prompts"]}
        assert names == {"a", "b"}

    def test_description_from_first_line(
        self, tmp_path: Path
    ) -> None:
        _write_md(
            tmp_path / "x.md",
            "First line description\n\nBody content",
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            include_defaults=False,
            prompt_paths=[str(tmp_path / "x.md")],
        )
        assert len(result["prompts"]) == 1
        assert result["prompts"][0].description == (
            "First line description"
        )

    def test_description_truncated(self, tmp_path: Path) -> None:
        long_line = "x" * 100
        _write_md(
            tmp_path / "x.md",
            f"{long_line}\nBody",
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            include_defaults=False,
            prompt_paths=[str(tmp_path / "x.md")],
        )
        # Truncated to 60 + "...".
        assert result["prompts"][0].description.startswith("x" * 60)
        assert result["prompts"][0].description.endswith("...")

    def test_argument_hint(self, tmp_path: Path) -> None:
        _write_md(
            tmp_path / "x.md",
            textwrap.dedent("""\
                ---
                description: With arg
                argument-hint: "[arg1] [arg2]"
                ---
                Body
            """),
        )
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            include_defaults=False,
            prompt_paths=[str(tmp_path / "x.md")],
        )
        assert result["prompts"][0].argument_hint == "[arg1] [arg2]"

    def test_skips_non_md(self, tmp_path: Path) -> None:
        _write_md(tmp_path / "x.txt", "not a prompt")
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            include_defaults=False,
            prompt_paths=[str(tmp_path / "x.txt")],
        )
        assert result["prompts"] == []

    def test_missing_path(self, tmp_path: Path) -> None:
        # Non-existent path is silently
        # skipped.
        result = load_prompt_templates(
            cwd=str(tmp_path),
            agent_dir=str(tmp_path / "agent"),
            include_defaults=False,
            prompt_paths=[str(tmp_path / "missing.md")],
        )
        assert result["prompts"] == []


class TestExpandPromptTemplate:
    def test_no_slash(self) -> None:
        assert expand_prompt_template("hello", []) == "hello"

    def test_unknown_command(self) -> None:
        # Unknown command → returns
        # input unchanged.
        result = expand_prompt_template("/unknown args", [])
        assert result == "/unknown args"

    def test_basic_substitution(self) -> None:
        template = PromptTemplate(
            name="review",
            description="Review",
            file_path="/x.md",
            body="Review $1 now",
        )
        result = expand_prompt_template(
            "/review pr-123", [template]
        )
        assert result == "Review pr-123 now"

    def test_multiple_args(self) -> None:
        template = PromptTemplate(
            name="multi",
            description="Multi",
            file_path="/x.md",
            body="Args: $1 $2 $3",
        )
        result = expand_prompt_template(
            "/multi foo bar baz", [template]
        )
        assert result == "Args: foo bar baz"

    def test_quoted_args(self) -> None:
        template = PromptTemplate(
            name="q",
            description="Q",
            file_path="/x.md",
            body="Arg: $1",
        )
        result = expand_prompt_template(
            '/q "hello world"',
            [template],
        )
        assert result == "Arg: hello world"

    def test_no_args(self) -> None:
        template = PromptTemplate(
            name="noop",
            description="Noop",
            file_path="/x.md",
            body="Just body",
        )
        result = expand_prompt_template("/noop", [template])
        assert result == "Just body"

    def test_picks_correct_template(self) -> None:
        a = PromptTemplate(
            name="a", description="A", file_path="/a.md", body="A"
        )
        b = PromptTemplate(
            name="b", description="B", file_path="/b.md", body="B"
        )
        assert expand_prompt_template("/a", [a, b]) == "A"
        assert expand_prompt_template("/b", [a, b]) == "B"


# ============================================================================
# system_prompt
# ============================================================================


class TestBuildSystemPrompt:
    def test_minimal(self) -> None:
        prompt = build_system_prompt({"cwd": "/tmp/proj"})
        # Has the date + cwd.
        assert "Current date:" in prompt
        assert "/tmp/proj" in prompt
        # Default tools appear.
        assert "read" in prompt or "(none)" in prompt

    def test_custom_prompt(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "customPrompt": "CUSTOM: do the thing",
        })
        assert "CUSTOM: do the thing" in prompt
        # Date/cwd are still appended.
        assert "Current date:" in prompt
        assert "/tmp/proj" in prompt

    def test_custom_prompt_with_context_files(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "customPrompt": "CUSTOM",
            "contextFiles": [
                {
                    "path": "AGENTS.md",
                    "content": "use Python 3.12",
                },
            ],
        })
        assert "CUSTOM" in prompt
        assert "<project_context>" in prompt
        assert "AGENTS.md" in prompt
        assert "use Python 3.12" in prompt

    def test_custom_prompt_with_bootstrap_context_first_turn(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "customPrompt": "CUSTOM",
            "contextFiles": [
                {
                    "path": "BOOTSTRAP.md",
                    "content": "priority bootstrap instructions",
                },
            ],
            "isFirstTurn": True,
        })
        assert "CUSTOM" in prompt
        assert "BOOTSTRAP.md" in prompt
        assert "priority bootstrap instructions" in prompt
        assert "A BOOTSTRAP.md file is present and this is the first turn of the session." in prompt

    def test_custom_prompt_with_bootstrap_context_not_first_turn(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "customPrompt": "CUSTOM",
            "contextFiles": [
                {
                    "path": "BOOTSTRAP.md",
                    "content": "priority bootstrap instructions",
                },
            ],
            "isFirstTurn": False,
        })
        assert "CUSTOM" in prompt
        assert "BOOTSTRAP.md" in prompt
        assert "priority bootstrap instructions" in prompt
        assert "A BOOTSTRAP.md file is present and this is the first turn of the session." not in prompt

    def test_custom_prompt_with_skills(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "customPrompt": "CUSTOM",
            "skills": [
                {
                    "name": "code-review",
                    "description": "Review code",
                },
            ],
        })
        assert "code-review" in prompt
        assert "<skills>" in prompt

    def test_custom_prompt_skips_skills_without_read(
        self,
    ) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "customPrompt": "CUSTOM",
            "selectedTools": ["bash"],  # no read
            "skills": [
                {
                    "name": "code-review",
                    "description": "Review code",
                },
            ],
        })
        # Skills are skipped when read
        # is not in selectedTools.
        assert "<skills>" not in prompt

    def test_append_system_prompt(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "appendSystemPrompt": "APPENDED CONTENT",
        })
        assert "APPENDED CONTENT" in prompt

    def test_default_tools_constant(self) -> None:
        assert "read" in DEFAULT_TOOLS
        assert "bash" in DEFAULT_TOOLS
        assert "edit" in DEFAULT_TOOLS
        assert "write" in DEFAULT_TOOLS

    def test_selected_tools_filter(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "selectedTools": ["read"],
            "toolSnippets": {"read": "Read a file"},
        })
        # Only "read" appears (no bash
        # / edit / write).
        assert "read:" in prompt
        assert "bash:" not in prompt

    def test_no_snippet_means_no_tool(self) -> None:
        # Without a tool snippet, the
        # tool is filtered out of the
        # prompt.
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "selectedTools": ["read"],
            # No toolSnippets.
        })
        assert "(none)" in prompt

    def test_guidelines_for_bash(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "selectedTools": ["bash"],
            "toolSnippets": {"bash": "Run a command"},
        })
        # Bash-specific guideline.
        assert "Execute bash commands" in prompt

    def test_guidelines_for_edit(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "selectedTools": ["edit"],
            "toolSnippets": {"edit": "Edit a file"},
        })
        assert "minimal patches" in prompt

    def test_prompt_guidelines_appended(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "promptGuidelines": ["Always run tests."],
        })
        assert "Always run tests." in prompt

    def test_cwd_windows_path(self) -> None:
        # Backslashes are converted to
        # forward slashes.
        prompt = build_system_prompt({
            "cwd": "C:\\Users\\me\\proj",
        })
        assert "C:/Users/me/proj" in prompt

    def test_default_skills_appended(self) -> None:
        prompt = build_system_prompt({
            "cwd": "/tmp/proj",
            "selectedTools": ["read"],
            "toolSnippets": {"read": "Read"},
            "skills": [
                {
                    "name": "my-skill",
                    "description": "My skill",
                },
            ],
        })
        # Default mode also appends
        # skills.
        assert "my-skill" in prompt
