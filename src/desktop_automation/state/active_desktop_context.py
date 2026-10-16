"""jarvis.desktop_automation.state.active_desktop_context — Live active desktop context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(slots=True)
class ActiveDesktopContext:
    active_application: Optional[str] = None
    active_window_title: Optional[str] = None
    active_hwnd: Optional[int] = None
    active_pid: Optional[int] = None
    focused_control: Optional[str] = None
    current_task: Optional[str] = None
    workflow_stage: Optional[str] = None
    active_recipient: Optional[str] = None
    active_document: Optional[str] = None
    pending_message: Optional[str] = None
    last_verified_action: Optional[str] = None
    next_expected_action: Optional[str] = None
    can_continue: bool = True
    completed_steps: list[dict[str, Any]] = field(default_factory=list)
    last_action_timestamp: float = 0.0
    user_reported_failure: bool = False
    needs_remedy_for: Optional[str] = None
    task_parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def reset(self) -> None:
        """Reset all transient context state to defaults."""
        self.active_application = None
        self.active_window_title = None
        self.active_pid = None
        self.active_hwnd = None
        self.current_task = None
        self.workflow_stage = "idle"
        self.active_document = None
        self.active_recipient = None
        self.pending_message = None
        self.last_verified_action = None
        self.next_expected_action = None
        self.can_continue = True
        self.completed_steps.clear()
        self.last_action_timestamp = 0.0
        self.user_reported_failure = False
        self.needs_remedy_for = None
        self.task_parameters.clear()

    def record_step(
        self, name: str, status: str = "success", details: Optional[Dict[str, Any]] = None
    ) -> None:
        self.completed_steps.append({
            "name": name,
            "status": status,
            "details": details or {},
        })
        if len(self.completed_steps) > 20:
            self.completed_steps = self.completed_steps[-20:]
        self.last_verified_action = f"{name} ({status})"

    def format_runtime_state_trailer(self) -> str:
        """Format an OpenClaw-parity runtime state block for injection into tool responses."""
        lines = ["[OPENCLAW RUNTIME STATE]"]
        app = self.active_application if self.active_application else "Desktop"
        win = f" (Window: '{self.active_window_title}')" if self.active_window_title else ""
        lines.append(f"- Active App: {app}{win}")
        if self.current_task:
            lines.append(f"- Task: {self.current_task}")
        lines.append(f"- Stage: {self.workflow_stage or 'idle'}")
        if self.active_recipient:
            lines.append(f"- Recipient: {self.active_recipient}")
        if self.last_verified_action:
            lines.append(f"- Last Action: {self.last_verified_action}")
        if self.completed_steps:
            lines.append("- Completed Steps:")
            for s in self.completed_steps[-3:]:
                step_name = s.get("name", "action")
                status = s.get("status", "done")
                lines.append(f"  • {step_name} [{status}]")
        if self.user_reported_failure:
            remedy = self.needs_remedy_for or "previous action"
            lines.append(f"- ⚠️ User reported failure/not visible for: '{remedy}'. Re-check physical window and retry or bring to front.")
        lines.append("[END RUNTIME STATE]")
        return "\n".join(lines)

    def format_context_prompt(self) -> str:
        lines = ["[ACTIVE DESKTOP CONTEXT]"]
        if self.active_application:
            lines.append(f"Foreground Application: {self.active_application.title()}")
        if self.active_window_title:
            lines.append(f"Window Title: {self.active_window_title}")
        if self.active_recipient:
            lines.append(f"Active Recipient/Contact: {self.active_recipient}")
        if self.active_document:
            lines.append(f"Active Document/File: {self.active_document}")
        if self.current_task:
            lines.append(f"Current Task: {self.current_task} (Stage: {self.workflow_stage or 'in_progress'})")
        if self.last_verified_action:
            lines.append(f"Last Verified Action: {self.last_verified_action}")
        if self.pending_message:
            lines.append(f"Pending Message: {repr(self.pending_message)}")
        return "\n".join(lines)

    format_for_prompt = format_context_prompt

