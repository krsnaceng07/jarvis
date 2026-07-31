"""jarvis.agents.sessions.tools.path_utils — session tool path normalization helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/path-utils.ts``.

Phase 6.10a — path normalization.

Expands user / file URL inputs and resolves
read/write paths against the active cwd with
macOS filename variants. The variants exist
because macOS uses NFD-decomposed filenames
+ U+2019 right-single-quote in screenshot
names — the helpers try multiple normalisations
so a user-typed path still resolves to a real
file on disk.

Adaptations
-----------
- The OpenClaw source uses Node ``fs.accessSync``
  + ``path.isAbsolute`` + ``path.resolve``.
  The Python port uses :func:`os.path.isabs` +
  :func:`os.path.realpath` (or :func:`os.path.join`
  + resolve) + :func:`os.access`.
- The OpenClaw source's
  ``fileURLToPath`` is replaced with
  :func:`urllib.parse.urlparse` +
  :func:`urllib.request.url2pathname` (the
  Python stdlib equivalent).
- The OpenClaw source's NFD normalisation
  via ``str.normalize("NFD")`` is preserved
  — :mod:`unicodedata`` provides the same
  on the Python side (``unicodedata.normalize("NFD", s)``).
- The OpenClaw source's
  ``fileExists`` becomes a thin
  :func:`os.path.isfile` + :func:`os.path.isdir`
  combo (the OpenClaw source's ``accessSync``
  with ``F_OK`` only checks existence, not
  type).
"""
from __future__ import annotations

import os
import re
import unicodedata
import urllib.parse
import urllib.request
from typing import Union


#: Unicode whitespace variants that should be
 #: normalised to ASCII space. Mirrors
 #: ``UNICODE_SPACES``
 #: (``path-utils.ts:11``).
_UNICODE_SPACES = re.compile(
    "[\u00A0\u2000-\u200A\u202F\u205F\u3000]"
)

#: Narrow no-break space (used by macOS in
 #: screenshot filenames). Mirrors
 #: ``NARROW_NO_BREAK_SPACE`` (``path-utils.ts:12``).
_NARROW_NO_BREAK_SPACE = "\u202f"


def _normalize_unicode_spaces(value: str) -> str:
    return _UNICODE_SPACES.sub(" ", value)


def _try_macos_screenshot_path(file_path: str) -> str:
    """Replace the ASCII space in `` AM`` / `` PM``
    with the narrow no-break space macOS uses.
    Mirrors ``tryMacOSScreenshotPath``
    (``path-utils.ts:17-19``)."""
    # The replacement is built via raw-string
    # concatenation so ``\\1`` is preserved
    # literally (Python's :func:`re.sub`
    # expansion of ``\\1`` gives the captured
    # group; an f-string ``\\1`` collapses to
    # a single ``\1`` which :func:`re.sub`
    # reads as a backreference but is brittle
    # when the captured group is followed by
    # other content). Use raw concatenation
    # to keep the regex semantics exact.
    return re.sub(
        r" (AM|PM)\.", _NARROW_NO_BREAK_SPACE + r"\1.", file_path
    )


def _try_nfd_variant(file_path: str) -> str:
    """Return the NFD-decomposed form of the
    path. macOS stores filenames in NFD form.
    Mirrors ``tryNFDVariant`` (``path-utils.ts:21-24``)."""
    return unicodedata.normalize("NFD", file_path)


def _try_curly_quote_variant(file_path: str) -> str:
    """Replace ASCII apostrophes with U+2019
    right-single-quote (used in French macOS
    screenshot names like "Capture d'écran").
    Mirrors ``tryCurlyQuoteVariant``
    (``path-utils.ts:26-30``)."""
    return file_path.replace("'", "\u2019")


def _file_exists(file_path: str) -> bool:
    return os.path.isfile(file_path) or os.path.isdir(file_path)


def _normalize_at_prefix(file_path: str) -> str:
    """Strip the leading ``@`` that the
    OpenClaw source strips. Some users wrap
    paths in ``@`` to escape terminal
    autocompletion; the tool layer should
    treat ``@/foo`` the same as ``/foo``.
    Mirrors ``normalizeAtPrefix``
    (``path-utils.ts:41-43``)."""
    if file_path.startswith("@"):
        return file_path[1:]
    return file_path


def _expand_path(file_path: str) -> str:
    """Expand ``~`` / ``file://`` / ``@`` prefix.
    Mirrors ``expandPath`` (``path-utils.ts:45-61``)."""
    normalized = _normalize_unicode_spaces(_normalize_at_prefix(file_path))
    if normalized.startswith("file://"):
        try:
            parsed = urllib.parse.urlparse(normalized)
            path = urllib.request.url2pathname(parsed.path)
            if parsed.netloc:
                # UNC path on Windows: file://server/share
                return f"//{parsed.netloc}{path}"
            return path
        except (ValueError, OSError):
            return normalized
    if normalized == "~":
        return os.path.expanduser("~")
    if normalized.startswith("~/") or normalized.startswith("~\\"):
        return os.path.expanduser("~") + normalized[1:]
    return normalized


def resolve_to_cwd(file_path: str, cwd: str) -> str:
    """Resolve a path relative to ``cwd``,
    expanding ``~`` and accepting absolute
    paths as-is. Mirrors ``resolveToCwd``
    (``path-utils.ts:67-73``)."""
    expanded = _expand_path(file_path)
    if os.path.isabs(expanded):
        return expanded
    return os.path.realpath(os.path.join(cwd, expanded))


def resolve_read_path(file_path: str, cwd: str) -> str:
    """Resolve a read-target path. Tries the
    expanded path + the macOS variants
    (NFD, curly-quote, AM/PM) so a
    user-typed path still resolves to a real
    file on disk. Mirrors ``resolveReadPath``
    (``path-utils.ts:75-106``)."""
    resolved = resolve_to_cwd(file_path, cwd)
    if _file_exists(resolved):
        return resolved

    am_pm = _try_macos_screenshot_path(resolved)
    if am_pm != resolved and _file_exists(am_pm):
        return am_pm

    nfd = _try_nfd_variant(resolved)
    if nfd != resolved and _file_exists(nfd):
        return nfd

    curly = _try_curly_quote_variant(resolved)
    if curly != resolved and _file_exists(curly):
        return curly

    nfd_curly = _try_curly_quote_variant(nfd)
    if nfd_curly != resolved and _file_exists(nfd_curly):
        return nfd_curly

    return resolved


__all__ = [
    "resolve_read_path",
    "resolve_to_cwd",
]
