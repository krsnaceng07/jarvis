"""vault_page_write — guarded atomic write for vault pages.

OpenClaw parity: mirrors
``extensions/memory-wiki/src/vault-page-write.ts``.

Provides a single ``write_guarded_vault_page`` helper
that the compile / apply / obsidian subcommands use to
overwrite an existing vault page safely. The helper:
- Refuses to write through a symlink
  (``FsSafeError("symlink")``).
- Breaks a hardlink (nlink > 1) before the atomic
  rename so the user-linked copy isn't silently
  poisoned by an in-place rewrite.
- Retries the transient "concurrent-rewrite race"
  (``FsSafeError("path-mismatch")``) a few times with
  linear backoff. A persistent guard failure
  propagates with a labeled message.
"""

from __future__ import annotations

from typing import Any

from jarvis_sdk import (
    FsSafeError,
    fs_root,
    is_regular_file_stat as _is_regular_file_stat,
    retry_async,
)


# Re-export the SDK type-guard under the same name the
# OpenClaw source uses locally in vault-page-write.ts
# so callers can ``from .vault_page_write import
# is_regular_file_stat`` without reaching into the SDK.
is_regular_file_stat = _is_regular_file_stat


def _is_concurrent_rewrite_race(error: BaseException) -> bool:
    """True iff ``error`` is the transient path-mismatch race.

    Mirrors OpenClaw's ``isConcurrentRewriteRace``:
    a concurrent atomic rewrite of the same vault page
    by the memory bridge re-export makes the
    ``opened-realpath`` check fail with
    ``path-mismatch``. The race resolves sub-ms and
    is benign; persistent guard failures still
    hard-fail.
    """
    return isinstance(error, FsSafeError) and error.code == "path-mismatch"


async def write_guarded_vault_page(
    *,
    vault_root: str,
    page_path: str,
    content: str,
    page_stat: Any,
    page_label: str,
) -> None:
    """Write ``content`` to ``page_path`` inside ``vault_root``.

    Mirrors OpenClaw's ``writeGuardedVaultPage``. The
    ``page_path`` is interpreted relative to the
    ``vault_root`` (so callers can pass a bare
    ``"syntheses/foo.md"``). A short, bounded retry
    closes the concurrent-rewrite window; any other
    guard failure raises a labeled ``RuntimeError``
    whose ``__cause__`` is the original
    ``FsSafeError``.
    """
    vault = fs_root(vault_root)

    async def _attempt() -> None:
        if _is_regular_file_stat(page_stat) and page_stat.nlink > 1:
            await _maybe_remove(vault, page_path)
        await _vault_write(vault, page_path, content)

    try:
        await retry_async(
            _attempt,
            {
                "attempts": 3,
                "minDelayMs": 25,
                "maxDelayMs": 50,
                "label": f"memory-wiki write {page_label} {page_path}",
                "shouldRetry": _is_concurrent_rewrite_race,
            },
        )
    except FsSafeError as exc:
        if exc.code != "symlink" and exc.code != "path-alias":
            raise RuntimeError(
                f"Refusing to write {page_label} ({exc.code}): "
                f"{page_path}: {exc}"
            ) from exc
        raise RuntimeError(
            f"Refusing to write {page_label} through symlink: {page_path}"
        ) from exc


async def _maybe_remove(vault: Any, page_path: str) -> None:
    """Best-effort remove for the hardlink-break step.

    Mirrors the inner ``vault.remove(pagePath)`` call
    in OpenClaw's guarded write. Failure to remove
    is non-fatal: the atomic write below will
    surface any persistent guard error.
    """
    try:
        vault.remove(page_path)
    except FsSafeError:
        # Best-effort: an ``already-exists`` or other
        # non-fatal error is not worth aborting the
        # write for.
        return


async def _vault_write(vault: Any, page_path: str, content: str) -> None:
    """Async wrapper around the fs-safe ``vault.write``.

    The Python fs-safe root is sync; wrap it in
    ``asyncio.to_thread`` so the await surface
    matches OpenClaw's async shape.
    """
    import asyncio

    await asyncio.to_thread(vault.write, page_path, content)


__all__ = [
    "is_regular_file_stat",
    "write_guarded_vault_page",
]
