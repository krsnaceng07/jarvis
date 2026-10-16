"""jarvis.agents.sessions.tools.secrets_tool — Safe credential management tool.

OpenClaw parity: mirrors credential isolation policies.
Ensures secret values are NEVER exposed in agent transcripts or tool outputs.
Actions:
  - list: list configured credential names and pending requests (NEVER values)
  - request: request a credential by name with a justification (creates pending request)
  - delete: remove a stored secret or pending request by name
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Optional
import uuid

from ..extensions.types import AgentToolResult, ToolDefinition

_SECRETS_LOCK = threading.Lock()


def _get_credentials_dir() -> Path:
    """Return ~/.jarvis/credentials directory resolved dynamically."""
    return Path.home() / ".jarvis" / "credentials"


def _get_pending_requests_path() -> Path:
    """Return ~/.jarvis/credentials/pending_requests.json resolved dynamically."""
    return _get_credentials_dir() / "pending_requests.json"


def _get_user_config_path() -> Path:
    """Return ~/.jarvis/config.json resolved dynamically."""
    return Path.home() / ".jarvis" / "config.json"


@dataclass(frozen=True, slots=True)
class SecretEntry:
    """Descriptor for a configured secret without exposing its value."""

    name: str
    source: str
    status: str = "configured"


@dataclass(frozen=True, slots=True)
class SecretRequestEntry:
    """Record of a pending credential request from an agent."""

    id: str
    name: str
    reason: str
    created_at: str
    status: str = "pending"


def _ensure_credentials_dir() -> None:
    """Ensure ~/.jarvis/credentials directory exists with private permissions."""
    _get_credentials_dir().mkdir(parents=True, exist_ok=True)


def _load_pending_requests() -> list[dict[str, Any]]:
    """Load list of pending credential requests."""
    pending_path = _get_pending_requests_path()
    if not pending_path.exists():
        return []
    try:
        data = json.loads(pending_path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _save_pending_requests(requests: list[dict[str, Any]]) -> None:
    """Atomically save pending credential requests."""
    _ensure_credentials_dir()
    pending_path = _get_pending_requests_path()
    tmp_path = pending_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(requests, indent=2), encoding="utf-8")
    tmp_path.replace(pending_path)


def _get_workspace_api_keys_path(cwd: str) -> Path | None:
    """Resolve config/api_keys.json in workspace root if it exists."""
    candidates = [
        Path(cwd) / "config" / "api_keys.json",
        Path(os.getcwd()) / "config" / "api_keys.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _discover_secret_names(cwd: str) -> list[SecretEntry]:
    """Discover names of all configured secrets without reading their values."""
    names_map: dict[str, str] = {}

    # 1. Credentials files in ~/.jarvis/credentials/
    creds_dir = _get_credentials_dir()
    if creds_dir.exists():
        try:
            for item in creds_dir.iterdir():
                if item.is_file() and item.name != "pending_requests.json":
                    stem = item.stem.upper()
                    if stem not in names_map:
                        names_map[stem] = "credentials_dir"
        except Exception:
            pass

    # 2. Workspace config/api_keys.json
    ws_keys_file = _get_workspace_api_keys_path(cwd)
    if ws_keys_file and ws_keys_file.exists():
        try:
            data = json.loads(ws_keys_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if v and str(v).strip():
                        names_map[k.upper()] = "workspace_api_keys"
        except Exception:
            pass

    # 3. User ~/.jarvis/config.json
    user_config_path = _get_user_config_path()
    if user_config_path.exists():
        try:
            data = json.loads(user_config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for k, v in data.items():
                    if ("key" in k.lower() or "secret" in k.lower() or "token" in k.lower()) and v:
                        names_map[k.upper()] = "user_config"
        except Exception:
            pass

    # 4. Standard environment variables
    secret_pat = re.compile(r"_(?:KEY|TOKEN|SECRET|AUTH|PASSWORD)$", re.IGNORECASE)
    for env_k, env_v in os.environ.items():
        if env_v and secret_pat.search(env_k):
            k_upper = env_k.upper()
            if k_upper not in names_map:
                names_map[k_upper] = "environment"

    return [
        SecretEntry(name=k, source=src, status="configured") for k, src in sorted(names_map.items())
    ]


def create_secrets_tool_definition(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Build the ToolDefinition for the secrets tool."""
    _ = options

    async def _execute(
        tool_call_id: str,
        params: dict,
        signal: object = None,
        on_update: object = None,
        ctx: object = None,
    ) -> AgentToolResult:
        _ = (tool_call_id, on_update, ctx)
        if signal is not None and getattr(signal, "is_set", lambda: False)():
            raise RuntimeError("Operation aborted")

        action = str(params.get("action", "")).strip().lower()
        if not action:
            raise ValueError("action is required (must be one of: 'request', 'list', 'delete').")

        workspace_root = cwd or os.getcwd()

        # ── ACTION: LIST ──────────────────────────────────────────────
        if action == "list":
            with _SECRETS_LOCK:
                configured_secrets = _discover_secret_names(workspace_root)
                raw_pending = _load_pending_requests()

            pending_entries = [
                SecretRequestEntry(
                    id=p.get("id", ""),
                    name=p.get("name", "").upper(),
                    reason=p.get("reason", ""),
                    created_at=p.get("created_at", ""),
                    status=p.get("status", "pending"),
                )
                for p in raw_pending
                if p.get("status") == "pending"
            ]

            lines: list[str] = [f"Stored Credentials ({len(configured_secrets)}):"]
            if configured_secrets:
                for sec in configured_secrets:
                    lines.append(f"• {sec.name} (source: {sec.source})")
            else:
                lines.append("(None configured)")

            lines.append(f"\nPending Credential Requests ({len(pending_entries)}):")
            if pending_entries:
                for req in pending_entries:
                    lines.append(
                        f"• {req.name} — Reason: '{req.reason}' (requested {req.created_at})"
                    )
            else:
                lines.append("(No pending requests)")

            return {
                "content": [{"type": "text", "text": "\n".join(lines)}],
                "details": {
                    "action": "list",
                    "configured_count": len(configured_secrets),
                    "pending_count": len(pending_entries),
                    "configured": [
                        {"name": s.name, "source": s.source} for s in configured_secrets
                    ],
                    "pending": [
                        {"name": p.name, "reason": p.reason, "id": p.id} for p in pending_entries
                    ],
                },
            }

        # ── ACTION: REQUEST ───────────────────────────────────────────
        elif action == "request":
            raw_name = str(params.get("secret_name") or params.get("name", "")).strip()
            if not raw_name:
                raise ValueError("name is required for 'request' action.")
            norm_name = raw_name.upper().replace("-", "_")

            reason = str(params.get("reason", "")).strip()
            if not reason:
                raise ValueError("reason is required when requesting a credential.")

            req_id = f"req_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:4]}"
            now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with _SECRETS_LOCK:
                pending_list = _load_pending_requests()
                # Check if identical request is already pending
                existing = [
                    p
                    for p in pending_list
                    if p.get("name", "").upper() == norm_name and p.get("status") == "pending"
                ]
                if existing:
                    existing[0]["reason"] = reason
                    existing[0]["updated_at"] = now_iso
                    req_id = existing[0].get("id", req_id)
                else:
                    pending_list.append(
                        {
                            "id": req_id,
                            "name": norm_name,
                            "reason": reason,
                            "created_at": now_iso,
                            "status": "pending",
                        }
                    )
                _save_pending_requests(pending_list)

            msg = (
                f"Credential request registered successfully:\n"
                f"• Secret Name: {norm_name}\n"
                f"• Reason: {reason}\n"
                f"• Request ID: {req_id}\n"
                f"• Status: Pending user entry\n\n"
                "The user will be prompted to provide this credential securely via the HUD settings or CLI."
            )
            return {
                "content": [{"type": "text", "text": msg}],
                "details": {
                    "action": "request",
                    "id": req_id,
                    "name": norm_name,
                    "reason": reason,
                    "status": "pending",
                },
            }

        # ── ACTION: DELETE ────────────────────────────────────────────
        elif action == "delete":
            raw_name = str(params.get("secret_name") or params.get("name", "")).strip()
            if not raw_name:
                raise ValueError("name is required for 'delete' action.")
            norm_name = raw_name.upper().replace("-", "_")

            deleted_locations: list[str] = []

            with _SECRETS_LOCK:
                # 1. Delete matching files in ~/.jarvis/credentials/
                creds_dir = _get_credentials_dir()
                if creds_dir.exists():
                    for ext in (".txt", ".key", ".json", ""):
                        candidate = creds_dir / f"{norm_name.lower()}{ext}"
                        if candidate.exists() and candidate.is_file():
                            try:
                                candidate.unlink()
                                deleted_locations.append("credentials_dir")
                            except Exception:
                                pass

                # 2. Remove key from workspace config/api_keys.json if present
                ws_keys_file = _get_workspace_api_keys_path(workspace_root)
                if ws_keys_file and ws_keys_file.exists():
                    try:
                        data = json.loads(ws_keys_file.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            keys_to_del = [k for k in data if k.upper() == norm_name]
                            if keys_to_del:
                                for k in keys_to_del:
                                    del data[k]
                                ws_keys_file.write_text(
                                    json.dumps(data, indent=2), encoding="utf-8"
                                )
                                deleted_locations.append("workspace_api_keys")
                    except Exception:
                        pass

                # 3. Cancel pending request if present
                pending_list = _load_pending_requests()
                remaining = [p for p in pending_list if p.get("name", "").upper() != norm_name]
                if len(remaining) != len(pending_list):
                    _save_pending_requests(remaining)
                    deleted_locations.append("pending_requests")

            # In testing or production, also unset from os.environ if present
            if norm_name in os.environ:
                del os.environ[norm_name]
                deleted_locations.append("environment")

            if deleted_locations:
                msg = f"Successfully removed credential '{norm_name}' from: {', '.join(deleted_locations)}."
                return {
                    "content": [{"type": "text", "text": msg}],
                    "details": {
                        "action": "delete",
                        "name": norm_name,
                        "deleted": True,
                        "status": "deleted",
                        "locations": deleted_locations,
                    },
                }
            else:
                msg = f"No stored credential or pending request found with name '{norm_name}'."
                return {
                    "content": [{"type": "text", "text": msg}],
                    "details": {
                        "action": "delete",
                        "name": norm_name,
                        "deleted": False,
                        "status": "deleted",
                    },
                }

        else:
            raise ValueError(
                f"Unknown action '{action}'. Supported actions are: 'request', 'list', 'delete'."
            )

    return {
        "name": "secrets",
        "description": (
            "Safe credential management tool. "
            "Inspect, request, and manage API keys and credentials securely. "
            "Actions: "
            "1. 'request': Request an API key or credential by name with a reason (creates a pending secret request). "
            "2. 'list': List stored secret names (never values). "
            "3. 'delete': Remove a secret by name."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action: 'request', 'list', or 'delete'.",
                    "enum": ["request", "list", "delete"],
                },
                "name": {
                    "type": "STRING",
                    "description": "Name of the credential/secret (e.g. 'OPENAI_API_KEY'). Required for 'request' and 'delete'.",
                },
                "reason": {
                    "type": "STRING",
                    "description": "Justification for requesting this secret. Required for 'request'.",
                },
            },
            "required": ["action"],
        },
        "execute": _execute,
    }


def create_secrets_tool(
    cwd: str = "",
    options: Optional[dict] = None,
) -> ToolDefinition:
    """Convenience alias matching create_write_tool / create_open_path_tool naming."""
    return create_secrets_tool_definition(cwd=cwd, options=options)


__all__ = [
    "SecretEntry",
    "SecretRequestEntry",
    "create_secrets_tool",
    "create_secrets_tool_definition",
]
