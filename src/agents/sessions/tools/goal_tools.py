"""JARVIS Goal Tools — OpenClaw Parity Architecture.

Mirrors openclaw-main/src/agents/tools/goal-tools.ts and config/sessions/goals.ts.
Provides persistent session goal tracking (backed by shared state SQLite ~/.jarvis/state/jarvis.sqlite),
model-callable AgentTools (get_goal, create_goal, update_goal),
voice prompt goal injection, and HUD / CLI /goal command execution.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

# In-memory session goals cache
_SESSION_GOALS: Dict[str, Dict[str, Any]] = {}
_DB_LOCK = threading.Lock()


def _get_state_db_path() -> Path:
    base = Path(os.environ.get("JARVIS_STATE_DIR", Path.home() / ".jarvis" / "state"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "jarvis.sqlite"


def _ensure_goals_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS session_goals (
            session_id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            token_budget INTEGER,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            notes_json TEXT NOT NULL
        )
        """
    )
    conn.commit()


def get_active_goal(session_id: str = "default_session") -> Optional[Dict[str, Any]]:
    """Retrieve the active goal for the session, checking cache then SQLite."""
    with _DB_LOCK:
        if session_id in _SESSION_GOALS:
            return dict(_SESSION_GOALS[session_id])

        db_path = _get_state_db_path()
        try:
            with sqlite3.connect(db_path) as conn:
                _ensure_goals_table(conn)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT session_id, objective, token_budget, status, created_at, updated_at, notes_json FROM session_goals WHERE session_id = ?",
                    (session_id,),
                )
                row = cursor.fetchone()
                if row:
                    goal = {
                        "session_id": row[0],
                        "objective": row[1],
                        "token_budget": row[2],
                        "status": row[3],
                        "created_at": row[4],
                        "updated_at": row[5],
                        "notes": json.loads(row[6]) if row[6] else [],
                    }
                    _SESSION_GOALS[session_id] = goal
                    return dict(goal)
        except Exception:
            pass
    return None


def set_goal(
    objective: str,
    session_id: str = "default_session",
    token_budget: Optional[int] = None,
) -> Dict[str, Any]:
    """Create or overwrite the active goal for a session."""
    now = time.time()
    goal = {
        "session_id": session_id,
        "objective": objective.strip(),
        "token_budget": token_budget,
        "status": "in_progress",
        "created_at": now,
        "updated_at": now,
        "notes": [],
    }
    with _DB_LOCK:
        _SESSION_GOALS[session_id] = goal
        db_path = _get_state_db_path()
        try:
            with sqlite3.connect(db_path) as conn:
                _ensure_goals_table(conn)
                conn.execute(
                    """
                    INSERT INTO session_goals (session_id, objective, token_budget, status, created_at, updated_at, notes_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        objective = excluded.objective,
                        token_budget = excluded.token_budget,
                        status = excluded.status,
                        updated_at = excluded.updated_at,
                        notes_json = excluded.notes_json
                    """,
                    (session_id, goal["objective"], token_budget, "in_progress", now, now, json.dumps([])),
                )
                conn.commit()
        except Exception:
            pass
    return goal


def update_goal_status(
    status: str,
    note: Optional[str] = None,
    session_id: str = "default_session",
) -> Optional[Dict[str, Any]]:
    """Update active goal status ('in_progress', 'complete', 'blocked') and append a note."""
    goal = get_active_goal(session_id)
    if not goal:
        return None

    now = time.time()
    goal["status"] = status
    goal["updated_at"] = now
    if note:
        goal.setdefault("notes", []).append({"note": note.strip(), "time": now})

    with _DB_LOCK:
        _SESSION_GOALS[session_id] = goal
        db_path = _get_state_db_path()
        try:
            with sqlite3.connect(db_path) as conn:
                _ensure_goals_table(conn)
                conn.execute(
                    """
                    UPDATE session_goals
                    SET status = ?, updated_at = ?, notes_json = ?
                    WHERE session_id = ?
                    """,
                    (status, now, json.dumps(goal.get("notes", [])), session_id),
                )
                conn.commit()
        except Exception:
            pass
    return goal


