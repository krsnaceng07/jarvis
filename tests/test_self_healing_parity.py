"""tests.test_self_healing_parity — Full parity test suite for JARVIS Self-Healing & Recovery.

Validates OpenClaw parity for:
1. Error taxonomy & classification (network, rate limit, auth, model, tool, system I/O)
2. Exponential backoff, jitter, and retry-after parsing
3. Autonomous tool argument repair heuristics (slashes, aliases, quotes, json strings)
4. Tool fallback execution (shell fallback for failed specialized tools)
5. Multi-provider failover chain
6. Loop prevention engine & signature circuit breaking
7. SQLite-backed recovery audit ledger (pure additive, zero schema bump)
8. Truthful escalation anti-hallucination contract (qa/scenarios/personal/failure-recovery.yaml)
9. Central RecoveryDecisionEngine orchestration
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from src.agents.self_healing import (
    EMPTY_RESPONSE_RETRY_INSTRUCTION,
    REASONING_ONLY_RETRY_INSTRUCTION,
    SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION,
    ErrorCategory,
    ErrorClassifier,
    FailureEvent,
    LastVerifiedState,
    LoopPreventionEngine,
    ProviderFallbackStrategy,
    RecoveryAction,
    RecoveryAuditLedger,
    RecoveryDecisionEngine,
    ToolArgumentRepairStrategy,
    ToolFallbackStrategy,
    TransientRetryStrategy,
    TruthfulEscalationFormatter,
    compute_failure_signature,
)


# ---------------------------------------------------------------------------
# 1. Error Classifier Tests
# ---------------------------------------------------------------------------


def test_classify_transient_network_errors() -> None:
    """Matches OpenClaw's TRANSIENT_NETWORK_CODES in packages/ai/src/utils/retryable-network-errors.ts."""
    network_errors = [
        ConnectionResetError("Connection reset by peer"),
        ConnectionRefusedError("Connection refused"),
        OSError("ECONNRESET: socket hang up"),
        OSError("getaddrinfo ENOTFOUND api.google.com"),
        TimeoutError("Operation timed out"),
        RuntimeError("und_err_connect_timeout: connection timed out"),
        RuntimeError("und_err_socket: socket closed unexpectedly"),
    ]

    for err in network_errors:
        event = ErrorClassifier.classify_exception(err)
        assert event.category == ErrorCategory.NETWORK_TRANSIENT, f"Failed for {err}"
        assert ErrorClassifier.is_transient(event.category) is True


def test_classify_rate_limits_and_overloads() -> None:
    """Matches OpenClaw's rate_limit and overloaded failover reasons."""
    rate_limit_err = RuntimeError("429 Too Many Requests: resource_exhausted, quota exceeded")
    event_rl = ErrorClassifier.classify_exception(rate_limit_err)
    assert event_rl.category == ErrorCategory.RATE_LIMIT
    assert event_rl.severity == "transient"
    assert ErrorClassifier.is_transient(event_rl.category) is True

    # HTTP 429 status code
    http_rl = ErrorClassifier.classify_http_status(429, "Rate limit reached")
    assert http_rl.category == ErrorCategory.RATE_LIMIT

    # HTTP 503 Overloaded
    overloaded_err = RuntimeError("503 Service Unavailable: upstream server overloaded")
    event_ov = ErrorClassifier.classify_exception(overloaded_err)
    assert event_ov.category == ErrorCategory.MODEL_OVERLOADED
    assert ErrorClassifier.is_transient(event_ov.category) is True

    http_503 = ErrorClassifier.classify_http_status(503, "Capacity exceeded")
    assert http_503.category == ErrorCategory.MODEL_OVERLOADED


def test_classify_auth_errors() -> None:
    """Distinguishes temporary token expiration from fatal credential rejections."""
    expired_err = RuntimeError("401 Unauthorized: token expired or invalid_grant")
    ev_expired = ErrorClassifier.classify_exception(expired_err)
    assert ev_expired.category == ErrorCategory.AUTH_EXPIRED
    assert ev_expired.severity == "recoverable"

    permanent_err = RuntimeError("403 Forbidden: invalid api key, account suspended")
    ev_perm = ErrorClassifier.classify_exception(permanent_err)
    assert ev_perm.category == ErrorCategory.AUTH_PERMANENT
    assert ev_perm.severity == "fatal"


