"""jarvis.auto_reply.reply.elevated_unavailable - Formats guidance when an elevated command cannot run in the current channel.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/reply/elevated-unavailable.ts``.
"""

from __future__ import annotations


def format_elevated_unavailable_message(
    runtime_sandboxed: bool,
    failures: list[dict[str, str]],
    session_key: str | None = None,
) -> str:
    lines: list[str] = []
    
    runtime_status = "sandboxed" if runtime_sandboxed else "direct"
    lines.append(f"elevated is not available right now (runtime={runtime_status}).")
    
    if failures:
        failures_str = ", ".join([f"{f.get('gate', 'unknown')} ({f.get('key', 'unknown')})" for f in failures])
        lines.append(f"Failing gates: {failures_str}")
    else:
        lines.append("Failing gates: enabled (tools.elevated.enabled / agents.list[].tools.elevated.enabled), allowFrom (tools.elevated.allowFrom.<provider>).")

    lines.append("Fix-it keys:")
    lines.append("- tools.elevated.enabled")
    lines.append("- tools.elevated.allowFrom.<provider>")
    lines.append("- agents.list[].tools.elevated.enabled")
    lines.append("- agents.list[].tools.elevated.allowFrom.<provider>")
    
    if session_key:
        lines.append(f"See: jarvis sandbox explain --session {session_key}")
        
    return "\n".join(lines)
