"""jarvis.agents.decision.observation_normalizer — Normalizes raw tool outputs into verified observations.

OpenClaw parity: Transforms tool execution outcomes into structured facts
with tangible evidence, determining whether real host effects occurred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class NormalizedObservation:
    tool_name: str
    status: str  # "success" | "failed" | "timeout" | "blocked"
    is_verified: bool
    tangible_evidence: dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""
    error_message: Optional[str] = None
    actionable_recovery_hint: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status == "success" and self.is_verified


class ObservationNormalizer:
    """Normalizes raw tool outputs and exceptions into verified evidence."""

    _ERROR_INDICATORS = (
        "error:",
        "failed:",
        "exception:",
        "access is denied",
        "permission denied",
        "cannot find",
        "not found",
        "commandnotfound",
        "invalidoperation",
        "does not exist",
    )

    @classmethod
    def normalize(
        cls,
        tool_name: str,
        args: dict[str, Any],
        raw_output: Any,
        error: Optional[Exception] = None,
    ) -> NormalizedObservation:
        out_str = str(raw_output) if raw_output is not None else ""
        lower_out = out_str.lower()

        # Handle explicit exception
        if error is not None:
            err_msg = str(error)
            return NormalizedObservation(
                tool_name=tool_name,
                status="failed",
                is_verified=False,
                raw_output=out_str,
                error_message=err_msg,
                actionable_recovery_hint=cls._infer_recovery_hint(tool_name, args, err_msg),
            )

        # Check for blocked actions
        if "blocked" in lower_out or "forbidden" in lower_out:
            return NormalizedObservation(
                tool_name=tool_name,
                status="blocked",
                is_verified=False,
                raw_output=out_str,
                error_message=out_str,
                actionable_recovery_hint="Action was blocked by safety policy or permission boundary.",
            )

        # Check for timeout
        if "timed out" in lower_out or "timeout" in lower_out:
            return NormalizedObservation(
                tool_name=tool_name,
                status="timeout",
                is_verified=False,
                raw_output=out_str,
                error_message=out_str,
                actionable_recovery_hint="Operation timed out. Retry with a larger timeout or check host responsiveness.",
            )

        # Check for error indicators in output text
        has_err = any(ind in lower_out for ind in cls._ERROR_INDICATORS)
        if has_err and "status: verified" not in lower_out:
            return NormalizedObservation(
                tool_name=tool_name,
                status="failed",
                is_verified=False,
                raw_output=out_str,
                error_message=out_str,
                actionable_recovery_hint=cls._infer_recovery_hint(tool_name, args, out_str),
            )

        # Extract tangible evidence based on tool
        evidence: dict[str, Any] = {}
        if tool_name in ("mkdir", "remove_path", "rename_path", "write", "read", "edit"):
            if "path" in args:
                evidence["path"] = str(args["path"])
            if "target" in args:
                evidence["target"] = str(args["target"])
        elif tool_name == "process":
            evidence["action"] = args.get("action", "")
            if "session_id" in args:
                evidence["target_app"] = str(args["session_id"])
        elif tool_name == "browser":
            evidence["action"] = args.get("action", "")
            if "url" in args:
                evidence["url"] = str(args["url"])
        elif tool_name == "open_path":
            evidence["target"] = str(args.get("target", ""))

        return NormalizedObservation(
            tool_name=tool_name,
            status="success",
            is_verified=True,
            tangible_evidence=evidence,
            raw_output=out_str,
        )

    @classmethod
    def _infer_recovery_hint(cls, tool_name: str, args: dict[str, Any], error_text: str) -> str:
        lower = error_text.lower()
        if (
            "access is denied" in lower
            or "access denied" in lower
            or "permission denied" in lower
            or "winerror 5" in lower
        ):
            return "Target requires elevated permissions or is a protected Windows directory."
        if "not found" in lower or "does not exist" in lower:
            return "Target path or process was not found. Verify the name/path using 'ls' or 'process(action=\"list_apps\")'."
        if "commandnotfound" in lower:
            return "Shell command or executable is not installed or not in PATH."
        if tool_name == "process" and args.get("action") == "kill":
            return "Application may already be closed or running under a different executable name."
        return "Inspect arguments and verify host state before retrying."
