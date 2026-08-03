"""jarvis.types.qrcode — type stub for the qrcode SDK.

OpenClaw parity: mirrors
``openclaw-main/src/types/qrcode.d.ts``.

Phase 8.1b — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Placeholder type alias for the QR-code toCanvas options.
QrToCanvasOptions = Dict[str, Any]

#: Placeholder type alias for the QR-code toDataURL options.
QrToDataUrlOptions = Dict[str, Any]

#: Placeholder type alias for the QR-code toString options.
QrToStringOptions = Dict[str, Any]

#: Placeholder type alias for the QR-code toBuffer result.
QrToBufferResult = bytes

#: Placeholder type alias for the QR-code error-correction level.
QrErrorCorrectionLevel = str  # "L" | "M" | "Q" | "H"


__all__ = [
    "QrToCanvasOptions",
    "QrToDataUrlOptions",
    "QrToStringOptions",
    "QrToBufferResult",
    "QrErrorCorrectionLevel",
]
