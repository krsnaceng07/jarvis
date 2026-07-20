"""Phase 2 tests — skills, hooks, cron, memory, doctor, bootstrap, cron extension.

Tests the new ``jarvis.*`` modules and the Phase 2 plugins
(``memory_core``, ``cron``).
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# ── Frontmatter + Skills ──────────────────────────────────────────


class TestFrontmatter:
    def test_parse_simple(self) -> None:
        from src.frontmatter import parse_frontmatter

        text = "---\nname: foo\ndescription: bar\n---\n# body"
        fm, body = parse_frontmatter(text)
        assert fm["name"] == "foo"
        assert fm["description"] == "bar"
        assert "body" in body

    def test_parse_with_metadata(self) -> None:
        from src.frontmatter import parse_frontmatter

        text = (
            "---\n"
            "name: weather\n"
            "description: get weather\n"
            'metadata: { "openclaw": { "emoji": "🌤️" } }\n'
            "---\n"
            "# body"
        )
        fm, body = parse_frontmatter(text)
        assert fm["name"] == "weather"
        assert fm["metadata"]["openclaw"]["emoji"] == "🌤️"

    def test_parse_no_frontmatter(self) -> None:
        from src.frontmatter import parse_frontmatter

        fm, body = parse_frontmatter("just a body, no frontmatter")
        assert fm == {}
        assert "just a body" in body


class TestSkills:
    def test_discover_skills_finds_both(self) -> None:
        from src.skills import discover_skills

        skills = discover_skills(REPO_ROOT / "skills")
        names = {s.name for s in skills}
        assert "weather" in names
        assert "summarize" in names

    def test_skill_has_required_fields(self) -> None:
        from src.skills import discover_skills

        for s in discover_skills(REPO_ROOT / "skills"):
            assert s.name
            assert s.description
            assert s.body

    def test_skills_to_prompt_section(self) -> None:
        from src.skills import discover_skills, skills_to_prompt_section

        section = skills_to_prompt_section(discover_skills(REPO_ROOT / "skills"))
        assert "# Skills" in section
        assert "weather" in section
        assert "summarize" in section

    def test_skill_with_invalid_frontmatter_skipped(self) -> None:
        from src.skills import parse_skill

        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "SKILL.md"
            bad.write_text("# no frontmatter here at all\n", encoding="utf-8")
            # parse_skill returns None for missing name/description.
            assert parse_skill(bad) is None


# ── Hooks ─────────────────────────────────────────────────────────


class TestHooks:
    def test_register_and_count(self) -> None:
        from jarvis_sdk import HookRegistration
        from src.hooks import HookBus

        bus = HookBus()
        bus.register(HookRegistration(name="before_agent_start", handler=lambda e: None))
        bus.register(HookRegistration(name="before_agent_start", handler=lambda e: None))
        assert bus.count() == 2
        assert bus.count("before_agent_start") == 2

    @pytest.mark.asyncio
    async def test_fire_calls_handlers(self) -> None:
        from jarvis_sdk import HookRegistration
        from src.hooks import HookBus

        seen: list[str] = []

        async def h1(payload):
            seen.append("h1:" + str(payload))

        def h2(payload):
            seen.append("h2:" + str(payload))

        bus = HookBus()
        bus.register(HookRegistration(name="x", handler=h1, priority=10))
        bus.register(HookRegistration(name="x", handler=h2, priority=0))
        await bus.fire("x", "payload")
        # h1 (priority 10) runs before h2 (priority 0).
        assert seen == ["h1:payload", "h2:payload"]

    @pytest.mark.asyncio
    async def test_fire_continues_after_handler_error(self) -> None:
        from jarvis_sdk import HookRegistration
        from src.hooks import HookBus

        seen: list[str] = []

        def bad(_payload):
            raise RuntimeError("boom")

        def good(_payload):
            seen.append("good")

        bus = HookBus()
        bus.register(HookRegistration(name="x", handler=bad))
        bus.register(HookRegistration(name="x", handler=good))
        await bus.fire("x", None)
        assert seen == ["good"]


# ── Cron ──────────────────────────────────────────────────────────


class TestCronEvaluator:
    def test_match_every_minute(self) -> None:
        from src.cron import _cron_matches

        assert _cron_matches("* * * * *", datetime(2026, 7, 20, 9, 30))
        assert _cron_matches("* * * * *", datetime(2026, 7, 20, 0, 0))

    def test_match_every_5_minutes(self) -> None:
        from src.cron import _cron_matches

        assert _cron_matches("*/5 * * * *", datetime(2026, 7, 20, 9, 30))
        assert not _cron_matches("*/5 * * * *", datetime(2026, 7, 20, 9, 32))
        assert _cron_matches("*/5 * * * *", datetime(2026, 7, 20, 9, 35))

    def test_match_specific_hours(self) -> None:
        from src.cron import _cron_matches

        assert _cron_matches("0 9 * * *", datetime(2026, 7, 20, 9, 0))
        assert not _cron_matches("0 9 * * *", datetime(2026, 7, 20, 10, 0))

    def test_match_weekday(self) -> None:
        from src.cron import _cron_matches

        # The runtime uses Python's weekday() (Mon=0, Sun=6) — same
        # convention as datetime.weekday().
        assert _cron_matches("0 9 * * 0", datetime(2026, 7, 20, 9, 0))  # Mon
        assert not _cron_matches("0 9 * * 0", datetime(2026, 7, 21, 9, 0))  # Tue


class TestCronRunner:
    def test_add_list(self) -> None:
        from jarvis_sdk import CronDecl
        from src.cron import CronRunner

        runner = CronRunner()
        runner.add(
            CronDecl(
                id="test.job",
                schedule="*/5 * * * *",
                handler=lambda: None,
            )
        )
        assert len(runner.list()) == 1
        # remove() is on CronTable (the data store), not the runner.
        # The runner takes a snapshot of jobs at start() time.


# ── Bootstrap ─────────────────────────────────────────────────────


class TestBootstrap:
    def test_seed_workspace(self, tmp_path: Path) -> None:
        from src.bootstrap import seed_workspace

        result = seed_workspace(tmp_path)
        # 5 files seeded on first run.
        assert len(result.seeded) == 5
        assert (tmp_path / "config" / "jarvis.json").is_file()
        assert (tmp_path / "core" / "MEMORY.md").is_file()
        assert (tmp_path / "core" / "IDENTITY.md").is_file()
        assert (tmp_path / "core" / "SOUL.md").is_file()
        assert (tmp_path / "core" / "USER.md").is_file()

    def test_seed_workspace_idempotent(self, tmp_path: Path) -> None:
        from src.bootstrap import seed_workspace

        seed_workspace(tmp_path)  # First call: 5 files seeded.
        # Second call: config is skipped (it already exists), but
        # the 4 core files still have the seed marker, so they get
        # re-seeded (the bootstrap considers them pristine).
        first = seed_workspace(tmp_path)
        # 4 core files re-seeded; config skipped.
        assert len(first.seeded) == 4
        assert any("jarvis.json" in p for p in first.skipped)

    def test_edited_file_not_overwritten(self, tmp_path: Path) -> None:
        from src.bootstrap import seed_workspace

        seed_workspace(tmp_path)
        # User edits IDENTITY.md (removes the seed marker).
        identity = tmp_path / "core" / "IDENTITY.md"
        edited = identity.read_text(encoding="utf-8").replace(
            "<!-- seeded by src.bootstrap; edit me -->", ""
        )
        identity.write_text(edited, encoding="utf-8")
        result = seed_workspace(tmp_path)
        # IDENTITY.md should be skipped (no marker).
        assert any("IDENTITY.md" in p for p in result.skipped)


# ── Doctor ────────────────────────────────────────────────────────


class TestDoctor:
    def test_run_all_aggregates_findings(self) -> None:
        from src.doctor import DoctorContract, DoctorFinding, DoctorRunner

        runner = DoctorRunner()
        runner.add(
            DoctorContract(
                id="t1",
                version=1,
                detect=lambda _sd, _cfg: [
                    DoctorFinding(label="a", path=Path("."), count=1),
                    DoctorFinding(label="b", path=Path("."), count=2),
                ],
            )
        )
        runner.add(
            DoctorContract(
                id="t2",
                version=1,
                detect=lambda _sd, _cfg: [DoctorFinding(label="c", path=Path("."), count=3)],
            )
        )
        report = runner.run_all(Path("."))
        assert len(report.findings) == 3
        assert len(report.contracts_run) == 2

    def test_run_one(self) -> None:
        from src.doctor import DoctorContract, DoctorFinding, DoctorRunner

        runner = DoctorRunner()
        runner.add(
            DoctorContract(
                id="known",
                version=1,
                detect=lambda _sd, _cfg: [DoctorFinding(label="x", path=Path("."))],
            )
        )
        report = runner.run_one("known", Path("."))
        assert len(report.findings) == 1

    def test_run_one_unknown(self) -> None:
        from src.doctor import DoctorRunner

        runner = DoctorRunner()
        report = runner.run_one("does_not_exist", Path("."))
        assert "does_not_exist" in report.contract_errors

    def test_add_raws_skips_bad(self) -> None:
        from src.doctor import DoctorRunner

        runner = DoctorRunner()
        runner.add_raws(
            [
                {},  # missing all keys — skip
                {
                    "id": "good",
                    "version": 1,
                    "detect": lambda _sd, _cfg: [],
                    "_owner_id": "x",
                },
            ]
        )
        assert runner.list_ids() == ["good"]


# ── Memory extension ─────────────────────────────────────────────


class TestMemoryRuntime:
    def test_set_get_delete_count(self, tmp_path: Path) -> None:
        from extensions.memory_core.runtime import MemoryRuntime

        # Override the data dir for this test.
        rt = MemoryRuntime(tmp_path / "memory.sqlite")
        try:
            rt.set("name", "Fatih")
            rt.set("city", "Istanbul")
            assert rt.get("name") == "Fatih"
            assert rt.count() == 2
            assert rt.delete("city")
            assert rt.count() == 1
        finally:
            rt.close()

    def test_search_substring(self, tmp_path: Path) -> None:
        from extensions.memory_core.runtime import MemoryRuntime

        rt = MemoryRuntime(tmp_path / "memory.sqlite")
        try:
            rt.set("favorite_food", "pizza")
            rt.set("sister_name", "Layla")
            rt.set("city", "Istanbul")
            rows = rt.search_substring("Istanbul")
            assert any(r["key"] == "city" for r in rows)
            rows = rt.search_substring("layla")  # case-insensitive via LIKE
            assert any(r["key"] == "sister_name" for r in rows)
        finally:
            rt.close()


class TestMemoryCorePlugin:
    @pytest.mark.asyncio
    async def test_call_unknown_tool(self) -> None:
        from extensions.memory_core.plugin import MemoryCorePlugin

        p = MemoryCorePlugin()
        from jarvis_sdk import Err

        result = await p.call("not_a_tool", {})
        assert isinstance(result, Err)
        assert result.code == "UNKNOWN_TOOL"

    @pytest.mark.asyncio
    async def test_call_memory_get_missing_arg(self, tmp_path: Path) -> None:
        from extensions.memory_core.plugin import MemoryCorePlugin
        from extensions.memory_core.runtime import MemoryRuntime
        from jarvis_sdk import Err

        rt = MemoryRuntime(tmp_path / "memory.sqlite")
        # Force default() to return our test instance.
        from extensions.memory_core import runtime as rt_mod

        prev_default = rt_mod.MemoryRuntime._default
        rt_mod.MemoryRuntime._default = rt
        try:
            p = MemoryCorePlugin()
            result = await p.call("memory_get", {})
            assert isinstance(result, Err)
            assert result.code == "MISSING_ARG"
        finally:
            rt_mod.MemoryRuntime._default = prev_default
            rt.close()

    def test_manifest(self) -> None:
        import json

        path = REPO_ROOT / "extensions" / "memory_core" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "memory_core"
        assert manifest["kind"] == "memory"
        assert {t["name"] for t in manifest["tools"]} == {"memory_search", "memory_get"}


# ── Cron extension ────────────────────────────────────────────────


class TestCronTable:
    def test_add_list_remove(self, tmp_path: Path) -> None:
        from extensions.cron.runtime import CronTable
        from jarvis_sdk import CronDecl

        table = CronTable(tmp_path / "cron.json")
        table.add(
            CronDecl(
                id="test.job",
                schedule="*/5 * * * *",
                handler=lambda: None,
                description="test",
            )
        )
        rows = table.list()
        assert len(rows) == 1
        assert rows[0]["id"] == "test.job"
        assert table.remove("test.job")
        assert table.list() == []

    def test_persistence(self, tmp_path: Path) -> None:
        from extensions.cron.runtime import CronTable
        from jarvis_sdk import CronDecl

        path = tmp_path / "cron.json"
        t1 = CronTable(path)
        t1.add(
            CronDecl(
                id="p.test",
                schedule="0 9 * * *",
                handler=lambda: None,
            )
        )
        # New instance reads the same JSON.
        t2 = CronTable(path)
        assert any(j["id"] == "p.test" for j in t2.list())


class TestCronExtensionPlugin:
    @pytest.mark.asyncio
    async def test_call_unknown_tool(self, tmp_path: Path) -> None:
        from extensions.cron import runtime as rt_mod
        from extensions.cron.plugin import CronExtensionPlugin

        # Force default to a test instance.
        from extensions.cron.runtime import CronTable
        from jarvis_sdk import Err

        rt_mod.CronTable._default = CronTable(tmp_path / "cron.json")
        p = CronExtensionPlugin()
        result = await p.call("not_a_tool", {})
        assert isinstance(result, Err)
        assert result.code == "UNKNOWN_TOOL"

    @pytest.mark.asyncio
    async def test_call_cron_schedule_and_list(self, tmp_path: Path) -> None:
        from extensions.cron import runtime as rt_mod
        from extensions.cron.plugin import CronExtensionPlugin
        from extensions.cron.runtime import CronTable
        from jarvis_sdk import Ok

        rt_mod.CronTable._default = CronTable(tmp_path / "cron.json")
        p = CronExtensionPlugin()
        result = await p.call(
            "cron_schedule",
            {"id": "test", "schedule": "*/5 * * * *", "description": "demo"},
        )
        assert isinstance(result, Ok)
        result = await p.call("cron_list", {})
        assert isinstance(result, Ok)
        assert "test" in result.value

    def test_manifest(self) -> None:
        import json

        path = REPO_ROOT / "extensions" / "cron" / "openclaw.plugin.json"
        assert path.is_file()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        assert manifest["id"] == "cron"
        assert manifest["kind"] == "infra"
        assert {t["name"] for t in manifest["tools"]} == {
            "cron_schedule",
            "cron_list",
            "cron_cancel",
        }


# ── Memory doctor contract ────────────────────────────────────────


class TestMemoryDoctor:
    def test_detect_legacy(self, tmp_path: Path) -> None:
        from extensions.memory_core.doctor import detect_legacy

        # Missing → no findings.
        assert detect_legacy(tmp_path, {}) == []

        # Create a legacy file.
        legacy = tmp_path / "memory" / "memory.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps({"name": "Fatih", "city": "Istanbul"}), encoding="utf-8")
        findings = detect_legacy(tmp_path, {})
        assert len(findings) == 1
        assert findings[0].count == 2


# ── SDK new types (Skill, Hook, Cron) ──────────────────────────────


class TestSdkNewTypes:
    def test_register_skill(self) -> None:
        from jarvis_sdk import (
            PluginApi,
            PluginContext,
            SkillDecl,
        )

        ctx = PluginContext(plugin_id="t", plugin_kind="tool")
        api = PluginApi(ctx)
        api.register_skill(
            SkillDecl(
                name="weather",
                description="Get weather.",
                body="# weather skill body",
            )
        )
        assert len(api.skills) == 1
        assert api.skills[0].name == "weather"

    def test_register_skill_requires_name(self) -> None:
        from jarvis_sdk import PluginApi, PluginContext, SkillDecl

        ctx = PluginContext(plugin_id="t", plugin_kind="tool")
        api = PluginApi(ctx)
        with pytest.raises(ValueError, match="name and description"):
            api.register_skill(SkillDecl(name="", description="x", body="y"))

    def test_register_hook(self) -> None:
        from jarvis_sdk import PluginApi, PluginContext

        ctx = PluginContext(plugin_id="t", plugin_kind="tool")
        api = PluginApi(ctx)
        api.register_hook("before_agent_start", lambda e: None, priority=5)
        assert len(api.hooks) == 1
        assert api.hooks[0].name == "before_agent_start"
        assert api.hooks[0].priority == 5

    def test_register_hook_requires_callable(self) -> None:
        from jarvis_sdk import PluginApi, PluginContext

        ctx = PluginContext(plugin_id="t", plugin_kind="tool")
        api = PluginApi(ctx)
        with pytest.raises(TypeError):
            api.register_hook("x", "not a function")  # type: ignore[arg-type]

    def test_register_cron(self) -> None:
        from jarvis_sdk import (
            CronDecl,
            PluginApi,
            PluginContext,
        )

        ctx = PluginContext(plugin_id="t", plugin_kind="tool")
        api = PluginApi(ctx)
        api.register_cron(
            CronDecl(
                id="t.job",
                schedule="*/5 * * * *",
                handler=lambda: None,
            )
        )
        assert len(api.cron_jobs) == 1
        assert api.cron_jobs[0].id == "t.job"
