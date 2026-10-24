"""
JARVIS Media Core package.
"""

__version__ = "0.1.0"

from .qr_terminal import (
    COMPACT_MARGIN_MODULES,
    TERMINAL_BLACK_ON_WHITE,
    TERMINAL_RESET,
    render_compact_terminal_qr,
    render_qr_terminal,
)
from .qr_image import (
    QR_PNG_DATA_URL_PREFIX,
    render_qr_png_bytes,
    render_qr_png_base64,
    render_qr_png_data_url,
)

__all__ = [
    "__version__",
    "COMPACT_MARGIN_MODULES",
    "TERMINAL_BLACK_ON_WHITE",
    "TERMINAL_RESET",
    "render_compact_terminal_qr",
    "render_qr_terminal",
    "QR_PNG_DATA_URL_PREFIX",
    "render_qr_png_bytes",
    "render_qr_png_base64",
    "render_qr_png_data_url",
]

