"""jarvis.agents.verification.execution_verifier — Real-world outcome verification.

Guarantees the Anti-Hallucination & Truthfulness rule:
  MODEL = proposes
  TOOL = executes
  OS = reports reality
  VERIFIER = confirms reality
  STATE = records reality
  MODEL = explains reality

Never treat tool requested as tool succeeded.
"""

from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..sessions.tools.path_utils import discover_system_drives, is_drive_available


@dataclass(slots=True)
class VerificationOutcome:
    """Standardized machine-readable verification outcome."""

    status: str  # "verified" | "failed" | "unknown"
    verified: bool  # True only if verified and successful
    tool_name: str
    target_resource: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_success(self) -> bool:
        return self.verified and self.status == "verified"


class ExecutionVerifier:
    """Verifies actual operating system outcomes after tool execution."""

    @staticmethod
    def verify_filesystem_write(
        path: str | Path,
        expected_bytes: Optional[int] = None,
    ) -> VerificationOutcome:
        """Verify that a file was actually created/written to disk with expected size."""
        try:
            target = Path(path).resolve()
            if not target.exists():
                # Check if parent drive exists
                if sys.platform == "win32" and not is_drive_available(str(target)):
                    available = discover_system_drives()
                    return VerificationOutcome(
                        status="failed",
                        verified=False,
                        tool_name="write",
                        target_resource=str(target),
                        error=f"Target drive does not exist. Available drives: {available}",
                    )
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="write",
                    target_resource=str(target),
                    error=f"Verification failed: File '{target}' does not exist on disk after write.",
                )

            if not target.is_file():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="write",
                    target_resource=str(target),
                    error=f"Verification failed: Target '{target}' is not a regular file.",
                )

            file_size = target.stat().st_size
            mtime = target.stat().st_mtime

            if expected_bytes is not None and file_size < expected_bytes:
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="write",
                    target_resource=str(target),
                    details={"size_on_disk": file_size, "expected_bytes": expected_bytes},
                    error=(
                        f"Verification failed: File size ({file_size} bytes) "
                        f"is smaller than expected ({expected_bytes} bytes)."
                    ),
                )

            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="write",
                target_resource=str(target),
                details={
                    "path": str(target),
                    "size_bytes": file_size,
                    "mtime": mtime,
                },
            )
        except Exception as e:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="write",
                target_resource=str(path),
                error=f"Verification encountered exception: {e}",
            )

    @staticmethod
    def verify_filesystem_edit(
        path: str | Path,
        expected_content_fragments: Optional[list[str]] = None,
    ) -> VerificationOutcome:
        """Verify that an edit was applied to disk and new content exists."""
        try:
            target = Path(path).resolve()
            if not target.exists() or not target.is_file():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="edit",
                    target_resource=str(target),
                    error=f"Verification failed: File '{target}' does not exist after edit.",
                )

            if expected_content_fragments:
                content = target.read_text(encoding="utf-8", errors="replace")
                missing = [frag for frag in expected_content_fragments if frag not in content]
                if missing:
                    return VerificationOutcome(
                        status="failed",
                        verified=False,
                        tool_name="edit",
                        target_resource=str(target),
                        details={"missing_fragments": missing},
                        error="Verification failed: Expected edits not found in file content on disk.",
                    )

            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="edit",
                target_resource=str(target),
                details={"size_bytes": target.stat().st_size, "mtime": target.stat().st_mtime},
            )
        except Exception as e:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="edit",
                target_resource=str(path),
                error=f"Verification exception: {e}",
            )

    @staticmethod
    def verify_filesystem_path(
        path: str | Path,
        must_be_dir: bool = False,
    ) -> VerificationOutcome:
        """Verify if a path or drive exists and is accessible."""
        try:
            target = Path(path).resolve()
            # Windows drive check
            if sys.platform == "win32" and not is_drive_available(str(target)):
                available = discover_system_drives()
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="path_check",
                    target_resource=str(target),
                    error=f"Drive not found: '{target}'. Available drives on this PC: {available}.",
                )

            if not target.exists():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="path_check",
                    target_resource=str(target),
                    error=f"Path not found: '{target}'.",
                )

            if must_be_dir and not target.is_dir():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="path_check",
                    target_resource=str(target),
                    error=f"Path is not a directory: '{target}'.",
                )

            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="path_check",
                target_resource=str(target),
                details={
                    "is_dir": target.is_dir(),
                    "size": target.stat().st_size if target.is_file() else None,
                },
            )
        except Exception as e:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="path_check",
                target_resource=str(path),
                error=f"Verification exception: {e}",
            )

    @staticmethod
    def verify_process_execution(
        exit_code: int,
        stdout: str = "",
        stderr: str = "",
    ) -> VerificationOutcome:
        """Verify process execution outcome based on exit code and error stream."""
        if exit_code == 0:
            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="exec",
                details={"exit_code": 0, "stdout_length": len(stdout)},
            )

        return VerificationOutcome(
            status="failed",
            verified=False,
            tool_name="exec",
            details={"exit_code": exit_code, "stderr": stderr[:500]},
            error=f"Process exited with non-zero code {exit_code}: {stderr.strip() or stdout.strip()}",
        )

    @staticmethod
    def verify_filesystem_removal(
        path: str | Path,
    ) -> VerificationOutcome:
        """Verify that a path was actually deleted from disk."""
        try:
            target = Path(path).resolve()
            if target.exists():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="remove_path",
                    target_resource=str(target),
                    error=f"Verification failed: Path '{target}' still exists on disk after removal.",
                )

            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="remove_path",
                target_resource=str(target),
                details={"path": str(target), "removed": True},
            )
        except Exception as e:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="remove_path",
                target_resource=str(path),
                error=f"Verification exception: {e}",
            )

    @staticmethod
    def verify_filesystem_rename(
        old_path: str | Path,
        new_path: str | Path,
    ) -> VerificationOutcome:
        """Verify that a path was renamed/moved: old path must not exist, new path must exist."""
        try:
            old_target = Path(old_path).resolve()
            new_target = Path(new_path).resolve()

            if old_target.exists():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="rename_path",
                    target_resource=f"{old_target} -> {new_target}",
                    error=f"Verification failed: Source path '{old_target}' still exists on disk after rename.",
                )

            if not new_target.exists():
                return VerificationOutcome(
                    status="failed",
                    verified=False,
                    tool_name="rename_path",
                    target_resource=f"{old_target} -> {new_target}",
                    error=f"Verification failed: Destination path '{new_target}' does not exist on disk after rename.",
                )

            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="rename_path",
                target_resource=f"{old_target} -> {new_target}",
                details={
                    "old_path": str(old_target),
                    "new_path": str(new_target),
                    "renamed": True,
                },
            )
        except Exception as e:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="rename_path",
                target_resource=f"{old_path} -> {new_path}",
                error=f"Verification exception: {e}",
            )

    @staticmethod
    def verify_audio_action(
        action: str,
        expected_volume: Optional[int] = None,
        expected_mute: Optional[bool] = None,
    ) -> VerificationOutcome:
        """Verify Windows Core Audio state via direct physical readback."""
        try:
            from src.system.audio_controller import AudioController
            controller = AudioController.get_instance()
            state = controller.get_volume()

            if expected_volume is not None:
                curr_vol = state.get("volume_percent", 0)
                # Tolerant to 1% difference due to float scalar quantization
                if abs(curr_vol - expected_volume) > 1:
                    return VerificationOutcome(
                        status="failed",
                        verified=False,
                        tool_name="audio",
                        target_resource=f"volume:{expected_volume}%",
                        error=(
                            f"Audio verification failed: Hardware volume is {curr_vol}%, "
                            f"expected {expected_volume}%."
                        ),
                        details=state,
                    )

            if expected_mute is not None:
                curr_mute = state.get("muted", False)
                if curr_mute != expected_mute:
                    return VerificationOutcome(
                        status="failed",
                        verified=False,
                        tool_name="audio",
                        target_resource=f"mute:{expected_mute}",
                        error=(
                            f"Audio verification failed: Hardware mute is {curr_mute}, "
                            f"expected {expected_mute}."
                        ),
                        details=state,
                    )

            return VerificationOutcome(
                status="verified",
                verified=True,
                tool_name="audio",
                target_resource=f"action:{action}",
                details=state,
            )
        except Exception as exc:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="audio",
                error=f"Audio verification exception: {exc}",
            )

    @staticmethod
    def verify_system_info(action: str, output_text: str = "") -> VerificationOutcome:
        """Verify ground-truth system telemetry output."""
        if not output_text or "failed" in output_text.lower() or "error" in output_text.lower():
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="system_info",
                target_resource=action,
                error=f"System info reported error: {output_text}",
            )
        return VerificationOutcome(
            status="verified",
            verified=True,
            tool_name="system_info",
            target_resource=action,
            details={"output_length": len(output_text)},
        )

    @staticmethod
    def verify_web_search(query: str, output_text: str = "") -> VerificationOutcome:
        """Verify web search returned valid structured text or clean zero-result message."""
        if not output_text or "failed" in output_text.lower() or "error" in output_text.lower():
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="web_search",
                target_resource=query,
                error=f"Web search failed: {output_text}",
            )
        return VerificationOutcome(
            status="verified",
            verified=True,
            tool_name="web_search",
            target_resource=query,
            details={"query": query, "output_length": len(output_text)},
        )

    @staticmethod
    def verify_desktop_action(
        action: str,
        target_app: str = "",
        output_text: str = "",
    ) -> VerificationOutcome:
        """Verify desktop automation action outcome against returned execution state."""
        out_l = output_text.lower()
        if "confirmation required" in out_l:
            return VerificationOutcome(
                status="pending",
                verified=False,
                tool_name="desktop",
                target_resource=f"{target_app}:{action}",
                error=output_text,
            )
        is_err = (
            "failed" in out_l
            or "error" in out_l
            or "could not" in out_l
            or "not found" in out_l
            or "traceback" in out_l
            or '"ok": false' in out_l
        )
        if is_err:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name="desktop",
                target_resource=f"{target_app}:{action}",
                error=output_text,
            )
        return VerificationOutcome(
            status="verified",
            verified=True,
            tool_name="desktop",
            target_resource=f"{target_app}:{action}",
            details={"action": action, "target_app": target_app, "output_length": len(output_text)},
        )

    @staticmethod
    def verify_messaging_action(
        platform: str,
        recipient: str = "",
        output_text: str = "",
    ) -> VerificationOutcome:
        """Verify messaging action (e.g. WhatsApp, Discord, Slack) succeeded."""
        out_l = output_text.lower()
        is_err = (
            "failed" in out_l
            or "error" in out_l
            or "could not" in out_l
            or "not found" in out_l
            or "traceback" in out_l
            or "exception" in out_l
        )
        if is_err and not ("task fulfilled" in out_l or "action completed" in out_l or "success" in out_l):
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name=platform,
                target_resource=recipient,
                error=output_text,
            )
        return VerificationOutcome(
            status="verified",
            verified=True,
            tool_name=platform,
            target_resource=recipient,
            details={"platform": platform, "recipient": recipient},
        )

    @staticmethod
    def verify_subagent_action(
        action: str,
        target_resource: str = "",
        output_text: str = "",
    ) -> VerificationOutcome:
        """Verify subagent spawn or cancellation action."""
        out_l = output_text.lower()
        is_err = (
            "error:" in out_l
            or "failed" in out_l
            or "exception" in out_l
            or "traceback" in out_l
        )
        if is_err:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name=action,
                target_resource=target_resource,
                error=output_text,
            )
        return VerificationOutcome(
            status="verified",
            verified=True,
            tool_name=action,
            target_resource=target_resource,
            details={"output_length": len(output_text)},
        )

    @staticmethod
    def verify_generic_tool(
        tool_name: str,
        output_text: str = "",
        target_resource: str = "",
    ) -> VerificationOutcome:
        """Verify generic tool output does not report error or crash."""
        out_l = output_text.lower()
        is_err = (
            out_l.startswith("error:")
            or out_l.startswith("failed:")
            or "traceback (most recent call last)" in out_l
            or '"ok": false' in out_l
            or '"error":' in out_l
        )
        if is_err:
            return VerificationOutcome(
                status="failed",
                verified=False,
                tool_name=tool_name,
                target_resource=target_resource,
                error=output_text,
            )
        return VerificationOutcome(
            status="verified",
            verified=True,
            tool_name=tool_name,
            target_resource=target_resource,
            details={"output_length": len(output_text)},
        )