def test_classify_windows_and_system_io() -> None:
    """Classifies Windows sharing violations, access denied, and missing paths."""
    win_err32 = OSError(
        "[WinError 32] The process cannot access the file because it is being used by another process"
    )
    ev_32 = ErrorClassifier.classify_exception(win_err32)
    assert ev_32.category == ErrorCategory.SYSTEM_IO_ERROR

    fnf = FileNotFoundError("No such file or directory: 'E:/test.txt'")
    ev_fnf = ErrorClassifier.classify_exception(fnf)
    assert ev_fnf.category == ErrorCategory.SYSTEM_IO_ERROR


def test_classify_tool_validation_and_timeout() -> None:
    """Validates tool validation errors and timeout detection."""
    val_err = ValueError("Tool argument validation failed: missing required argument 'path'")
    ev_val = ErrorClassifier.classify_tool_error("write", {}, val_err)
    assert ev_val.category == ErrorCategory.TOOL_VALIDATION_ERROR

    tout_err = asyncio.TimeoutError()
    ev_tout = ErrorClassifier.classify_tool_error("exec", {"command": "sleep 10"}, tout_err)
    assert ev_tout.category == ErrorCategory.TOOL_TIMEOUT


# ---------------------------------------------------------------------------
# 2. Transient Retry & Backoff Strategy Tests
# ---------------------------------------------------------------------------


def test_transient_retry_backoff_calculation() -> None:
    """Validates exponential backoff with positive and symmetric jitter."""
    strategy = TransientRetryStrategy(
        min_delay_ms=200.0,
        max_delay_ms=1000.0,
        factor=2.0,
        jitter=0.0,  # disable jitter for exact math check
    )

    # Attempt 1: min_delay = 200ms -> 0.2s
    d1 = strategy.calculate_delay_sec(attempt=1)
    assert pytest.approx(d1, 0.01) == 0.2

    # Attempt 2: 200 * 2^1 = 400ms -> 0.4s
    d2 = strategy.calculate_delay_sec(attempt=2)
    assert pytest.approx(d2, 0.01) == 0.4

    # Attempt 3: 200 * 2^2 = 800ms -> 0.8s
    d3 = strategy.calculate_delay_sec(attempt=3)
    assert pytest.approx(d3, 0.01) == 0.8

    # Attempt 4: capped at max_delay_ms = 1000ms -> 1.0s
    d4 = strategy.calculate_delay_sec(attempt=4)
    assert pytest.approx(d4, 0.01) == 1.0

    # Retry-After header override capped by max_delay_ms (1000ms = 1.0s)
    d_hdr = strategy.calculate_delay_sec(attempt=1, retry_after_sec=5.5)
    assert pytest.approx(d_hdr, 0.01) == 1.0

    # Retry-After header override within higher max_delay_ms
    strategy_high = TransientRetryStrategy(
        min_delay_ms=200.0,
        max_delay_ms=10_000.0,
        jitter=0.0,
    )
    d_hdr_high = strategy_high.calculate_delay_sec(attempt=1, retry_after_sec=5.5)
    assert pytest.approx(d_hdr_high, 0.01) == 5.5


@pytest.mark.asyncio
async def test_transient_retry_execute() -> None:
    """Ensures TransientRetryStrategy handles execution with backoff."""
    strategy = TransientRetryStrategy(min_delay_ms=50.0, max_delay_ms=100.0)
    event = FailureEvent(
        category=ErrorCategory.NETWORK_TRANSIENT,
        attempt_count=1,
        context={"tool_name": "gemini_live"},
    )

    res = await strategy.execute(event)
    assert res.success is True
    assert res.requires_retry is True
    assert res.backoff_delay_sec >= 0.05


# ---------------------------------------------------------------------------
# 3. Tool Argument Repair Tests
# ---------------------------------------------------------------------------


