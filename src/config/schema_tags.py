"""jarvis.config.schema_tags — config tag derivation for UI hints.

OpenClaw parity: mirrors ``openclaw-main/src/config/schema.tags.ts``.

Focused minimal port: the tag vocabulary + per-path tag derivation
exposed as Python helpers. The full UI-hint pass is delegated to
caller-provided callables.
"""
from __future__ import annotations

import re
from typing import List, Tuple


#: Stable config UI tag vocabulary used for filtering and grouping hints.
CONFIG_TAGS: Tuple[str, ...] = (
    "security", "auth", "network", "access", "privacy", "observability",
    "performance", "reliability", "storage", "models", "media", "automation",
    "channels", "tools", "advanced",
)


#: Tag ordering priority (lower index = higher priority).
TAG_PRIORITY: dict = {
    "security": 0,
    "auth": 1,
    "access": 2,
    "network": 3,
    "privacy": 4,
    "observability": 5,
    "reliability": 6,
    "performance": 7,
    "storage": 8,
    "models": 9,
    "media": 10,
    "automation": 11,
    "channels": 12,
    "tools": 13,
    "advanced": 14,
}


#: Per-path override tags (selected paths get explicit tag sets).
TAG_OVERRIDES: dict = {
    "cloudWorkers": ["network", "automation"],
    "gateway.auth.token": ["security", "auth", "access", "network"],
    "gateway.auth.password": ["security", "auth", "access", "network"],
    "gateway.push.apns.relay.baseUrl": ["network", "advanced"],
    "gateway.controlUi.embedSandbox": ["security", "access", "advanced"],
    "gateway.controlUi.allowExternalEmbedUrls": ["security", "access", "network", "advanced"],
    "gateway.controlUi.chatMessageMaxWidth": ["advanced"],
    "gateway.controlUi.toolTitles": ["advanced"],
    "gateway.controlUi.dangerouslyAllowHostHeaderOriginFallback": [
        "security", "access", "network", "advanced",
    ],
    "gateway.controlUi.dangerouslyDisableDeviceAuth": ["security", "access", "network", "advanced"],
    "gateway.controlUi.allowInsecureAuth": ["security", "access", "network", "advanced"],
    "gateway.nodes.pairing.autoApproveCidrs": ["security", "access", "network", "advanced"],
    "gateway.nodes.pairing.sshVerify": ["security", "access", "network", "advanced"],
    "mcp.apps.enabled": ["security", "access", "advanced"],
    "mcp.apps.sandboxOrigin": ["security", "network", "advanced"],
    "mcp.apps.sandboxPort": ["network", "advanced"],
    "gateway.nodes.pluginTools.enabled": ["tools", "security", "access", "network", "advanced"],
    "gateway.nodes.skills.enabled": ["tools", "security", "access", "network", "advanced"],
    "nodeHost.agentRuns.claude.enabled": ["tools", "security", "access", "network", "advanced"],
    "nodeHost.mcp.servers": ["tools", "network", "advanced"],
    "nodeHost.skills.enabled": ["tools", "network", "advanced"],
    "proxy.tls.caFile": ["security", "network", "storage", "advanced"],
    "tools.exec.applyPatch.workspaceOnly": ["tools", "security", "access", "advanced"],
    "tools.exec.mode": ["tools", "security", "access"],
}


#: Per-path prefix tag rules.
PREFIX_RULES: list = [
    ("cloudworkers.", ["network", "automation"]),
    ("channels.", ["channels", "network"]),
    ("tools.", ["tools"]),
    ("gateway.", ["network"]),
    ("nodehost.", ["network"]),
    ("discovery.", ["network"]),
    ("auth.", ["auth", "access"]),
    ("memory.", ["storage"]),
    ("models.", ["models"]),
    ("diagnostics.", ["observability"]),
    ("logging.", ["observability"]),
    ("cron.", ["automation"]),
    ("talk.", ["media"]),
    ("audio.", ["media"]),
]


