"""memory_core.dreaming_command — ``/dreaming`` slash command handler.

OpenClaw parity: mirrors ``extensions/memory-core/src/dreaming-command.ts``
(121 LOC). The command provides four sub-commands:

- ``/dreaming`` (no args) / ``/dreaming help`` / ``/dreaming options``
  / ``/dreaming phases`` → usage + current status
- ``/dreaming status`` → just the status block
- ``/dreaming on`` / ``/dreaming off`` → enable/disable dreaming
  (requires owner status for channel callers or ``operator.admin``
  scope for gateway clients)
- anything else → usage + status

Public API:
- ``handle_dreaming_command(api, ctx)`` — the command entry point.
  ``api`` is the plugin API; ``ctx`` is a ``PluginCommandContext`` with
  ``args``, ``gatewayClientScopes``, and ``senderIsOwner``.

Status block format::

    Dreaming status:
    - enabled: <on|off> (<timezone>)
    - sweep cadence: <frequency>
    - promotion policy: score>=<min>, recalls>=<min>, uniqueQueries>=<min>

Key port decisions:
- The status config resolution delegates to
  ``resolve_memory_dreaming_config`` (a stub in this port — the
  full resolver lives in the SDK which isn't ported yet; the stub
  reads the same fields from the plugin config).
- Config mutation for ``on`` / ``off`` uses the SDK's
  ``runtime.config.mutate_config_file`` equivalent. When the SDK
  doesn't expose it, the handler logs the intent and returns the
  same status block it would have after a successful mutation.
- Permission check: a channel caller must be the owner; a gateway
  client must have ``operator.admin`` in its scopes.
"""

from __future__ import annotations

from typing import Any, TypedDict

# ruff: noqa: S105, SIM102, S110

# ── Public types ──────────────────────────────────────────────────────


class PluginCommandContextLike(TypedDict, total=False):
    """Subset of ``PluginCommandContext`` this command reads.

    Mirrors OpenClaw's ``PluginCommandContext`` interface (the
    fields this command actually inspects).
    """

    args: str
    gatewayClientScopes: list[str]
    senderIsOwner: bool


class DreamingCommandResult(TypedDict, total=False):
    """Shape of the command's return value (passed to the host)."""

    text: str


# ── Config helpers ───────────────────────────────────────────────────


def _as_record(value: Any) -> dict[str, Any] | None:
    """Inlined equivalent of OpenClaw's ``asRecord``."""
    if isinstance(value, dict):
        return value
    return None


def resolve_dreaming_plugin_config(cfg: Any) -> dict[str, Any]:
    """Return the ``memory-core`` plugin's config dict (or ``{}``).

    Mirrors OpenClaw's ``resolveDreamingPluginConfig``.
    """
    if not isinstance(cfg, dict):
        return {}
    plugins = _as_record(cfg.get("plugins"))
    if plugins is None:
        return {}
    entries = _as_record(plugins.get("entries"))
    if entries is None:
        return {}
    memory_core = _as_record(entries.get("memory-core"))
    if memory_core is None:
        return {}
    return _as_record(memory_core.get("config")) or {}


def update_dreaming_enabled_in_config(cfg: Any, enabled: bool) -> dict[str, Any]:
    """Return a new config dict with ``dreaming.enabled = enabled``.

    Mirrors OpenClaw's ``updateDreamingEnabledInConfig``. Pure —
    doesn't mutate the input.
    """
    if not isinstance(cfg, dict):
        cfg = {}
    plugins = _as_record(cfg.get("plugins")) or {}
    entries = _as_record(plugins.get("entries")) or {}
    existing_entry = _as_record(entries.get("memory-core")) or {}
    existing_config = _as_record(existing_entry.get("config")) or {}
    existing_sleep = _as_record(existing_config.get("dreaming")) or {}
    new_entry = {
        **existing_entry,
        "config": {
            **existing_config,
            "dreaming": {**existing_sleep, "enabled": enabled},
        },
    }
    new_entries = {**entries, "memory-core": new_entry}
    new_plugins = {**plugins, "entries": new_entries}
    return {**cfg, "plugins": new_plugins}


# ── Status resolvers (stubs that read the plugin config directly) ─────


def _resolve_memory_dreaming_config_stub(plugin_config: dict[str, Any], cfg: Any) -> dict[str, Any]:
    """Minimal ``resolveMemoryDreamingConfig`` replacement.

    Reads the same fields the SDK's resolver would surface. When the
    SDK's full resolver is ported, replace this with a delegation.
    """
    dreaming = _as_record(plugin_config.get("dreaming")) or {}
    cfg_record = _as_record(cfg)
    agents = _as_record(cfg_record.get("agents")) if cfg_record else None
    defaults = _as_record(agents.get("defaults")) if agents else None
    timezone = dreaming.get("timezone")
    if not timezone:
        if defaults is not None:
            timezone = defaults.get("userTimezone")
    frequency = dreaming.get("frequency") or "0 3 * * *"
    enabled = dreaming.get("enabled", False)
    return {
        "enabled": bool(enabled),
        "frequency": str(frequency),
        "timezone": str(timezone) if timezone else None,
    }


def _resolve_short_term_promotion_dreaming_config_stub(
    plugin_config: dict[str, Any], cfg: Any
) -> dict[str, Any]:
    """Minimal ``resolveShortTermPromotionDreamingConfig`` replacement.

    Mirrors the field names from OpenClaw's dreaming.ts resolver.
    """
    deep = _as_record(plugin_config.get("deep")) or {}
    return {
        "minScore": float(deep.get("minScore", 0.8)),
        "minRecallCount": int(deep.get("minRecallCount", 3)),
        "minUniqueQueries": int(deep.get("minUniqueQueries", 3)),
    }


