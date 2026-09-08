"""Codex app-server launch configuration policy (pure helpers).

OpenClaw parity: mirrors ``normalizeTrimmedStringList`` +
``withoutClearedCodexHomeEnv`` (``auth-bridge.ts``),
``assertCodexAppServerCommandHasNoInlineArgs`` (``config-parsing.ts``),
``resolveArgs`` (``config-utils.ts``), ``resolvePolicyMode``
(``config-security.ts``), and the ``detectWindowsSpawnCommandInlineArgs``
shape (``openclaw/plugin-sdk/windows-spawn.ts``).

These helpers normalize *configuration* (what the operator wrote). The
actual child-process spawn applies them later; see ``managed_binary.py``
for candidate resolution and ``doctor.py`` for setup verification.
"""

from __future__ import annotations

import os
from typing import Any

#: Env vars the launch normalization protects: CODEX_HOME stays pointed at
#: the selected agent/user scope, HOME stays inherited. Mirrors
#: ``CODEX_APP_SERVER_HOME_ENV_VARS``.
PROTECTED_LAUNCH_ENV_VARS: frozenset[str] = frozenset({"CODEX_HOME", "HOME"})

#: Legacy adapter id renamed upstream (kept here for parity reference only;
#: the doctor migration owns the rewrite).
LEGACY_CODEX_RESPONSES_API = "openai-codex-responses"

#: Policy modes. Mirrors ``CodexAppServerPolicyMode`` (``resolvePolicyMode``).
CODEX_POLICY_MODES: tuple[str, ...] = ("guardian", "yolo")

#: Executables whose leading token implies inline spawned arguments.
#: Mirrors ``INLINE_ARGUMENT_EXECUTABLES``.
INLINE_ARGUMENT_EXECUTABLES: frozenset[str] = frozenset(
    {
        "node",
        "node.exe",
        "npm",
        "npm.cmd",
        "npm.exe",
        "npx",
        "npx.cmd",
        "npx.exe",
        "pnpm",
        "pnpm.cmd",
        "pnpm.exe",
        "yarn",
        "yarn.cmd",
        "yarn.exe",
    }
)

#: Local-testing env override names. Mirrors the ``OPENCLAW_CODEX_APP_SERVER_*``
#: reads in ``config-options.ts``. ``OPENCLAW_CODEX_APP_SERVER_GUARDIAN`` was
#: removed upstream; only ``..._MODE=guardian`` remains.
APP_SERVER_BIN_ENV_VAR = "OPENCLAW_CODEX_APP_SERVER_BIN"
APP_SERVER_ARGS_ENV_VAR = "OPENCLAW_CODEX_APP_SERVER_ARGS"
APP_SERVER_MODE_ENV_VAR = "OPENCLAW_CODEX_APP_SERVER_MODE"
APP_SERVER_APPROVAL_POLICY_ENV_VAR = "OPENCLAW_CODEX_APP_SERVER_APPROVAL_POLICY"
APP_SERVER_SANDBOX_ENV_VAR = "OPENCLAW_CODEX_APP_SERVER_SANDBOX"


def read_non_empty_env(env: Any, name: str) -> str | None:
    """Read a non-empty string env override. Mirrors ``readNonEmptyString``
    over ``process.env`` for the ``OPENCLAW_CODEX_APP_SERVER_*`` names."""
    if not isinstance(env, dict):
        return None
    value = env.get(name)
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def normalize_trimmed_string_list(value: Any) -> list[str]:
    """Trim string entries, drop empties. Mirrors ``normalizeTrimmedStringList``
    as applied to ``clearEnv`` (``config-options.ts``)."""
    if not isinstance(value, list):
        return []
    return [entry.strip() for entry in value if isinstance(entry, str) and entry.strip()]


def normalize_launch_clear_env(clear_env: Any) -> list[str]:
    """Normalize a configured ``clearEnv`` list for launch.

    Mirrors ``withoutClearedCodexHomeEnv``: reserved vars (case-insensitive)
    are removed because the launcher owns them. Returns a new list, or the
    input unchanged (by identity semantics) when nothing was reserved.
    """
    names = normalize_trimmed_string_list(clear_env)
    filtered = [name for name in names if name.strip().upper() not in PROTECTED_LAUNCH_ENV_VARS]
    return filtered


def split_command_args(raw: str, *, allow_unclosed_quotes: bool = False) -> list[str] | None:
    """Split shell-like argv (no backslash escapes outside quotes).

    Mirrors ``splitCommandArgs`` "command" syntax: single + double quotes
    group, whitespace splits, empty tokens drop. Returns ``None`` for
    unterminated quotes unless *allow_unclosed_quotes*.
    """
    tokens: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    for character in raw:
        if in_single:
            if character == "'":
                in_single = False
            else:
                buf.append(character)
            continue
        if in_double:
            if character == '"':
                in_double = False
            else:
                buf.append(character)
            continue
        if character == "'":
            in_single = True
            continue
        if character == '"':
            in_double = True
            continue
        if character.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
            continue
        buf.append(character)
    if in_single or in_double:
        if not allow_unclosed_quotes:
            return None
    if buf:
        tokens.append("".join(buf))
    return tokens


