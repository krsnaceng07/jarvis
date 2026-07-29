"""Device Pair -> Gateway live-display envelope.

Mirrors OpenClaw's ``extensions/device-pair/pairing-qr-channel-data.ts``.

This module keeps pairing QR metadata off the public
Plugin SDK by routing the live-display channel data
through a known-private key (``openclawPairingQr``).

Public surface (mirrors the TS source):
- ``build_device_pair_pairing_qr_channel_data(params)``

Python adaptations (documented in code):
- TS ``Record<string, unknown>`` → Python ``dict[str, object]``
"""
from __future__ import annotations

from typing import TypedDict


# Private key for the live-display channel envelope.
DEVICE_PAIR_PAIRING_QR_CHANNEL_DATA_KEY = "openclawPairingQr"


class DevicePairPairingQrChannelData(TypedDict, total=False):
    setupCode: str
    expiresAtMs: int


def build_device_pair_pairing_qr_channel_data(
    params: DevicePairPairingQrChannelData,
) -> dict[str, object]:
    """Build the live-display channel data envelope for the pairing QR.

    Mirrors ``buildDevicePairPairingQrChannelData``. The
    returned dict has a single key
    (``openclawPairingQr``) wrapping the setup code and
    its expiry timestamp; the live-display channel reads
    it without exposing the plugin id.
    """
    return {
        DEVICE_PAIR_PAIRING_QR_CHANNEL_DATA_KEY: {
            "setupCode": params["setupCode"],
            "expiresAtMs": params["expiresAtMs"],
        }
    }


__all__ = [
    "DEVICE_PAIR_PAIRING_QR_CHANNEL_DATA_KEY",
    "DevicePairPairingQrChannelData",
    "build_device_pair_pairing_qr_channel_data",
]
