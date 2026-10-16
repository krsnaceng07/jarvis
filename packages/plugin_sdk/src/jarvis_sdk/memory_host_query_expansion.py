r"""jarvis_sdk.memory_host_query_expansion — keyword extraction for FTS.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/query-expansion.ts`` (776 LOC).
Query expansion for FTS-only search mode. When no embedding
provider is available, the memory host falls back to FTS (full-text
search). FTS works best with specific keywords, but users often ask
conversational queries like "that thing we discussed yesterday" or
"之前讨论的那个方案". This module extracts meaningful keywords
from such queries to improve FTS results.

Public API:
- ``is_query_stop_word_token(token)`` — true for low-value
  conversational tokens that should not drive FTS matching.
- ``extract_keywords(query, opts)`` — extract meaningful keywords
  from a conversational query.

The tokenizer handles English, Chinese, Korean, and Japanese:
- English: whitespace + punctuation split, lowercased.
- Chinese (CJK): unigrams + bigrams by default; in trigram mode,
  whole contiguous CJK blocks are emitted.
- Japanese: per-script chunking (kana / kanji / ASCII) + kanji
  bigrams.
- Korean: whole-word tokenization + trailing-particle stripping.

Key port decisions:
- All 7 stop-word sets (en/es/pt/ar/ko/ja/zh) preserved verbatim.
- The KO_TRAILING_PARTICLES list is sorted by descending length
  (longest match wins). Mirrors the TS source's
  ``.toSorted((a, b) => b.length - a.length)``.
- Token regex patterns preserved: ``/[\s\p{P}]+/u`` for splitting,
  Hangul ranges ``\uac00-\ud7af\u3131-\u3163`` for KO detection,
  CJK ranges preserved.
- Helper types use ``frozenset`` (immutable + hashable) for the
  stop-word sets; ``SortedList`` for the particle list.
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

# Re-export the ``normalize_lowercase_string_or_empty`` helper from
# the SDK. Mirrors the TS source's
# ``import { normalizeLowercaseStringOrEmpty } from "@openclaw/normalization-core/string-coerce"``.
try:
    from jarvis_normalization_core.string_coerce import (
        normalize_lowercase_string_or_empty,  # type: ignore[attr-defined]
    )
except ImportError:  # pyright: ignore[reportMissingImports]

    def normalize_lowercase_string_or_empty(value: object) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip().lower()


# ── Stop-word sets (7 languages) ─────────────────────────────────────
# Each set is preserved verbatim from OpenClaw. The TS source uses
# ``new Set([...])``; the Python port uses ``frozenset`` for
# immutability + faster membership tests.

#: English stop words. Mirrors OpenClaw's ``STOP_WORDS_EN``.
STOP_WORDS_EN: frozenset[str] = frozenset(
    [
        # Articles and determiners
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        # Pronouns
        "i",
        "me",
        "my",
        "we",
        "our",
        "you",
        "your",
        "he",
        "she",
        "it",
        "they",
        "them",
        # Common verbs
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "can",
        "may",
        "might",
        # Prepositions
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "about",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "over",
        # Conjunctions
        "and",
        "or",
        "but",
        "if",
        "then",
        "because",
        "as",
        "while",
        "when",
        "where",
        "what",
        "which",
        "who",
        "how",
        "why",
        # Time references (vague)
        "yesterday",
        "today",
        "tomorrow",
        "earlier",
        "later",
        "recently",
        "before",
        "ago",
        "just",
        "now",
        # Vague references
        "thing",
        "things",
        "stuff",
        "something",
        "anything",
        "everything",
        "nothing",
        # Question words
        "please",
        "help",
        "find",
        "show",
        "get",
        "tell",
        "give",
    ]
)

#: Spanish stop words. Mirrors OpenClaw's ``STOP_WORDS_ES``.
STOP_WORDS_ES: frozenset[str] = frozenset(
    [
        # Articles and determiners
        "el",
        "la",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "este",
        "esta",
        "ese",
        "esa",
        # Pronouns
        "yo",
        "me",
        "mi",
        "nosotros",
        "nosotras",
        "tu",
        "tus",
        "usted",
        "ustedes",
        "ellos",
        "ellas",
        # Prepositions and conjunctions
        "de",
        "del",
        "a",
        "en",
        "con",
        "por",
        "para",
        "sobre",
        "entre",
        "y",
        "o",
        "pero",
        "si",
        "porque",
        "como",
        # Common verbs / auxiliaries
        "es",
        "son",
        "fue",
        "fueron",
        "ser",
        "estar",
        "haber",
        "tener",
        "hacer",
        # Time references (vague)
        "ayer",
        "hoy",
        "mañana",
        "antes",
        "despues",
        "después",
        "ahora",
        "recientemente",
        # Question/request words
        "que",
        "qué",
        "cómo",
        "cuando",
        "cuándo",
        "donde",
        "dónde",
        "porqué",
        "favor",
        "ayuda",
    ]
)

#: Portuguese stop words. Mirrors OpenClaw's ``STOP_WORDS_PT``.
STOP_WORDS_PT: frozenset[str] = frozenset(
    [
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "uns",
        "umas",
        "este",
        "esta",
        "esse",
        "essa",
        # Pronouns
        "eu",
        "me",
        "meu",
        "minha",
        "nos",
        "nós",
        "você",
        "vocês",
        "ele",
        "ela",
        "eles",
        "elas",
        # Prepositions and conjunctions
        "de",
        "do",
        "da",
        "em",
        "com",
        "por",
        "para",
        "sobre",
        "entre",
        "e",
        "ou",
        "mas",
        "se",
        "porque",
        "como",
        # Common verbs / auxiliaries
        "é",
        "são",
        "foi",
        "foram",
        "ser",
        "estar",
        "ter",
        "fazer",
        # Time references (vague)
        "ontem",
        "hoje",
        "amanhã",
        "antes",
        "depois",
        "agora",
        "recentemente",
        # Question/request words
        "que",
        "quê",
        "quando",
        "onde",
        "porquê",
        "favor",
        "ajuda",
    ]
)

#: Arabic stop words. Mirrors OpenClaw's ``STOP_WORDS_AR``.
STOP_WORDS_AR: frozenset[str] = frozenset(
    [
        # Articles and connectors
        "ال",
        "و",
        "أو",
        "لكن",
        "ثم",
        "بل",
        # Pronouns / references
        "أنا",
        "نحن",
        "هو",
        "هي",
        "هم",
        "هذا",
        "هذه",
        "ذلك",
        "تلك",
        "هنا",
        "هناك",
        # Common prepositions
        "من",
        "إلى",
        "الى",
        "في",
        "على",
        "عن",
        "مع",
        "بين",
        "ل",
        "ب",
        "ك",
        # Common auxiliaries / vague verbs
        "كان",
        "كانت",
        "يكون",
        "تكون",
        "صار",
        "أصبح",
        "يمكن",
        "ممكن",
        # Time references (vague)
        "بالأمس",
        "امس",
        "اليوم",
        "غدا",
        "الآن",
        "قبل",
        "بعد",
        "مؤخرا",
        # Question/request words
        "لماذا",
        "كيف",
        "ماذا",
        "متى",
        "أين",
        "هل",
        "من فضلك",
        "فضلا",
        "ساعد",
    ]
)

#: Korean stop words. Mirrors OpenClaw's ``STOP_WORDS_KO``.
STOP_WORDS_KO: frozenset[str] = frozenset(
    [
        # Particles (조사)
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "에서",
        "로",
        "으로",
        "와",
        "과",
        "도",
        "만",
        "까지",
        "부터",
        "한테",
        "에게",
        "께",
        "처럼",
        "같이",
        "보다",
        "마다",
        "밖에",
        "대로",
        # Pronouns (대명사)
        "나",
        "나는",
        "내가",
        "나를",
        "너",
        "우리",
        "저",
        "저희",
        "그",
        "그녀",
        "그들",
        "이것",
        "저것",
        "것것",
        "여기",
        "저기",
        "거기",
        # Common verbs / auxiliaries (일반 동사/보조 동사)
        "있다",
        "없다",
        "하다",
        "되다",
        "이다",
        "아니다",
        "보다",
        "주다",
        "오다",
        "가다",
        # Nouns (의존 명사 / vague)
        "것",
        "거",
        "등",
        "수",
        "때",
        "곳",
        "중",
        "분",
        # Adverbs
        "잘",
        "더",
        "또",
        "매우",
        "정말",
        "아주",
        "많이",
        "너무",
        "좀",
        # Conjunctions
        "그리고",
        "하지만",
        "그래서",
        "그런데",
        "그러나",
        "또는",
        "그러면",
        # Question words
        "왜",
        "어떻게",
        "뭐",
        "언제",
        "어디",
        "누구",
        "무엇",
        "어떤",
        # Time (vague)
        "어제",
        "오늘",
        "내일",
        "최근",
        "지금",
        "아까",
        "나중",
        "전에",
        # Request words
        "제발",
        "부탁",
    ]
)

#: Japanese stop words. Mirrors OpenClaw's ``STOP_WORDS_JA``.
STOP_WORDS_JA: frozenset[str] = frozenset(
    [
        # Pronouns and references
        "これ",
        "それ",
        "あれ",
        "この",
        "その",
        "あの",
        "ここ",
        "そこ",
        "あそこ",
        # Common auxiliaries / vague verbs
        "する",
        "した",
        "して",
        "です",
        "ます",
        "いる",
        "ある",
        "なる",
        "できる",
        # Particles / connectors
        "の",
        "こと",
        "もの",
        "ため",
        "そして",
        "しかし",
        "また",
        "でも",
        "から",
        "まで",
        "より",
        "だけ",
        # Question words
        "なぜ",
        "どう",
        "何",
        "いつ",
        "どこ",
        "誰",
        "どれ",
        # Time (vague)
        "昨日",
        "今日",
        "明日",
        "最近",
        "今",
        "さっき",
        "前",
        "後",
    ]
)

#: Chinese stop words. Mirrors OpenClaw's ``STOP_WORDS_ZH``.
STOP_WORDS_ZH: frozenset[str] = frozenset(
    [
        # Pronouns
        "我",
        "我们",
        "你",
        "你们",
        "他",
        "她",
        "它",
        "他们",
        "这",
        "那",
        "这个",
        "那个",
        "这些",
        "那些",
        # Auxiliary words
        "的",
        "了",
        "着",
        "过",
        "得",
        "地",
        "吗",
        "呢",
        "吧",
        "啊",
        "呀",
        "嘛",
        "啦",
        # Verbs (common, vague)
        "是",
        "有",
        "在",
        "被",
        "把",
        "给",
        "让",
        "用",
        "到",
        "去",
        "来",
        "做",
        "说",
        "看",
        "找",
        "想",
        "要",
        "能",
        "会",
        "可以",
        # Prepositions and conjunctions
        "和",
        "与",
        "或",
        "但",
        "但是",
        "因为",
        "所以",
        "如果",
        "虽然",
        "而",
        "也",
        "都",
        "就",
        "还",
        "又",
        "再",
        "才",
        "只",
        # Time (vague)
        "之前",
        "以前",
        "之后",
        "以后",
        "刚才",
        "现在",
        "昨天",
        "今天",
        "明天",
        "最近",
        # Vague references
        "东西",
        "事情",
        "事",
        "什么",
        "哪个",
        "哪些",
        "怎么",
        "为什么",
        "多少",
        # Question/request words
        "请",
        "帮",
        "帮忙",
        "告诉",
    ]
)

#: Korean trailing particles to strip from words for tokenization.
#: Sorted by descending length so longest-match-first is guaranteed.
#: Mirrors OpenClaw's ``KO_TRAILING_PARTICLES`` (sorted via
#: ``.toSorted((a, b) => b.length - a.length)``).
KO_TRAILING_PARTICLES: list[str] = sorted(
    [
        "에서",
        "으로",
        "에게",
        "한테",
        "처럼",
        "같이",
        "보다",
        "까지",
        "부터",
        "마다",
        "밖에",
        "대로",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "로",
        "와",
        "과",
        "도",
        "만",
    ],
    key=len,
    reverse=True,
)


# ── Public API ────────────────────────────────────────────────────────


def is_query_stop_word_token(token: str) -> bool:
    """True for low-value conversational tokens that should not drive FTS.

    Mirrors OpenClaw's ``isQueryStopWordToken``. Returns ``True``
    when ``token`` (case-sensitive) is a stop word in any of the 7
    supported languages.
    """
    return (
        token in STOP_WORDS_EN
        or token in STOP_WORDS_ES
        or token in STOP_WORDS_PT
        or token in STOP_WORDS_AR
        or token in STOP_WORDS_ZH
        or token in STOP_WORDS_KO
        or token in STOP_WORDS_JA
    )


# ── Private helpers (mirrors the TS source) ────────────────────────


_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
_HANGUL_JAMO_RE = re.compile(r"[\uac00-\ud7af\u3131-\u3163]")
_KANJI_RE = re.compile(r"[\u4e00-\u9fff]")
_KATAKANA_RE = re.compile(r"[\u30a0-\u30ffー]")
_HIRAGANA_RE = re.compile(r"[\u3040-\u309f]")
_JP_SCRIPT_RE = re.compile(r"[\u3040-\u30ff]")
_LATIN_RE = re.compile(r"^[a-zA-Z]+$")
_NUMBER_RE = re.compile(r"^\d+$")
# Use the ``regex`` module for Unicode property escapes (``\p{P}``,
# ``\p{S}``). The standard ``re`` module does not support them.
try:
    import regex as _regex_mod  # type: ignore[import-not-found]

    _PUNCT_ONLY_RE = _regex_mod.compile(r"^[\p{P}\p{S}]+$")
    _SEGMENT_SPLIT_RE = _regex_mod.compile(r"[\s\p{P}]+")
    _JP_PARTS_RE = _regex_mod.compile(
        r"[a-z0-9_]+|[\u30a0-\u30ffー]+|[\u4e00-\u9fff]+|[\u3040-\u309f]{2,}"
    )
except ImportError:  # pyright: ignore[reportMissingImports]
    # Fallback: use ``re`` without Unicode property escapes. The
    # OpenClaw source relies on Unicode property support, so the
    # fallback is a degraded mode (mostly works for ASCII text).
    _regex_mod = None  # type: ignore[assignment]
    _PUNCT_ONLY_RE = re.compile(r"^[\W_]+$", re.UNICODE)  # noqa: F821
    _SEGMENT_SPLIT_RE = re.compile(r"[\s\W_]+", re.UNICODE)  # noqa: F821
    _JP_PARTS_RE = re.compile(r"[a-z0-9_]+|[\u30a0-\u30ffー]+|[\u4e00-\u9fff]+|[\u3040-\u309f]{2,}")


def _strip_korean_trailing_particle(token: str) -> str | None:
    """Strip the longest matching Korean trailing particle.

    Mirrors OpenClaw's ``stripKoreanTrailingParticle``. Returns the
    stripped stem when a particle matched and the stem is longer
    than the particle; ``None`` otherwise.
    """
    for particle in KO_TRAILING_PARTICLES:
        if len(token) > len(particle) and token.endswith(particle):
            return token[: -len(particle)]
    return None


def _is_useful_korean_stem(stem: str) -> bool:
    """True when a stripped Korean stem is a useful search keyword.

    Mirrors OpenClaw's ``isUsefulKoreanStem``. Prevents bogus
    one-syllable Hangul stems (e.g. ``"논의"`` → ``"논"``) and
    keeps mixed-script ASCII stems (e.g. ``"API를"`` → ``"api"``).
    """
    if _HANGUL_RE.search(stem):
        return len(stem) >= 2
    return bool(re.match(r"^[a-z0-9_]+$", stem, re.IGNORECASE))


def _is_valid_keyword(token: str) -> bool:
    """Check if ``token`` looks like a meaningful keyword.

    Mirrors OpenClaw's ``isValidKeyword``. Filters out very short
    English words, pure numbers, and all-punctuation tokens.
    """
    if not token:
        return False
    # Skip very short English words (likely stop words or fragments)
    if _LATIN_RE.match(token) and len(token) < 3:
        return False
    # Skip pure numbers
    if _NUMBER_RE.match(token):
        return False
    # Skip all-punctuation tokens
    if _PUNCT_ONLY_RE.match(token):
        return False
    return True


def _tokenize(
    text: str,
    *,
    fts_tokenizer: Literal["unicode61", "trigram"] | None = None,
) -> list[str]:
    """Simple tokenizer for English/Chinese/Korean/Japanese text.

    Mirrors OpenClaw's ``tokenize``. Handles the four scripts
    differently:
    - English: split on whitespace + punctuation, lowercase.
    - Japanese: per-script chunking (kana / kanji / ASCII) +
      kanji bigrams.
    - Chinese (CJK): unigrams + bigrams by default; in trigram
      mode, whole contiguous CJK blocks are emitted.
    - Korean: whole-word tokenization + trailing-particle stripping.
    """
    use_trigram = fts_tokenizer == "trigram"
    tokens: list[str] = []
    normalized = normalize_lowercase_string_or_empty(text)

    # Split into segments (whitespace + unicode punctuation)
    segments = [s for s in _SEGMENT_SPLIT_RE.split(normalized) if s]

    for segment in segments:
        # Japanese text often mixes scripts (kanji/kana/ASCII)
        if _JP_SCRIPT_RE.search(segment):
            jp_parts = _JP_PARTS_RE.findall(segment)
            for part in jp_parts:
                if _KANJI_RE.match(part):
                    tokens.append(part)
                    if not use_trigram:
                        for i in range(len(part) - 1):
                            tokens.append(part[i : i + 2])
                else:
                    tokens.append(part)
        elif _KANJI_RE.search(segment):
            # Chinese: extract contiguous CJK chars
            chars = [c for c in segment if _KANJI_RE.match(c)]
            if use_trigram:
                block = "".join(chars)
                if block:
                    tokens.append(block)
            else:
                tokens.extend(chars)
                for i in range(len(chars) - 1):
                    tokens.append("".join(chars[i : i + 2]))
        elif _HANGUL_JAMO_RE.search(segment):
            # Korean: keep word unless it / its stem is a stop word
            stem = _strip_korean_trailing_particle(segment)
            stem_is_stop_word = stem is not None and stem in STOP_WORDS_KO
            if segment not in STOP_WORDS_KO and not stem_is_stop_word:
                tokens.append(segment)
            if stem is not None and stem not in STOP_WORDS_KO and _is_useful_korean_stem(stem):
                tokens.append(stem)
        else:
            # Non-CJK: keep as single token
            tokens.append(segment)

    return tokens


# ── Public entry point ──────────────────────────────────────────────


class ExtractKeywordsOptions(TypedDict, total=False):
    """Optional options for ``extract_keywords``.

    Mirrors the OpenClaw ``opts`` parameter:
    ``{ ftsTokenizer?: "unicode61" | "trigram" }``.
    """

    ftsTokenizer: Literal["unicode61", "trigram"]


def extract_keywords(
    query: str,
    opts: ExtractKeywordsOptions | None = None,
) -> list[str]:
    """Extract meaningful keywords from a conversational query for FTS search.

    Mirrors OpenClaw's ``extractKeywords``. Examples (from the
    OpenClaw docstring):

    - ``"that thing we discussed about the API"`` → ``["discussed", "API"]``
    - ``"之前讨论的那个方案"`` → ``["讨论", "方案"]``
    - ``"what was the solution for the bug"`` → ``["solution", "bug"]``

    The order is preserved (no sorting); duplicates are de-duplicated
    by insertion order via the internal ``seen`` set.
    """
    fts_tokenizer = opts.get("ftsTokenizer") if opts else None
    raw_tokens = _tokenize(query, fts_tokenizer=fts_tokenizer)
    keywords: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        if is_query_stop_word_token(token):
            continue
        if not _is_valid_keyword(token):
            continue
        if token in seen:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords


__all__ = [
    # Stop-word sets
    "STOP_WORDS_EN",
    "STOP_WORDS_ES",
    "STOP_WORDS_PT",
    "STOP_WORDS_AR",
    "STOP_WORDS_KO",
    "STOP_WORDS_JA",
    "STOP_WORDS_ZH",
    "KO_TRAILING_PARTICLES",
    # Public API
    "is_query_stop_word_token",
    "extract_keywords",
    "ExtractKeywordsOptions",
]
