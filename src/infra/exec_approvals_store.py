"""src.infra.exec_approvals_store - SQLite backed exec approvals storage.

OpenClaw parity: mirrors ``openclaw-main/src/infra/exec-approvals-store.ts``
"""

import json
import sqlite3
import time
from pathlib import Path

from src.infra.exec_approvals_types import (
    ExecApprovalsFile,
    ExecApprovalsSnapshot,
)

EXEC_APPROVALS_CONFIG_KEY = "exec_approvals_config"


def _get_db_path() -> Path:
    return Path.home() / ".jarvis" / "state" / "jarvis.sqlite"


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS exec_approvals_config (
            config_key TEXT NOT NULL PRIMARY KEY,
            raw_json TEXT NOT NULL,
            socket_path TEXT,
            has_socket_token INTEGER NOT NULL,
            default_security TEXT,
            default_ask TEXT,
            default_ask_fallback TEXT,
            auto_allow_skills INTEGER,
            agent_count INTEGER NOT NULL,
            allowlist_count INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )


def read_exec_approvals_snapshot() -> ExecApprovalsSnapshot:
    db_path = _get_db_path()
    if not db_path.exists():
        # Return an empty default if the DB doesn't exist yet
        return {
            "path": str(db_path) + "#exec_approvals_config",
            "exists": False,
            "raw": None,
            "file": {"version": 1},
            "hash": "",
        }

    try:
        with sqlite3.connect(str(db_path)) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                "SELECT raw_json FROM exec_approvals_config WHERE config_key = ?",
                (EXEC_APPROVALS_CONFIG_KEY,),
            )
            row = cursor.fetchone()
            if not row:
                return {
                    "path": str(db_path) + "#exec_approvals_config",
                    "exists": False,
                    "raw": None,
                    "file": {"version": 1},
                    "hash": "",
                }
            
            raw_json = row[0]
            try:
                file_data: ExecApprovalsFile = json.loads(raw_json)
            except json.JSONDecodeError:
                file_data = {"version": 1}

            return {
                "path": str(db_path) + "#exec_approvals_config",
                "exists": True,
                "raw": raw_json,
                "file": file_data,
                "hash": str(hash(raw_json)),
            }
    except sqlite3.Error:
        return {
            "path": str(db_path) + "#exec_approvals_config",
            "exists": False,
            "raw": None,
            "file": {"version": 1},
            "hash": "",
        }


def write_exec_approvals_snapshot(file_data: ExecApprovalsFile) -> None:
    db_path = _get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    raw_json = json.dumps(file_data, indent=2)
    socket_path = file_data.get("socket", {}).get("path")
    has_socket_token = 1 if file_data.get("socket", {}).get("token") else 0
    defaults = file_data.get("defaults", {})
    default_security = defaults.get("security")
    default_ask = defaults.get("ask")
    default_ask_fallback = defaults.get("askFallback")
    auto_allow_skills = 1 if defaults.get("autoAllowSkills") else 0
    agents = file_data.get("agents", {})
    agent_count = len(agents)
    allowlist_count = sum(len(a.get("allowlist", [])) for a in agents.values())
    updated_at = int(time.time() * 1000)

    with sqlite3.connect(str(db_path)) as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO exec_approvals_config (
                config_key, raw_json, socket_path, has_socket_token,
                default_security, default_ask, default_ask_fallback,
                auto_allow_skills, agent_count, allowlist_count, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(config_key) DO UPDATE SET
                raw_json = excluded.raw_json,
                socket_path = excluded.socket_path,
                has_socket_token = excluded.has_socket_token,
                default_security = excluded.default_security,
                default_ask = excluded.default_ask,
                default_ask_fallback = excluded.default_ask_fallback,
                auto_allow_skills = excluded.auto_allow_skills,
                agent_count = excluded.agent_count,
                allowlist_count = excluded.allowlist_count,
                updated_at = excluded.updated_at
            """,
            (
                EXEC_APPROVALS_CONFIG_KEY,
                raw_json,
                socket_path,
                has_socket_token,
                default_security,
                default_ask,
                default_ask_fallback,
                auto_allow_skills,
                agent_count,
                allowlist_count,
                updated_at,
            )
        )
