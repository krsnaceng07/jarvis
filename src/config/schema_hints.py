"""jarvis.config.schema_hints — schema hint metadata for config UI.

OpenClaw parity: mirrors ``openclaw-main/src/config/schema.hints.ts``.

Focused minimal port: exposes the public hint-builder surface. The
heavy zod-walking and sensitive-path mapping are delegated to
caller-provided callables until those subsystems land.
"""
from __future__ import annotations

from typing import Any, Optional


#: Group labels keyed by top-level config section name.
GROUP_LABELS: dict = {
    "wizard": "Wizard",
    "update": "Update",
    "cli": "CLI",
    "diagnostics": "Diagnostics",
    "logging": "Logging",
    "gateway": "Gateway",
    "nodeHost": "Node Host",
    "cloudWorkers": "Cloud Workers",
    "agents": "Agents",
    "tools": "Tools",
    "bindings": "Bindings",
    "audio": "Audio",
    "models": "Models",
    "messages": "Messages",
    "commands": "Commands",
    "session": "Session",
    "cron": "Cron",
    "worktrees": "Worktrees",
    "hooks": "Hooks",
    "ui": "UI",
    "browser": "Browser",
    "talk": "Talk",
    "channels": "Messaging Channels",
    "skills": "Skills",
    "plugins": "Plugins",
    "discovery": "Discovery",
    "presence": "Presence",
    "voicewake": "Voice Wake",
}


#: Group ordering priorities (lower = earlier).
GROUP_ORDER: dict = {
    "wizard": 20, "update": 25, "cli": 26, "diagnostics": 27,
    "gateway": 30, "nodeHost": 35, "cloudWorkers": 37,
    "agents": 40, "tools": 50, "bindings": 55, "audio": 60,
    "models": 70, "messages": 80, "commands": 85, "session": 90,
    "cron": 100, "worktrees": 105, "hooks": 110, "ui": 120,
    "browser": 130, "talk": 140, "channels": 150, "skills": 200,
    "plugins": 205, "discovery": 210, "presence": 220, "voicewake": 230,
    "logging": 900,
}


#: Field placeholder text keyed by config path.
FIELD_PLACEHOLDERS: dict = {
    "gateway.remote.url": "ws://host:18789",
    "gateway.remote.tlsFingerprint": "sha256:ab12cd34…",
    "gateway.remote.sshTarget": "user@host",
    "gateway.remote.sshHostKeyPolicy": "strict",
    "gateway.controlUi.basePath": "/openclaw",
    "gateway.controlUi.root": "dist/control-ui",
    "gateway.controlUi.allowedOrigins": "https://control.example.com",
    "gateway.push.apns.relay.baseUrl": "https://ios-push-relay.openclaw.ai",
    "channels.mattermost.baseUrl": "https://chat.example.com",
    "agents.list[].identity.avatar": "avatars/openclaw.png",
}


#: Sensitive-URL hint tag.
SENSITIVE_URL_HINT_TAG = "sensitive-url"


def is_kernel_owned_channel_hint_path(path: Any) -> bool:
    """Return whether ``path`` is a kernel-owned channel namespace entry."""
    if not isinstance(path, str):
        return False
    if path == "channels":
        return True
    for prefix in ("channels.defaults", "channels.modelByChannel"):
        if path == prefix or path.startswith(f"{prefix}."):
            return True
    return False


def is_plugin_owned_channel_hint_path(path: Any) -> bool:
    """Return whether ``path`` belongs to a plugin-owned channel namespace."""
    if not isinstance(path, str) or not path.startswith("channels."):
        return False
    return not is_kernel_owned_channel_hint_path(path)


def build_base_hints(
    *,
    field_labels: Optional[dict] = None,
    field_help: Optional[dict] = None,
    apply_derived_tags_fn=None,
) -> dict:
    """Build core config UI hints (without the plugin-owned channel namespaces)."""
    out: dict = {}
    for group, label in GROUP_LABELS.items():
        out[group] = {"label": label, "group": label, "order": GROUP_ORDER[group]}
    labels = field_labels or {}
    for path, label in labels.items():
        if is_plugin_owned_channel_hint_path(path):
            continue
        existing = out.get(path)
        out[path] = existing if existing else {"label": label}
        if not existing:
            out[path] = {"label": label}
        else:
            out[path] = {**existing, "label": label}
    for path, help_text in (field_help or {}).items():
        if is_plugin_owned_channel_hint_path(path):
            continue
        existing = out.get(path) or {}
        out[path] = {**existing, "help": help_text}
    for path, placeholder in FIELD_PLACEHOLDERS.items():
        if is_plugin_owned_channel_hint_path(path):
            continue
        existing = out.get(path) or {}
        out[path] = {**existing, "placeholder": placeholder}
    if callable(apply_derived_tags_fn):
        out = apply_derived_tags_fn(out)
    return out


