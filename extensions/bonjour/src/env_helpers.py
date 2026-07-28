"""Bonjour env helpers.

Mirrors OpenClaw's ``extensions/bonjour/src/advertiser.ts``
helper functions (the parts that don't require ciao):

- ``is_truthy_env_value`` — operator-truthy env string check
  (mirrors ``isTruthyEnvValue`` from OpenClaw's
  ``src/infra/env.ts``: accepts ``"1"``, ``"on"``, ``"true"``,
  ``"yes"`` lowercase).
- ``read_bonjour_disable_override`` — reads
  ``OPENCLAW_DISABLE_BONJOUR`` and returns True/False/None
  (None = not set or unparseable).
- ``is_container_environment`` — detects Fly/Docker/k3s/LXC
  via sentinel files + ``/proc/1/cgroup``.
- ``is_disabled_by_env`` — combines NODE_ENV=test,
  VITEST, env override, container detection.
- ``resolve_system_mdns_hostname`` — ``socket.gethostname()``
  validated against DNS label rules.
- ``truncate_to_dns_label`` — UTF-8 safe truncation to
  63 bytes.
- ``safe_service_name`` / ``prettify_instance_name`` —
  mDNS name helpers.
"""
from __future__ import annotations

import os
import re
import socket
from pathlib import Path
from typing import Optional

MAX_DNS_LABEL_BYTES = 63
CONTAINER_SENTINEL_PATHS = (
    "/.dockerenv",
    "/run/.containerenv",
    "/var/run/.containerenv",
)
CGROUP_PATH = "/proc/1/cgroup"
CGROUP_CONTAINER_RE = re.compile(
    r"/docker/|cri-containerd-[0-9a-f]|containerd/[0-9a-f]{64}|/kubepods[/.]|\blxc\b",
    re.IGNORECASE,
)
DNS_LABEL_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
ENV_TRUTHY_VALUES = frozenset({"1", "on", "true", "yes"})


def is_truthy_env_value(value: Optional[str]) -> bool:
    """Check if a string is a common truthy env value.

    Mirrors OpenClaw's ``isTruthyEnvValue`` from
    ``src/infra/env.ts``. Returns False for non-strings,
    None, and unknown values.
    """
    if not isinstance(value, str):
        return False
    return value.strip().lower() in ENV_TRUTHY_VALUES


def read_bonjour_disable_override() -> Optional[bool]:
    """Read ``OPENCLAW_DISABLE_BONJOUR`` env override.

    Returns:
    - ``True`` if the env value is a known truthy string.
    - ``False`` if it's a known falsy string
      (``"0"``, ``"false"``, ``"no"``, ``"off"``).
    - ``None`` if unset, blank, or unrecognized.

    Mirrors the TS ``readBonjourDisableOverride`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    raw = os.environ.get("OPENCLAW_DISABLE_BONJOUR")
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if not normalized:
        return None
    if is_truthy_env_value(raw):
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def is_container_environment() -> bool:
    """Detect if the current process is running inside a container.

    Checks (in order):
    1. ``FLY_MACHINE_ID`` + ``FLY_APP_NAME`` env (Fly.io)
    2. Container sentinel files (Docker, Podman, etc.)
    3. ``/proc/1/cgroup`` for docker / containerd / kubepods / lxc

    Mirrors the TS ``isContainerEnvironment`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    fly_machine = os.environ.get("FLY_MACHINE_ID", "").strip()
    fly_app = os.environ.get("FLY_APP_NAME", "").strip()
    if fly_machine and fly_app:
        return True

    for sentinel in CONTAINER_SENTINEL_PATHS:
        try:
            if Path(sentinel).exists():
                return True
        except OSError:
            # ignore — path not accessible
            pass

    try:
        cgroup_text = Path(CGROUP_PATH).read_text(encoding="utf-8")
        return bool(CGROUP_CONTAINER_RE.search(cgroup_text))
    except (OSError, UnicodeDecodeError):
        return False


def is_disabled_by_env() -> bool:
    """Check if Bonjour should be disabled based on env state.

    Returns True when:
    - ``NODE_ENV == "test"`` or ``VITEST`` is set
    - ``OPENCLAW_DISABLE_BONJOUR`` is set to a truthy value
    - We're in a container environment (default: disabled)

    Returns False when ``OPENCLAW_DISABLE_BONJOUR`` is
    explicitly set to a falsy value (override).

    Mirrors the TS ``isDisabledByEnv`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    if os.environ.get("NODE_ENV") == "test":
        return True
    if os.environ.get("VITEST"):
        return True
    env_override = read_bonjour_disable_override()
    if env_override is not None:
        return env_override
    return is_container_environment()


def resolve_system_mdns_hostname() -> Optional[str]:
    """Resolve the local mDNS hostname from the OS.

    Returns the first DNS label of the OS hostname
    (stripping ``.local`` suffix), or ``None`` if the
    hostname is missing, blank, or doesn't match DNS
    label rules.

    Mirrors the TS ``resolveSystemMdnsHostname`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    try:
        raw = socket.gethostname()
    except OSError:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    first_label = (
        trimmed.replace(".local", "").split(".")[0].strip() if trimmed else ""
    )
    if not DNS_LABEL_RE.match(first_label):
        return None
    return first_label


def truncate_to_dns_label(name: str, fallback: str = "openclaw") -> str:
    """Truncate a name to a valid DNS label (max 63 bytes UTF-8).

    Walks back from 63 bytes until it finds a valid UTF-8
    boundary, strips trailing hyphens, and returns the
    fallback if everything else fails.

    Mirrors the TS ``truncateToDnsLabel`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    encoded = name.encode("utf-8")
    if len(encoded) <= MAX_DNS_LABEL_BYTES:
        return name
    for end in range(MAX_DNS_LABEL_BYTES, 0, -1):
        try:
            decoded = encoded[:end].decode("utf-8")
            stripped = re.sub(r"-+$", "", decoded).strip()
            return stripped or fallback
        except UnicodeDecodeError:
            # Try the next shorter prefix until the byte slice
            # ends on a UTF-8 boundary.
            continue
    return fallback


def safe_service_name(name: str) -> str:
    """Return a valid mDNS service name (trimmed + truncated).

    Mirrors the TS ``safeServiceName`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    trimmed = name.strip()
    return truncate_to_dns_label(trimmed) if trimmed else "openclaw"


def prettify_instance_name(name: str) -> str:
    """Strip a trailing ``(OpenClaw)`` suffix for display.

    Mirrors the TS ``prettifyInstanceName`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """
    normalized = re.sub(r"\s+", " ", name.strip())
    stripped = re.sub(r"\s+\(OpenClaw\)\s*$", "", normalized, flags=re.IGNORECASE).strip()
    return stripped or normalized