def clear_goal(session_id: str = "default_session") -> bool:
    """Clear/remove the active session goal."""
    with _DB_LOCK:
        _SESSION_GOALS.pop(session_id, None)
        db_path = _get_state_db_path()
        try:
            with sqlite3.connect(db_path) as conn:
                _ensure_goals_table(conn)
                conn.execute("DELETE FROM session_goals WHERE session_id = ?", (session_id,))
                conn.commit()
                return True
        except Exception:
            return False


def format_goal_display(session_id: str = "default_session") -> str:
    """Format the active goal into a clean status string for CLI/terminal HUD."""
    goal = get_active_goal(session_id)
    if not goal:
        return "No active session goal declared. Use '/goal start <objective>' or 'jarvis goal start <objective>'."

    budget_str = f"{goal['token_budget']:,} tokens" if goal.get("token_budget") else "None"
    status = goal.get("status", "in_progress")
    status_icon = "🟢" if status == "in_progress" else ("✅" if status == "complete" else "⚠️")
    lines = [
        f"🎯 ACTIVE GOAL: {goal.get('objective', '')}",
        f"Status: {status_icon} {status}",
        f"Token Budget: {budget_str}",
    ]
    notes = goal.get("notes", [])
    if notes:
        lines.append("Progress Notes:")
        for n in notes[-5:]:
            ts = time.strftime("%H:%M:%S", time.localtime(n.get("time", time.time())))
            lines.append(f"  • [{ts}] {n.get('note', '')}")
    return "\n".join(lines)


def handle_goal_command(cmd_text: str, session_id: str = "default_session") -> str:
    """Parses and executes a `/goal` or `goal` slash command or CLI input string."""
    parts = cmd_text.strip().split(maxsplit=2)
    if not parts:
        return format_goal_display(session_id)

    prefix = parts[0].lower()
    if prefix not in ("/goal", "goal"):
        if prefix.startswith("/goal"):
            subcmd = prefix[5:].strip() or (parts[1].lower() if len(parts) > 1 else "status")
        else:
            return format_goal_display(session_id)
    else:
        subcmd = parts[1].lower() if len(parts) > 1 else "status"

    if subcmd in ("status", "show", "list"):
        return format_goal_display(session_id)
    elif subcmd in ("start", "create", "set"):
        if len(parts) < 3:
            return "Usage: /goal start <objective>"
        obj = parts[2].strip()
        set_goal(obj, session_id=session_id)
        return f"🎯 Active goal set: {obj}\nJARVIS will pursue and settle this goal autonomously."
    elif subcmd in ("complete", "done", "finish"):
        note = parts[2].strip() if len(parts) > 2 else "Goal completed by user."
        updated = update_goal_status("complete", note=note, session_id=session_id)
        if updated:
            return f"✅ Goal marked as COMPLETE!\nNote: {note}"
        return "⚠️ No active goal found to complete."
    elif subcmd in ("blocked", "pause"):
        note = parts[2].strip() if len(parts) > 2 else "Goal blocked."
        updated = update_goal_status("blocked", note=note, session_id=session_id)
        if updated:
            return f"⚠️ Goal marked as BLOCKED.\nNote: {note}"
        return "⚠️ No active goal found."
    elif subcmd in ("clear", "reset", "delete"):
        clear_goal(session_id)
        return "🗑️ Active session goal cleared."
    else:
        # Fallback: if user types `/goal build BigMart CV`, treat everything after `/goal` as objective
        raw_obj = " ".join(parts[1:]).strip()
        if raw_obj:
            set_goal(raw_obj, session_id=session_id)
            return f"🎯 Active goal set: {raw_obj}\nJARVIS will pursue and settle this goal autonomously."
        return format_goal_display(session_id)


