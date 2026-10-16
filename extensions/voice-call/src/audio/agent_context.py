"""Agent voice context capsule builder for Voice Call realtime sessions."""

from __future__ import annotations

from pathlib import Path

from ..config import VoiceCallAgentContextConfig


def build_agent_voice_context_capsule(
    config: VoiceCallAgentContextConfig,
    workspace_root: str | Path | None = None,
    agent_id: str = "main",
) -> str:
    """Build a bounded agent identity and workspace capsule for realtime session instructions."""
    if not config.enabled:
        return ""

    root_path = Path(workspace_root) if workspace_root else Path.cwd()
    capsule_parts: list[str] = []

    if config.include_identity:
        capsule_parts.append(
            f"[AGENT IDENTITY]\nYou are Voice Agent '{agent_id}' running in JARVIS.\n"
            "Speak conversationally, concisely, and naturally for telephony audio."
        )

    if config.include_workspace_files and config.files:
        files_content: list[str] = []
        total_len = sum(len(p) for p in capsule_parts)

        for filename in config.files:
            file_path = root_path / filename
            if file_path.is_file():
                try:
                    text = file_path.read_text(encoding="utf-8").strip()
                    if text:
                        snippet = f"--- {filename} ---\n{text}"
                        if total_len + len(snippet) > config.max_chars:
                            remaining = max(0, config.max_chars - total_len - 30)
                            if remaining > 50:
                                files_content.append(
                                    f"--- {filename} (truncated) ---\n{text[:remaining]}..."
                                )
                            break
                        files_content.append(snippet)
                        total_len += len(snippet)
                except Exception:
                    pass

        if files_content:
            capsule_parts.append("[WORKSPACE CAPSULE]\n" + "\n\n".join(files_content))

    full_capsule = "\n\n".join(capsule_parts)
    if len(full_capsule) > config.max_chars:
        return full_capsule[: config.max_chars].rstrip() + "..."
    return full_capsule
