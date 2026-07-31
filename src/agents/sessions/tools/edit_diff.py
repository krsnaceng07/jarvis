"""jarvis.agents.sessions.tools.edit_diff — edit/diff engine for the edit tool.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/edit-diff.ts``.

Phase 6.10c — focused port.

Ships the critical contract every
downstream caller (read/write/edit tools,
tool-execution preview) needs:

- :class:`Edit` — the oldText/newText
  replacement pair
- :class:`EditNoChangeError` — raised when
  an edit doesn't change the content
- ``apply_edits(content, edits)`` — apply
  a list of edits to a string, returning
  the new content
- ``detect_line_ending(content)`` — return
  ``"\\r\\n"`` or ``"\\n"`` based on the
  content's line ending
- ``normalize_to_lf(text)`` / ``restore_line_endings(text, ending)``
  — round-trip helpers
- ``strip_bom(content)`` — strip UTF-8 BOM
  if present
- :func:`fuzzy_find_text` — try exact
  match first, fall back to whitespace-
  + Unicode-quote-tolerant fuzzy match
- :func:`levenshtein_distance` — the
  shared fuzzy-match helper (mirrors
  ``shared/levenshtein-distance.js``)

Adaptations
-----------
- The OpenClaw source uses the npm ``diff``
  package (``createPatch``, ``structuredPatch``)
  + ``shared/levenshtein-distance.js``. The
  Python port re-implements the essential
  Levenshtein helper locally (the OpenClaw
  one is a small function) and uses
  :mod:`difflib` for the structured patch.
- The OpenClaw source's
  ``resolveToCwd`` import is preserved
  via the local :mod:`.path_utils` module.
- The OpenClaw source's
  ``applyReplacementsPreservingUnchangedLines``
  (the line-preserving variant for fuzzy
  matches) is ported as
  :func:`apply_edits_preserving_unchanged_lines`.
  This is the canonical OpenClaw
  edit-application contract.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Optional


# ============================================================================
# Constants
# ============================================================================


#: Maximum number of edit candidates to surface
#: in a "closest matching lines" hint.
#: Mirrors ``EDIT_CANDIDATE_LIMIT``
#: (``edit-diff.ts:267``).
EDIT_CANDIDATE_LIMIT: int = 3

#: Maximum number of candidate lines to scan.
#: Mirrors ``EDIT_CANDIDATE_MAX_LINES``
#: (``edit-diff.ts:268``).
EDIT_CANDIDATE_MAX_LINES: int = 1000

#: Maximum bytes to scan when looking for
#: edit candidates. Mirrors
#: ``EDIT_CANDIDATE_MAX_SCAN_CHARS``
#: (``edit-diff.ts:269``).
EDIT_CANDIDATE_MAX_SCAN_CHARS: int = 128 * 1024

#: Maximum line length to score. Mirrors
#: ``EDIT_CANDIDATE_MAX_LINE_CHARS``
#: (``edit-diff.ts:270``).
EDIT_CANDIDATE_MAX_LINE_CHARS: int = 120

#: Minimum score to surface a candidate.
#: Mirrors ``EDIT_CANDIDATE_MIN_SCORE``
#: (``edit-diff.ts:271``).
EDIT_CANDIDATE_MIN_SCORE: float = 0.45


# ============================================================================
# Public types
# ============================================================================


class EditNoChangeError(Exception):
    """Raised when an edit doesn't change the
    content. Mirrors ``EditNoChangeError``
    (``edit-diff.ts:83-88``)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.name = "EditNoChangeError"


#: An ``Edit`` is an oldText/newText
#: replacement pair. Mirrors ``Edit``
#: (``edit-diff.ts:78-81``).
Edit = dict  # {oldText: str, newText: str}


# ============================================================================
# Line ending helpers
# ============================================================================


LineEnding = str  # "\r\n" | "\n"


def detect_line_ending(content: str) -> LineEnding:
    """Detect the dominant line ending. Mirrors
    ``detectLineEnding`` (``edit-diff.ts:12-22``).
    """
    crlf_idx = content.find("\r\n")
    lf_idx = content.find("\n")
    if lf_idx == -1:
        return "\n"
    if crlf_idx == -1:
        return "\n"
    return "\r\n" if crlf_idx < lf_idx else "\n"


