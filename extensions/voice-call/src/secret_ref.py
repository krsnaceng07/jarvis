"""SecretRef resolution utilities for Voice Call credentials."""

from __future__ import annotations

import os
from typing import Any


def resolve_secret_value(value: Any, env: dict[str, str] | None = None) -> str | None:
    """Resolve SecretRef object or string value.

    Supports:
    - plain string: "secret-value"
    - SecretRef object: {"secret": "ENV_VAR_NAME"}
    - OpenClaw SecretRef object: {"$secret": "ENV_VAR_NAME"}
    - URI SecretRef: "secret://ENV_VAR_NAME"
    """
    if value is None:
        return None

    environ = env if env is not None else dict(os.environ)

    if isinstance(value, str):
        val_str = value.strip()
        if val_str.startswith("secret://"):
            key = val_str[len("secret://") :].strip()
            return environ.get(key)
        return val_str

    if isinstance(value, dict):
        # {"secret": "NAME"} or {"$secret": "NAME"}
        sec_name = value.get("secret") or value.get("$secret") or value.get("name")
        if sec_name and isinstance(sec_name, str):
            return environ.get(sec_name.strip())

    return str(value)
