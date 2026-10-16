"""Post-compaction AGENTS.md context injection.

Port of ``src/auto-reply/reply/post-compaction-context.ts``.

After a compaction round, critical sections from the workspace ``AGENTS.md``
file are injected into the rebuilt context as a synthetic system event.  This
prevents the model from forgetting safety rules, session-startup sequences,
or other hard constraints that were in the summarized portion of the
transcript.

Configuration (``openclaw.json`` → ``agents.defaults.compaction``):
    ``postCompactionSections``: list of H2/H3 heading names to extract.
    ``postCompactionMaxChars``: optional per-agent char limit override.

When the configured sections match the default pair ``["Session Startup",
"Red Lines"]``, the legacy pair ``["Every Session", "Safety"]`` is tried as
a fallback for workspaces that haven't been updated yet.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants (parity: post-compaction-context.ts)
# ---------------------------------------------------------------------------

MAX_CONTEXT_CHARS: int = 1800

DEFAULT_POST_COMPACTION_SECTIONS: list[str] = ["Session Startup", "Red Lines"]
LEGACY_POST_COMPACTION_SECTIONS: list[str] = ["Every Session", "Safety"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_section_name(name: str) -> str:
    """Lower-case and strip for case-insensitive comparison."""
    return name.strip().lower()


def _matches_section_set(section_names: list[str], expected: list[str]) -> bool:
    """Return True if the two lists contain the same names (case-insensitive).

    Order-independent.
    Parity: ``matchesSectionSet``.
    """
    if len(section_names) != len(expected):
        return False
    counts: dict[str, int] = {}
    for name in expected:
        norm = _normalize_section_name(name)
        counts[norm] = counts.get(norm, 0) + 1
    for name in section_names:
        norm = _normalize_section_name(name)
        count = counts.get(norm, 0)
        if not count:
            return False
        if count == 1:
            del counts[norm]
        else:
            counts[norm] = count - 1
    return len(counts) == 0


def extract_sections(
    content: str,
    section_names: list[str],
    found_names: list[str] | None = None,
) -> list[str]:
    """Extract named H2/H3 sections from markdown content.

    - Matches headings case-insensitively.
    - Skips content inside fenced code blocks.
    - Captures until the next heading of equal or higher level, or EOF.

    Parity: ``extractSections``.
    """
    results: list[str] = []
    lines = content.split("\n")

    for name in section_names:
        section_lines: list[str] = []
        in_section = False
        section_level = 0
        in_code_block = False

        for line in lines:
            # Track fenced code blocks.
            if line.lstrip().startswith("```"):
                in_code_block = not in_code_block
                if in_section:
                    section_lines.append(line)
                continue

            # Skip heading detection inside code blocks.
            if in_code_block:
                if in_section:
                    section_lines.append(line)
                continue

            # Check for a heading.
            heading_match = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
            if heading_match:
                level = len(heading_match.group(1))  # 2 or 3
                heading_text = heading_match.group(2)

                if not in_section:
                    if _normalize_section_name(heading_text) == _normalize_section_name(name):
                        in_section = True
                        section_level = level
                        section_lines = [line]
                        continue
                else:
                    # Stop at same or higher level heading.
                    if level <= section_level:
                        break
                    section_lines.append(line)
                    continue
            elif in_section:
                section_lines.append(line)

        if section_lines:
            results.append("\n".join(section_lines).strip())
            if found_names is not None:
                found_names.append(name)

    return results


def _truncate_utf16_safe(s: str, max_chars: int) -> str:
    """Truncate *s* to *max_chars* UTF-16 code units."""
    try:
        from jarvis_normalization_core.text_utility import truncate_utf16_safe  # type: ignore[import]

        return truncate_utf16_safe(s, max_chars)
    except Exception:
        return s[:max_chars]


def _format_date_stamp(now_ms: float, timezone: str | None = None) -> str:
    """Return ``YYYY-MM-DD`` in the given timezone (UTC fallback).

    Parity: ``formatDateStamp``.
    """
    from datetime import datetime, timezone as tz

    dt = datetime.fromtimestamp(now_ms / 1000, tz=tz.utc)
    if timezone:
        try:
            import zoneinfo

            dt = dt.astimezone(zoneinfo.ZoneInfo(timezone))
        except Exception:
            pass
    return dt.strftime("%Y-%m-%d")


def _resolve_user_timezone(cfg: Any) -> str | None:
    """Extract user timezone string from config.

    Parity: ``resolveUserTimezone``.
    """
    if cfg is None:
        return None
    try:
        return cfg.agents.defaults.user_timezone or None
    except Exception:
        pass
    try:
        return cfg.get("agents", {}).get("defaults", {}).get("userTimezone", None)
    except Exception:
        return None


def _get_post_compaction_sections(cfg: Any) -> list[str] | None:
    """Read configured section names from ``agents.defaults.compaction``.

    Returns ``None`` when unconfigured.
    """
    if cfg is None:
        return None
    try:
        sections = cfg.agents.defaults.compaction.post_compaction_sections
        if isinstance(sections, list) and sections:
            return sections
    except Exception:
        pass
    try:
        sections = (
            cfg.get("agents", {})
            .get("defaults", {})
            .get("compaction", {})
            .get("postCompactionSections", None)
        )
        if isinstance(sections, list) and sections:
            return sections
    except Exception:
        pass
    return None


def _get_max_context_chars(cfg: Any, agent_id: str | None) -> int:
    """Resolve per-agent or global ``postCompactionMaxChars`` limit."""
    try:
        if agent_id:
            per_agent = (
                cfg.get("agents", {})
                .get("perAgent", {})
                .get(agent_id, {})
                .get("compaction", {})
                .get("postCompactionMaxChars", None)
            )
            if isinstance(per_agent, int) and per_agent > 0:
                return per_agent
        global_limit = (
            cfg.get("agents", {})
            .get("defaults", {})
            .get("compaction", {})
            .get("postCompactionMaxChars", None)
        )
        if isinstance(global_limit, int) and global_limit > 0:
            return global_limit
    except Exception:
        pass
    return MAX_CONTEXT_CHARS


def _resolve_cron_style_now(cfg: Any, now_ms: float) -> str:
    """Return a concise ``Current time: YYYY-MM-DD HH:MM UTC`` line.

    Parity: the ``timeLine`` produced by ``resolveCronStyleNow``.
    """
    from datetime import datetime, timezone as tz

    dt = datetime.fromtimestamp(now_ms / 1000, tz=tz.utc)
    return f"Current time: {dt.strftime('%Y-%m-%d %H:%M UTC')}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_post_compaction_context(
    workspace_dir: str | Path,
    cfg: Any = None,
    agent_id: str | None = None,
    now_ms: float | None = None,
) -> str | None:
    """Read critical sections from ``AGENTS.md`` for post-compaction injection.

    Returns formatted system-event text (or ``None`` when nothing should be
    injected).

    Parity: ``readPostCompactionContext``.

    Args:
        workspace_dir: Absolute path to the workspace root.
        cfg: Parsed ``openclaw.json`` / JARVIS config object or dict.
        agent_id: Current agent id, used for per-agent context limits.
        now_ms: Optional override for ``Date.now()`` (ms epoch).  Defaults to
            the real wall clock.
    """
    import time as _time

    configured_sections = _get_post_compaction_sections(cfg)
    if not configured_sections:
        return None

    agents_path = Path(workspace_dir) / "AGENTS.md"
    if not agents_path.is_file():
        return None

    try:
        content = agents_path.read_text(encoding="utf-8")
    except Exception:
        return None

    found_section_names: list[str] = []
    sections = extract_sections(content, configured_sections, found_section_names)

    # Legacy fallback only when the default section names are configured.
    is_default_sections = _matches_section_set(
        configured_sections, DEFAULT_POST_COMPACTION_SECTIONS
    )
    if not sections and is_default_sections:
        sections = extract_sections(content, LEGACY_POST_COMPACTION_SECTIONS, found_section_names)

    if not sections:
        return None

    # Only reference section names that were actually found and injected.
    display_names = found_section_names if found_section_names else configured_sections

    effective_now_ms = now_ms if now_ms is not None else _time.time() * 1000
    timezone = _resolve_user_timezone(cfg)
    date_stamp = _format_date_stamp(effective_now_ms, timezone)
    max_context_chars = _get_max_context_chars(cfg, agent_id)
    time_line = _resolve_cron_style_now(cfg, effective_now_ms)

    # Substitute YYYY-MM-DD placeholder and enforce character budget.
    combined = "\n\n".join(sections).replace("YYYY-MM-DD", date_stamp)
    if len(combined) > max_context_chars:
        safe_content = _truncate_utf16_safe(combined, max_context_chars) + "\n...[truncated]..."
    else:
        safe_content = combined

    # Build prose and section label.
    if is_default_sections:
        prose = (
            "Session was just compacted. The conversation summary above is a hint, "
            "NOT a substitute for your startup sequence. "
            "Run your Session Startup sequence - read the required files before "
            "responding to the user."
        )
        section_label = "Critical rules from AGENTS.md:"
    else:
        prose = (
            "Session was just compacted. The conversation summary above is a hint, "
            "NOT a substitute for your full startup sequence. "
            f"Re-read the sections injected below ({', '.join(display_names)}) and follow "
            "your configured startup procedure before responding to the user."
        )
        section_label = f"Injected sections from AGENTS.md ({', '.join(display_names)}):"

    return (
        "[Post-compaction context refresh]\n\n"
        f"{prose}\n\n"
        f"{section_label}\n\n{safe_content}\n\n{time_line}"
    )


__all__ = [
    "DEFAULT_POST_COMPACTION_SECTIONS",
    "LEGACY_POST_COMPACTION_SECTIONS",
    "MAX_CONTEXT_CHARS",
    "extract_sections",
    "read_post_compaction_context",
]
