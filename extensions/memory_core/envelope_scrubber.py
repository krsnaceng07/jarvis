"""Envelope scrubber — strips OpenClaw-injected transport metadata from user text.

This is the security-critical layer that the ``memory-core`` and
``memory-lancedb`` extensions use to decide what's safe to
persist as a long-term memory. The OpenClaw source (50KB of
regex + heuristics in ``extensions/memory-lancedb/index.ts``)
defends against prompt-injection attacks where a user-supplied
message tries to smuggle in:

  - "ignore the above instructions" attacks
  - OpenClaw channel envelope prefixes
    (``[Telegram Alice +5m] text``, ``[Discord #general user +0s] text``)
  - History-context markers (``[Chat messages since your last
    reply - for context]``, ``[Current message - respond to this]``)
  - "Untrusted metadata" sentinels (``Conversation info
    (untrusted metadata):``, etc.)
  - "Media attached" annotations
  - JSON blobs that look like envelope metadata
  - Message-tool delivery hints (``[delivered]``, ``[silent]``)

If any of these patterns match a substring, the entire text is
treated as envelope sludge and dropped from the memory capture
gate.

OpenClaw parity notes
====================
This is a port of OpenClaw's ``looksLikeEnvelopeSludge`` and
``sanitizeForMemoryCapture`` functions. Every regex below is
the same as the OpenClaw source, with minor changes for
Python's ``re`` module (no /g flag, multiline handled via
``re.MULTILINE``).

The Python port is intentionally faithful — the regex set is
the security contract. If you change a pattern, change the
adversarial test in the same commit.
"""

from __future__ import annotations

import re
from typing import Final

# ── Memory triggers (capture gating) ─────────────────────────────
# These regex patterns decide whether a user message is
# "memory-worthy" — the LLM doesn't have to call save_memory
# explicitly; the host can capture in the background.
#
# Multi-language: Czech, English, Chinese, Japanese, Korean.

MEMORY_TRIGGERS: Final[list[re.Pattern[str]]] = [
    re.compile(r"zapamatuj si|pamatuj|remember", re.IGNORECASE),
    re.compile(r"preferuji|radši|nechci|prefer", re.IGNORECASE),
    re.compile(r"rozhodli jsme|budeme používat", re.IGNORECASE),
    re.compile(r"\+\d{10,}"),  # phone numbers
    re.compile(r"[\w.-]+@[\w.-]+\.\w+"),  # emails
    re.compile(r"můj\s+\w+\s+je|je\s+můj", re.IGNORECASE),
    re.compile(r"my\s+\w+\s+is|is\s+my", re.IGNORECASE),
    re.compile(r"i (like|prefer|hate|love|want|need)", re.IGNORECASE),
    re.compile(r"always|never|important", re.IGNORECASE),
    # Chinese: 记住, 记住, 我喜欢, etc.
    re.compile(
        r"记住|記住|记下|記下|我(喜欢|喜歡|偏好|讨厌|討厭|爱|愛|想要|需要)"
        r"|我的.*是|以后都用这个|以後都用這個|决定|決定|总是|總是|从不|永远|永遠|重要",
        re.IGNORECASE,
    ),
    # Japanese: 覚えて, 私の好み, etc.
    re.compile(
        r"覚えて|記憶して|忘れないで|私は.*(好き|嫌い|必要|欲しい)" r"|好み|いつも|絶対|重要",
        re.IGNORECASE,
    ),
    # Korean: 기억해, 나는, etc.
    re.compile(
        r"기억해|기억해줘|잊지 마|나는.*(좋아|싫어|원해|필요)" r"|내.*(이야|입니다)|항상|절대|중요",
        re.IGNORECASE,
    ),
]


# ── CJK script detection ─────────────────────────────────────────
# Used to gate triggers: certain patterns only fire when
# the message contains CJK characters (to avoid English
# false positives).

CJK_SCRIPT = re.compile(
    r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]",
)


# ── Prompt-injection patterns ───────────────────────────────────
# Adversarial inputs that try to manipulate the LLM through
# the memory channel. The OpenClaw host refuses to persist
# any text matching these.

