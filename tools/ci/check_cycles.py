"""Detect import cycles in JARVIS packages/ and apps/.

Mirrors OpenClaw's `pnpm check:import-cycles` + `pnpm check:madge-import-cycles`.

Phase 0.2 stub: when packages/ and apps/ are empty, this is a no-op.
Full cycle detection (using `importlib` + DFS) is added in Phase 1.
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCAN_DIRS = [ROOT / "packages", ROOT / "apps", ROOT / "extensions"]


def collect_module_graph() -> dict[str, set[str]]:
    """Walk every .py file under SCAN_DIRS, parse imports, build module -> deps graph."""
    graph: dict[str, set[str]] = defaultdict(set)
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for py_file in base.rglob("*.py"):
            if "__pycache__" in py_file.parts or "legacy_" in py_file.name:
                continue
            mod = _file_to_module(py_file, base)
            if not mod:
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        graph[mod].add(alias.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    graph[mod].add(node.module)
    return graph


def _file_to_module(path: Path, base: Path) -> str:
    rel = path.relative_to(base).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join([base.name, *parts])


def find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """DFS-based cycle finder. Returns list of cycles, each as list of module names."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    path: list[str] = []
    path_set: set[str] = set()

    def dfs(node: str) -> None:
        if node in path_set:
            # Found a cycle: extract it from path
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        path.append(node)
        path_set.add(node)
        for neighbor in graph.get(node, ()):
            if neighbor in path_set or neighbor in visited:
                continue
            dfs(neighbor)
        path.pop()
        path_set.discard(node)
        visited.add(node)

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node)
    return cycles


def main() -> int:
    graph = collect_module_graph()
    if not graph:
        print("OK: no packages/ or apps/ or extensions/ code yet (Phase 0)")
        return 0
    cycles = find_cycles(graph)
    if cycles:
        for c in cycles:
            print(f"FAIL: import cycle: {' -> '.join(c)}")
        return 1
    print(f"OK: scanned {len(graph)} modules; no import cycles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
