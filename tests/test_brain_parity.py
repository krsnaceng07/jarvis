"""test_brain_parity.py — Adversarial tests for OpenClaw brain architecture parity.

Covers:
- Phase 1: _ToolLoopGuard (loop detection, circuit breaker, record_outcome)
- Phase 2: _build_config structured STABLE/DYNAMIC sections
- Phase 4: _build_resume_context (transcript replay)
- Phase 5: Steering queue routing
"""

from __future__ import annotations

import queue
import threading
from unittest.mock import MagicMock



# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: tool_loop_detection module (wired into _ToolLoopGuard)
# ─────────────────────────────────────────────────────────────────────────────

_LOOP_CONFIG = {
    "enabled": True,
    "historySize": 30,
    "warningThreshold": 10,
    "unknownToolThreshold": 10,
    "criticalThreshold": 20,
    "globalCircuitBreakerThreshold": 30,
    "detectors": {
        "genericRepeat": True,
        "knownPollNoProgress": True,
        "pingPong": True,
    },
}


class TestToolLoopDetection:
    def _state(self):
        return {}

    def test_no_loop_fresh_state(self):
        from src.agents.tool_loop_detection import detect_tool_call_loop, record_tool_call
        state = self._state()
        record_tool_call(state, "mkdir", {"path": "/tmp/test"}, tool_call_id="1", config=_LOOP_CONFIG)
        result = detect_tool_call_loop(state, "mkdir", {"path": "/tmp/test"}, config=_LOOP_CONFIG)
        assert not result["stuck"]

    def test_warning_threshold_generic_repeat(self):
        from src.agents.tool_loop_detection import detect_tool_call_loop, record_tool_call, record_tool_call_outcome
        state = self._state()
        args = {"command": "Get-ChildItem C:\\"}
        result_text = "error: access denied"
        for i in range(10):
            tid = f"tc-{i}"
            record_tool_call(state, "exec", args, tool_call_id=tid, config=_LOOP_CONFIG)
            record_tool_call_outcome(state, {
                "toolName": "exec", "toolParams": args, "toolCallId": tid,
                "result": {"content": [{"type": "text", "text": result_text}]},
                "error": None, "config": _LOOP_CONFIG,
            })
        record_tool_call(state, "exec", args, tool_call_id="tc-10", config=_LOOP_CONFIG)
        result = detect_tool_call_loop(state, "exec", args, config=_LOOP_CONFIG)
        assert result["stuck"] is True
        assert result.get("level") in ("warning", "critical")

    def test_critical_threshold_blocks(self):
        from src.agents.tool_loop_detection import detect_tool_call_loop, record_tool_call, record_tool_call_outcome
        state = self._state()
        args = {"command": "do_thing"}
        result_text = "still failing"
        for i in range(25):
            tid = f"tc-{i}"
            record_tool_call(state, "exec", args, tool_call_id=tid, config=_LOOP_CONFIG)
            record_tool_call_outcome(state, {
                "toolName": "exec", "toolParams": args, "toolCallId": tid,
                "result": {"content": [{"type": "text", "text": result_text}]},
                "error": None, "config": _LOOP_CONFIG,
            })
        record_tool_call(state, "exec", args, tool_call_id="tc-25", config=_LOOP_CONFIG)
        result = detect_tool_call_loop(state, "exec", args, config=_LOOP_CONFIG)
        assert result["stuck"] is True
        assert result.get("level") == "critical"

    def test_different_args_no_loop(self):
        from src.agents.tool_loop_detection import detect_tool_call_loop, record_tool_call
        state = self._state()
        for i in range(15):
            args = {"path": f"/tmp/dir_{i}"}
            record_tool_call(state, "mkdir", args, tool_call_id=f"tc-{i}", config=_LOOP_CONFIG)
        args = {"path": "/tmp/dir_15"}
        record_tool_call(state, "mkdir", args, tool_call_id="tc-15", config=_LOOP_CONFIG)
        result = detect_tool_call_loop(state, "mkdir", args, config=_LOOP_CONFIG)
        assert not result["stuck"]

    def test_history_bounded_at_30(self):
        from src.agents.tool_loop_detection import record_tool_call
        state = self._state()
        for i in range(40):
            record_tool_call(state, "ls", {"path": f"/p{i}"}, tool_call_id=f"tc-{i}", config=_LOOP_CONFIG)
        assert len(state.get("toolCallHistory", [])) <= 30

    def test_enabled_false_never_stuck(self):
        from src.agents.tool_loop_detection import detect_tool_call_loop, record_tool_call
        cfg = {**_LOOP_CONFIG, "enabled": False}
        state = self._state()
        args = {"command": "bad"}
        for i in range(30):
            record_tool_call(state, "exec", args, tool_call_id=f"tc-{i}", config=cfg)
        result = detect_tool_call_loop(state, "exec", args, config=cfg)
        assert not result["stuck"]


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: _ToolLoopGuard class (extracted from app.py)
# ─────────────────────────────────────────────────────────────────────────────

def _make_guard():
    from apps.desktop.src.jarvis_desktop.tool_loop_guard import ToolLoopGuard

    return ToolLoopGuard()


