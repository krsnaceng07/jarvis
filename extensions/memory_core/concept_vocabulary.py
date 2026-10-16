"""memory_core.concept_vocabulary — concept tag derivation for short-term promotion.

OpenClaw parity: mirrors ``extensions/memory-core/src/concept-vocabulary.ts``.

Provides:
- ``MAX_CONCEPT_TAGS`` — maximum tags per snippet (8, matches OpenClaw).
- ``derive_concept_tags`` — extract concept tags from a memory path + snippet.
  Tags are lowercase normalized significant words; stop-words are filtered out.
- ``summarize_concept_tag_script_coverage`` — aggregate script coverage stats
  over a list of per-entry tag lists.
"""

from __future__ import annotations

import os
import re
from typing import TypedDict

# Maximum number of concept tags per entry — mirrors OpenClaw exactly.
MAX_CONCEPT_TAGS = 8

# ── Stop words (mirrored from concept-vocabulary.ts) ────────────────────────

_SHARED_STOP_WORDS: frozenset[str] = frozenset(
    [
        "about",
        "after",
        "agent",
        "again",
        "also",
        "assistant",
        "because",
        "before",
        "being",
        "between",
        "build",
        "called",
        "could",
        "daily",
        "default",
        "deploy",
        "during",
        "every",
        "file",
        "files",
        "from",
        "have",
        "into",
        "just",
        "line",
        "lines",
        "long",
        "main",
        "make",
        "memory",
        "month",
        "more",
        "most",
        "move",
        "much",
        "next",
        "note",
        "notes",
        "over",
        "part",
        "past",
        "port",
        "same",
        "score",
        "search",
        "session",
        "sessions",
        "short",
        "should",
        "since",
        "some",
        "subagent",
        "system",
        "than",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "through",
        "today",
        "user",
        "using",
        "with",
        "work",
        "workspace",
        "year",
    ]
)

_ENGLISH_STOP_WORDS: frozenset[str] = frozenset(
    ["and", "are", "for", "into", "its", "our", "the", "then", "were", "you", "your"]
)

_SPANISH_STOP_WORDS: frozenset[str] = frozenset(
    [
        "al",
        "con",
        "como",
        "de",
        "del",
        "el",
        "en",
        "es",
        "la",
        "las",
        "los",
        "para",
        "por",
        "que",
        "si",
        "su",
        "sus",
        "una",
        "uno",
        "y",
    ]
)

_FRENCH_STOP_WORDS: frozenset[str] = frozenset(
    [
        "au",
        "aux",
        "avec",
        "ce",
        "ces",
        "du",
        "en",
        "et",
        "il",
        "ils",
        "je",
        "le",
        "les",
        "leur",
        "leurs",
        "ma",
        "me",
        "mes",
        "mon",
        "ne",
        "nos",
        "notre",
        "on",
        "ou",
        "par",
        "pas",
        "sa",
        "se",
        "ses",
        "si",
        "son",
        "sur",
        "ta",
        "te",
        "tes",
        "ton",
        "tu",
        "un",
        "une",
        "vos",
        "vous",
        "vu",
    ]
)

_GERMAN_STOP_WORDS: frozenset[str] = frozenset(
    [
        "aber",
        "als",
        "am",
        "an",
        "auf",
        "aus",
        "bei",
        "bin",
        "bis",
        "da",
        "das",
        "dem",
        "den",
        "der",
        "des",
        "die",
        "dies",
        "ein",
        "eine",
        "einem",
        "einen",
        "einer",
        "eines",
        "er",
        "es",
        "fur",
        "hat",
        "ich",
        "ih",
        "ihm",
        "ihn",
        "ihr",
        "im",
        "in",
        "ist",
        "ja",
        "kann",
        "kein",
        "konnen",
        "mir",
        "mit",
        "nach",
        "nicht",
        "noch",
        "nun",
        "oder",
        "ohne",
        "schon",
        "sehr",
        "sein",
        "sie",
        "so",
        "uber",
        "und",
        "uns",
        "unter",
        "vom",
        "von",
        "vor",
        "war",
        "was",
        "weil",
        "wenn",
        "wer",
        "wie",
        "wir",
        "wird",
        "wo",
        "wohl",
        "zu",
        "zum",
        "zur",
    ]
)

_ALL_STOP_WORDS: frozenset[str] = (
    _SHARED_STOP_WORDS
    | _ENGLISH_STOP_WORDS
    | _SPANISH_STOP_WORDS
    | _FRENCH_STOP_WORDS
    | _GERMAN_STOP_WORDS
)

# ── Script classification ────────────────────────────────────────────────────

_CJK_RE = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef"
    r"\u3040-\u309f\u30a0-\u30ff\uac00-\ud7a3]"
)
_LATIN_RE = re.compile(r"[a-zA-Z]")

_TOKEN_RE = re.compile(r"[^\w\u4e00-\u9fff\u3400-\u4dbf\uac00-\ud7a3]+", re.UNICODE)
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _script_family(token: str) -> str:
    """Classify a token as latin, cjk, mixed, or other."""
    has_latin = bool(_LATIN_RE.search(token))
    has_cjk = bool(_CJK_RE.search(token))
    if has_latin and has_cjk:
        return "mixed"
    if has_latin:
        return "latin"
    if has_cjk:
        return "cjk"
    return "other"