def test_tool_argument_repair_aliases() -> None:
    """Verifies that common parameter hallucinations are mapped to canonical keys."""
    strategy = ToolArgumentRepairStrategy()

    # 1. edit tool: old_text -> oldText
    raw_edit = {"path": "foo.py", "old_text": "hello", "new_text": "world"}
    repaired_edit, changes_edit = strategy.repair_arguments("edit", raw_edit)
    assert repaired_edit["oldText"] == "hello"
    assert repaired_edit["newText"] == "world"
    assert len(changes_edit) >= 2

    # 2. write tool: filepath -> path, text -> content
    raw_write = {"filepath": "main.py", "text": "print('ok')"}
    repaired_write, changes_write = strategy.repair_arguments("write", raw_write)
    assert repaired_write["path"] == "main.py"
    assert repaired_write["content"] == "print('ok')"

    # 3. exec tool: cmd -> command
    raw_exec = {"cmd": "git status"}
    repaired_exec, changes_exec = strategy.repair_arguments("exec", raw_exec)
    assert repaired_exec["command"] == "git status"


def test_tool_argument_repair_string_cleaning() -> None:
    """Verifies stripping of outer quotes and backticks, plus JSON string decoding."""
    strategy = ToolArgumentRepairStrategy()

    raw = {
        "path": '"C:/My Projects/test.py"',
        "command": "`dir /b`",
        "metadata": '{"author": "JARVIS", "version": 2}',
    }
    repaired, changes = strategy.repair_arguments("write", raw)
    assert repaired["path"] == "C:/My Projects/test.py"
    assert repaired["command"] == "dir /b"
    assert isinstance(repaired["metadata"], dict)
    assert repaired["metadata"]["author"] == "JARVIS"


def test_tool_argument_repair_path_normalization(tmp_path: Path) -> None:
    """Verifies Windows slash normalization and automatic parent directory creation."""
    strategy = ToolArgumentRepairStrategy()

    deep_dir = tmp_path / "deep" / "nested" / "dir"
    target_file = deep_dir / "output.txt"
    raw = {"path": f"{target_file}/", "content": "hello"}

    # Parent directory does not exist initially
    assert not deep_dir.exists()

    repaired, changes = strategy.repair_arguments("write", raw)

    # 1. Trailing slash stripped on file
    assert not repaired["path"].endswith("/")
    # 2. Missing parent directory auto-created
    assert deep_dir.exists()
    assert any("Auto-created missing parent directory" in c for c in changes)


# ---------------------------------------------------------------------------
# 4. Tool Fallback Strategy Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_fallback_ls_to_exec() -> None:
    """Verifies that a failure in 'ls' generates an 'exec' shell fallback."""
    strategy = ToolFallbackStrategy()
    event = FailureEvent(
        category=ErrorCategory.TOOL_EXECUTION_ERROR,
        context={"tool_name": "ls", "args": {"path": "C:/Windows"}},
        error_message="Access is denied",
    )

    assert await strategy.can_handle(event) is True
    res = await strategy.execute(event)
    assert res.success is True
    assert res.details.get("fallback_tool") == "exec"
    assert "dir" in res.repaired_args.get("command", "") or "ls" in res.repaired_args.get(
        "command", ""
    )


# ---------------------------------------------------------------------------
# 5. Provider Fallback Strategy Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provider_fallback_chain() -> None:
    """Verifies model rotation on provider overload."""
    strategy = ProviderFallbackStrategy()
    event = FailureEvent(
        category=ErrorCategory.MODEL_OVERLOADED,
        context={"model": "models/gemini-3.1-flash-live-preview"},
        error_message="503 Service Unavailable",
    )

    assert await strategy.can_handle(event) is True
    res = await strategy.execute(event)
    assert res.success is True
    assert res.details.get("fallback_model") != "models/gemini-3.1-flash-live-preview"
    assert res.details.get("fallback_provider") in ("groq", "openai", "ollama")


# ---------------------------------------------------------------------------
# 6. Loop Prevention & Circuit Breaker Tests
# ---------------------------------------------------------------------------


def test_loop_prevention_circuit_breaker() -> None:
    """Verifies strict prevention of infinite recovery cycles."""
    engine = LoopPreventionEngine(max_tool_repairs=2, max_transient_retries=3)
    sig = compute_failure_signature(
        category=ErrorCategory.TOOL_EXECUTION_ERROR,
        source="write",
        error_snippet="Permission denied",
        target="C:/locked.txt",
    )

    # Attempt 1: allowed
    can_rec, _ = engine.can_attempt_recovery(sig, ErrorCategory.TOOL_EXECUTION_ERROR)
    assert can_rec is True
    engine.record_attempt(sig, action="repair_arguments", success=False)

    # Attempt 2: allowed
    can_rec, _ = engine.can_attempt_recovery(sig, ErrorCategory.TOOL_EXECUTION_ERROR)
    assert can_rec is True
    engine.record_attempt(sig, action="repair_arguments", success=False)

    # Attempt 3: blocked (circuit breaker tripped!)
    can_rec, reason = engine.can_attempt_recovery(sig, ErrorCategory.TOOL_EXECUTION_ERROR)
    assert can_rec is False
    assert "circuit breaker tripped" in (reason or "").lower()

    # Reset allows recovery again
    engine.reset()
    assert engine.get_signature_attempt_count(sig) == 0
    can_rec_after_reset, _ = engine.can_attempt_recovery(sig, ErrorCategory.TOOL_EXECUTION_ERROR)
    assert can_rec_after_reset is True


