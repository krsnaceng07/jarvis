"""jarvis.config.redact_argv — credential-bearing argv redactor.

OpenClaw parity: mirrors
``openclaw-main/src/config/redact-argv.ts``.

Focused minimal port: enumerates known secret flag names and a suffix
heuristic. The shared secret-text redactor is delegated to a
caller-provided callable (the OpenClaw source uses
``redactToolPayloadText`` from the logging redact module).
"""
from __future__ import annotations

import re
from typing import Callable, List, Optional


SECRET_FLAG_NAMES = frozenset({
    "--token",
    "--api-key",
    "--apikey",
    "--secret",
    "--password",
    "--passwd",
    "--auth-token",
    "--access-token",
    "--refresh-token",
    "--client-secret",
    "--hook-token",
    "--gateway-token",
    "--bot-token",
    "--app-token",
    "--remote-token",
    "--push-token",
    "--webhook-secret",
    "--webhook-token",
    "--service-account-token",
    "--op-service-account-token",
    "--bearer",
    "--bearer-token",
    "--pat",
    "--personal-access-token",
    "--oauth-token",
    "--id-token",
    "--identity-token",
    "--session-token",
    "--service-token",
    "--private-key",
    "--recovery-key",
    "--gateway-key",
    "--session-key",
    "--active-key",
})

_SECRET_FLAG_SUFFIX_RE = re.compile(
    r"^--(?:[a-z0-9]+(?:[-_][a-z0-9]+)*[-_])?(?:"
    r"token|secret|password|passwd|passphrase|pin|"
    r"api[-_]?key|api[-_]?secret|secret[-_]?key|secret[-_]?access[-_]?key|"
    r"access[-_]?key(?:[-_]?id)?|account[-_]?key|client[-_]?key|consumer[-_]?key|"
    r"license[-_]?key|subscription[-_]?key|webhook|credentials?|creds?|"
    r"auth(?:orization)?|bearer|pat|cookie|private[-_]?key|recovery[-_]?key|"
    r"signing[-_]?key|encryption[-_]?key|master[-_]?key|session[-_]?key|"
    r"gateway[-_]?key|service[-_]?key|hook[-_]?key"
    r")$",
    re.IGNORECASE,
)


def _parse_flag_name(arg: str) -> Optional[str]:
    if not isinstance(arg, str) or not arg.startswith("--"):
        return None
    equals_index = arg.find("=")
    return (arg if equals_index == -1 else arg[:equals_index]).lower()


def _is_secret_flag_name(flag_name: str) -> bool:
    return flag_name in SECRET_FLAG_NAMES or bool(_SECRET_FLAG_SUFFIX_RE.match(flag_name))


def redact_sensitive_argv(
    argv,
    *,
    redacted_value: Optional[str] = None,
    redact_text: Optional[Callable[[str], str]] = None,
) -> List[str]:
    """Redact recognized argv secrets without changing array length or non-secret flags.

    Mirrors :func:`redactSensitiveArgv`
    (``shared/config/redact-argv.ts`).
    """
    replacement = redacted_value or "***"
    result: List[str] = []
    redact_next = False
    for current in argv or []:
        if not isinstance(current, str):
            result.append(current)
            continue
        if redact_next:
            redact_next = False
            result.append(replacement)
            continue
        flag = _parse_flag_name(current)
        if flag is not None and _is_secret_flag_name(flag):
            equals_index = current.find("=")
            if equals_index != -1:
                result.append(f"{current[:equals_index + 1]}{replacement}")
                continue
            result.append(current)
            redact_next = True
            continue
        if callable(redact_text):
            redacted = redact_text(current)
            result.append(redacted if redacted != current else (redacted_value or redacted))
        else:
            result.append(current)
    return result


__all__ = ["redact_sensitive_argv", "SECRET_FLAG_NAMES"]