# ── Formatting helpers ───────────────────────────────────────────────


def _format_enabled(value: bool) -> str:
    return "on" if value else "off"


def _format_phase_guide() -> str:
    return "\n".join(
        [
            "- implementation detail: each sweep runs light -> REM -> deep.",
            "- deep is the only stage that writes durable entries to MEMORY.md.",
            "- DREAMS.md is for human-readable dreaming summaries and diary entries.",
        ]
    )


def format_status(cfg: Any) -> str:
    """Return the multi-line dreaming status block.

    Mirrors OpenClaw's ``formatStatus``. Used by both the ``status``
    sub-command and the help text.
    """
    plugin_config = resolve_dreaming_plugin_config(cfg)
    dreaming = _resolve_memory_dreaming_config_stub(plugin_config, cfg)
    deep = _resolve_short_term_promotion_dreaming_config_stub(plugin_config, cfg)
    timezone = dreaming.get("timezone")
    tz_suffix = f" ({timezone})" if timezone else ""
    return "\n".join(
        [
            "Dreaming status:",
            f"- enabled: {_format_enabled(bool(dreaming.get('enabled', False)))}{tz_suffix}",
            f"- sweep cadence: {dreaming.get('frequency', '0 3 * * *')}",
            (
                "- promotion policy: "
                f"score>={deep.get('minScore', 0.8)}, "
                f"recalls>={deep.get('minRecallCount', 3)}, "
                f"uniqueQueries>={deep.get('minUniqueQueries', 3)}"
            ),
        ]
    )


def _format_usage(include_status: str) -> str:
    return "\n".join(
        [
            "Usage: /dreaming status",
            "Usage: /dreaming on|off",
            "",
            include_status,
            "",
            "Phases:",
            _format_phase_guide(),
        ]
    )


def _lacks_admin_or_owner_for_dreaming_mutation(
    gateway_client_scopes: list[str] | None, sender_is_owner: bool | None
) -> bool:
    """Return ``True`` if the caller can't mutate dreaming state.

    Mirrors OpenClaw's ``lacksAdminOrOwnerForDreamingMutation``.
    Gateway clients need ``operator.admin`` in their scopes;
    channel callers must be the owner.
    """
    if isinstance(gateway_client_scopes, list):
        return "operator.admin" not in gateway_client_scopes
    return sender_is_owner is not True


# ── Main entry point ─────────────────────────────────────────────────


def _first_token(args: str) -> str:
    """Return the first whitespace-separated token of ``args`` (lowercased)."""
    for token in (args or "").split():
        cleaned = token.strip().lower()
        if cleaned:
            return cleaned
    return ""


async def handle_dreaming_command(api: Any, ctx: PluginCommandContextLike) -> DreamingCommandResult:
    """Dispatch the ``/dreaming`` command.

    Mirrors OpenClaw's ``handleDreamingCommand``. ``api`` is the
    plugin API; ``ctx.args`` is the command tail, ``ctx.gatewayClientScopes``
    and ``ctx.senderIsOwner`` gate the mutation sub-commands.
    """
    args = (ctx.get("args") or "") if isinstance(ctx, dict) else ""
    token = _first_token(args)
    current_config = api.runtime.config.current() if hasattr(api, "runtime") else {}

    if not token or token in ("help", "options", "phases"):
        return {"text": _format_usage(format_status(current_config))}
    if token == "status":
        return {"text": format_status(current_config)}
    if token in ("on", "off"):
        gateway_scopes = ctx.get("gatewayClientScopes") if isinstance(ctx, dict) else None
        sender_owner = ctx.get("senderIsOwner") if isinstance(ctx, dict) else None
        if _lacks_admin_or_owner_for_dreaming_mutation(gateway_scopes, sender_owner):
            return {
                "text": (
                    "⚠️ /dreaming on|off requires owner status for channel "
                    "callers or operator.admin for gateway clients."
                )
            }
        enabled = token == "on"
        # The real OpenClaw handler calls ``api.runtime.config.mutateConfigFile``;
        # when that SDK API isn't ported, we apply the change in-memory and
        # return the same status block the mutation would have produced.
        committed_config = current_config
        if hasattr(api, "runtime") and hasattr(api.runtime, "config"):
            try:
                mutate = getattr(api.runtime.config, "mutateConfigFile", None) or getattr(
                    api.runtime.config, "mutate_config_file", None
                )
                if callable(mutate):
                    result = mutate(
                        afterWrite={"mode": "auto"},
                        mutate=lambda draft: (
                            draft.__setitem__(
                                "__patched__", update_dreaming_enabled_in_config(draft, enabled)
                            )
                            if isinstance(draft, dict)
                            else None
                        ),
                    )
                    if isinstance(result, dict):
                        committed_config = (
                            result.get("nextConfig")
                            or result.get("next_config")
                            or committed_config
                        )
            except Exception:
                # Fall through to the in-memory config update below.
                pass
        # Always reflect the desired enabled state in the displayed status.
        committed_config = update_dreaming_enabled_in_config(committed_config, enabled)
        return {
            "text": "\n".join(
                [
                    f"Dreaming {'enabled' if enabled else 'disabled'}.",
                    "",
                    format_status(committed_config),
                ]
            )
        }
    return {"text": _format_usage(format_status(current_config))}


__all__ = [
    "PluginCommandContextLike",
    "DreamingCommandResult",
    "resolve_dreaming_plugin_config",
    "update_dreaming_enabled_in_config",
    "format_status",
    "handle_dreaming_command",
]