# ---------------------------------------------------------------------------
# 7. Recovery Audit Ledger Tests
# ---------------------------------------------------------------------------


def test_recovery_audit_ledger_sqlite_and_stats() -> None:
    """Verifies pure additive SQLite persistence and statistics reporting."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_state.sqlite"
        ledger = RecoveryAuditLedger(db_path=db_path)

        ev = FailureEvent(
            category=ErrorCategory.TOOL_VALIDATION_ERROR,
            error_message="Schema mismatch for 'write'",
            context={"tool_name": "write", "args": {"bad": 123}},
        )

        # Record 1: success
        ledger.record_recovery_event(
            ev,
            action="repair_arguments",
            verified=True,
            details={"changes": ["mapped bad -> path"]},
            session_key="test_session",
        )

        # Record 2: failed
        ledger.record_recovery_event(
            ev,
            action="escalate_to_user",
            verified=False,
            details={"reason": "exhausted"},
            session_key="test_session",
        )

        # Query recent recoveries
        records = ledger.get_recent_recoveries(limit=10, session_key="test_session")
        assert len(records) == 2
        assert records[0]["action"] == "escalate_to_user"
        assert records[1]["action"] == "repair_arguments"
        assert records[1]["verified"] == 1

        # Check stats
        stats = ledger.get_recovery_stats()
        assert stats["total"] == 2
        assert stats["verified_count"] == 1
        assert stats["success_rate"] == 0.5


# ---------------------------------------------------------------------------
# 8. Truthful Escalation Formatter Tests
# ---------------------------------------------------------------------------


def test_truthful_escalation_anti_hallucination_contract() -> None:
    """Matches qa/scenarios/personal/failure-recovery.yaml:
    Must contain 'Completed:', 'Failed step:', 'Retry boundary:', 'Next step:'.
    Must never claim premature success.
    """
    msg = TruthfulEscalationFormatter.format_escalation(
        completed_steps=["Created target workspace directory", "Generated source template"],
        failed_step="Compile project assets",
        error_message="error TS2304: Cannot find name 'UnknownSymbol'",
        retry_boundary_reason="Maximum repair attempts (2/2) reached. Build errors require operator inspection.",
        next_steps=[
            "Fix the missing import in 'src/index.ts'.",
            "Rerun the task.",
        ],
        tool_name="exec",
    )

    assert "**Completed:**" in msg
    assert "✅ Created target workspace directory" in msg
    assert "**Failed step:**" in msg
    assert "[exec] Compile project assets" in msg
    assert "**Retry boundary:**" in msg
    assert "Maximum repair attempts" in msg
    assert "**Next step:**" in msg
    assert "1. Fix the missing import" in msg

    # Anti-hallucination check: ensure no false completion markers
    assert "all done" not in msg.lower()
    assert "success!" not in msg.lower()


# ---------------------------------------------------------------------------
# 9. Recovery Decision Engine Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recovery_decision_engine_pipeline() -> None:
    """Verifies end-to-end orchestration in RecoveryDecisionEngine."""
    engine = RecoveryDecisionEngine()

    # Case 1: Tool validation failure triggers argument repair
    val_event = FailureEvent(
        category=ErrorCategory.TOOL_VALIDATION_ERROR,
        context={
            "tool_name": "write",
            "args": {"filepath": "hello.py", "text": "print(1)"},
        },
        error_message="Missing required property: path",
    )
    decision, res = await engine.execute_recovery(val_event, session_key="test_run")
    assert decision.action == RecoveryAction.REPAIR_ARGUMENTS
    assert res.success is True
    assert res.repaired_args.get("path") == "hello.py"

    # Case 2: Permanent auth triggers immediate escalation
    auth_event = FailureEvent(
        category=ErrorCategory.AUTH_PERMANENT,
        error_message="403 Forbidden: Invalid API Key",
    )
    dec_auth, res_auth = await engine.execute_recovery(auth_event, session_key="test_run")
    assert dec_auth.action == RecoveryAction.ESCALATE_TO_USER
    assert res_auth.success is False
    assert dec_auth.abort_task is True


# ---------------------------------------------------------------------------
# 10. Desktop Host End-to-End Self-Healing Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_desktop_host_self_healing_argument_repair(tmp_path: Path) -> None:
    """Verifies that JarvisLive._execute_tool autonomously heals parameter hallucinations.
    e.g. 'filepath' -> 'path' and 'text' -> 'content', then verifies file on disk.
    """
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    live = JarvisLive(mock_ui)

    target_file = tmp_path / "healed_output.txt"
    # LLM hallucinated 'filepath' and 'text' instead of canonical 'path' and 'content'
    fc = SimpleNamespace(
        id="call_heal_1",
        name="write",
        args={"filepath": str(target_file), "text": "self-healing verified content"},
    )

    resp = await live._execute_tool(fc)
    assert resp.name == "write"
    # Must succeed and be verified on physical disk
    assert "Verified" in resp.response["result"]
    assert target_file.exists()
    assert target_file.read_text(encoding="utf-8") == "self-healing verified content"


@pytest.mark.asyncio
async def test_desktop_host_truthful_escalation_on_failure() -> None:
    """Verifies that an unrecoverable failure produces a truthful escalation report."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from apps.desktop.src.jarvis_desktop.app import JarvisLive

    mock_ui = MagicMock()
    mock_ui.muted = False
    live = JarvisLive(mock_ui)

    # Tool call missing required args entirely
    fc = SimpleNamespace(
        id="call_fail_1",
        name="write",
        args={},
    )

    resp = await live._execute_tool(fc)
    assert resp.name == "write"
    result_text = resp.response.get("result", "")
    assert "Tool argument validation failed" in result_text


