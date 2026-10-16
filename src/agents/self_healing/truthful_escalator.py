"""src.agents.self_healing.truthful_escalator — Anti-hallucination escalation formatter.

OpenClaw parity: mirrors qa/scenarios/personal/failure-recovery.yaml:
Explicitly requires:
- Completed: [verified steps]
- Failed step: [exact failing step and error]
- Retry boundary: [why automatic retry stopped]
- Next step: [actionable next steps]
Forbids premature claims of success.
"""

from __future__ import annotations

from typing import Sequence


class TruthfulEscalationFormatter:
    """Formats honest, structured escalation reports when self-healing reaches a boundary."""

    @staticmethod
    def format_escalation(
        completed_steps: Sequence[str] | None,
        failed_step: str,
        error_message: str,
        retry_boundary_reason: str,
        next_steps: Sequence[str] | None = None,
        tool_name: str | None = None,
    ) -> str:
        """Format an anti-hallucination escalation report adhering to OpenClaw contract."""
        lines: list[str] = []
        lines.append("### ⚠️ Task Execution Boundary Reached\n")

        # Completed section
        lines.append("**Completed:**")
        if completed_steps and len(completed_steps) > 0:
            for step in completed_steps:
                lines.append(f"- ✅ {step}")
        else:
            lines.append("- (None — failure occurred before any verified state transition)")
        lines.append("")

        # Failed step section
        lines.append("**Failed step:**")
        step_prefix = f"[{tool_name}] " if tool_name else ""
        clean_err = error_message.strip().replace("\r\n", "\n")
        lines.append(f"- ❌ {step_prefix}{failed_step}: {clean_err}")
        lines.append("")

        # Retry boundary section
        lines.append("**Retry boundary:**")
        lines.append(f"- 🛑 {retry_boundary_reason}")
        lines.append("")

        # Next step section
        lines.append("**Next step:**")
        if next_steps and len(next_steps) > 0:
            for n_step in next_steps:
                lines.append(f"1. {n_step}")
        else:
            lines.append("1. Verify the target path, credentials, or system state manually.")
            lines.append(
                "2. Do not repeat this exact tool action with identical arguments. Reassess the task, ask the user for clarification, or choose an alternative tool."
            )

        return "\n".join(lines)


__all__ = [
    "TruthfulEscalationFormatter",
]