def apply_sensitive_hints(hints: dict, allowed_keys=None) -> dict:
    """Mark sensitive config paths in a hint map (without overwriting explicit sensitivity).

    Mirrors :func:`applySensitiveHints`
    (``shared/config/schema.hints.ts`).
    """
    if not isinstance(hints, dict):
        return {}
    keys = list(allowed_keys) if allowed_keys else list(hints.keys())
    out: dict = {k: v for k, v in hints.items()}
    for key in keys:
        current = out.get(key) or {}
        if not isinstance(current, dict):
            continue
        if "sensitive" in current:
            continue
        # Without the real ``is_sensitive_config_path`` call we approximate by
        # a structural check; the focused minimal port uses the helper
        # exported by ``src.config.sensitive_paths``.
        from src.config.sensitive_paths import is_sensitive_config_path
        if is_sensitive_config_path(key):
            out[key] = {**current, "sensitive": True}
    return out


def apply_sensitive_url_hints(
    hints: dict,
    allowed_keys=None,
    *,
    is_sensitive_url_config_path_fn=None,
) -> dict:
    """Add the sensitive-url tag to hint paths that carry credential-risk URLs."""
    if not isinstance(hints, dict):
        return {}
    keys = list(allowed_keys) if allowed_keys else list(hints.keys())
    out: dict = {k: v for k, v in hints.items()}
    for key in keys:
        if not callable(is_sensitive_url_config_path_fn):
            continue
        if not is_sensitive_url_config_path_fn(key):
            continue
        current = out.get(key) or {}
        if not isinstance(current, dict):
            current = {}
        tags = set(current.get("tags") or [])
        tags.add(SENSITIVE_URL_HINT_TAG)
        out[key] = {**current, "tags": list(tags)}
    return out


def collect_matching_schema_paths(
    schema: Any,
    path: str = "",
    matches_path=None,
) -> set:
    """Walk a schema-shaped dict and collect concrete/wildcard paths matching ``matches_path``.

    The focused minimal port walks a plain dict shape rather than a real
    zod schema; the zod walker lands with the schema validator port.
    """
    if not isinstance(schema, dict) or not callable(matches_path):
        return set()
    out: set = set()
    if matches_path(path):
        out.add(path)
    props = schema.get("properties")
    if isinstance(props, dict):
        for key, child in props.items():
            child_path = f"{path}.{key}" if path else key
            out |= collect_matching_schema_paths(child, child_path, matches_path)
    addl = schema.get("additionalProperties")
    if isinstance(addl, dict):
        wild_path = f"{path}.*" if path else "*"
        out |= collect_matching_schema_paths(addl, wild_path, matches_path)
    items = schema.get("items")
    if isinstance(items, dict):
        item_path = f"{path}[]" if path else "[]"
        out |= collect_matching_schema_paths(items, item_path, matches_path)
    return out


def map_sensitive_paths(schema: Any, path: str, hints: dict) -> dict:
    """Mark every sensitive path under ``schema`` in the hint map.

    The focused minimal port delegates the schema walk to
    :func:`collect_matching_schema_paths` so the real zod walker can
    land later without changing this contract.
    """
    if not isinstance(hints, dict):
        return {}
    from src.config.sensitive_paths import is_sensitive_config_path
    out: dict = {k: v for k, v in hints.items()}
    matches = collect_matching_schema_paths(
        schema, path, lambda p: is_sensitive_config_path(p),
    )
    for key in matches:
        current = out.get(key) or {}
        if not isinstance(current, dict):
            current = {}
        out[key] = {**current, "sensitive": True}
    return out


__all__ = [
    "GROUP_LABELS",
    "GROUP_ORDER",
    "FIELD_PLACEHOLDERS",
    "SENSITIVE_URL_HINT_TAG",
    "is_kernel_owned_channel_hint_path",
    "is_plugin_owned_channel_hint_path",
    "build_base_hints",
    "apply_sensitive_hints",
    "apply_sensitive_url_hints",
    "collect_matching_schema_paths",
    "map_sensitive_paths",
]
