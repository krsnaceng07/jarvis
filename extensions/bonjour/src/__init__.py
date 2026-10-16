"""Bonjour src/ subpackage — env helpers, error classification, advertiser.

Mirrors OpenClaw's ``extensions/bonjour/src/``:
- ``errors.py`` — error formatting helper
- ``ciao.py`` — ciao process-error classifier
- ``env_helpers.py`` — env override + container + DNS label helpers
- ``advertiser.py`` — main mDNS advertiser (using ``zeroconf`` in
  the Python port; the TS source uses ``@homebridge/ciao``)
"""

from __future__ import annotations

from .ciao import (
    CiaoProcessErrorClassification,
    InterfaceEnumerationFailure,
    NetmaskAssertion,
    classify_ciao_process_error,
)
from .env_helpers import (
    is_container_environment,
    is_disabled_by_env,
    is_truthy_env_value,
    prettify_instance_name,
    read_bonjour_disable_override,
    resolve_system_mdns_hostname,
    safe_service_name,
    truncate_to_dns_label,
)
from .errors import format_bonjour_error

__all__ = [
    "CiaoProcessErrorClassification",
    "InterfaceEnumerationFailure",
    "NetmaskAssertion",
    "classify_ciao_process_error",
    "format_bonjour_error",
    "is_container_environment",
    "is_disabled_by_env",
    "is_truthy_env_value",
    "prettify_instance_name",
    "read_bonjour_disable_override",
    "resolve_system_mdns_hostname",
    "safe_service_name",
    "truncate_to_dns_label",
]
