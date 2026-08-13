"""jarvis.agents.promised_work_prompt — promised-work prompt policy.

OpenClaw parity: mirrors
``openclaw-main/src/agents/promised-work-prompt.ts``
(1:1 — shared prompt policy for commitments that
outlive the current turn).
"""
from __future__ import annotations


def build_promised_work_prompt_section() -> list[str]:
    """Mirrors ``buildPromisedWorkPromptSection``
    (``promised-work-prompt.ts:2-13``) — verbatim
    lines."""
    return [
        "## Promised Work",
        "- Promising future, background, delegated, or continued work creates follow-through ownership.",
        "- Before ending a turn, arrange an available push-based completion or watch path; keep the originating request and any existing goal or task open.",
        "- Proactively return with the result, link, proof, or a concrete blocker; do not wait for the requester to ask.",
        "- If no completion path exists, do not promise later; stay in the turn or state the blocker.",
        "- Progress such as `running` is not completion.",
        "",
    ]


__all__ = ["build_promised_work_prompt_section"]
