"""fix_internal_imports — fix circular imports in the new memory_host_sdk.

For each file in ``packages/memory_host_sdk/src/jarvis_memory_host_sdk/``,
read the original ``memory_host_*.py`` from git HEAD and use its
``from .memory_host_X import ...`` lines to rewrite the
``from jarvis_memory_host_sdk import ...`` lines in the new file.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NEW_DIR = REPO_ROOT / "packages/memory_host_sdk/src/jarvis_memory_host_sdk"


def _git_show(module_name: str) -> str:
    """Read the file as of HEAD from the original location."""
    path = f"packages/plugin_sdk/src/jarvis_sdk/{module_name}.py"
    result = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    # Decode as UTF-8; on Windows the default is cp1252 which can't
    # decode CJK bytes in some files.
    return result.stdout.decode("utf-8", errors="replace")


def _extract_imports(text: str) -> list[tuple[str, list[str]]]:
    """Parse ``from .memory_host_X import (a, b, c)`` or ``from .memory_host_X import a``.

    Returns a list of ``(submodule_without_prefix, [symbols])``.
    """
    out: list[tuple[str, list[str]]] = []
    # Match the multi-line form
    pattern = re.compile(
        r"from\s+\.memory_host_(\w+)\s+import\s+\(((?:[^\(\)]|\([^\(\)]*\))*?)\)",
        re.DOTALL,
    )
    for m in pattern.finditer(text):
        submodule = m.group(1)
        body = m.group(2)
        symbols = [s.strip() for s in body.replace("\n", " ").split(",") if s.strip()]
        out.append((submodule, symbols))
    # Match the single-line form (no parens)
    pattern2 = re.compile(r"from\s+\.memory_host_(\w+)\s+import\s+([^\n]+)")
    for m in pattern2.finditer(text):
        submodule = m.group(1)
        symbols = [s.strip() for s in m.group(2).split(",") if s.strip()]
        if (submodule, symbols) in out:
            continue
        out.append((submodule, symbols))
    return out


def main() -> int:
    for new_file in sorted(NEW_DIR.glob("*.py")):
        if new_file.name == "__init__.py":
            continue
        original_name = f"memory_host_{new_file.stem}"
        original = _git_show(original_name)
        if not original:
            print(f"  ! no git history for {original_name}")
            continue
        imports = _extract_imports(original)
        if not imports:
            continue
        text = new_file.read_text(encoding="utf-8")
        new_text = text
        # Build a symbol → submodule map.
        symbol_to_submodule: dict[str, str] = {}
        for submodule, symbols in imports:
            for s in symbols:
                # Strip the ``as`` alias.
                s_name = s.split(" as ")[0].strip()
                if s_name:
                    symbol_to_submodule[s_name] = submodule
        # Find the ``from jarvis_memory_host_sdk import (...)`` block and rewrite.
        pattern = re.compile(
            r"from jarvis_memory_host_sdk import \(((?:[^\(\)]|\([^\(\)]*\))*?)\)",
            re.DOTALL,
        )

        def repl(m: re.Match[str]) -> str:
            body = m.group(1)
            symbols = [s.strip() for s in body.replace("\n", " ").split(",") if s.strip()]
            # Group by submodule.
            groups: dict[str, list[str]] = {}
            for s in symbols:
                s_name = s.split(" as ")[0].strip()
                sub = symbol_to_submodule.get(s_name)
                if sub is None:
                    # Symbol not in our map; put in a fallback group.
                    sub = "unknown"
                groups.setdefault(sub, []).append(s)
            if not groups:
                return m.group(0)
            # Emit one ``from .X import (...)`` per group.
            blocks = []
            for sub, syms in groups.items():
                if sub == "unknown":
                    # Fall back to package import.
                    blocks.append(f"from jarvis_memory_host_sdk import (\n    " + ",\n    ".join(syms) + ",\n)")
                else:
                    blocks.append(f"from .{sub} import (\n    " + ",\n    ".join(syms) + ",\n)")
            return "\n".join(blocks)

        new_text = pattern.sub(repl, new_text)
        if new_text != text:
            new_file.write_text(new_text, encoding="utf-8")
            print(f"  rewrote: {new_file.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