def normalize_to_lf(text: str) -> str:
    """Normalise all line endings to ``\\n``.
    Mirrors ``normalizeToLF``
    (``edit-diff.ts:24-26``)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def restore_line_endings(text: str, ending: LineEnding) -> str:
    """Restore the original line ending. Mirrors
    ``restoreLineEndings``
    (``edit-diff.ts:28-30``).

    The OpenClaw source assumes the input is
    LF-normalised (no existing ``\\r\\n``),
    so the simple ``replace("\\n", "\\r\\n")``
    is safe. The Python port must handle
    mixed input (the line-preserving code
    keeps the original ``\\r\\n`` for
    untouched lines + the LF form for the
    edited line) — a naive replace would
    double-up the existing ``\\r\\n`` into
    ``\\r\\r\\n``. The fix is to first stash
    the existing ``\\r\\n`` as a placeholder,
    replace the lone ``\\n`` with ``\\r\\n``,
    then restore the placeholder.
    """
    if ending == "\r\n":
        placeholder = "\u0000CRLF_PLACEHOLDER\u0000"
        text = text.replace("\r\n", placeholder)
        text = text.replace("\n", "\r\n")
        text = text.replace(placeholder, "\r\n")
        return text
    return text


# ============================================================================
# BOM
# ============================================================================


def strip_bom(content: str) -> dict:
    """Strip a UTF-8 BOM if present. Returns
    ``{"bom": str, "text": str}``. Mirrors
    ``stripBom`` (``edit-diff.ts:255-259``)."""
    if content.startswith("\ufeff"):
        return {"bom": "\ufeff", "text": content[1:]}
    return {"bom": "", "text": content}


# ============================================================================
# Fuzzy matching
# ============================================================================


#: The progressive normalisation chain
#: (NFKC + trim trailing whitespace + smart
#: quotes → ASCII + dashes → ASCII hyphen +
#: special spaces → ASCII space). Mirrors
#: ``normalizeForFuzzyMatch``
#: (``edit-diff.ts:39-60``).
_SMART_SINGLE_QUOTES_RE = re.compile("[\u2018\u2019\u201A\u201B]")
_SMART_DOUBLE_QUOTES_RE = re.compile("[\u201C\u201D\u201E\u201F]")
_UNICODE_DASHES_RE = re.compile("[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]")
_SPECIAL_SPACES_RE = re.compile("[\u00A0\u2002-\u200A\u202F\u205F\u3000]")


def normalize_for_fuzzy_match(text: str) -> str:
    """Apply the progressive normalisation
    chain. Mirrors ``normalizeForFuzzyMatch``
    (``edit-diff.ts:39-60``)."""
    text = unicodedata.normalize("NFKC", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = _SMART_SINGLE_QUOTES_RE.sub("'", text)
    text = _SMART_DOUBLE_QUOTES_RE.sub('"', text)
    text = _UNICODE_DASHES_RE.sub("-", text)
    text = _SPECIAL_SPACES_RE.sub(" ", text)
    return text


def fuzzy_find_text(content: str, old_text: str) -> dict:
    """Try exact match first, then fall back
    to the fuzzy-normalised form. Mirrors
    ``fuzzyFindText`` (``edit-diff.ts:214-252``).

    Returns ``{"found": bool, "index": int,
    "matchLength": int, "usedFuzzyMatch": bool,
    "contentForReplacement": str}``.
    """
    # Exact match
    exact_index = content.find(old_text)
    if exact_index != -1:
        return {
            "found": True,
            "index": exact_index,
            "matchLength": len(old_text),
            "usedFuzzyMatch": False,
            "contentForReplacement": content,
        }
    # Fuzzy match in normalised space
    fuzzy_content = normalize_for_fuzzy_match(content)
    fuzzy_old = normalize_for_fuzzy_match(old_text)
    fuzzy_index = fuzzy_content.find(fuzzy_old)
    if fuzzy_index == -1:
        return {
            "found": False,
            "index": -1,
            "matchLength": 0,
            "usedFuzzyMatch": False,
            "contentForReplacement": content,
        }
    return {
        "found": True,
        "index": fuzzy_index,
        "matchLength": len(fuzzy_old),
        "usedFuzzyMatch": True,
        "contentForReplacement": fuzzy_content,
    }


def count_occurrences(content: str, old_text: str) -> int:
    """Count how many times ``old_text`` appears
    in ``content`` (using the fuzzy-normalised
    form). Mirrors ``countOccurrences``
    (``edit-diff.ts:261-265``)."""
    fuzzy_content = normalize_for_fuzzy_match(content)
    fuzzy_old = normalize_for_fuzzy_match(old_text)
    if not fuzzy_old:
        return 0
    return fuzzy_content.count(fuzzy_old)


# ============================================================================
# Levenshtein distance
# ============================================================================


def levenshtein_distance(a: str, b: str) -> int:
    """Classic Levenshtein edit distance. Mirrors
    the shared ``levenshteinDistance``
    (``shared/levenshtein-distance.js``).

    The Python port uses a 2-row dynamic-programming
    table (O(min(len(a), len(b))) memory) — the
    OpenClaw source uses the same 2-row
    optimisation.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            current[j] = min(
                current[j - 1] + 1,  # insertion
                previous[j] + 1,  # deletion
                previous[j - 1] + (0 if ca == cb else 1),  # substitution
            )
        previous = current
    return previous[-1]