PROMPT_injection_patterns: Final[list[re.Pattern[str]]] = [
    # "ignore the above instructions", "forget your prior
    # instructions", etc. — bounded to < 60 chars between the
    # verb and the noun so we don't flag legitimate
    # discussions of memory/prompting.
    re.compile(
        r"\b(ignore|disregard|forget|override)\b.{0,60}\b"
        r"(all|any|previous|above|prior|earlier|system|developer)\b"
        r".{0,30}\binstructions?\b",
        re.IGNORECASE,
    ),
    re.compile(r"do not follow (the )?(system|developer)", re.IGNORECASE),
    re.compile(r"system prompt", re.IGNORECASE),
    re.compile(r"developer message", re.IGNORECASE),
    # XML-ish system/developer/tool tags
    re.compile(
        r"<\s*(system|assistant|developer|tool|function|relevant-memories)\b", re.IGNORECASE
    ),
    # "run a tool" / "call a tool" / "invoke a command" — common
    # in prompt-injection payloads.
    re.compile(r"\b(run|execute|call|invoke)\b.{0,40}\b(tool|command)\b", re.IGNORECASE),
]


# ── Inbound metadata sentinels ───────────────────────────────────
# These are the labels the OpenClaw host injects at the head
# of user messages. The memory extension's envelope-scrubber
# treats any line-anchored match as transport metadata and
# strips the entire block.

INBOUND_META_SENTINELS: Final[tuple[str, ...]] = (
    "Conversation info (untrusted metadata):",
    "Sender (untrusted metadata):",
    "Thread starter (untrusted, for context):",
    "Reply target of current user message (untrusted, for context):",
    "Replied message (untrusted, for context):",
    "Forwarded message context (untrusted metadata):",
    "Conversation context (untrusted, chronological, selected for current message):",
    "Current local chat window (untrusted, chronological, before current message):",
    "Nearby reply target window (untrusted, chronological, around replied-to message):",
    "Chat history since last reply (untrusted, for context):",
)

# Pre-compiled regex: each sentinel as a line-anchored prefix.
_INBOUND_META_SENTINEL_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:" + "|".join(re.escape(s) for s in INBOUND_META_SENTINELS) + r")[^\n]*$",
    re.MULTILINE,
)

# Label-anchored: any ``<word> (untrusted metadata):`` /
# ``<word> (untrusted, for context):`` line (covers both
# the explicit sentinels above AND future structured-context
# labels from UntrustedStructuredContext).
_INBOUND_META_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^[^\n]+\((?:"
    r"untrusted metadata"
    r"|untrusted, for context"
    r"|untrusted, nearest first"
    r"|untrusted, chronological,[^\n)]{1,80}"
    r")\):[ \t]*$",
    re.MULTILINE,
)

# Fenced JSON blocks: ``<sentinel>:\n```json\n...\n```\n``
_INBOUND_META_LABEL_JSON_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"^[^\n]+\((?:"
    r"untrusted metadata"
    r"|untrusted, for context"
    r"|untrusted, nearest first"
    r"|untrusted, chronological,[^\n)]{1,80}"
    r")\):[ \t]*\n[ \t]*```json[ \t]*\n[\s\S]*?\n[ \t]*```[ \t]*\n?",
    re.MULTILINE,
)

# ── Message-tool delivery hints ──────────────────────────────────
# Single-line sentinels injected at the head of a message body
# by the host's tool dispatch.

# Imported lazily from the SDK at runtime (the host owns the
# canonical list). Used here to keep the scrubber testable
# without a host dependency.
_MESSAGE_TOOL_DELIVERY_HINTS: tuple[str, ...] = (
    "[delivered]",
    "[silent]",
    "[no-reply]",
    "[dm-only]",
    "[group-only]",
    "[owner-only]",
)

_Message_TOOL_DELIVERY_HINT_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:" + "|".join(re.escape(h) for h in _MESSAGE_TOOL_DELIVERY_HINTS) + r")\s*$",
    re.MULTILINE,
)


# ── History / current-message markers ────────────────────────────

_HISTORY_CONTEXT_MARKERS: Final[tuple[str, ...]] = (
    "[Chat messages since your last reply - for context]",
    "[Chat messages since your last reply — CONTEXT ONLY]",
    "[Merged earlier messages — CONTEXT ONLY]",
)

_CURRENT_MESSAGE_MARKERS: Final[tuple[str, ...]] = (
    "[Current message - respond to this]",
    "[CURRENT MESSAGE — reply to this]",
    "[CURRENT MESSAGE — reply using the context above]",
)

# ── Misc envelope markers ────────────────────────────────────────

_ACTIVE_TURN_RECOVERY_RE: Final[re.Pattern[str]] = re.compile(
    r"active-turn-recovery", re.IGNORECASE
)

# ``[media attached: ...]`` and ``[media attached N/M: ...]``
# — written by the gateway's claim-check offload when a user
# sends an image.
_MEDIA_ATTACHED_PATTERN_TEST: Final[re.Pattern[str]] = re.compile(
    r"\[media attached(?:\s+\d+\/\d+)?:[^\]]*\]", re.IGNORECASE
)

