"""YAML frontmatter parser for SKILL.md / HOOK.md files.

Mirrors OpenClaw's ``packages/markdown-core/src/frontmatter.ts``.
A skill file looks like::

    ---
    name: weather
    description: "Get current weather and forecasts."
    metadata: { "openclaw": { "emoji": "🌤️" } }
    ---

    # Body starts here...

The parser returns ``(frontmatter_dict, body_str)``. The body is
everything after the closing ``---``.

We do **not** require a full YAML library; the frontmatter keys we
care about are flat-ish, so a tiny inline parser handles 99% of real
files. For complex nested structures (the ``metadata.openclaw``
block), we fall back to a permissive `json.loads` on the value
(matching the style OpenClaw uses for ``metadata: { "...": ... }``).

This keeps the SDK stdlib-only. If users have PyYAML installed, we
use it as a faster / more-correct path; otherwise we fall back to
the inline parser.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

try:
    import yaml as _yaml  # type: ignore[import-not-found]

    yaml = _yaml  # bind for use in parse_frontmatter
    _HAS_YAML = True
except ImportError:
    yaml = None  # type: ignore[assignment]
    _HAS_YAML = False


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<fm>.*?)\n---\s*\n?(?P<body>.*)\Z",
    re.DOTALL,
)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``text`` into (frontmatter_dict, body_str).

    Returns ``({}, text)`` if the file has no frontmatter.
    """
    match = _FRONTMATTER_RE.search(text)
    if not match:
        return {}, text

    fm_raw = match.group("fm")
    body = match.group("body")

    if _HAS_YAML and yaml is not None:
        try:
            fm: dict[str, object] = yaml.safe_load(fm_raw) or {}
        except yaml.YAMLError:
            fm = _inline_parse(fm_raw)
    else:
        fm = _inline_parse(fm_raw)

    return fm, body


def load_skill(path: Path) -> dict[str, Any] | None:
    """Read a SKILL.md file and return its parsed frontmatter + body.

    Returns ``None`` if the file is unreadable. The caller is
    responsible for validating that ``name`` and ``description`` are
    present.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return {"path": str(path), "text": text}


def split_skill_file(path: Path) -> tuple[dict[str, Any], str] | None:
    """Read a SKILL.md file and return ``(frontmatter, body)`` or None.

    Convenience wrapper combining ``load_skill`` + ``parse_frontmatter``.
    """
    raw = load_skill(path)
    if raw is None:
        return None
    fm, body = parse_frontmatter(raw["text"])
    fm["_source_path"] = raw["path"]
    return fm, body


# ── Tiny inline YAML parser (fallback) ───────────────────────────────
# Handles the common skill-frontmatter shapes:
#   key: value
#   key: "quoted value"
#   key: { json: "object" }    ← OpenClaw metadata style
#   key:
#     nested_key: value
# We do NOT try to be a full YAML parser; we cover the cases real
# SKILL.md files use. If a file has weird YAML, we raise so the
# caller can fail loud (vs silent corruption).


def _inline_parse(text: str) -> dict[str, Any]:
    """Parse a flat-ish YAML subset.

    Raises ``ValueError`` on malformed input. Supports:
      - top-level key: value
      - quoted values (single or double)
      - nested one-level dicts (4-space indent)
      - JSON object values (e.g. ``{ "openclaw": {...} }``)
    """
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_dict: dict[str, Any] | None = None
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  ") and current_key and current_dict is not None:
            # Nested key inside the current top-level key.
            k, _, v = line.strip().partition(":")
            v = v.strip()
            current_dict[k.strip()] = _coerce_value(v)
            continue
        # Top-level key:value (or key: alone, signaling nested block).
        if ":" not in line:
            raise ValueError(f"frontmatter: malformed line {line_no}: {raw_line!r}")
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v == "":
            # Nested block starting on next indented line.
            current_key = k
            current_dict = {}
            result[k] = current_dict
            continue
        current_key = k
        current_dict = None
        result[k] = _coerce_value(v)
    return result


def _coerce_value(v: str) -> Any:
    """Coerce a frontmatter scalar to a Python value.

    Tries: JSON object / array (OpenClaw style), then a few common
    scalars, then falls back to the raw string.
    """
    v_stripped = v.strip()
    # JSON-style object / array (OpenClaw metadata)
    if v_stripped.startswith(("{", "[")):
        try:
            return json.loads(v_stripped)
        except json.JSONDecodeError:
            pass
    # Strip surrounding quotes
    if (v_stripped.startswith('"') and v_stripped.endswith('"')) or (
        v_stripped.startswith("'") and v_stripped.endswith("'")
    ):
        return v_stripped[1:-1]
    # Booleans / null
    if v_stripped in ("true", "True"):
        return True
    if v_stripped in ("false", "False"):
        return False
    if v_stripped in ("null", "Null", "~"):
        return None
    return v_stripped


__all__ = ["load_skill", "parse_frontmatter", "split_skill_file"]