def _read_command_token(command: str) -> tuple[str, str] | None:
    """Split a leading executable token from its rest. Mirrors
    ``readCommandToken`` (quoted first token or ``\\S+``)."""
    trimmed = command.strip()
    if not trimmed:
        return None
    if trimmed.startswith('"'):
        close = trimmed.find('"', 1)
        if close <= 0:
            return None
        return trimmed[1:close], trimmed[close + 1 :].strip()
    parts = trimmed.split(None, 1)
    if len(parts) < 2:
        return None
    return parts[0], parts[1].strip()


def detect_inline_args(command: str) -> dict[str, str] | None:
    """Detect ``node script.js``-style inline spawned arguments. Mirrors
    ``detectWindowsSpawnCommandInlineArgs``: only known launcher
    executables count, and existing file paths are left alone (a directory
    may itself be named node/pnpm)."""
    parsed = _read_command_token(command)
    if parsed is None:
        return None
    token, rest = parsed
    if not rest:
        return None
    executable = os.path.basename(token.replace("\\", "/")).lower()
    # Existing paths can contain spaces after a directory named node/pnpm.
    if executable not in INLINE_ARGUMENT_EXECUTABLES or os.path.isfile(command):
        return None
    return {"executable": token, "arguments": rest}


def assert_no_inline_args(command: str, *, source: str) -> None:
    """Fail closed when a command override carries inline arguments. Mirrors
    ``assertCodexAppServerCommandHasNoInlineArgs``; *source* is ``"config"``
    or ``"env"`` (selects the setting labels in the message)."""
    found = detect_inline_args(command) if isinstance(command, str) else None
    if found is None:
        return
    if source == "env":
        source_label = "OPENCLAW_CODEX_APP_SERVER_BIN"
        args_label = "OPENCLAW_CODEX_APP_SERVER_ARGS"
    else:
        source_label = "plugins.entries.codex.config.appServer.command"
        args_label = "plugins.entries.codex.config.appServer.args"
    raise ValueError(
        f"{source_label} must be only the Codex app-server executable path; "
        f'"{found["executable"]}" was configured with inline arguments '
        f'"{found["arguments"]}". Move those arguments to {args_label}, or remove '
        "the override to use the managed Codex startup path."
    )


def resolve_app_server_args(config_args: Any, env_args: Any = None) -> list[str]:
    """Resolve the app-server argument list. Mirrors ``resolveArgs``:
    a configured list wins (non-empty strings only); otherwise the
    string-or-env value splits with unclosed quotes tolerated (v2026.9.1
    preserves backslashes and unfinished quotes)."""
    if isinstance(config_args, list):
        return [entry.strip() for entry in config_args if isinstance(entry, str) and entry.strip()]
    raw = (
        config_args
        if isinstance(config_args, str)
        else (env_args if isinstance(env_args, str) else "")
    )
    return split_command_args(raw, allow_unclosed_quotes=True) or []


def resolve_policy_mode(value: Any) -> str | None:
    """Resolve ``yolo``/``guardian`` or ``None``. Mirrors ``resolvePolicyMode``."""
    return value if value in CODEX_POLICY_MODES else None


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalize_network_proxy(value: Any) -> dict[str, Any] | None:
    """Normalize the ``networkProxy`` config record. Mirrors
    ``codexAppServerNetworkProxySchema`` (strict shape, lenient
    container): unknown keys are dropped, bad permission values drop
    their entry, non-records become ``None``. Fingerprint/profile
    generation happens at runtime, not at parse."""
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    if isinstance(value.get("enabled"), bool):
        out["enabled"] = value["enabled"]
    for key in (
        "profileName",
        "proxyUrl",
        "socksUrl",
    ):
        if _is_nonempty_str(value.get(key)):
            out[key] = value[key].strip()
    if value.get("baseProfile") in ("read-only", "workspace"):
        out["baseProfile"] = value["baseProfile"]
    if value.get("mode") in ("limited", "full"):
        out["mode"] = value["mode"]
    domains = value.get("domains")
    if isinstance(domains, dict):
        clean = {
            host.strip(): perm
            for host, perm in domains.items()
            if isinstance(host, str) and host.strip() and perm in ("allow", "deny")
        }
        if clean:
            out["domains"] = clean
    sockets = value.get("unixSockets")
    if isinstance(sockets, dict):
        clean_sockets = {
            path.strip(): perm
            for path, perm in sockets.items()
            if isinstance(path, str) and path.strip() and perm in ("allow", "none")
        }
        if clean_sockets:
            out["unixSockets"] = clean_sockets
    for key in (
        "enableSocks5",
        "enableSocks5Udp",
        "allowUpstreamProxy",
        "allowLocalBinding",
        "dangerouslyAllowNonLoopbackProxy",
        "dangerouslyAllowAllUnixSockets",
    ):
        if isinstance(value.get(key), bool):
            out[key] = value[key]
    return out or None