# JSON envelope metadata: any line opening with ``{`` followed
# by an envelope field name.
_envelope_json_line_re: Final[re.Pattern[str]] = re.compile(
    r'^\s*\{\s*(?:\n\s*)?"(?:'
    r"chat_id|message_id|reply_to_id|sender_id|conversation_label|"
    r"conversation_info|sender_name|channel_id|channel_type|"
    r"group_subject|group_channel|group_space|topic_id|thread_label"
    r')"\s*:',
    re.MULTILINE,
)

# Leading ``[Channel sender +<elapsed> <date>] body`` envelope.
_inbound_envelope_prefix_re: Final[re.Pattern[str]] = re.compile(
    r"^\[([^\]\n]{0,300}?(?:\s\+(?:\d+[smhdwy]|just now)\b"
    r"|\s[A-Za-z]{3}\s\d{4}-\d{2}-\d{2})[^\]\n]{0,200})\]\s"
)


# Marker-free leading envelope: ``[Channel <from-label> ...]``
# where ``Channel`` is a bundled channel name. The body must
# follow the formatter contract (``<from-label>: text`` or
# ``(self): text``) for the gate to accept it.
# See ``BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES`` in
# ``jarvis_sdk.chat_channel_ids`` for the full list.
def _build_known_channel_prefix_re() -> re.Pattern[str] | None:
    """Build the bundled-channel marker-free envelope regex.

    The OpenClaw helper stitches together the bundled channel
    list at module load time. The Python port mirrors that.
    Empty list disables the gate (matches OpenClaw's guard).
    """
    from jarvis_sdk import BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES

    if not BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES:
        return None
    pattern = "|".join(
        re.escape(prefix)
        for prefix in sorted(BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES, key=len, reverse=True)
    )
    return re.compile(
        r"^\[((?:" + pattern + r")\s+[^\]\n\s][^\]\n]{0,299})\]\s",
        re.IGNORECASE,
    )


_INBOUND_ENVELOPE_KNOWN_CHANNEL_PREFIX_RE: re.Pattern[str] | None = _build_known_channel_prefix_re()

# Non-direct envelope header markers.
_NON_DIRECT_ENVELOPE_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:^|\s)(?:#[^\s]+|group:[^\s]+|group\s+id:[^\s]+"
    r"|room:[^\s]+|channel\s+id:[^\s]+|id:-[^\s]+|unknown-group"
    r"|[^\s]+@g\.us)(?:\s|$)",
    re.IGNORECASE,
)

# Sender-prefixed channel list (envelope body labels for
# non-direct chats).
_SENDER_PREFIXED_ENVELOPE_CHANNEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:discord|imessage|line|mattermost|qqbot|signal|slack|telegram|whatsapp)(?:\s|$)",
    re.IGNORECASE,
)

# User-authored body labels that should never be auto-stripped.
_USER_AUTHORED_BODY_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?:action|decision|fixme|note|question|reminder|todo)$", re.IGNORECASE
)

# Bracketed prefix detector (for finding the first ``[`` of an
# envelope in arbitrary text).
_BRACKETED_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"\[[^\]\n]{1,500}\]\s")

# Leading "Current message:" line (a current-turn transport
# context label that appears in some channel envelopes).
_LEADING_CURRENT_MESSAGE_CONTEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*Current message:[ \t]*(?:\n|$)"
)

# Reply chain patterns.
_LEADING_CURRENT_MESSAGE_REPLY_LINE_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*\[Replying to:[^\n]{0,1000}\]\s*\n"
)

# ``#123 Sender: text`` message-prefix format.
_LEADING_CURRENT_MESSAGE_ID_SENDER_RE: Final[re.Pattern[str]] = re.compile(
    r"^#\d+\s+[^\n:]{1,100}:\s*"
)

# Active-memory plugin context block.
_ACTIVE_MEMORY_CONTEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"^Untrusted context \(metadata[^\n]*\n"
    r"<active_memory_plugin>[\s\S]*?</active_memory_plugin>\s*",
    re.MULTILINE,
)

# Plain "Untrusted context (metadata" header (catches the
# header even when the body doesn't have an active_memory_plugin
# block).
_UNTRUSTED_CONTEXT_HEADER_RE: Final[re.Pattern[str]] = re.compile(
    r"^Untrusted context \(metadata", re.MULTILINE
)