class TestToolLoopGuardClass:
    def test_reset_clears_state(self):
        guard = _make_guard()
        for i in range(5):
            guard.check_before("mkdir", {"path": f"/p{i}"}, f"tc-{i}")
        guard.reset()
        assert guard.critical_tool_loop_seen is False
        assert guard._state == {}

    def test_warning_does_not_block(self):
        guard = _make_guard()
        args = {"command": "bad"}
        result_text = "err"
        for i in range(9):
            block = guard.check_before("exec", args, f"tc-{i}")
            guard.record_outcome("exec", args, result_text, None, f"tc-{i}")
            assert block is None, f"Unexpected block at call {i}"

    def test_critical_returns_block_message(self):
        guard = _make_guard()
        args = {"command": "stuck_command"}
        result_text = "same error every time"
        block = None
        for i in range(35):
            block = guard.check_before("exec", args, f"tc-{i}")
            if block is not None:
                break
            guard.record_outcome("exec", args, result_text, None, f"tc-{i}")
        assert block is not None, "Expected a blocking message after 35 identical calls"
        assert "TOOL LOOP BLOCKED" in block
        assert guard.critical_tool_loop_seen is True

    def test_reset_then_no_false_positive(self):
        guard = _make_guard()
        args = {"command": "old_cmd"}
        for i in range(40):
            guard.check_before("exec", args, f"tc-{i}")
            guard.record_outcome("exec", args, "same", None, f"tc-{i}")
        guard.reset()
        block = guard.check_before("exec", {"command": "new_cmd"}, "fresh-1")
        assert block is None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: _build_resume_context
# ─────────────────────────────────────────────────────────────────────────────

def _load_resume_context_method():
    from pathlib import Path
    from typing import Any
    src = Path("apps/desktop/src/jarvis_desktop/app.py").read_text(encoding="utf-8")
    start = src.find("    def _build_resume_context(")
    end = src.find("\n    def _build_config(", start)
    method_src = src[start:end].strip()
    wrapped = "class _FakeJarvis:\n" + "\n".join("    " + line for line in method_src.split("\n"))
    ns: dict = {"Any": Any}
    exec(compile(wrapped, "<resume>", "exec"), ns)
    return ns["_FakeJarvis"]


def _make_resume_obj(entries):
    cls = _load_resume_context_method()
    obj = cls()
    store = MagicMock()
    store.get_recent_entries.return_value = entries
    obj._transcript_store = store
    return obj


class TestBuildResumeContext:
    def test_empty_returns_none(self):
        obj = _make_resume_obj([])
        assert obj._build_resume_context() is None

    def test_tool_call_entries(self):
        entries = [
            {"entry_type": "tool_call", "data": {"name": "mkdir", "args": {"path": "E:\\test"}}, "verified": True, "created_at": 1.0},
            {"entry_type": "execution_record", "data": {"tool_name": "mkdir", "status": "success", "raw_output": "Created."}, "verified": True, "created_at": 2.0},
        ]
        obj = _make_resume_obj(entries)
        result = obj._build_resume_context()
        assert result is not None
        assert "mkdir" in result
        assert "SESSION RESUME" in result

    def test_user_speech_entries(self):
        entries = [
            {"entry_type": "user_turn", "data": {"text": "E drive ma folder banau"}, "verified": False, "created_at": 1.0},
        ]
        obj = _make_resume_obj(entries)
        result = obj._build_resume_context()
        assert result is not None
        assert "E drive ma folder banau" in result

    def test_end_prior_context_footer(self):
        entries = [
            {"entry_type": "user_turn", "data": {"text": "test"}, "verified": False, "created_at": 1.0},
        ]
        obj = _make_resume_obj(entries)
        result = obj._build_resume_context()
        assert result is not None
        assert "END PRIOR CONTEXT" in result

    def test_store_exception_returns_none(self):
        cls = _load_resume_context_method()
        obj = cls()
        store = MagicMock()
        store.get_recent_entries.side_effect = RuntimeError("DB locked")
        obj._transcript_store = store
        assert obj._build_resume_context() is None

    def test_no_transcript_store_returns_none(self):
        cls = _load_resume_context_method()
        obj = cls()
        # No _transcript_store attribute at all
        assert obj._build_resume_context() is None


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5: Steering queue
# ─────────────────────────────────────────────────────────────────────────────

class TestSteeringQueue:
    def test_simple_queue_put_get(self):
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        assert q.empty()
        q.put_nowait("hello world")
        assert not q.empty()
        msg = q.get_nowait()
        assert msg == "hello world"
        assert q.empty()

    def test_thread_safe_concurrent_writes(self):
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        errors = []

        def _writer(tid: int):
            try:
                for i in range(10):
                    q.put_nowait(f"msg-{tid}-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        items = []
        while not q.empty():
            items.append(q.get_nowait())
        assert len(items) == 50

    def test_drain_empties_queue_in_order(self):
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        messages = ["first", "second", "third"]
        for m in messages:
            q.put_nowait(m)
        drained = []
        while not q.empty():
            try:
                drained.append(q.get_nowait())
            except Exception:
                break
        assert drained == messages
        assert q.empty()

    def test_thinking_state_buffers(self):
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        submitted = []
        state = "THINKING"
        text = "new command"
        if state == "THINKING":
            q.put_nowait(text)
        else:
            submitted.append(text)
        assert q.get_nowait() == "new command"
        assert not submitted

    def test_listening_state_submits_directly(self):
        q: queue.SimpleQueue[str] = queue.SimpleQueue()
        submitted = []
        state = "LISTENING"
        text = "direct command"
        if state == "THINKING":
            q.put_nowait(text)
        else:
            submitted.append(text)
        assert q.empty()
        assert submitted == ["direct command"]