def test_classify_model_turn_empty_and_reasoning_only() -> None:
    """Matches OpenClaw qa/scenarios/runtime/empty-response-recovery-replay-safe-read.yaml
    and reasoning-only-recovery-replay-safe-read.yaml.
    """
    # 1. Normal turn with content -> None (no failure)
    res_normal = ErrorClassifier.classify_model_turn(
        content="I have read the file.",
        has_tool_calls=False,
    )
    assert res_normal is None

    # 2. Turn with tool calls -> None (no failure even if content is empty)
    res_tools = ErrorClassifier.classify_model_turn(
        content="",
        has_tool_calls=True,
    )
    assert res_tools is None

    # 3. Empty response (0 tokens / empty content without tool calls)
    res_empty = ErrorClassifier.classify_model_turn(
        content="",
        has_tool_calls=False,
    )
    assert res_empty is not None
    assert res_empty.category == ErrorCategory.EMPTY_RESPONSE
    assert res_empty.severity == "recoverable"

    # 4. Reasoning-only turn (model only output thinking tokens without text/calls)
    res_reasoning = ErrorClassifier.classify_model_turn(
        content="",
        has_tool_calls=False,
        is_reasoning_only=True,
    )
    assert res_reasoning is not None
    assert res_reasoning.category == ErrorCategory.REASONING_ONLY
    assert res_reasoning.severity == "recoverable"


@pytest.mark.asyncio
async def test_provider_fallback_strict_user_selection_and_notices() -> None:
    """Verifies OpenClaw policy: strict user selection forbids silent fallback,
    and fallback notices match OpenClaw exact formatting contracts.
    """
    strat = ProviderFallbackStrategy()

    # 1. OpenClaw notice formatting contract
    notice = strat.format_fallback_notice(
        fallback_model="groq/llama-3.3-70b-versatile",
        primary_model="models/gemini-3.1-flash-live-preview",
        reason="429 Resource Exhausted",
    )
    assert (
        notice
        == "↪️ Model Fallback: groq/llama-3.3-70b-versatile (selected models/gemini-3.1-flash-live-preview; 429 Resource Exhausted)"
    )

    cleared_notice = strat.format_fallback_cleared_notice(
        primary_model="models/gemini-3.1-flash-live-preview",
        fallback_model="groq/llama-3.3-70b-versatile",
    )
    assert (
        cleared_notice
        == "↪️ Model Fallback cleared: models/gemini-3.1-flash-live-preview (was groq/llama-3.3-70b-versatile)"
    )

    # 2. Strict user model selection -> automatic fallback blocked
    strict_event = FailureEvent(
        category=ErrorCategory.MODEL_OVERLOADED,
        severity="transient",
        error_message="503 Service Unavailable",
        context={
            "model": "models/gemini-3.1-flash-live-preview",
            "model_override_source": "user",
        },
    )
    res_strict = await strat.execute(strict_event)
    assert res_strict.success is False
    assert "blocked by strict user selection" in res_strict.action_taken