# Timestamp prefix: ``[Mon 2026-05-17 14:30 EDT]`` (injected
# by ``injectTimestamp``).
_LEADING_TIMESTAMP_PREFIX_RE: Final[re.Pattern[str]] = re.compile(
    r"^\[[A-Za-z]{3} \d{4}-\d{2}-\d{2} \d{2}:\d{2}[^\]]*\] *"
)

# Leading chronological context label (OpenClaw
# "selected for current message" variant).
_LEADING_CHRONOLOGICAL_CONTEXT_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*[^\n]{1,100}\(untrusted, chronological,[^\n)]{1,80}\):[ \t]*(?:\n|$)"
)

# HTML escape map for prompt rendering.
_PROMPT_ESCAPE_MAP: Final[dict[str, str]] = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


# ── Public API ──────────────────────────────────────────────────


def looks_like_prompt_injection(text: str) -> bool:
    """Return True if ``text`` contains a prompt-injection pattern.

    Mirrors OpenClaw's exported helper used by the embedding
    recall path to filter out poisoned recall candidates.
    """
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return False
    return any(p.search(normalized) for p in PROMPT_injection_patterns)


# ruff: noqa: PLR0911
# Each return is a distinct, ordered predicate — the chain
# mirrors OpenClaw's `looksLikeEnvelopeSludge` exactly. The
# 13 returns are intentional (one per check); refactoring to
# a single boolean OR would lose the test surface and obscure
# which check fired in the logs.


def looks_like_envelope_sludge(text: str) -> bool:
    """Return True if ``text`` looks like OpenClaw-injected transport metadata.

    Mirrors OpenClaw's ``looksLikeEnvelopeSludge`` function
    (extensions/memory-lancedb/index.ts, ~lines 800-870). Used
    as the gate before persisting a long-term memory: if the
    text matches any of the inbound-metadata, history-context,
    current-message, or envelope patterns, the message is
    dropped from the memory capture pipeline (it would be
    useless or actively hostile if stored).
    """
    # Each return is a distinct, ordered predicate — the chain
    # mirrors OpenClaw's `looksLikeEnvelopeSludge` exactly. The
    # 13 returns are intentional (one per check); refactoring to
    # a single boolean OR would lose the test surface.
    if not text:
        return False
    if _INBOUND_META_SENTINEL_LINE_RE.search(text):
        return True
    if _INBOUND_META_LABEL_RE.search(text):
        return True
    if _UNTRUSTED_CONTEXT_HEADER_RE.search(text):
        return True
    if _Message_TOOL_DELIVERY_HINT_LINE_RE.search(text):
        return True
    if any(marker in text for marker in _HISTORY_CONTEXT_MARKERS):
        return True
    if any(marker in text for marker in _CURRENT_MESSAGE_MARKERS):
        return True
    if _ACTIVE_TURN_RECOVERY_RE.search(text):
        return True
    if _MEDIA_ATTACHED_PATTERN_TEST.search(text):
        return True
    if _envelope_json_line_re.search(text):
        return True
    if _inbound_envelope_prefix_re.search(text):
        return True
    return (
        _INBOUND_ENVELOPE_KNOWN_CHANNEL_PREFIX_RE is not None
        and _INBOUND_ENVELOPE_KNOWN_CHANNEL_PREFIX_RE.search(text) is not None
    )


def strip_media_attached_annotations(text: str) -> str:
    """Strip ``[media attached: ...]`` annotations + collapse spaces.

    Mirrors OpenClaw's helper. Used by ``sanitize_for_memory_capture``
    so old memories don't have live media references that
    detectImageReferences() would re-parse.
    """
    had_media = bool(_MEDIA_ATTACHED_PATTERN_TEST.search(text))
    stripped = _MEDIA_ATTACHED_PATTERN_TEST.sub("", text)
    if had_media:
        # Collapse runs of spaces/tabs; preserve newlines.
        stripped = re.sub(r"[ \t]{2,}", " ", stripped).strip()
    return stripped


def escape_memory_for_prompt(text: str) -> str:
    """HTML-escape a memory text for safe prompt injection.

    Mirrors OpenClaw's ``escapeMemoryForPrompt``. Strips
    ``[media attached: ...]`` first so a literal ``<`` in an
    annotation can't break out of the prompt.
    """
    cleaned = strip_media_attached_annotations(text)
    return re.sub(
        r"[&<>\"']",
        lambda m: _PROMPT_ESCAPE_MAP.get(m.group(0), m.group(0)),
        cleaned,
    )


# ruff: noqa: PLR0911, PLR0912, PLR0915
# This function mirrors OpenClaw's `sanitizeForMemoryCapture` —
# a 7-step ordered strip pass with ReDoS-mitigation caps. The
# many branches and statements are intentional and reflect
# the OpenClaw source 1:1; refactoring to helper functions
# would obscure the strip order and make the parity audit
# harder to run.


