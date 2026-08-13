"""Gateway agent-run entrypoints and lifecycle wait registry.

Mirrors OpenClaw's ``agent`` / ``agent.wait`` contract while keeping the
model runner injectable. The gateway owns acceptance, per-session lanes,
run lifecycle, and bounded wait semantics; the embedded runner owns the turn.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, cast


AgentRunEvent = dict[str, Any]

Runner = Callable[[dict[str, Any], threading.Event, Callable[[dict[str, Any]], None]], Any]


@dataclass
class _AgentRun:
    run_id: str
    session_key: str
    accepted_at: int
    done: threading.Event = field(default_factory=threading.Event)
    abort: threading.Event = field(default_factory=threading.Event)
    started_at: int | None = None
    ended_at: int | None = None
    error: str | None = None
    timed_out: bool = False
    result: Any = None
    lifecycle: list[AgentRunEvent] = field(default_factory=lambda: cast(list[AgentRunEvent], []))
    events: list[AgentRunEvent] = field(default_factory=lambda: cast(list[AgentRunEvent], []))


class AgentRunService:
    """Accept and wait for serialized embedded-agent runs."""

    def __init__(self, runner: Runner) -> None:
        self._runner = runner
        self._runs: dict[str, _AgentRun] = {}
        self._session_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    def agent(self, params: dict[str, Any]) -> dict[str, Any]:
        message = params.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("agent requires a non-empty message")
        session_key = str(params.get("sessionKey") or params.get("sessionId") or "default")
        run = _AgentRun(
            run_id=str(uuid.uuid4()),
            session_key=session_key,
            accepted_at=_now_ms(),
        )
        with self._lock:
            self._runs[run.run_id] = run
            lane = self._session_locks.setdefault(session_key, threading.Lock())
        thread = threading.Thread(
            target=self._run,
            args=(run, lane, dict(params)),
            name=f"jarvis-agent-{run.run_id[:8]}",
            daemon=True,
        )
        thread.start()
        return {"runId": run.run_id, "acceptedAt": run.accepted_at}

    def wait(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = params.get("runId")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("agent.wait requires runId")
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise ValueError(f"unknown runId: {run_id}")
        timeout_ms = params.get("timeoutMs", 30_000)
        try:
            timeout = max(0, int(timeout_ms)) / 1000
        except (TypeError, ValueError):
            raise ValueError("timeoutMs must be an integer") from None
        if not run.done.wait(timeout):
            return {
                "status": "timeout",
                "runId": run_id,
                "startedAt": run.started_at,
                "endedAt": None,
            }
        payload: dict[str, Any] = {
            "status": "error" if run.error else "ok",
            "runId": run_id,
            "startedAt": run.started_at,
            "endedAt": run.ended_at,
        }
        if run.error:
            payload["error"] = run.error
        if run.result is not None:
            payload["result"] = run.result
        return payload

    def abort(self, params: dict[str, Any]) -> dict[str, Any]:
        run_id = params.get("runId")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("agent.abort requires runId")
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise ValueError(f"unknown runId: {run_id}")
        if run.done.is_set():
            return {"runId": run_id, "aborted": False}
        run.abort.set()
        self._emit(run, "abort_requested")
        return {"runId": run_id, "aborted": True}

    def lifecycle(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise ValueError(f"unknown runId: {run_id}")
        return list(run.lifecycle)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            run = self._runs.get(run_id)
        if run is None:
            raise ValueError(f"unknown runId: {run_id}")
        return list(run.events)

    def _run(
        self,
        run: _AgentRun,
        lane: threading.Lock,
        params: dict[str, Any],
    ) -> None:
        with lane:
            run.started_at = _now_ms()
            self._emit(run, "start")
            timeout_timer: threading.Timer | None = None
            timeout_ms = params.get("runTimeoutMs")
            if timeout_ms is not None:
                try:
                    timeout_seconds = max(0, int(timeout_ms)) / 1000
                except (TypeError, ValueError):
                    timeout_seconds = 0
                if timeout_seconds > 0:
                    timeout_timer = threading.Timer(
                        timeout_seconds, self._request_timeout, args=(run,)
                    )
                    timeout_timer.daemon = True
                    timeout_timer.start()
            try:
                run.result = self._runner(params, run.abort, lambda event: self._emit(run, event))
                if run.timed_out:
                    run.error = "agent run timed out"
            except Exception as exc:  # noqa: BLE001
                run.error = str(exc)
                self._emit(run, "error", error=str(exc))
            else:
                if run.error:
                    self._emit(run, "error", error=run.error)
                else:
                    self._emit(run, "end")
            finally:
                if timeout_timer is not None:
                    timeout_timer.cancel()
                run.ended_at = _now_ms()
                run.done.set()

    def _request_timeout(self, run: _AgentRun) -> None:
        if run.done.is_set():
            return
        run.timed_out = True
        run.abort.set()
        self._emit(run, "timeout")

    def _emit(self, run: _AgentRun, phase: str | dict[str, Any], **extra: Any) -> None:
        event = {"stream": "lifecycle", "phase": phase} if isinstance(phase, str) else dict(phase)
        event.update(extra)
        with self._lock:
            run.events.append(event)
            if event.get("stream") == "lifecycle":
                run.lifecycle.append(event)


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["AgentRunService", "Runner"]
