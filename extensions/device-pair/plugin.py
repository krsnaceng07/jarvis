"""Device Pairing infra plugin entry point — re-export shim.

Mirrors OpenClaw's ``extensions/device-pair/index.ts``.
The Python port keeps the same plugin descriptor
(``DevicePairingPlugin``) + entry (``entry``) but the
real implementation lives in ``lib/__init__.py`` (the
``lib/`` directory mirrors the OpenClaw ``src/`` so the
module name is unhyphenated; the dotted path
``extensions.device_pair`` is unresolvable because the
extension directory is ``device-pair``).

This file is the shim the JARVIS plugin loader uses
(``extensions/device-pair/__init__.py`` re-exports
``entry`` from here).
"""

from __future__ import annotations

from .lib import (
    DevicePairingPlugin,
    device_pair_plugin,
    entry,
)

__all__ = ["DevicePairingPlugin", "device_pair_plugin", "entry"]
