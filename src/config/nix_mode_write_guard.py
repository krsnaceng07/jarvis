"""jarvis.config.nix_mode_write_guard — Nix-mode config write guard.

OpenClaw parity: mirrors
``openclaw-main/src/config/nix-mode-write-guard.ts``.
"""
from __future__ import annotations

from typing import Optional


#: Agent-first Nix install docs shown when runtime config writes are blocked.
NIX_OPENCLAW_AGENT_FIRST_URL = "https://github.com/openclaw/nix-openclaw#quick-start"
#: Public OpenClaw Nix overview shown with immutable-config errors.
OPENCLAW_NIX_OVERVIEW_URL = "https://docs.openclaw.ai/install/nix"


def resolve_is_nix_mode(env=None) -> bool:
    """Return whether the current environment marks OpenClaw config as Nix-managed.

    Focused minimal stub: the OpenClaw source consults
    ``OPENCLAW_NIX_MODE``; the Python port accepts an injectable resolver
    so tests can flip the mode without touching the environment.
    """
    if env is None:
        return False
    val = env.get("OPENCLAW_NIX_MODE")
    if val is None:
        return False
    if isinstance(val, str):
        return val.strip() in ("1", "true", "yes")
    return bool(val)


class NixModeConfigMutationError(Exception):
    """Error thrown when a mutating config path is attempted while Nix owns config state.

    Mirrors :class:`NixModeConfigMutationError`
    (``shared/config/nix-mode-write-guard.ts`).
    """
    code = "OPENCLAW_NIX_MODE_CONFIG_IMMUTABLE"

    def __init__(self, config_path: Optional[str] = None) -> None:
        self.config_path = config_path
        super().__init__(self._format(config_path))
        self.name = "NixModeConfigMutationError"

    @staticmethod
    def _format(config_path: Optional[str]) -> str:
        return "\n".join([
            "Config is managed by Nix (`OPENCLAW_NIX_MODE=1`), so OpenClaw treats openclaw.json as immutable.",
            "This usually means nix-openclaw, the first-party Nix distribution, or another Nix-managed package set this mode.",
            *(["Config path: " + config_path] if config_path else []),
            "Do not run setup, onboarding, openclaw update, plugin install/update/uninstall/enable, doctor repair/token-generation, or config set against this file.",
            "Edit the Nix source for this install instead. For nix-openclaw, edit `programs.openclaw.config` or `instances.<name>.config`, then rebuild with Home Manager or NixOS.",
            f"Agent-first Nix setup: {NIX_OPENCLAW_AGENT_FIRST_URL}",
            f"OpenClaw Nix overview: {OPENCLAW_NIX_OVERVIEW_URL}",
        ])


def assert_config_write_allowed_in_current_mode(
    config_path: Optional[str] = None,
    *,
    env: Optional[dict] = None,
    resolve_is_nix_mode_fn=None,
) -> None:
    """Throw when the current environment marks OpenClaw config as Nix-managed.

    Mirrors :func:`assertConfigWriteAllowedInCurrentMode`
    (``shared/config/nix-mode-write-guard.ts`).
    """
    resolver = resolve_is_nix_mode_fn or resolve_is_nix_mode
    if not resolver(env):
        return
    raise NixModeConfigMutationError(config_path)


__all__ = [
    "NIX_OPENCLAW_AGENT_FIRST_URL",
    "OPENCLAW_NIX_OVERVIEW_URL",
    "NixModeConfigMutationError",
    "assert_config_write_allowed_in_current_mode",
    "resolve_is_nix_mode",
]
