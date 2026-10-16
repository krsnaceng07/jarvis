"""jarvis.agents.sandbox.environment — Environment sanitization and secret scrubbing.

Mirrors OpenClaw's ``src/agents/bash-tools.exec-request-preparation.ts``:
- Strips credentials, API keys, and sensitive tokens from the child environment.
- Passes only clean, platform-safe system environment variables.
- Merges explicitly provided tool overrides safely.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any

# Suffixes and patterns that identify credentials
_SENSITIVE_KEY_PATTERNS = (
    re.compile(r".*API_?KEY.*", re.IGNORECASE),
    re.compile(r".*TOKEN.*", re.IGNORECASE),
    re.compile(r".*SECRET.*", re.IGNORECASE),
    re.compile(r".*PASSWORD.*", re.IGNORECASE),
    re.compile(r".*PASSWD.*", re.IGNORECASE),
    re.compile(r".*CREDENTIAL.*", re.IGNORECASE),
    re.compile(r".*AUTH.*", re.IGNORECASE),
    re.compile(r"^AWS_.*", re.IGNORECASE),
    re.compile(r"^AZURE_.*", re.IGNORECASE),
    re.compile(r"^GOOGLE_.*", re.IGNORECASE),
    re.compile(r"^GCP_.*", re.IGNORECASE),
    re.compile(r"^GITHUB_.*", re.IGNORECASE),
    re.compile(r"^GH_.*", re.IGNORECASE),
    re.compile(r"^SSH_.*", re.IGNORECASE),
    re.compile(r"^GEMINI_.*", re.IGNORECASE),
    re.compile(r"^OPENAI_.*", re.IGNORECASE),
    re.compile(r"^ANTHROPIC_.*", re.IGNORECASE),
    re.compile(r"^GROQ_.*", re.IGNORECASE),
)

# Standard platform variables permitted for normal process execution
_WINDOWS_SAFE_VARS = {
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "PATH",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "APPDATA",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
    "COMPUTERNAME",
}

_POSIX_SAFE_VARS = {
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "SHELL",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TMPDIR",
    "TERM",
    "PWD",
}


def is_sensitive_env_key(key: str) -> bool:
    """Return True if an environment key contains secrets or credentials."""
    k = (key or "").strip()
    if not k:
        return False
    return any(p.match(k) for p in _SENSITIVE_KEY_PATTERNS)


def sanitize_execution_environment(
    base_env: dict[str, str] | None = None,
    overrides: dict[str, Any] | None = None,
    is_sandboxed: bool = False,
) -> dict[str, str]:
    """Build a sanitized environment mapping for child processes.

    Parameters
    ----------
    base_env:
        Base environment mapping (defaults to ``os.environ``).
    overrides:
        Caller-supplied environment variable overrides.
    is_sandboxed:
        If True, restricts the environment even further for container execution.

    Returns
    -------
    dict[str, str]
        Sanitized environment dictionary safe for process execution.
    """
    raw_env = dict(base_env if base_env is not None else os.environ)
    safe_keys = _WINDOWS_SAFE_VARS if sys.platform == "win32" else _POSIX_SAFE_VARS

    clean_env: dict[str, str] = {}

    for k, v in raw_env.items():
        k_upper = k.upper()
        # Always strip sensitive keys
        if is_sensitive_env_key(k):
            continue

        # In sandboxed mode or general restrictive mode, keep known safe vars
        if is_sandboxed:
            if k_upper in safe_keys:
                clean_env[k] = str(v)
        else:
            # On host, allow standard system vars unless they match sensitive patterns
            clean_env[k] = str(v)

    # Always ensure minimal PATH and TEMP exist
    if "PATH" not in clean_env and "PATH" in raw_env:
        clean_env["PATH"] = raw_env["PATH"]

    # Merge explicit caller overrides
    if overrides and isinstance(overrides, dict):
        for ok, ov in overrides.items():
            if ov is not None:
                clean_env[str(ok)] = str(ov)

    return clean_env
