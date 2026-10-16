import re
from typing import Any, Dict, List, Literal, Optional

IMessageService = Literal["imessage", "sms", "auto"]

CHAT_ID_PREFIXES = ["chat_id:", "chatid:", "chat:"]
CHAT_GUID_PREFIXES = ["chat_guid:", "chatguid:", "guid:"]
CHAT_IDENTIFIER_PREFIXES = ["chat_identifier:", "chatidentifier:", "chatident:"]
SERVICE_PREFIXES = [
    {"prefix": "imessage:", "service": "imessage"},
    {"prefix": "sms:", "service": "sms"},
    {"prefix": "auto:", "service": "auto"},
]


def normalize_bare_imessage_chat_identifier(raw: str) -> Optional[str]:
    trimmed = raw.strip()
    if not trimmed:
        return None
    if ";" in trimmed:
        return trimmed
    return None


def normalize_e164(raw: str) -> Optional[str]:
    # Very basic e164 normalizer for port parity
    trimmed = raw.strip()
    if trimmed.startswith("+") and re.match(r"^\+[\d\s\.\-\(\)]+$", trimmed):
        return trimmed
    return None


def normalize_lowercase_string_or_empty(raw: str) -> str:
    return raw.strip().lower()


def normalize_imessage_handle(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return ""

    lowered = normalize_lowercase_string_or_empty(trimmed)
    if lowered.startswith("imessage:"):
        return normalize_imessage_handle(trimmed[9:])
    if lowered.startswith("sms:"):
        return normalize_imessage_handle(trimmed[4:])
    if lowered.startswith("auto:"):
        return normalize_imessage_handle(trimmed[5:])

    for prefix in CHAT_ID_PREFIXES:
        if lowered.startswith(prefix):
            return f"chat_id:{trimmed[len(prefix) :].strip()}"

    for prefix in CHAT_GUID_PREFIXES:
        if lowered.startswith(prefix):
            return f"chat_guid:{trimmed[len(prefix) :].strip()}"

    for prefix in CHAT_IDENTIFIER_PREFIXES:
        if lowered.startswith(prefix):
            return f"chat_identifier:{trimmed[len(prefix) :].strip()}"

    if "@" in trimmed:
        return lowered

    bare_chat_identifier = normalize_bare_imessage_chat_identifier(trimmed)
    if bare_chat_identifier:
        return f"chat_identifier:{bare_chat_identifier}"

    normalized = normalize_e164(trimmed)
    if normalized:
        return normalized

    return re.sub(r"\s+", "", trimmed)


def parse_service_prefixed_bare_chat_identifier(
    trimmed: str, lower: str
) -> Optional[Dict[str, Any]]:
    for prefix_info in SERVICE_PREFIXES:
        prefix = prefix_info["prefix"]
        if not lower.startswith(prefix):
            continue

        chat_identifier = normalize_bare_imessage_chat_identifier(trimmed[len(prefix) :])
        if chat_identifier:
            return {"kind": "chat_identifier", "chatIdentifier": chat_identifier}

    return None


def parse_imessage_target(raw: str) -> Dict[str, Any]:
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError("iMessage target is required")

    lower = normalize_lowercase_string_or_empty(trimmed)

    bare_prefixed = parse_service_prefixed_bare_chat_identifier(trimmed, lower)
    if bare_prefixed:
        return bare_prefixed

    for prefix in CHAT_ID_PREFIXES:
        if lower.startswith(prefix):
            val = trimmed[len(prefix) :].strip()
            try:
                return {"kind": "chat_id", "chatId": int(val)}
            except ValueError:
                pass

    for prefix in CHAT_GUID_PREFIXES:
        if lower.startswith(prefix):
            return {"kind": "chat_guid", "chatGuid": trimmed[len(prefix) :].strip()}

    for prefix in CHAT_IDENTIFIER_PREFIXES:
        if lower.startswith(prefix):
            return {"kind": "chat_identifier", "chatIdentifier": trimmed[len(prefix) :].strip()}

    bare_chat_identifier = normalize_bare_imessage_chat_identifier(trimmed)
    if bare_chat_identifier:
        return {"kind": "chat_identifier", "chatIdentifier": bare_chat_identifier}

    return {"kind": "handle", "to": trimmed, "service": "auto"}


def looks_like_imessage_explicit_target_id(raw: str) -> bool:
    trimmed = raw.strip()
    if not trimmed:
        return False

    lower = normalize_lowercase_string_or_empty(trimmed)
    if re.match(r"^(imessage:|sms:|auto:)", lower):
        return True

    for prefix in CHAT_ID_PREFIXES + CHAT_GUID_PREFIXES + CHAT_IDENTIFIER_PREFIXES:
        if lower.startswith(prefix):
            return True

    if normalize_bare_imessage_chat_identifier(trimmed):
        return True

    return False


def infer_imessage_target_chat_type(raw: str) -> Optional[Literal["direct", "group"]]:
    try:
        parsed = parse_imessage_target(raw)
        if parsed.get("kind") == "handle":
            return "direct"
        return "group"
    except Exception:
        return None


def parse_imessage_allow_target(raw: str) -> Dict[str, Any]:
    trimmed = raw.strip()
    if not trimmed:
        return {"kind": "handle", "handle": ""}

    # Very basic port, mostly we just care about handles for pairing
    return {"kind": "handle", "handle": normalize_imessage_handle(trimmed)}


def is_allowed_imessage_sender(sender: str, allowed: List[str]) -> bool:
    normalized_sender = normalize_imessage_handle(sender)
    for rule in allowed:
        target = parse_imessage_allow_target(rule)
        if target.get("kind") == "handle" and target.get("handle") == normalized_sender:
            return True
        if target.get("handle") == "*":
            return True
    return False


def format_imessage_chat_target(chat_id: Optional[int]) -> str:
    if not chat_id:
        return ""
    return f"chat_id:{chat_id}"
