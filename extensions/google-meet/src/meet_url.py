"""Google Meet URL validator, normalizer, and target parser."""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urlparse

MEET_CODE_RE = re.compile(r"^[a-z]{3}-[a-z]{4}-[a-z]{3}$", re.IGNORECASE)
MEET_PATH_RE = re.compile(r"^/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:$|[/?#])", re.IGNORECASE)
LOOKUP_PATH_RE = re.compile(r"^/lookup/([a-zA-Z0-9_-]+)(?:$|[/?#])", re.IGNORECASE)


@dataclass(slots=True, frozen=True)
class ParsedGoogleMeetTarget:
    is_valid: bool
    url: str | None = None
    space_name: str | None = None
    meeting_code: str | None = None


def is_valid_google_meet_url(input_val: object) -> bool:
    """Check if input is a valid Google Meet URL or lookup URL."""
    if not input_val or not isinstance(input_val, str):
        return False
    raw = input_val.strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False

    if not parsed.scheme or not parsed.netloc:
        return False
    if parsed.scheme.lower() not in ("http", "https"):
        return False
    if parsed.hostname is None or parsed.hostname.lower() != "meet.google.com":
        return False

    if MEET_PATH_RE.match(parsed.path) or LOOKUP_PATH_RE.match(parsed.path):
        return True
    return False


def normalize_google_meet_url(input_val: object) -> str:
    """Normalize Google Meet URL to https://meet.google.com/abc-defg-hij."""
    if not input_val:
        raise ValueError("url required")
    raw = str(input_val).strip()
    parsed = parse_google_meet_target(raw)
    if not parsed.is_valid or not parsed.url:
        raise ValueError("url must be a valid Google Meet URL")
    return parsed.url


def normalize_meet_url(input_val: object) -> str:
    """Validate and return normalized Google Meet URL.

    Raises ValueError with standard message if invalid.
    """
    if input_val is None:
        raise ValueError("url required")
    raw = str(input_val).strip()
    if not raw:
        raise ValueError("url required")

    try:
        parsed = urlparse(raw)
    except Exception:
        raise ValueError("url must be a valid Google Meet URL")

    if not parsed.scheme or not parsed.netloc:
        raise ValueError("url must be a valid Google Meet URL")

    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname is None
        or parsed.hostname.lower() != "meet.google.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("url must be an explicit https://meet.google.com/... URL")

    if not MEET_PATH_RE.match(parsed.path):
        raise ValueError("url must include a Google Meet meeting code")

    return raw


def parse_google_meet_target(input_val: object) -> ParsedGoogleMeetTarget:
    """Parse meeting target into structured ParsedGoogleMeetTarget."""
    if not input_val or not isinstance(input_val, str):
        return ParsedGoogleMeetTarget(is_valid=False)

    raw = input_val.strip()
    if not raw:
        return ParsedGoogleMeetTarget(is_valid=False)

    # 1. Direct space resource: spaces/abc-defg-hij or spaces/12345
    if raw.startswith("spaces/"):
        space_id = raw.replace("spaces/", "").strip()
        code = space_id.lower()
        return ParsedGoogleMeetTarget(
            is_valid=True,
            url=f"https://meet.google.com/{code}",
            space_name=f"spaces/{code}",
            meeting_code=code,
        )

    # 2. Raw code: abc-defg-hij
    if MEET_CODE_RE.match(raw):
        code = raw.lower()
        return ParsedGoogleMeetTarget(
            is_valid=True,
            url=f"https://meet.google.com/{code}",
            space_name=f"spaces/{code}",
            meeting_code=code,
        )

    # 3. URL: https://meet.google.com/abc-defg-hij or lookup
    try:
        parsed = urlparse(raw)
    except Exception:
        return ParsedGoogleMeetTarget(is_valid=False)

    if parsed.hostname and parsed.hostname.lower() == "meet.google.com":
        code_match = MEET_PATH_RE.match(parsed.path)
        if code_match:
            code = code_match.group(1).lower()
            return ParsedGoogleMeetTarget(
                is_valid=True,
                url=f"https://meet.google.com/{code}",
                space_name=f"spaces/{code}",
                meeting_code=code,
            )
        lookup_match = LOOKUP_PATH_RE.match(parsed.path)
        if lookup_match:
            code = lookup_match.group(1).lower()
            return ParsedGoogleMeetTarget(
                is_valid=True,
                url=f"https://meet.google.com/lookup/{code}",
                space_name=f"spaces/{code}",
                meeting_code=code,
            )

    return ParsedGoogleMeetTarget(is_valid=False)
