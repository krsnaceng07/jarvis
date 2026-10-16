"""jarvis_refactor — automated module-move helper for Step 2 of the refactor.

For each module in a "move list", this script:
1. Reads the source file from the old location.
2. Writes it to the new location (creating intermediate dirs).
3. Rewrites ``from jarvis_sdk.<name>`` → ``from <new_path>.<name>`` and
   ``jarvis_sdk.<name>`` (used in expressions) → ``<new_path>.<name>``
   across all .py files in the repo.
4. Optionally deletes the old file.

Usage::

    uv run python tools/jarvis_refactor.py \\
        --module jarvis_sdk.retry_runtime \\
        --new-path jarvis_retry.retry_runtime \\
        --new-file packages/retry/src/jarvis_retry/retry_runtime.py \\
        --delete-old

Dry-run mode (default): reports what would change without
writing. Pass ``--apply`` to write.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = [REPO_ROOT / "packages", REPO_ROOT / "extensions", REPO_ROOT / "src", REPO_ROOT / "apps"]
EXCLUDE_DIRS = {".venv", "build", "dist", "__pycache__", "openclaw-main"}


def _iter_py_files() -> list[Path]:
    out: list[Path] = []
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in EXCLUDE_DIRS for part in path.parts):
                continue
            out.append(path)
    return out


def _rewrite_file(path: Path, *, module: str, new_path: str) -> bool:
    """Rewrite ``module`` → ``new_path`` in ``path``.

    Returns True if the file was modified.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False  # Skip non-UTF-8 files (binaries, lock files, etc.)
    new_text = text
    # Match ``from jarvis_sdk.retry_runtime import x`` → ``from jarvis_retry.retry_runtime import x``
    new_text = re.sub(
        rf"\bfrom\s+{re.escape(module)}\b",
        f"from {new_path}",
        new_text,
    )
    # Match ``import jarvis_sdk.retry_runtime`` → ``import jarvis_retry.retry_runtime``
    new_text = re.sub(
        rf"\bimport\s+{re.escape(module)}\b",
        f"import {new_path}",
        new_text,
    )
    # Match ``jarvis_sdk.retry_runtime`` used in expressions
    new_text = re.sub(
        rf"\b{re.escape(module)}\b",
        new_path,
        new_text,
    )
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def move_module(
    *,
    module: str,
    new_path: str,
    old_file: Path,
    new_file: Path,
    apply: bool,
    delete_old: bool,
) -> None:
    """Move a module from ``old_file`` to ``new_file`` and rewrite imports."""
    if not old_file.exists():
        print(f"  ! old file not found: {old_file}", file=sys.stderr)
        sys.exit(1)

    if apply:
        new_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_file, new_file)
        print(f"  + copied: {old_file.relative_to(REPO_ROOT)} -> {new_file.relative_to(REPO_ROOT)}")
    else:
        print(f"  [DRY-RUN] would copy: {old_file.relative_to(REPO_ROOT)} -> {new_file.relative_to(REPO_ROOT)}")

    # Rewrite imports across the repo.
    changed_files: list[Path] = []
    for path in _iter_py_files():
        if path == old_file or path == new_file:
            continue
        # Skip the re-export shims (those will be cleaned up later).
        if path.name == "__init__.py" and "src" in str(path):
            continue
        if _rewrite_file(path, module=module, new_path=new_path):
            changed_files.append(path)
    if changed_files:
        for p in changed_files:
            action = "rewrote" if apply else "[DRY-RUN] would rewrite"
            print(f"  {action}: {p.relative_to(REPO_ROOT)}")
    else:
        print("  no import sites to rewrite")

    if delete_old:
        if apply:
            old_file.unlink()
            print(f"  - deleted: {old_file.relative_to(REPO_ROOT)}")
        else:
            print(f"  [DRY-RUN] would delete: {old_file.relative_to(REPO_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module", required=True, help="Old module path, e.g. jarvis_sdk.retry_runtime")
    parser.add_argument("--new-path", required=True, help="New module path, e.g. jarvis_retry.retry_runtime")
    parser.add_argument("--old-file", required=True, help="Old file path (relative to repo root or absolute)")
    parser.add_argument("--new-file", required=True, help="New file path (relative to repo root or absolute)")
    parser.add_argument("--apply", action="store_true", help="Apply the move (default: dry-run)")
    parser.add_argument("--delete-old", action="store_true", help="Delete the old file after the move")
    args = parser.parse_args()

    old_file = Path(args.old_file)
    if not old_file.is_absolute():
        old_file = REPO_ROOT / old_file
    new_file = Path(args.new_file)
    if not new_file.is_absolute():
        new_file = REPO_ROOT / new_file

    print(f"Move: {args.module} -> {args.new_path}")
    print(f"  old: {old_file.relative_to(REPO_ROOT)}")
    print(f"  new: {new_file.relative_to(REPO_ROOT)}")
    move_module(
        module=args.module,
        new_path=args.new_path,
        old_file=old_file,
        new_file=new_file,
        apply=args.apply,
        delete_old=args.delete_old,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
