"""IRC protocol message parser, builder, and text sanitizers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class IrcMessage:
    prefix: str | None = None
    command: str = ""
    params: list[str] = field(default_factory=list)
    trailing: str | None = None

    @property
    def nick(self) -> str | None:
        if self.prefix and "!" in self.prefix:
            return self.prefix.split("!", 1)[0]
        return self.prefix


def parse_irc_line(line: str) -> IrcMessage | None:
    """Parse a single raw line from IRC socket according to RFC 1459 / RFC 2812."""
    line = line.strip("\r\n")
    if not line:
        return None

    prefix = None
    if line.startswith(":"):
        parts = line[1:].split(" ", 1)
        prefix = parts[0]
        line = parts[1] if len(parts) > 1 else ""

    trailing = None
    if " :" in line:
        line, trailing = line.split(" :", 1)
    elif line.startswith(":"):
        trailing = line[1:]
        line = ""

    tokens = [t for t in line.split(" ") if t]
    if not tokens and trailing is None:
        return None

    command = tokens[0].upper() if tokens else ""
    params = tokens[1:] if len(tokens) > 1 else []

    return IrcMessage(prefix=prefix, command=command, params=params, trailing=trailing)


def format_irc_line(command: str, *params: str, trailing: str | None = None) -> str:
    """Format an IRC command line ready to be sent to socket with CRLF."""
    parts = [command.upper()]
    parts.extend(params)
    if trailing is not None:
        parts.append(f":{trailing}")
    return " ".join(parts) + "\r\n"


def strip_irc_formatting(text: str) -> str:
    """Strip mIRC color codes, bold (\x02), italic (\x1d), underline (\x1f), and reset (\x0f)."""
    # Remove color codes: \x03 followed by optional fg,bg numbers
    text = re.sub(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?", "", text)
    # Remove other control formatting chars
    text = re.sub(r"[\x02\x1D\x1F\x16\x0F]", "", text)
    return text
