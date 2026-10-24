"""jarvis_media.qr_image — Base64 PNG QR code generator.

OpenClaw parity: mirrors src/media/qr-image.ts.
"""

from __future__ import annotations

import base64
import io
import qrcode

QR_PNG_DATA_URL_PREFIX = "data:image/png;base64,"


def render_qr_png_bytes(
    input_text: str,
    border: int = 1,
    box_size: int = 10,
) -> bytes:
    """Render text into raw PNG image bytes."""
    qr = qrcode.QRCode(border=border, box_size=box_size)
    qr.add_data(input_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_qr_png_base64(
    input_text: str,
    border: int = 1,
    box_size: int = 10,
) -> str:
    """Render text into a base64-encoded PNG string."""
    raw_bytes = render_qr_png_bytes(input_text, border=border, box_size=box_size)
    return base64.b64encode(raw_bytes).decode("ascii")


def render_qr_png_data_url(
    input_text: str,
    border: int = 1,
    box_size: int = 10,
) -> str:
    """Render text into a standard data URL (data:image/png;base64,...)."""
    return f"{QR_PNG_DATA_URL_PREFIX}{render_qr_png_base64(input_text, border=border, box_size=box_size)}"


__all__ = [
    "QR_PNG_DATA_URL_PREFIX",
    "render_qr_png_bytes",
    "render_qr_png_base64",
    "render_qr_png_data_url",
]
