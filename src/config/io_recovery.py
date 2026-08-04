"""jarvis.config.io_recovery — config-snapshot recovery helpers.

OpenClaw parity: mirrors ``openclaw-main/src/config/io.recovery.ts``.

Focused minimal port: the JSON-root-suffix recovery helper delegates
all real work (parse, includes resolution, validation, snapshot
persistence) to caller-provided callables.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

#: Matches a line that starts with ``{`` or ``[`` after optional whitespace.
_JSON_LINE_RE = re.compile(r"^\s*[\{\[]")


def find_json_root_suffix(raw: str, json5: Any) -> Optional[dict]:
    """Find the first line that opens with ``{``/``[`` and parse it as a JSON5 root.

    Mirrors :func:`findJsonRootSuffix`
    (``shared/config/io.recovery.ts`).
    """
    if not isinstance(raw, str) or _JSON_LINE_RE.match(raw):
        return None
    parse_fn: Optional[Callable] = None
    if isinstance(json5, dict):
        parse_fn = json5.get("parse")
    elif callable(json5):
        parse_fn = json5
    if not callable(parse_fn):
        return None
    offset = 0
    while offset < len(raw):
        next_nl = raw.find("\n", offset)
        line_end = len(raw) if next_nl == -1 else next_nl + 1
        line = raw[offset:line_end]
        if _JSON_LINE_RE.match(line):
            candidate = raw[offset:]
            try:
                parsed = parse_fn(candidate)
            except Exception:
                return None
            return {"raw": candidate, "parsed": parsed}
        offset = line_end
    return None


async def recover_config_from_json_root_suffix_with_context(
    context: Any,
    snapshot: Any,
    *,
    resolve_config_includes_for_read_fn: Optional[Callable] = None,
    resolve_config_for_read_fn: Optional[Callable] = None,
    validate_config_object_with_plugins_fn: Optional[Callable] = None,
    strip_shipped_plugin_install_config_records_fn: Optional[Callable] = None,
    persist_bounded_clobbered_config_snapshot_fn: Optional[Callable] = None,
) -> bool:
    """Recover a config snapshot whose valid JSON5 root appears after a non-JSON prefix.

    Mirrors :func:`recoverConfigFromJsonRootSuffixWithContext`
    (``shared/config/io.recovery.ts`).
    """
    if not (callable(resolve_config_includes_for_read_fn)
            and callable(resolve_config_for_read_fn)
            and callable(validate_config_object_with_plugins_fn)
            and callable(strip_shipped_plugin_install_config_records_fn)
            and callable(persist_bounded_clobbered_config_snapshot_fn)):
        return False
    if not isinstance(snapshot, dict):
        return False
    if snapshot.get("valid") or not snapshot.get("exists") or not isinstance(snapshot.get("raw"), str):
        return False
    deps = getattr(context, "deps", context) if context else {}
    json5 = deps.get("json5") if isinstance(deps, dict) else None
    suffix_recovery = find_json_root_suffix(snapshot["raw"], json5)
    if not suffix_recovery:
        return False
    try:
        resolved = resolve_config_includes_for_read_fn(
            suffix_recovery["parsed"],
            context.configPath,
            deps,
        )
    except Exception:
        return False
    try:
        resolution = resolve_config_for_read_fn(
            resolved, deps.get("env"), deps.get("lowerPrecedenceEnv"),
        )
    except Exception:
        return False
    try:
        validated = validate_config_object_with_plugins_fn(
            strip_shipped_plugin_install_config_records_fn(resolution.get("resolvedConfigRaw")),
            {"env": deps.get("env"), "sourceRaw": suffix_recovery["parsed"]},
        )
    except Exception:
        return False
    if not validated.get("ok"):
        return False
    try:
        await persist_bounded_clobbered_config_snapshot_fn({
            "deps": deps,
            "configPath": context.configPath,
            "raw": snapshot["raw"],
            "observedAt": None,
        })
    except Exception:
        pass
    return True


__all__ = [
    "find_json_root_suffix",
    "recover_config_from_json_root_suffix_with_context",
]
