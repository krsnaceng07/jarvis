"""jarvis.plugins.oc_path — oc-path plugin & workspace file addressing scheme (`oc://`).

OpenClaw parity: mirrors
``openclaw-main/extensions/oc-path/src/oc-path/sentinel.ts`` and
``openclaw-main/extensions/oc-path/src/oc-path/oc-path.ts``.

Features:
- `OC_PATH_PLUGIN_ID`: `"oc-path"`
- `REDACTED_SENTINELS`: List containing `"__OPENCLAW_REDACTED__"` and `"__JARVIS_REDACTED__"`.
- `JarvisEmitSentinelError`: Exception raised when a write containing a redaction sentinel is attempted.
- `guard_sentinel()`: Validates that text does not contain redaction sentinels.
- `OC_PATH_FILE_KINDS`: `"markdown"`, `"jsonc"`, `"jsonl"`, `"yaml"`.
- `OC_PATH_VERBS`: `"resolve"`, `"find"`, `"set"`, `"validate"`, `"emit"`.
- `parse_oc_uri()`: Parses `oc://<file_path>/<leaf_path>` into `(file_path, leaf_path)`.
"""

from __future__ import annotations

from typing import Any, Literal

OC_PATH_PLUGIN_ID: str = "oc-path"

REDACTED_SENTINEL_OPENCLAW: str = "__OPENCLAW_REDACTED__"
REDACTED_SENTINEL_JARVIS: str = "__JARVIS_REDACTED__"
REDACTED_SENTINELS: list[str] = [REDACTED_SENTINEL_OPENCLAW, REDACTED_SENTINEL_JARVIS]

OcPathFileKind = Literal["markdown", "jsonc", "jsonl", "yaml"]
OC_PATH_FILE_KINDS: list[OcPathFileKind] = ["markdown", "jsonc", "jsonl", "yaml"]

OcPathVerb = Literal["resolve", "find", "set", "validate", "emit"]
OC_PATH_VERBS: list[OcPathVerb] = ["resolve", "find", "set", "validate", "emit"]


class JarvisEmitSentinelError(ValueError):
    """Raised when an emit or write operation contains a redaction sentinel literal."""

    def __init__(self, oc_path: str) -> None:
        super().__init__(
            f"emit refused to write redaction sentinel literal at {oc_path}"
        )
        self.code = "OC_EMIT_SENTINEL"
        self.oc_path = oc_path


def guard_sentinel(value: Any, oc_path: str) -> None:
    """Refuse writes if value contains any redaction sentinel string."""
    if isinstance(value, str):
        for sentinel in REDACTED_SENTINELS:
            if sentinel in value:
                raise JarvisEmitSentinelError(oc_path)


def parse_oc_uri(uri: str) -> tuple[str, str]:
    """Parse an oc:// URI into (file_path, leaf_pointer)."""
    if not uri or not isinstance(uri, str) or not uri.startswith("oc://"):
        raise ValueError(f"Invalid oc-path URI '{uri}'. Must start with 'oc://'.")

    raw = uri[5:].strip()
    if not raw:
        raise ValueError(f"Invalid oc-path URI '{uri}'. Path cannot be empty.")

    if "/" not in raw:
        return raw, ""

    slash_idx = raw.find("/")
    file_path = raw[:slash_idx].strip()
    leaf_pointer = raw[slash_idx + 1 :].strip()

    return file_path, leaf_pointer


def detect_file_kind(file_path: str) -> OcPathFileKind:
    """Detect oc-path file kind from filename extension."""
    lower = file_path.lower()
    if lower.endswith(".md"):
        return "markdown"
    if lower.endswith(".jsonl") or lower.endswith(".ndjson"):
        return "jsonl"
    if lower.endswith(".yaml") or lower.endswith(".yml") or lower.endswith(".lobster"):
        return "yaml"
    return "jsonc"


__all__ = [
    "JarvisEmitSentinelError",
    "OC_PATH_FILE_KINDS",
    "OC_PATH_PLUGIN_ID",
    "OC_PATH_VERBS",
    "REDACTED_SENTINELS",
    "REDACTED_SENTINEL_JARVIS",
    "REDACTED_SENTINEL_OPENCLAW",
    "OcPathFileKind",
    "OcPathVerb",
    "detect_file_kind",
    "guard_sentinel",
    "parse_oc_uri",
]
