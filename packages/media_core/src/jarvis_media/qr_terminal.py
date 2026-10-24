"""jarvis_media.qr_terminal — In-terminal compact QR code renderer.

OpenClaw parity: mirrors src/media/qr-terminal.ts and renderCompactTerminalQr.
Renders phone-scannable QR codes directly in terminal stdout using ANSI colors
and Unicode half-block characters (█, ▀, ▄, ' ').
"""

from __future__ import annotations

from typing import Any, List, Optional
import qrcode

COMPACT_MARGIN_MODULES = 1
TERMINAL_BLACK_ON_WHITE = "\x1b[47m\x1b[30m"
TERMINAL_RESET = "\x1b[0m"


def _compact_block(top: bool, bottom: bool) -> str:
    """Return the Unicode half-block corresponding to top/bottom module states."""
    if top:
        return "\u2588" if bottom else "\u2580"
    return "\u2584" if bottom else " "


def render_compact_terminal_qr(
    matrix: List[List[bool]],
    margin: int = COMPACT_MARGIN_MODULES,
) -> str:
    """Render a 2D boolean matrix into an ANSI-colored half-block string."""
    size = len(matrix)
    lines: List[str] = []

    def _read_module(x: int, y: int) -> bool:
        if 0 <= y < size and 0 <= x < size:
            return bool(matrix[y][x])
        return False

    for y in range(-margin, size + margin, 2):
        line = TERMINAL_BLACK_ON_WHITE
        for x in range(-margin, size + margin):
            top_val = _read_module(x, y)
            bot_val = _read_module(x, y + 1)
            line += _compact_block(top_val, bot_val)
        lines.append(f"{line}{TERMINAL_RESET}")
    return "\n".join(lines)


def render_qr_terminal(
    input_text: str,
    small: bool = True,
    margin: int = COMPACT_MARGIN_MODULES,
) -> str:
    """Render text into an in-terminal phone-scannable QR code string."""
    qr = qrcode.QRCode(border=0)
    qr.add_data(input_text)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    return render_compact_terminal_qr(matrix, margin=margin)


__all__ = [
    "COMPACT_MARGIN_MODULES",
    "TERMINAL_BLACK_ON_WHITE",
    "TERMINAL_RESET",
    "render_compact_terminal_qr",
    "render_qr_terminal",
]