# ============================================================================
# Edit application
# ============================================================================


def _split_lines_with_endings(content: str) -> list[str]:
    """Split ``content`` into lines preserving
    their trailing newline characters.
    Mirrors ``splitLinesWithEndings``
    (``edit-diff.ts:104-106``)."""
    return re.findall(r"[^\n]*\n|[^\n]+", content) or []


def _get_line_spans(content: str) -> list[dict]:
    """Return ``[{"start": int, "end": int}]``
    for each line. Mirrors ``getLineSpans``
    (``edit-diff.ts:108-115``)."""
    offset = 0
    spans: list[dict] = []
    for line in _split_lines_with_endings(content):
        span = {"start": offset, "end": offset + len(line)}
        spans.append(span)
        offset = span["end"]
    return spans


def _get_replacement_line_range(
    lines: list[dict], match_index: int, match_length: int
) -> dict:
    """Map a replacement range to the line
    range it spans. Mirrors
    ``getReplacementLineRange``
    (``edit-diff.ts:117-139``)."""
    replacement_start = match_index
    replacement_end = match_index + match_length
    start_line = -1
    for idx, line in enumerate(lines):
        if (
            replacement_start >= line["start"]
            and replacement_start < line["end"]
        ):
            start_line = idx
            break
    if start_line == -1:
        raise RuntimeError("Replacement range is outside the base content.")
    end_line = start_line
    while end_line < len(lines):
        line = lines[end_line]
        if line["end"] >= replacement_end:
            break
        end_line += 1
    if end_line >= len(lines):
        raise RuntimeError("Replacement range is outside the base content.")
    return {"startLine": start_line, "endLine": end_line + 1}


def _apply_replacements(
    content: str,
    replacements: list[dict],
    offset: int = 0,
) -> str:
    """Apply a list of replacements to
    ``content``. Mirrors ``applyReplacements``
    (``edit-diff.ts:141-151``). The replacements
    are applied in reverse so earlier indexes
    stay valid."""
    result = content
    for replacement in reversed(replacements):
        match_index = replacement["matchIndex"] - offset
        result = (
            result[:match_index]
            + replacement["newText"]
            + result[match_index + replacement["matchLength"] :]
        )
    return result


def apply_edits(content: str, edits: list[Edit]) -> str:
    """Apply a list of :class:`Edit` objects
    to ``content`` + return the new content.
    Mirrors the OpenClaw source's main
    ``applyEdits`` path (the one with
    line-preserving rewrite).

    Raises :class:`EditNoChangeError` when
    an edit's newText equals its oldText.
    Raises ``RuntimeError`` when an edit's
    oldText cannot be found (neither exact
    nor fuzzy).
    """
    if not edits:
        return content
    # Track which edits actually change
    # anything; raise EditNoChangeError if
    # none of them do (the OpenClaw source's
    # caller expects the no-change error to
    # surface BEFORE the file is rewritten).
    base_content = normalize_to_lf(content)
    line_ending = detect_line_ending(content)
    had_change = False
    replacements: list[dict] = []
    for edit in edits:
        old_text = edit.get("oldText", "")
        new_text = edit.get("newText", "")
        if old_text == new_text:
            # No-op edit. The OpenClaw source
            # surfaces this as an error so
            # callers don't accidentally write
            # a file with zero changes.
            raise EditNoChangeError(
                "oldText and newText are identical; nothing to change"
            )
        match = fuzzy_find_text(base_content, old_text)
        if not match["found"]:
            raise RuntimeError(
                f"Could not find oldText in content: {old_text!r}"
            )
        replacements.append(
            {
                "matchIndex": match["index"],
                "matchLength": match["matchLength"],
                "newText": new_text,
            }
        )
        had_change = True
    if not had_change:
        raise EditNoChangeError("No edits changed the content")
    new_content = _apply_edits_preserving_unchanged_lines(
        content, base_content, replacements
    )
    # Restore the original line ending (the
    # line-preserving code may have left the
    # edited line in LF form while untouched
    # lines retain their original CRLF; the
    # restore helper handles the mixed case).
    new_content = restore_line_endings(new_content, line_ending)
    return new_content


