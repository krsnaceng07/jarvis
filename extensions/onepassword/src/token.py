"""Service account token discovery and permission verification.

OpenClaw parity: mirrors token path discovery under state directory
(`~/.openclaw/credentials/onepassword/service-account-token` or
`~/.jarvis/credentials/onepassword/service-account-token`), non-empty check,
and permission warning if readable/writable by group or others.
"""

from __future__ import annotations

import logging
import os
import stat
import sys
from pathlib import Path

logger = logging.getLogger("jarvis.onepassword.token")

TOKEN_SUBPATH = ("credentials", "onepassword", "service-account-token")


def get_state_dir() -> Path:
    """Resolve the state directory root honoring environment overrides."""
    env_state = (
        os.environ.get("OPENCLAW_STATE_DIR") or os.environ.get("JARVIS_STATE_DIR") or ""
    ).strip()
    if env_state:
        return Path(env_state).expanduser().resolve()

    # If ~/.openclaw exists, prioritize it for OpenClaw parity, otherwise ~/.jarvis
    openclaw_home = Path("~/.openclaw").expanduser().resolve()
    if openclaw_home.exists():
        return openclaw_home

    jarvis_home = Path("~/.jarvis").expanduser().resolve()
    if jarvis_home.exists():
        return jarvis_home

    # Default to ~/.openclaw
    return openclaw_home


def get_token_file_path(state_dir: Path | None = None) -> Path:
    """Return the canonical path to the service-account token file."""
    root = state_dir or get_state_dir()
    return root.joinpath(*TOKEN_SUBPATH)


def check_token_permissions(token_path: Path) -> list[str]:
    """Check file permissions and return any security warnings.

    Warns once if group or other users have read or write permissions.
    """
    warnings: list[str] = []
    if not token_path.exists():
        return warnings

    try:
        st = token_path.stat()
        # On POSIX systems, check if group or other can read/write (0o077)
        if sys.platform != "win32":
            mode = st.st_mode
            if (mode & 0o077) != 0:
                warnings.append(
                    f"Token file {token_path} has loose permissions ({oct(stat.S_IMODE(mode))}). "
                    "Recommend setting chmod 600."
                )
        else:
            # On Windows, basic check
            pass
    except Exception as exc:
        warnings.append(f"Failed to check permissions for {token_path}: {exc}")

    return warnings


def verify_token_prerequisites(state_dir: Path | None = None) -> tuple[bool, str | None]:
    """Check if token file exists and is non-empty.

    Returns (ready, error_message).
    """
    path = get_token_file_path(state_dir)
    if not path.exists():
        return False, f"Token file not found at {path}"

    if not path.is_file():
        return False, f"Token path {path} is not a file"

    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return False, f"Token file at {path} is empty"
        return True, None
    except Exception as exc:
        return False, f"Failed to read token file at {path}: {exc}"


def read_service_account_token(state_dir: Path | None = None) -> str | None:
    """Read the service-account token from disk.

    Returns None if missing or empty. Never logs the token content.
    """
    path = get_token_file_path(state_dir)
    if not path.exists() or not path.is_file():
        return None

    for warning in check_token_permissions(path):
        logger.warning(warning)

    try:
        token = path.read_text(encoding="utf-8").strip()
        return token if token else None
    except Exception as exc:
        logger.error(f"Error reading 1Password service-account token: {exc}")
        return None
