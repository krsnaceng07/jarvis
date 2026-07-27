"""jarvis_bulk_move — bulk-move all ``jarvis_sdk.<name>`` modules to a new home.

Used by the refactor Step 2 waves. Reads the file list from
``--src-dir``, derives the destination by stripping the
``jarvis_sdk.`` prefix, and writes each module to
``--dst-dir``.

After the move, this script also rewrites imports across
the repo (per the same logic as ``jarvis_refactor.py``).
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
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    new_text = text
    new_text = re.sub(rf"\bfrom\s+{re.escape(module)}\b", f"from {new_path}", new_text)
    new_text = re.sub(rf"\bimport\s+{re.escape(module)}\b", f"import {new_path}", new_text)
    new_text = re.sub(rf"\b{re.escape(module)}\b", new_path, new_text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-dir", required=True, help="Source directory containing modules to move")
    parser.add_argument("--dst-dir", required=True, help="Destination directory for the moved modules")
    parser.add_argument("--prefix", required=True, help="Module prefix to strip (e.g. jarvis_sdk)")
    parser.add_argument("--package-prefix", required=True, help="New package prefix (e.g. memory_host_sdk)")
    parser.add_argument("--apply", action="store_true", help="Apply (default: dry-run)")
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    if not src_dir.is_absolute():
        src_dir = REPO_ROOT / src_dir
    dst_dir = Path(args.dst_dir)
    if not dst_dir.is_absolute():
        dst_dir = REPO_ROOT / dst_dir

    moved: list[tuple[Path, Path, str, str]] = []
    for src_file in sorted(src_dir.glob("*.py")):
        if src_file.name == "__init__.py":
            continue
        module_name = src_file.stem
        if not module_name.startswith(args.prefix + "_"):
            continue
        bare = module_name[len(args.prefix) + 1:]  # strip ``prefix_``
        dst_file = dst_dir / f"{bare}.py"
        new_module = f"{args.package_prefix}.{bare}"
        old_module = f"{args.prefix}.{module_name}"
        if args.apply:
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            print(f"  + {src_file.relative_to(REPO_ROOT)} -> {dst_file.relative_to(REPO_ROOT)}")
        else:
            print(f"  [DRY-RUN] would copy: {src_file.relative_to(REPO_ROOT)} -> {dst_file.relative_to(REPO_ROOT)}")
        moved.append((src_file, dst_file, old_module, new_module))

    # Rewrite imports across the repo.
    changed_files: set[Path] = set()
    for _, _, old_module, new_module in moved:
        for path in _iter_py_files():
            if _rewrite_file(path, module=old_module, new_path=new_module):
                changed_files.add(path)
    if changed_files:
        for p in sorted(changed_files):
            action = "rewrote" if args.apply else "[DRY-RUN] would rewrite"
            print(f"  {action}: {p.relative_to(REPO_ROOT)}")

    # Delete the old files.
    for src_file, _, _, _ in moved:
        if args.apply:
            src_file.unlink()
            print(f"  - deleted: {src_file.relative_to(REPO_ROOT)}")
        else:
            print(f"  [DRY-RUN] would delete: {src_file.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
