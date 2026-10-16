"""jarvis_learning.evaluation.tool_gateway — Shadow Tool Gateway & Side-Effect Isolation.

Mandatory Policy:
Python monkeypatching is NOT considered a sufficient security boundary.
All side-effect isolation is strictly enforced at the Tool Gateway and OS boundary:
1. Tool Classification (INV-SHD-001):
   - READ_ONLY_PUBLIC: get_current_time, read_volume, read_window_title (Safe live access)
   - READ_ONLY_SENSITIVE: read_browser_tabs, get_application_state, clipboard (Sanitized snapshot only)
   - READ_ONLY_PRIVILEGED: read_cookies, read_credentials, read_private_keys (Strictly FORBIDDEN in shadow)
   - SIMULATABLE: focus_window, switch_tab, dry_run_calc (Simulated state return)
   - SIDE_EFFECTING: send_whatsapp_message, delete_file, write_file, execute_shell (Intercepted, NEVER executed)
   - FORBIDDEN: direct socket writes, native Win32 mutations, process injection (Hard blocked)
2. Canonical Request Envelope with Sanitized State Snapshot (INV-PRIV-001)
3. Shadow Tool Simulator providing dry-run responses without live system mutation.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Patterns identifying sensitive tokens that must NEVER enter shadow state snapshots
SENSITIVE_PATTERNS = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(r"ghp_[a-zA-Z0-9]{20,}", re.IGNORECASE),
    re.compile(
        r"(password|secret|bearer|token|cookie)[\s:=]+['\"]?([^\s'\"]+)['\"]?", re.IGNORECASE
    ),
)


class ToolSensitivityClass(enum.StrEnum):
    """Granular sensitivity and execution classification for agent tools."""

    READ_ONLY_PUBLIC = "READ_ONLY_PUBLIC"
    READ_ONLY_SENSITIVE = "READ_ONLY_SENSITIVE"
    READ_ONLY_PRIVILEGED = "READ_ONLY_PRIVILEGED"
    PUBLIC_READ_ONLY = "READ_ONLY_PUBLIC"
    SENSITIVE_READ_ONLY = "READ_ONLY_SENSITIVE"
    PRIVILEGED_READ_ONLY = "READ_ONLY_PRIVILEGED"
    SIMULATABLE = "SIMULATABLE"
    SIMULATED_STATE = "SIMULATED_STATE"
    SIDE_EFFECTING = "SIDE_EFFECTING"
    FORBIDDEN = "FORBIDDEN"
    SANITIZED_SNAPSHOT = "SANITIZED_SNAPSHOT"
    REDACTED = "REDACTED"
    UNAVAILABLE = "UNAVAILABLE"


SimulatedToolResult = dict[str, Any]


# Canonical registry mapping known tools to their sensitivity class
TOOL_SENSITIVITY_REGISTRY: dict[str, ToolSensitivityClass] = {
    "get_current_time": ToolSensitivityClass.READ_ONLY_PUBLIC,
    "read_volume": ToolSensitivityClass.READ_ONLY_PUBLIC,
    "read_window_title": ToolSensitivityClass.READ_ONLY_PUBLIC,
    "read_browser_tabs": ToolSensitivityClass.READ_ONLY_SENSITIVE,
    "get_application_state": ToolSensitivityClass.READ_ONLY_SENSITIVE,
    "read_clipboard": ToolSensitivityClass.READ_ONLY_SENSITIVE,
    "read_browser_cookies": ToolSensitivityClass.READ_ONLY_PRIVILEGED,
    "read_credentials": ToolSensitivityClass.READ_ONLY_PRIVILEGED,
    "read_private_keys": ToolSensitivityClass.READ_ONLY_PRIVILEGED,
    "focus_window": ToolSensitivityClass.SIMULATABLE,
    "switch_tab": ToolSensitivityClass.SIMULATABLE,
    "set_volume": ToolSensitivityClass.SIMULATABLE,
    "send_whatsapp_message": ToolSensitivityClass.SIDE_EFFECTING,
    "send_email": ToolSensitivityClass.SIDE_EFFECTING,
    "delete_file": ToolSensitivityClass.SIDE_EFFECTING,
    "write_file": ToolSensitivityClass.SIDE_EFFECTING,
    "execute_shell": ToolSensitivityClass.SIDE_EFFECTING,
    "browser_checkout": ToolSensitivityClass.SIDE_EFFECTING,
    "raw_socket_send": ToolSensitivityClass.FORBIDDEN,
    "inject_process": ToolSensitivityClass.FORBIDDEN,
}


@dataclass(frozen=True, slots=True)
class CanonicalRequestEnvelope:
    """Immutable normalized request envelope dispatched identically to active and shadow models."""

    request_id: str
    conversation_id: str
    turn_id: str
    timestamp_ns: int
    normalized_user_input: str
    conversation_context_hash: str
    available_tools_snapshot: tuple[str, ...]
    active_model_id: str
    shadow_model_id: str
    policy_context_hash: str
    environment_context: dict[str, Any] = field(default_factory=dict)
    sanitized_state_snapshot: dict[str, Any] = field(default_factory=dict)

    def compute_digest(self) -> str:
        """Compute deterministic RFC-style SHA-256 digest of request content."""
        payload = {
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "input": self.normalized_user_input,
            "tools": sorted(self.available_tools_snapshot),
            "context_hash": self.conversation_context_hash,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class StateSnapshotSanitizer:
    """Sanitizes runtime state before exposure to shadow models (INV-PRIV-001)."""

    @classmethod
    def sanitize(cls, raw_state: Mapping[str, Any]) -> dict[str, Any]:
        """Scrub secrets, API keys, cookies, and tokens from observation dictionaries."""
        clean: dict[str, Any] = {}
        for k, v in raw_state.items():
            lower_k = k.lower()
            if any(s in lower_k for s in ("cookie", "token", "secret", "key", "password", "auth")):
                clean[k] = "[REDACTED_SECRET]"
                continue

            if isinstance(v, str):
                cleaned_str = v
                for pat in SENSITIVE_PATTERNS:
                    cleaned_str = pat.sub("[REDACTED_CREDENTIAL]", cleaned_str)
                clean[k] = cleaned_str
            elif isinstance(v, dict):
                clean[k] = cls.sanitize(v)
            elif isinstance(v, list):
                clean[k] = [cls.sanitize(item) if isinstance(item, dict) else item for item in v]
            else:
                clean[k] = v
        return clean

    sanitize_state = sanitize


class ShadowToolExecutionError(Exception):
    """Raised when shadow model attempts forbidden or unhandled tool call."""


class ShadowToolSimulator:
    """Interception gateway enforcing INV-SHD-001 side-effect isolation."""

    def __init__(self, dry_run_mode: bool = True) -> None:
        self.dry_run_mode = dry_run_mode
        self.intercepted_calls: list[dict[str, Any]] = []

    def classify_tool(self, tool_name: str) -> ToolSensitivityClass:
        """Query sensitivity tier of tool."""
        return TOOL_SENSITIVITY_REGISTRY.get(tool_name, ToolSensitivityClass.SIDE_EFFECTING)

    def dispatch_shadow_call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        sanitized_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Intercept shadow tool intent; simulate outcome without real-world mutation."""
        classification = self.classify_tool(tool_name)
        call_record = {
            "tool_name": tool_name,
            "classification": classification.value,
            "arguments": dict(arguments),
            "timestamp": time.time(),
        }
        self.intercepted_calls.append(call_record)

        if classification == ToolSensitivityClass.FORBIDDEN:
            logger.error("Shadow model attempted FORBIDDEN tool call: %s", tool_name)
            raise ShadowToolExecutionError(
                f"Tool '{tool_name}' is strictly FORBIDDEN in shadow mode (INV-SHD-001)"
            )

        if classification == ToolSensitivityClass.READ_ONLY_PRIVILEGED:
            logger.warning("Shadow model attempted READ_ONLY_PRIVILEGED access: %s", tool_name)
            return {
                "status": "access_denied",
                "message": "Privileged credentials unavailable in shadow mode (INV-PRIV-001)",
                "data": None,
            }

        if classification == ToolSensitivityClass.READ_ONLY_PUBLIC:
            # Controlled simulated or passive return
            if tool_name == "get_current_time":
                return {"time": "2026-09-17T23:00:00Z", "timestamp": 1789665000}
            if tool_name == "read_volume":
                return {"volume": 50, "muted": False}
            if tool_name == "read_window_title":
                return {"active_window": "JARVIS Dashboard"}
            return {"status": "ok", "read_only": True}

        if classification == ToolSensitivityClass.READ_ONLY_SENSITIVE:
            # Return sanitized snapshot only; never query live browser/cookies
            state = sanitized_state or {}
            if tool_name == "read_browser_tabs":
                return {
                    "tabs": state.get(
                        "sanitized_tabs",
                        [{"id": 1, "title": "Documentation", "url": "https://docs.jarvis.local"}],
                    )
                }
            if tool_name == "get_application_state":
                return {"state": state.get("application_state", "running")}
            return {"status": "sanitized_snapshot", "data": {}}

        if classification == ToolSensitivityClass.SIMULATABLE:
            # Dry-run simulated execution without mutating real desktop/browser state
            logger.info("Simulating non-destructive tool call in shadow: %s", tool_name)
            return {
                "status": "simulated_success",
                "simulated": True,
                "tool_name": tool_name,
                "result": "action_simulated_successfully",
            }

        if classification == ToolSensitivityClass.SIDE_EFFECTING:
            # Strictly intercepted; NEVER executed on OS or network
            logger.info("INTERCEPTED side-effecting shadow call: %s (Dry-run only)", tool_name)
            return {
                "status": "dry_run_intercepted",
                "executed": False,
                "real_world_mutation": False,
                "tool_name": tool_name,
                "message": "Tool intent captured for trace evaluation; real action suppressed (INV-SHD-001)",
            }

        return {"status": "unknown_classification"}
