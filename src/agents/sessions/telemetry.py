"""jarvis.agents.sessions.telemetry — install telemetry switch.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/telemetry.ts``.

Environment overrides win over persisted settings for
CI and packaged launcher control.

Parity
======
- ``is_install_telemetry_enabled(settings_manager, telemetry_env=None) -> bool``
  (``telemetry.ts:16-22``).
- Default ``telemetry_env`` reads
  ``process.env["OPENCLAW_TELEMETRY"]``; the JARVIS
  port keeps the same env var name so the launcher
  contract matches.
- Truthy flag values are ``"1"``, ``"true"`` (any
  case), or ``"yes"`` (any case) — same as the
  OpenClaw source.
- When the env override is *unset*, the function
  delegates to ``settings_manager.get_enable_install_telemetry()``.

Phase 6.0 — scaffolding + helpers + small types.

The ``SettingsManager.get_enable_install_telemetry()``
method lands in Phase 6.8; this module is
dependency-free because the type-hint uses
:class:`typing.Protocol`.
"""
from __future__ import annotations

import os
from typing import Optional, Protocol


class _SettingsManagerLike(Protocol):
    """Protocol for the subset of ``SettingsManager``
    we depend on. The concrete class lands in
    Phase 6.8; this keeps Phase 6.0 dependency-free.
    """

    def get_enable_install_telemetry(self) -> bool:
        ...


_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes"})


def _is_truthy_env_flag(value: Optional[str]) -> bool:
    """Return True iff ``value`` is a truthy env flag.

    Mirrors ``isTruthyEnvFlag`` (``telemetry.ts:8-13``).
    The OpenClaw check is case-insensitive for
    ``"true"`` and ``"yes"``; ``"1"`` is exact.
    """
    if not value:
        return False
    return value == "1" or value.lower() in _TRUTHY_ENV_VALUES


def is_install_telemetry_enabled(
    settings_manager: _SettingsManagerLike,
    telemetry_env: Optional[str] = None,
) -> bool:
    """Resolve whether install telemetry is enabled
    from the env override or the persisted settings.

    Mirrors ``isInstallTelemetryEnabled``
    (``telemetry.ts:16-22``).

    Parameters
    ----------
    settings_manager : SettingsManager
        The host's settings manager. Consulted only
        when the env override is *unset*.
    telemetry_env : str | None
        Override the env lookup (default: the
        ``OPENCLAW_TELEMETRY`` env var, read at call
        time). When this is not ``None`` (including
        when it's an empty string), the function
        returns ``is_truthy_env_flag(telemetry_env)``
        and never touches the settings.

    Returns
    -------
    bool
        True iff install telemetry is enabled.
    """
    if telemetry_env is None:
        telemetry_env = os.environ.get("OPENCLAW_TELEMETRY")
    if telemetry_env is not None:
        return _is_truthy_env_flag(telemetry_env)
    return settings_manager.get_enable_install_telemetry()


__all__ = [
    "is_install_telemetry_enabled",
]