#: Per-path keyword regex rules.
KEYWORD_RULES: list = [
    (re.compile(r"(token|password|secret|api[_.-]?key|tlsfingerprint)", re.IGNORECASE),
     ["security", "auth"]),
    (re.compile(r"(allow|deny|owner|permission|policy|access)", re.IGNORECASE),
     ["access"]),
    (re.compile(r"(timeout|debounce|interval|concurrency|max|limit|cachettl)", re.IGNORECASE),
     ["performance"]),
    (re.compile(r"(retry|backoff|fallback|circuit|health|reload|probe)", re.IGNORECASE),
     ["reliability"]),
    (re.compile(r"(path|dir|file|store|db|session|cache)", re.IGNORECASE),
     ["storage"]),
    (re.compile(r"(telemetry|trace|metrics|logs|diagnostic)", re.IGNORECASE),
     ["observability"]),
    (re.compile(r"(experimental|dangerously|insecure)", re.IGNORECASE),
     ["advanced", "security"]),
    (re.compile(r"(privacy|redact|sanitize|anonym|pseudonym)", re.IGNORECASE),
     ["privacy"]),
]


#: Extra path-pattern add-ons.
_MODEL_PATH = re.compile(r"(^|\.)(model|models|modelid|imagemodel)(\.|$)", re.IGNORECASE)
_MEDIA_PATH = re.compile(r"(tools\.media\.|^audio\.|^talk\.|image|video|stt|tts)", re.IGNORECASE)
_AUTOMATION_PATH = re.compile(r"(cron|heartbeat|schedule|onstart|watchdebounce)", re.IGNORECASE)
_AUTH_KEYWORD = re.compile(r"(token|password|secret|api[_.-]?key|credential|oauth)", re.IGNORECASE)


def normalize_tag(tag: str) -> str:
    """Return ``tag`` if it's a known config tag, else empty string."""
    if not isinstance(tag, str):
        return ""
    return tag if tag in CONFIG_TAGS else ""


def normalize_tags(tags) -> list:
    """Normalize + de-duplicate + sort ``tags`` by :data:`TAG_PRIORITY`."""
    seen: set = set()
    out: list = []
    for tag in tags or []:
        normalized = normalize_tag(tag)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return sorted(out, key=lambda t: TAG_PRIORITY.get(t, 99))


def collect_unknown_tags(tags) -> list:
    """Return tags that did not normalize (custom tags preserved after known ones)."""
    out: list = []
    seen: set = set()
    for tag in tags or []:
        if not isinstance(tag, str):
            continue
        normalized = tag.strip().lower()
        if not normalized:
            continue
        if normalize_tag(normalized) or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def resolve_override(path: str) -> list:
    """Return the override tag set for ``path`` (None when no override matches)."""
    if path in TAG_OVERRIDES:
        return list(TAG_OVERRIDES[path])
    return None


def derive_tags_for_path(path: str, hint=None) -> list:
    """Derive the canonical tag set for ``path`` using the upstream rule table."""
    override = resolve_override(path)
    if override is not None:
        return normalize_tags(override)
    tags: set = set()
    lower = path.lower() if isinstance(path, str) else ""
    for prefix, prefix_tags in PREFIX_RULES:
        if lower.startswith(prefix):
            tags.update(prefix_tags)
    for pattern, kw_tags in KEYWORD_RULES:
        if pattern.search(path):
            tags.update(kw_tags)
    if _MODEL_PATH.search(path):
        tags.add("models")
    if _MEDIA_PATH.search(path):
        tags.add("media")
    if _AUTOMATION_PATH.search(path):
        tags.add("automation")
    if hint and isinstance(hint, dict) and hint.get("sensitive"):
        tags.add("security")
        if _AUTH_KEYWORD.search(path):
            tags.add("auth")
    if hint and isinstance(hint, dict) and hint.get("advanced"):
        tags.add("advanced")
    if not tags:
        tags.add("advanced")
    return normalize_tags(sorted(tags, key=lambda t: TAG_PRIORITY.get(t, 99)))


def apply_derived_tags(hints: dict) -> dict:
    """Return a copy of ``hints`` with derived tags merged ahead of any existing ones.

    Mirrors :func:`applyDerivedTags`
    (``shared/config/schema.tags.ts`).
    """
    if not isinstance(hints, dict):
        return {}
    out: dict = {}
    for path, hint in hints.items():
        if not isinstance(hint, dict):
            hint = {}
        existing = list(hint.get("tags") or [])
        derived = derive_tags_for_path(path, hint)
        tags = [
            *normalize_tags([*derived, *existing]),
            *collect_unknown_tags(existing),
        ]
        out[path] = {**hint, "tags": tags}
    return out


__all__ = [
    "CONFIG_TAGS",
    "TAG_PRIORITY",
    "TAG_OVERRIDES",
    "PREFIX_RULES",
    "KEYWORD_RULES",
    "normalize_tag",
    "normalize_tags",
    "collect_unknown_tags",
    "resolve_override",
    "derive_tags_for_path",
    "apply_derived_tags",
]