def test_last_verified_state_checkpoint_and_rollback() -> None:
    """Verifies LastVerifiedState physical record tracking, checkpointing, and rollback."""
    lvs = LastVerifiedState("test_session")
    assert lvs.get_completed_steps() == []
    assert lvs.get_last_checkpoint() is None

    # Record first action
    rec1 = lvs.record_verified_action(
        tool_name="write",
        target_resource="test.txt",
        step_summary="Created test.txt",
        details={"bytes": 42},
    )
    assert rec1.step_summary == "Created test.txt"
    assert lvs.get_completed_steps() == ["Created test.txt"]

    # Checkpoint
    cp = lvs.create_checkpoint("step_1")

    # Record second action
    rec2 = lvs.record_verified_action(
        tool_name="exec",
        target_resource="pytest",
        step_summary="Ran tests",
        details={"exit_code": 0},
    )
    assert lvs.get_completed_steps() == ["Created test.txt", "Ran tests"]
    assert lvs.get_last_checkpoint() == rec2

    # Rollback to checkpoint
    rolled_back = lvs.rollback_to_checkpoint(cp)
    assert len(rolled_back) == 1
    assert rolled_back[0].step_summary == "Ran tests"
    assert lvs.get_completed_steps() == ["Created test.txt"]
    assert lvs.get_last_checkpoint() == rec1

    # Reset
    lvs.reset()
    assert lvs.get_completed_steps() == []


def test_classify_openclaw_failover_reasons() -> None:
    """Verifies classification of OpenClaw-specific failover categories:
    tls_certificate, billing_exhausted, model_not_found, format_error, session_expired.
    """
    # 1. TLS Certificate
    err_tls = OSError(
        "SSL: CERTIFICATE_VERIFY_FAILED: certificate verify failed: self-signed certificate"
    )
    ev_tls = ErrorClassifier.classify_exception(err_tls)
    assert ev_tls.category == ErrorCategory.TLS_CERTIFICATE_ERROR

    # 2. Billing / Quota Exhausted
    err_billing = RuntimeError(
        "insufficient_quota: You have exceeded your current quota. Check your plan and billing details."
    )
    ev_billing = ErrorClassifier.classify_exception(err_billing)
    assert ev_billing.category == ErrorCategory.BILLING_EXHAUSTED
    assert ev_billing.severity == "fatal"

    # HTTP 402
    ev_402 = ErrorClassifier.classify_http_status(402, "Payment Required")
    assert ev_402.category == ErrorCategory.BILLING_EXHAUSTED

    # 3. Model Not Found
    err_model = RuntimeError("404 Not Found: The model `models/nonexistent-model` does not exist")
    ev_model = ErrorClassifier.classify_exception(err_model)
    assert ev_model.category == ErrorCategory.MODEL_NOT_FOUND

    # HTTP 404 with model
    ev_404 = ErrorClassifier.classify_http_status(404, "model not found")
    assert ev_404.category == ErrorCategory.MODEL_NOT_FOUND

    # 4. Format Error
    err_fmt = ValueError("JSONDecodeError: Expecting value: line 1 column 1 (char 0)")
    ev_fmt = ErrorClassifier.classify_exception(err_fmt)
    assert ev_fmt.category == ErrorCategory.FORMAT_ERROR

    # 5. Session Expired
    err_sess = ConnectionResetError("Session expired: remote session terminated due to inactivity")
    ev_sess = ErrorClassifier.classify_exception(err_sess)
    assert ev_sess.category == ErrorCategory.SESSION_EXPIRED