# ── Path-derived tags ────────────────────────────────────────────────────────

_PATH_SEGMENT_RE = re.compile(r"[/\\]")
_NON_ALPHA_RE = re.compile(r"[^a-z0-9]")


def _derive_tags_from_path(memory_path: str) -> list[str]:
    """Extract concept tags from a memory file path.

    Mirrors OpenClaw's ``deriveTagsFromPath``. Takes the basename (without
    extension) and segments it into tokens, filtering date-like and short words.
    """
    if not memory_path:
        return []
    basename = os.path.basename(memory_path)
    # Remove extension
    stem = os.path.splitext(basename)[0]
    # Split on camelCase boundaries then non-alpha
    expanded = _CAMEL_RE.sub(" ", stem)
    raw_tokens = re.split(r"[-_\s.]+", expanded)
    tags: list[str] = []
    for token in raw_tokens:
        t = token.strip().lower()
        # Skip pure date segments like 2024-01-15 components
        if re.match(r"^\d{4}$", t) or re.match(r"^\d{1,2}$", t):
            continue
        # Skip very short or stop-word tokens
        if len(t) < 3 or t in _ALL_STOP_WORDS:
            continue
        # Only keep alphanumeric segments
        cleaned = _NON_ALPHA_RE.sub("", t)
        if cleaned and len(cleaned) >= 3:
            tags.append(cleaned)
    return tags[:MAX_CONCEPT_TAGS]


# ── Snippet-derived tags ─────────────────────────────────────────────────────

_MIN_TOKEN_LEN = 3
_MAX_TOKEN_LEN = 40


def _derive_tags_from_snippet(snippet: str) -> list[str]:
    """Extract concept tags from a memory snippet.

    Mirrors OpenClaw's ``deriveTagsFromSnippet``. Splits on word boundaries,
    normalizes, removes stop words, deduplicates, and caps at MAX_CONCEPT_TAGS.
    """
    if not snippet:
        return []

    # Split on non-word characters, expand camelCase
    expanded = _CAMEL_RE.sub(" ", snippet)
    raw_tokens = _TOKEN_RE.split(expanded)

    seen: set[str] = set()
    tags: list[str] = []
    for raw in raw_tokens:
        token = raw.strip().lower()
        if not token:
            continue
        # Filter by length
        if len(token) < _MIN_TOKEN_LEN or len(token) > _MAX_TOKEN_LEN:
            continue
        # Filter stop words
        if token in _ALL_STOP_WORDS:
            continue
        # Filter purely numeric tokens
        if token.isdigit():
            continue
        # Deduplicate
        if token in seen:
            continue
        seen.add(token)
        tags.append(token)
        if len(tags) >= MAX_CONCEPT_TAGS:
            break

    return tags


# ── Public API ───────────────────────────────────────────────────────────────


def derive_concept_tags(
    *,
    path: str = "",
    snippet: str = "",
) -> list[str]:
    """Return concept tags for the given path + snippet.

    Mirrors OpenClaw's ``deriveConceptTags``. Combines path-derived and
    snippet-derived tags, deduplicates, and caps at ``MAX_CONCEPT_TAGS``.
    """
    path_tags = _derive_tags_from_path(path)
    snippet_tags = _derive_tags_from_snippet(snippet)
    seen: set[str] = set()
    combined: list[str] = []
    for tag in snippet_tags + path_tags:
        if tag not in seen:
            seen.add(tag)
            combined.append(tag)
        if len(combined) >= MAX_CONCEPT_TAGS:
            break
    return combined


class ConceptTagScriptCoverage(TypedDict, total=False):
    latin_entry_count: int
    cjk_entry_count: int
    mixed_entry_count: int
    other_entry_count: int


def summarize_concept_tag_script_coverage(
    tag_lists: list[list[str]],
) -> ConceptTagScriptCoverage:
    """Aggregate per-entry script coverage stats.

    Mirrors OpenClaw's ``summarizeConceptTagScriptCoverage``. For each entry
    (list of tags), classify its dominant script family and count.
    """
    latin = 0
    cjk = 0
    mixed = 0
    other = 0
    for tags in tag_lists:
        if not tags:
            other += 1
            continue
        families = [_script_family(tag) for tag in tags]
        # Dominant family = most frequent
        from collections import Counter  # noqa: PLC0415

        dominant = Counter(families).most_common(1)[0][0]
        if dominant == "latin":
            latin += 1
        elif dominant == "cjk":
            cjk += 1
        elif dominant == "mixed":
            mixed += 1
        else:
            other += 1
    return {
        "latin_entry_count": latin,
        "cjk_entry_count": cjk,
        "mixed_entry_count": mixed,
        "other_entry_count": other,
    }


__all__ = [
    "MAX_CONCEPT_TAGS",
    "ConceptTagScriptCoverage",
    "derive_concept_tags",
    "summarize_concept_tag_script_coverage",
]