def normalize_supervision_endpoint(value: Any) -> dict[str, Any] | None:
    """Normalize one supervision endpoint. Mirrors
    ``codexSupervisionEndpointSchema``: ``websocket`` variant requires a
    non-empty ``url``; anything else parses as the ``stdio-proxy``
    variant. Returns ``None`` when neither variant matches."""
    if not isinstance(value, dict):
        return None
    base: dict[str, Any] = {}
    for key in ("id", "label"):
        if _is_nonempty_str(value.get(key)):
            base[key] = value[key].strip()
    if value.get("transport") == "websocket":
        if not _is_nonempty_str(value.get("url")):
            return None
        base["transport"] = "websocket"
        base["url"] = value["url"].strip()
        if _is_nonempty_str(value.get("authTokenEnv")):
            base["authTokenEnv"] = value["authTokenEnv"].strip()
        return base
    endpoint = dict(base)
    if value.get("transport") in (None, "stdio-proxy"):
        endpoint["transport"] = "stdio-proxy"
    else:
        return None
    for key in ("command", "cwd"):
        if _is_nonempty_str(value.get(key)):
            endpoint[key] = value[key].strip()
    args = value.get("args")
    if isinstance(args, list):
        clean_args = [entry.strip() for entry in args if _is_nonempty_str(entry)]
        if clean_args:
            endpoint["args"] = clean_args
    return endpoint


def normalize_supervision(value: Any) -> dict[str, Any] | None:
    """Normalize the ``supervision`` config record. Mirrors
    ``codexSupervisionConfigSchema`` (entries that match neither endpoint
    variant are dropped)."""
    if not isinstance(value, dict):
        return None
    out: dict[str, Any] = {}
    if isinstance(value.get("enabled"), bool):
        out["enabled"] = value["enabled"]
    endpoints = value.get("endpoints")
    if isinstance(endpoints, list):
        clean = [hit for hit in (normalize_supervision_endpoint(e) for e in endpoints) if hit]
        if clean:
            out["endpoints"] = clean
    for key in ("allowRawTranscripts", "allowWriteControls"):
        if isinstance(value.get(key), bool):
            out[key] = value[key]
    return out or None


def resolve_approval_policy(value: Any) -> str | None:
    """Resolve the config-level approval policy. Mirrors ``resolveApprovalPolicy``
    (``config-exec-policy.ts``): ``"never"`` / ``"on-request"`` pass;
    retired ``"on-failure"`` aliases to ``"on-request"``; anything else
    (including retired ``"untrusted"``) resolves to ``None`` so doctor,
    not the parser, reports it."""
    if value == "on-failure":
        return "on-request"
    return value if value in ("never", "on-request") else None


def resolve_sandbox_mode(value: Any) -> str | None:
    """Resolve the sandbox mode. Mirrors ``resolveSandbox``."""
    return value if value in ("read-only", "workspace-write", "danger-full-access") else None


def resolve_approvals_reviewer(value: Any) -> str | None:
    """Resolve the approvals reviewer. Mirrors ``resolveApprovalsReviewer``
    (``guardian_subagent`` stays a legacy alias and passes through)."""
    return value if value in ("user", "auto_review", "guardian_subagent") else None


def normalize_service_tier(value: Any) -> str | None:
    """Normalize the service tier. Mirrors ``normalizeCodexServiceTier``:
    legacy ``"fast"`` becomes ``"priority"``; blank/non-strings clear;
    any other non-empty string passes through for forward compatibility."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    lowered = trimmed.lower()
    if lowered in ("fast", "priority"):
        return "priority"
    if lowered == "flex":
        return "flex"
    return trimmed


def normalize_headers(value: Any) -> dict[str, str]:
    """Normalize extra WebSocket headers. Mirrors ``normalizeHeaders``:
    trimmed string values keyed by trimmed names; non-records become ``{}``.
    Values stay raw (SecretInput ``${VAR}`` resolution happens at connect,
    not at parse)."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, child in value.items():
        if not isinstance(key, str) or not isinstance(child, str):
            continue
        name = key.strip()
        text = child.strip()
        if name and text:
            out[name] = text
    return out


__all__ = [
    "APP_SERVER_APPROVAL_POLICY_ENV_VAR",
    "APP_SERVER_ARGS_ENV_VAR",
    "APP_SERVER_BIN_ENV_VAR",
    "APP_SERVER_MODE_ENV_VAR",
    "APP_SERVER_SANDBOX_ENV_VAR",
    "CODEX_POLICY_MODES",
    "INLINE_ARGUMENT_EXECUTABLES",
    "LEGACY_CODEX_RESPONSES_API",
    "PROTECTED_LAUNCH_ENV_VARS",
    "assert_no_inline_args",
    "detect_inline_args",
    "normalize_headers",
    "normalize_launch_clear_env",
    "normalize_network_proxy",
    "normalize_service_tier",
    "normalize_supervision",
    "normalize_supervision_endpoint",
    "read_non_empty_env",
    "normalize_trimmed_string_list",
    "resolve_app_server_args",
    "resolve_approval_policy",
    "resolve_approvals_reviewer",
    "resolve_policy_mode",
    "resolve_sandbox_mode",
    "split_command_args",
]