def test_loop_prevention_openclaw_retry_limits() -> None:
    """Verifies that LoopPreventionEngine respects OpenClaw's exact retry limits:
    - EMPTY_RESPONSE: 1 attempt max
    - REASONING_ONLY: 2 attempts max
    """
    lp = LoopPreventionEngine()

    assert lp.get_max_attempts_for_category(ErrorCategory.EMPTY_RESPONSE) == 1
    assert lp.get_max_attempts_for_category(ErrorCategory.REASONING_ONLY) == 2

    # Verify circuit breaker trips after 1 empty response retry
    sig_empty = "empty_response_sig_1"
    ok1, _ = lp.can_attempt_recovery(sig_empty, ErrorCategory.EMPTY_RESPONSE)
    assert ok1 is True
    lp.record_attempt(sig_empty, "continue_incomplete_turn", success=True)

    ok2, reason = lp.can_attempt_recovery(sig_empty, ErrorCategory.EMPTY_RESPONSE)
    assert ok2 is False
    assert "circuit breaker tripped" in str(reason)


@pytest.mark.asyncio
async def test_decision_engine_incomplete_turn_and_failover_parity() -> None:
    """Verifies RecoveryDecisionEngine behavior for incomplete turns (empty/reasoning-only)
    and immediate failovers (billing, TLS, model_not_found).
    """
    engine = RecoveryDecisionEngine()

    # 1. Empty response without previous tools -> inject EMPTY_RESPONSE_RETRY_INSTRUCTION
    ev_empty_no_tools = FailureEvent(
        category=ErrorCategory.EMPTY_RESPONSE,
        severity="recoverable",
        error_message="Empty model response",
        context={"has_completed_tools": False},
        attempt_count=1,
    )
    dec_empty = engine.evaluate_decision(ev_empty_no_tools)
    assert dec_empty.action == RecoveryAction.CONTINUE_INCOMPLETE_TURN
    assert dec_empty.continuation_instruction == EMPTY_RESPONSE_RETRY_INSTRUCTION

    # 2. Empty response after completed tools -> inject SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION
    ev_empty_tools = FailureEvent(
        category=ErrorCategory.EMPTY_RESPONSE,
        severity="recoverable",
        error_message="Empty model response",
        context={"has_completed_tools": True},
        attempt_count=1,
    )
    dec_empty_tools = engine.evaluate_decision(ev_empty_tools)
    assert dec_empty_tools.action == RecoveryAction.CONTINUE_INCOMPLETE_TURN
    assert (
        dec_empty_tools.continuation_instruction == SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION
    )

    # 3. Reasoning only turn -> inject REASONING_ONLY_RETRY_INSTRUCTION
    ev_reasoning = FailureEvent(
        category=ErrorCategory.REASONING_ONLY,
        severity="recoverable",
        error_message="Reasoning tokens only",
        attempt_count=1,
    )
    dec_reasoning = engine.evaluate_decision(ev_reasoning)
    assert dec_reasoning.action == RecoveryAction.CONTINUE_INCOMPLETE_TURN
    assert dec_reasoning.continuation_instruction == REASONING_ONLY_RETRY_INSTRUCTION

    # 4. Immediate provider fallbacks: Billing, TLS, Model not found
    ev_billing = FailureEvent(
        category=ErrorCategory.BILLING_EXHAUSTED,
        severity="fatal",
        error_message="Quota exhausted",
    )
    assert engine.evaluate_decision(ev_billing).action == RecoveryAction.FALLBACK_PROVIDER

    ev_tls = FailureEvent(
        category=ErrorCategory.TLS_CERTIFICATE_ERROR,
        severity="recoverable",
        error_message="TLS verification error",
    )
    assert engine.evaluate_decision(ev_tls).action == RecoveryAction.FALLBACK_PROVIDER

    ev_model_nf = FailureEvent(
        category=ErrorCategory.MODEL_NOT_FOUND,
        severity="recoverable",
        error_message="Model not found",
    )
    assert engine.evaluate_decision(ev_model_nf).action == RecoveryAction.FALLBACK_PROVIDER

    # 5. Execute recovery for CONTINUE_INCOMPLETE_TURN
    dec, res = await engine.execute_recovery(ev_reasoning)
    assert dec.action == RecoveryAction.CONTINUE_INCOMPLETE_TURN
    assert res.success is True
    assert res.requires_retry is True
    assert res.details["continuation_instruction"] == REASONING_ONLY_RETRY_INSTRUCTION