def _extract_call_params(call_args: tuple, call_kwargs: dict) -> tuple[dict, dict]:
    """Extract params dict and context dict across multiple calling conventions."""
    params: dict = {}
    context: dict = {}
    if len(call_args) >= 2 and isinstance(call_args[0], str) and isinstance(call_args[1], dict):
        params = call_args[1]
        if len(call_args) >= 5 and isinstance(call_args[4], dict):
            context = call_args[4]
    elif len(call_args) >= 1 and isinstance(call_args[0], dict):
        params = call_args[0]
        if len(call_args) >= 2 and isinstance(call_args[1], dict):
            context = call_args[1]
    elif "params" in call_kwargs and isinstance(call_kwargs["params"], dict):
        params = call_kwargs["params"]
    elif "args" in call_kwargs and isinstance(call_kwargs["args"], dict):
        params = call_kwargs["args"]

    if "context" in call_kwargs and isinstance(call_kwargs["context"], dict):
        context = call_kwargs["context"]
    elif "ctx" in call_kwargs and isinstance(call_kwargs["ctx"], dict):
        context = call_kwargs["ctx"]

    return params, context


def create_get_goal_tool(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Retrieve the currently registered session goal and its execution status."""
    async def execute(*call_args: Any, **call_kwargs: Any) -> Dict[str, Any]:
        params, context = _extract_call_params(call_args, call_kwargs)
        session_id = context.get("session_id") or (options or {}).get("session_id", "default_session")
        goal = get_active_goal(session_id)
        if not goal:
            return {"goal": None, "status": "none"}
        return {"goal": goal, "status": goal.get("status", "in_progress")}

    schema = {"type": "object", "properties": {}}
    return {
        "name": "get_goal",
        "id": "get_goal",
        "label": "Get Goal",
        "displaySummary": "Get the current session goal",
        "description": "Retrieve the currently registered session goal and its execution status.",
        "parameters": schema,
        "parameter_schema": schema,
        "execute": execute,
    }


def create_create_goal_tool(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Declare a concrete objective and optional token budget for this session."""
    async def execute(*call_args: Any, **call_kwargs: Any) -> Dict[str, Any]:
        params, context = _extract_call_params(call_args, call_kwargs)
        session_id = context.get("session_id") or (options or {}).get("session_id", "default_session")
        objective = params.get("objective", "")
        token_budget = params.get("token_budget")
        if not objective:
            return {"error": "objective parameter is required"}

        goal = set_goal(objective, session_id=session_id, token_budget=token_budget)
        return {"status": "ok", "created": True, "goal": goal}

    schema = {
        "type": "object",
        "properties": {
            "objective": {"type": "string", "description": "Concrete objective for this session."},
            "token_budget": {"type": "integer", "description": "Positive token budget, or omit."},
        },
        "required": ["objective"],
    }
    return {
        "name": "create_goal",
        "id": "create_goal",
        "label": "Create Goal",
        "displaySummary": "Create a session goal",
        "description": "Declare a concrete objective and optional token budget for this session.",
        "parameters": schema,
        "parameter_schema": schema,
        "execute": execute,
    }


def create_update_goal_tool(options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Update session goal status to complete or blocked with a short note."""
    async def execute(*call_args: Any, **call_kwargs: Any) -> Dict[str, Any]:
        params, context = _extract_call_params(call_args, call_kwargs)
        session_id = context.get("session_id") or (options or {}).get("session_id", "default_session")
        status = params.get("status", "complete")
        note = params.get("note")

        goal = update_goal_status(status, note=note, session_id=session_id)
        if not goal:
            return {"error": "No active session goal exists to update."}
        return {"status": "ok", "updated": True, "goal": goal}

    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["in_progress", "complete", "blocked"], "description": "New goal status."},
            "note": {"type": "string", "description": "Short status explanation or note."},
        },
        "required": ["status"],
    }
    return {
        "name": "update_goal",
        "id": "update_goal",
        "label": "Update Goal",
        "displaySummary": "Update session goal status",
        "description": "Update session goal status to complete or blocked with a short note.",
        "parameters": schema,
        "parameter_schema": schema,
        "execute": execute,
    }


__all__ = [
    "get_active_goal",
    "set_goal",
    "update_goal_status",
    "clear_goal",
    "format_goal_display",
    "handle_goal_command",
    "create_get_goal_tool",
    "create_create_goal_tool",
    "create_update_goal_tool",
]
