"""Phase 0 Acceptance Tests — Contract & Architecture Freeze.

Verifies:
1. OpenClaw plugin loader contract (openclaw.plugin.json discovery & registration).
2. Extensions registration entrypoint signature (register(api) and entry dict).
3. Multi-agent isolation context (AgentContext schema & serialization).
4. Two-tier event idempotency (L1 in-memory + L2 SQLite durability).
5. Versioned ToolPrediction structured contract.
6. Append-only learning audit log in LearningDatabase.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jarvis_learning.events import AgentContext, EventIdempotencyStore, LearningEvent
from jarvis_learning.models.base import ToolPrediction
from jarvis_learning.storage.learning_db import LearningDatabase


class TestOpenClawPluginContract:
    """Verifies extensions/learning conforms to the OpenClaw plugin loader specification."""

    def test_openclaw_manifest_exists_and_valid(self) -> None:
        workspace_root = Path(__file__).resolve().parents[3]
        manifest_path = workspace_root / "extensions" / "learning" / "openclaw.plugin.json"
        assert manifest_path.is_file(), f"Missing manifest at {manifest_path}"

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest.get("id") == "learning"
        assert manifest.get("name") == "JARVIS Continual Learning Engine"
        assert manifest.get("activation") == "always"
        assert manifest.get("entrypoint") == "plugin:register"
        assert "capabilities" in manifest
        assert "configSchema" in manifest

    def test_plugin_module_exports_registration_contract(self) -> None:
        from extensions.learning import plugin

        assert hasattr(plugin, "register"), "plugin.py must define register(api)"
        assert callable(plugin.register)
        assert hasattr(plugin, "entry"), "plugin.py must export entry dict"
        assert isinstance(plugin.entry, dict)
        assert "register" in plugin.entry
        assert callable(plugin.entry["register"])

    def test_jarvis_sdk_loader_discovers_learning_plugin(self) -> None:
        workspace_root = Path(__file__).resolve().parents[3]
        extensions_root = workspace_root / "extensions"

        from jarvis_sdk.loader import load_all_plugins

        result = load_all_plugins(extensions_root, workspace=workspace_root)
        manifest_ids = [m.get("id") for m in result.manifest_metadata]
        assert "learning" in manifest_ids, (
            f"learning not found in discovered plugins: {manifest_ids}"
        )
        assert "learning" not in result.skipped, (
            f"learning was skipped during loading: {result.skipped}"
        )


class TestAgentContext:
    """Verifies multi-agent isolation context propagation."""

    def test_agent_context_roundtrip(self) -> None:
        ctx = AgentContext(
            task_id="task_42",
            session_id="sess_abc",
            run_id="run_99",
            agent_id="primary_agent",
            turn_id="turn_3",
            sequence_number=5,
            parent_agent_id="parent_agent",
            channel_id="desktop",
            workspace_id="ws_local",
            tool_call_id="call_007",
        )

        d = ctx.to_dict()
        assert d["task_id"] == "task_42"
        assert d["channel_id"] == "desktop"
        assert d["sequence_number"] == 5

        restored = AgentContext.from_dict(d)
        assert restored == ctx

    def test_agent_context_immutability(self) -> None:
        ctx = AgentContext(
            task_id="t1",
            session_id="s1",
            run_id="r1",
            agent_id="a1",
        )
        with pytest.raises(Exception):
            ctx.agent_id = "other_agent"  # type: ignore[misc]

    def test_learning_event_with_context(self) -> None:
        ctx = AgentContext(task_id="t", session_id="s", run_id="r", agent_id="a")
        event = LearningEvent(
            event_type="tool_executed",
            timestamp=1000,
            event_id="evt_123",
            agent_context=ctx,
            data={"tool": "system_audio"},
        )
        assert event.event_id == "evt_123"
        assert event.agent_context is not None
        assert event.agent_context.agent_id == "a"


class TestTwoTierEventIdempotency:
    """Verifies L1 in-memory + L2 SQLite durable deduplication."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> LearningDatabase:
        db_path = tmp_path / "test_idempotency.sqlite"
        return LearningDatabase(db_path)

    def test_l1_in_memory_deduplication(self) -> None:
        store = EventIdempotencyStore(ttl_seconds=60.0)
        # First attempt: new event
        assert not store.is_duplicate_and_record(agent_id="agent_1", event_id="evt_001")
        # Second attempt: duplicate event
        assert store.is_duplicate_and_record(agent_id="agent_1", event_id="evt_001")
        # Different agent with same event_id: NOT duplicate (multi-agent isolation)
        assert not store.is_duplicate_and_record(agent_id="agent_2", event_id="evt_001")

    def test_l2_sqlite_persistence_across_restart(self, db: LearningDatabase) -> None:
        store1 = EventIdempotencyStore(db=db, ttl_seconds=60.0)
        assert not store1.is_duplicate_and_record(agent_id="agent_1", event_id="evt_persistent")

        # Simulate process restart by creating a new store instance with clean L1 cache
        store2 = EventIdempotencyStore(db=db, ttl_seconds=60.0)
        # Even though L1 is empty in store2, L2 SQLite catches the replay!
        assert store2.is_duplicate_and_record(agent_id="agent_1", event_id="evt_persistent")
        assert store2.is_duplicate(agent_id="agent_1", event_id="evt_persistent")

    def test_clean_old_processed_events(self, db: LearningDatabase) -> None:
        db.record_processed_event("agent_1", "old_evt", "type_a", processed_at=1000)
        db.record_processed_event("agent_1", "new_evt", "type_b", processed_at=5000)

        cleaned = db.clean_old_processed_events(older_than_ms=3000)
        assert cleaned == 1
        assert not db.has_processed_event("agent_1", "old_evt")
        assert db.has_processed_event("agent_1", "new_evt")


class TestToolPredictionContract:
    """Verifies advisory neural prediction contract."""

    def test_tool_prediction_fields_and_immutability(self) -> None:
        pred = ToolPrediction(
            prediction_id="pred_1",
            tool_name="system_audio",
            intent="set_volume",
            confidence=0.95,
            calibrated_confidence=0.92,
            model_id="tool_policy",
            model_version="v001",
            task_family="audio_control",
            label_id=3,
            ood_score=0.08,
            latency_ms=12.4,
            is_finite=True,
        )

        assert pred.tool_name == "system_audio"
        assert pred.calibrated_confidence == 0.92
        assert pred.is_finite is True
        assert pred.argument_strategy == "deterministic"

        with pytest.raises(Exception):
            pred.tool_name = "rm -rf"  # type: ignore[misc]


class TestLearningAuditLog:
    """Verifies append-only learning audit log in SQLite."""

    @pytest.fixture
    def db(self, tmp_path: Path) -> LearningDatabase:
        db_path = tmp_path / "test_audit.sqlite"
        return LearningDatabase(db_path)

    def test_audit_log_append_and_retrieve(self, db: LearningDatabase) -> None:
        db.append_audit_log(
            entry_id="audit_1",
            event_type="PROMOTION",
            model_id="tool_policy",
            version="v002",
            metrics={"macro_f1": 0.91, "latency_p95_ms": 14.2},
            operator_id="admin",
            reason="Beat baseline by +7.2% Macro-F1",
            timestamp=1700000000,
        )

        logs = db.get_audit_logs(limit=10)
        assert len(logs) == 1
        entry = logs[0]
        assert entry["entry_id"] == "audit_1"
        assert entry["event_type"] == "PROMOTION"
        assert entry["metrics"]["macro_f1"] == 0.91
        assert entry["operator_id"] == "admin"