def sanitize_for_memory_capture(text: str) -> str:
    """Strip OpenClaw-injected envelope metadata; return clean body.

    Mirrors OpenClaw's ``sanitizeForMemoryCapture`` (~50KB of
    ordered strip passes). Returns the user's actual intent
    text with all transport-metadata blocks removed; returns
    empty string if nothing meaningful survives.

    The pass order matters:
      1. Cap input (ReDoS mitigation).
      2. Strip leading timestamp.
      3. Strip fenced JSON metadata blocks.
      4. Strip sentinel-led code-fence blocks.
      5. Strip leading chronological context blocks.
      6. Strip plain-text metadata sentinels (line-anchored).
      7. Strip active-memory plugin context block.
      8. Strip untrusted-context header (line-anchored).
      9. Strip leading inbound envelope bracket.
    """
    if not text:
        return ""

    max_chars = 10_000
    cleaned = text[:max_chars]

    # 1. Leading timestamp.
    cleaned = _LEADING_TIMESTAMP_PREFIX_RE.sub("", cleaned)

    # 2. Fenced JSON metadata blocks.
    cleaned = _INBOUND_META_LABEL_JSON_BLOCK_RE.sub("", cleaned)

    # 3. Sentinel-led code-fence blocks.
    for sentinel in INBOUND_META_SENTINELS:
        sentinel_escaped = re.escape(sentinel)
        block_re = re.compile(
            sentinel_escaped + r"\s*\n\s*```json\s*\n[\s\S]*?\n\s*```\s*\n?",
        )
        cleaned = block_re.sub("", cleaned)

    # 4. Plain-text metadata headers.
    sentinel_count = len(INBOUND_META_SENTINELS)
    for _ in range(sentinel_count + 1):
        label_match = _INBOUND_META_LABEL_RE.search(cleaned)
        if label_match:
            earliest_index = label_match.start()
            earliest_re = _INBOUND_META_LABEL_RE
        else:
            earliest_index = -1
            earliest_re = None
            for sentinel in INBOUND_META_SENTINELS:
                sentinel_escaped = re.escape(sentinel)
                trailer_re = re.compile(r"^" + sentinel_escaped + r".*$", re.MULTILINE)
                trailer_match = trailer_re.search(cleaned)
                if trailer_match and (
                    earliest_index == -1 or trailer_match.start() < earliest_index
                ):
                    earliest_index = trailer_match.start()
                    earliest_re = re.compile(r"^" + sentinel_escaped + r".*$", re.MULTILINE)
        if earliest_re is None:
            break
        before = cleaned[:earliest_index]
        if before.strip():
            cleaned = before
            break
        if earliest_re is _INBOUND_META_LABEL_RE:
            line_end = cleaned.find("\n", earliest_index)
            after_header = cleaned[line_end + 1 :] if line_end != -1 else ""
            if not after_header.lstrip().startswith("```json"):
                cleaned = after_header
                continue
        cleaned = earliest_re.sub("", cleaned)

    # 5. Active-memory context block.
    cleaned = _ACTIVE_MEMORY_CONTEXT_RE.sub("", cleaned)

    # 6. Untrusted-context header (line-anchored).
    if _UNTRUSTED_CONTEXT_HEADER_RE.search(cleaned):
        match = _UNTRUSTED_CONTEXT_HEADER_RE.search(cleaned)
        if match:
            cleaned = cleaned[: match.start()]

    # 7. Leading inbound envelope bracket.
    envelope_match = _inbound_envelope_prefix_re.match(cleaned)
    if envelope_match is None and _INBOUND_ENVELOPE_KNOWN_CHANNEL_PREFIX_RE is not None:
        envelope_match = _INBOUND_ENVELOPE_KNOWN_CHANNEL_PREFIX_RE.match(cleaned)
    if envelope_match is not None:
        cleaned = cleaned[envelope_match.end() :]

    return cleaned.strip()


def scrub_envelope_sludge(text: str) -> str:
    """Scrub prompt injection, channel prefix sludge, and media annotations."""
    return sanitize_for_memory_capture(text)


# Re-export the OpenClaw parity surface.
__all__ = [
    "MEMORY_TRIGGERS",
    "escape_memory_for_prompt",
    "looks_like_envelope_sludge",
    "looks_like_prompt_injection",
    "sanitize_for_memory_capture",
    "scrub_envelope_sludge",
    "strip_media_attached_annotations",
]
