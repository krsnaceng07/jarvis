"""jarvis.config.includes_scan — recursive include-path scanner.

OpenClaw parity: mirrors
``openclaw-main/src/config/includes-scan.ts``.

Focused minimal port: walks parsed config trees for ``$include``
directives and surfaces the resolved canonical include paths so
permission-repair tooling can decide which files to retain.
"""
from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Set


INCLUDE_KEY = "$include"
MAX_INCLUDE_DEPTH = 10


def _list_direct_includes(parsed: Any) -> List[str]:
    out: List[str] = []
    def _visit(value) -> None:
        if not value:
            return
        if isinstance(value, list):
            for item in value:
                _visit(item)
            return
        if not isinstance(value, dict):
            return
        include_val = value.get(INCLUDE_KEY)
        if isinstance(include_val, str):
            out.append(include_val)
        elif isinstance(include_val, list):
            for item in include_val:
                if isinstance(item, str):
                    out.append(item)
        for v in value.values():
            _visit(v)
    _visit(parsed)
    return out


def collect_include_paths_recursive(
    params: dict,
    *,
    read_file: Optional[Callable[[str], str]] = None,
    parse_json: Optional[Callable[[str], Any]] = None,
    resolve_include: Optional[Callable] = None,
    resolve_include_roots: Optional[Callable[[Optional[dict]], list]] = None,
    create_session: Optional[Callable] = None,
    read_with_guards: Optional[Callable] = None,
) -> List[str]:
    """Collect recursively referenced config include files.

    Mirrors :func:`collectIncludePathsRecursive`
    (``shared/config/includes-scan.ts``).
    """
    config_path = params["configPath"]
    parsed = params.get("parsed")
    allowed_roots = params.get("allowedRoots")
    if allowed_roots is None and callable(resolve_include_roots):
        allowed_roots = resolve_include_roots(params.get("env"))
    included_paths: Set[str] = set()
    walked_depth: dict = {}

    def _walk(base_path: str, p: Any, depth: int) -> None:
        if depth >= MAX_INCLUDE_DEPTH:
            return
        for include_path in _list_direct_includes(p):
            opened_base: Optional[str] = None
            nested: Optional[dict] = None
            if callable(resolve_include):
                try:
                    def _resolver(_: Any, __: str, resolver: Any) -> None:
                        nonlocal opened_base, nested
                        if callable(read_file):
                            resolver["readFile"] = lambda p: read_file(p)
                        if callable(read_with_guards):
                            def _with_guards(read_params: dict) -> Any:
                                opened = read_with_guards(read_params)
                                if isinstance(opened, dict) and opened.get("resolvedPath"):
                                    resolved = opened["resolvedPath"]
                                    included_paths.add(resolved)
                                    opened_base = resolved
                                return opened
                            resolver["readFileWithGuards"] = _with_guards
                        if callable(parse_json):
                            def _parse(raw: str) -> Any:
                                np = parse_json(raw)
                                if opened_base:
                                    nested = {"basePath": opened_base, "parsed": np}
                                return {}
                            resolver["parseJson"] = _parse
                        return None
                    resolve_include({INCLUDE_KEY: include_path}, base_path, _resolver)
                except Exception:
                    # Invalid includes are reported by config validation.
                    pass
            if nested is not None:
                _walk(nested["basePath"], nested["parsed"], depth + 1)

    _walk(config_path, parsed, 0)
    return list(included_paths)


__all__ = [
    "INCLUDE_KEY",
    "MAX_INCLUDE_DEPTH",
    "collect_include_paths_recursive",
]