def _apply_edits_preserving_unchanged_lines(
    original_content: str,
    base_content: str,
    replacements: list[dict],
) -> str:
    """Rewrite only lines touched by the
    replacements, leaving the rest of the
    original content untouched. Mirrors
    ``applyReplacementsPreservingUnchangedLines``
    (``edit-diff.ts:157-206``)."""
    original_lines = _split_lines_with_endings(original_content)
    base_lines = _get_line_spans(base_content)
    if len(original_lines) != len(base_lines):
        # Fall back to the simple apply if
        # the line count differs (the OpenClaw
        # source throws — the Python port is
        # more forgiving for the no-trailing-
        # newline case).
        return _apply_replacements(base_content, replacements)
    # Group overlapping replacements by line
    sorted_replacements = sorted(
        replacements, key=lambda r: r["matchIndex"]
    )
    groups: list[dict] = []
    for replacement in sorted_replacements:
        range_ = _get_replacement_line_range(
            base_lines,
            replacement["matchIndex"],
            replacement["matchLength"],
        )
        current = groups[-1] if groups else None
        if current and range_["startLine"] < current["endLine"]:
            current["endLine"] = max(
                current["endLine"], range_["endLine"]
            )
            current["replacements"].append(replacement)
        else:
            groups.append(
                {**range_, "replacements": [replacement]}
            )
    original_line_index = 0
    result_parts: list[str] = []
    for group in groups:
        # Preserve untouched lines
        result_parts.append(
            "".join(original_lines[original_line_index : group["startLine"]])
        )
        first = base_lines[group["startLine"]]
        last = base_lines[group["endLine"] - 1]
        group_start_offset = first["start"]
        group_end_offset = last["end"]
        result_parts.append(
            _apply_replacements(
                base_content[group_start_offset:group_end_offset],
                group["replacements"],
                group_start_offset,
            )
        )
        original_line_index = group["endLine"]
    result_parts.append(
        "".join(original_lines[original_line_index:])
    )
    return "".join(result_parts)


# ============================================================================
# Diff / patch
# ============================================================================


def create_unified_patch(
    file_path: str,
    old_content: str,
    new_content: str,
    context_lines: int = 3,
) -> str:
    """Build a unified diff patch. Mirrors
    ``createPatch`` from the npm ``diff``
    package (``edit-diff.ts``).

    The OpenClaw source uses
    ``createPatch(filePath, oldStr, newStr, oldHeader, newHeader, options)``
    + ``FILE_HEADERS_ONLY``. The Python port
    uses :func:`difflib.unified_diff` to
    produce the same output shape.

    Returns the patch text (or an empty
    string when the contents are equal).
    """
    if old_content == new_content:
        return ""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    # ``difflib`` doesn't emit the "---" /
    # "+++" headers when given a single
    # file pair — add them manually to
    # match the ``diff`` package output.
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"--- {file_path}",
            tofile=f"+++ {file_path}",
            n=context_lines,
        )
    )
    return "".join(diff_lines)


__all__ = [
    "EDIT_CANDIDATE_LIMIT",
    "EDIT_CANDIDATE_MAX_LINES",
    "EDIT_CANDIDATE_MAX_SCAN_CHARS",
    "EDIT_CANDIDATE_MAX_LINE_CHARS",
    "EDIT_CANDIDATE_MIN_SCORE",
    "Edit",
    "EditNoChangeError",
    "LineEnding",
    "apply_edits",
    "count_occurrences",
    "create_unified_patch",
    "detect_line_ending",
    "fuzzy_find_text",
    "levenshtein_distance",
    "normalize_for_fuzzy_match",
    "normalize_to_lf",
    "restore_line_endings",
    "strip_bom",
]
