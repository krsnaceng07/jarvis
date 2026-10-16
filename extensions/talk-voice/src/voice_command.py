"""Talk Voice command implementation.

Handles /voice and /talkvoice slash commands for inspecting and updating
active Talk speech provider voices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

TALK_ADMIN_SCOPE = "operator.admin"


@dataclass(frozen=True, slots=True)
class SpeechVoiceOption:
    """Represents an available speech voice from a provider."""

    id: str
    name: str = ""
    category: str | None = None
    locale: str | None = None
    gender: str | None = None
    personalities: list[str] = field(default_factory=list)
    description: str | None = None


def mask(s: str, keep: int = 6) -> str:
    """Mask sensitive string, showing up to keep characters."""
    trimmed = s.strip()
    if len(trimmed) <= keep:
        return "***"
    return f"{trimmed[:keep]}…"


def is_likely_voice_id(value: str) -> bool:
    """Check if value looks like an alphanumeric ID."""
    v = value.strip()
    if len(v) < 10 or len(v) > 64:
        return False
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", v))


def resolve_provider_label(provider_id: str) -> str:
    """Resolve user-friendly label for provider."""
    match provider_id.lower():
        case "openai":
            return "OpenAI"
        case "microsoft":
            return "Microsoft"
        case "elevenlabs":
            return "ElevenLabs"
        case _:
            return provider_id


def format_voice_meta(voice: SpeechVoiceOption) -> str | None:
    """Format voice metadata attributes into a single string."""
    parts: list[str] = []
    if voice.locale and voice.locale.strip():
        parts.append(voice.locale.strip())
    if voice.gender and voice.gender.strip():
        parts.append(voice.gender.strip())
    valid_personalities = [p.strip() for p in voice.personalities if p.strip()]
    if valid_personalities:
        parts.append(", ".join(valid_personalities))
    return " · ".join(parts) if parts else None


def format_voice_list(voices: list[SpeechVoiceOption], limit: int | float, provider_id: str) -> str:
    """Format a list of voices into a readable message."""
    limit_clamped = max(1, min(int(limit), 50))
    sliced = voices[:limit_clamped]
    lines: list[str] = [
        f"{resolve_provider_label(provider_id)} voices: {len(voices)}",
        "",
    ]
    for v in sliced:
        name = v.name.strip() if v.name else "(unnamed)"
        category = v.category.strip() if v.category else ""
        meta = f" · {category}" if category else ""
        lines.append(f"- {name}{meta}")
        lines.append(f"  id: {v.id}")
        details = format_voice_meta(v)
        if details:
            lines.append(f"  meta: {details}")
        if v.description and v.description.strip():
            lines.append(f"  note: {v.description.strip()}")

    if len(voices) > len(sliced):
        lines.append("")
        lines.append(f"(showing first {len(sliced)})")

    return "\n".join(lines)


def find_voice(voices: list[SpeechVoiceOption], query: str) -> SpeechVoiceOption | None:
    """Find voice by ID, exact name, or partial name."""
    q = query.strip()
    if not q:
        return None
    lower_q = q.lower()

    for v in voices:
        if v.id == q:
            return v

    for v in voices:
        if (v.name or "").lower() == lower_q:
            return v

    for v in voices:
        if lower_q in (v.name or "").lower():
            return v

    return None


def resolve_command_label(channel: str) -> str:
    """Determine channel-specific command prefix."""
    return "/talkvoice" if channel == "discord" else "/voice"


def requires_admin_to_set_voice(
    sender_is_owner: bool | None,
    gateway_client_scopes: list[str] | tuple[str, ...] | None,
) -> bool:
    """Determine whether caller needs admin scope or ownership to mutate voice."""
    if gateway_client_scopes is not None:
        return TALK_ADMIN_SCOPE not in gateway_client_scopes
    return sender_is_owner is not True


def parse_positive_int(val: str | None) -> int | None:
    """Parse positive integer or None."""
    if not val:
        return None
    try:
        # Match only valid integer representation
        cleaned = val.strip()
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        if not cleaned.isdigit():
            return None
        res = int(cleaned)
        return res if res > 0 else None
    except ValueError:
        return None


async def handle_voice_command(ctx: Any, runtime: Any) -> dict[str, str]:
    """Execute the /voice command."""
    channel = getattr(ctx, "channel", "webchat")
    command_label = resolve_command_label(channel)
    args = getattr(ctx, "args", "") or ""
    tokens = args.strip().split() if args.strip() else []
    action = tokens[0].lower() if tokens else "status"

    cfg = runtime.config.current() if hasattr(runtime, "config") else {}
    talk_cfg = cfg.get("talk", {}) if isinstance(cfg, dict) else {}
    provider_id = talk_cfg.get("provider")
    providers = talk_cfg.get("providers", {}) if isinstance(talk_cfg, dict) else {}
    provider_config = (
        providers.get(provider_id, {}) if provider_id and isinstance(providers, dict) else None
    )

    if not provider_id or provider_config is None:
        return {
            "text": (
                "Talk voice is not configured.\n\n"
                "Missing: talk.provider and talk.providers.<provider>.\n"
                "Set it on the gateway, then retry."
            )
        }

    provider_label = resolve_provider_label(provider_id)
    api_key = str(provider_config.get("apiKey", "") or "").strip()
    base_url = provider_config.get("baseUrl")
    current_voice_id = str(provider_config.get("voiceId", "") or "").strip()

    if action == "status":
        return {
            "text": (
                "Talk voice status:\n"
                f"- provider: {provider_id}\n"
                f"- talk.providers.{provider_id}.voiceId: {current_voice_id if current_voice_id else '(unset)'}\n"
                f"- {provider_id}.apiKey: {mask(api_key) if api_key else '(unset)'}"
            )
        }

    if action == "list":
        limit = parse_positive_int(tokens[1]) if len(tokens) > 1 else 12
        if limit is None:
            limit = 12
        try:
            voices_raw = await runtime.tts.list_voices(
                provider=provider_id,
                cfg=cfg,
                api_key=api_key or None,
                base_url=base_url,
            )
            # Normalize list of voice items to SpeechVoiceOption
            voices: list[SpeechVoiceOption] = []
            for item in voices_raw:
                if isinstance(item, SpeechVoiceOption):
                    voices.append(item)
                elif isinstance(item, dict):
                    voices.append(
                        SpeechVoiceOption(
                            id=item.get("id", ""),
                            name=item.get("name", ""),
                            category=item.get("category"),
                            locale=item.get("locale"),
                            gender=item.get("gender"),
                            personalities=item.get("personalities", []),
                            description=item.get("description"),
                        )
                    )
            return {"text": format_voice_list(voices, limit, provider_id)}
        except Exception as err:
            return {"text": f"{provider_label} voice list failed: {err}"}

    if action == "set":
        sender_is_owner = getattr(ctx, "sender_is_owner", None) or getattr(
            ctx, "senderIsOwner", None
        )
        gateway_client_scopes = getattr(ctx, "gateway_client_scopes", None) or getattr(
            ctx, "gatewayClientScopes", None
        )

        if requires_admin_to_set_voice(sender_is_owner, gateway_client_scopes):
            return {"text": f"⚠️ {command_label} set requires operator.admin."}

        query = " ".join(tokens[1:]).strip()
        if not query:
            return {"text": f"Usage: {command_label} set <voiceId|name>"}

        try:
            voices_raw = await runtime.tts.list_voices(
                provider=provider_id,
                cfg=cfg,
                api_key=api_key or None,
                base_url=base_url,
            )
            voices = [
                v
                if isinstance(v, SpeechVoiceOption)
                else SpeechVoiceOption(
                    id=v.get("id", ""),
                    name=v.get("name", ""),
                    category=v.get("category"),
                    locale=v.get("locale"),
                    gender=v.get("gender"),
                    personalities=v.get("personalities", []),
                    description=v.get("description"),
                )
                for v in voices_raw
            ]
        except Exception as err:
            return {"text": f"{provider_label} voice lookup failed: {err}"}

        chosen = find_voice(voices, query)
        if not chosen:
            hint = query if is_likely_voice_id(query) else f'"{query}"'
            return {"text": f"No voice found for {hint}. Try: {command_label} list"}

        async def _mutate(draft: dict[str, Any]) -> None:
            if "talk" not in draft or not isinstance(draft["talk"], dict):
                draft["talk"] = {}
            draft["talk"]["provider"] = provider_id
            if "providers" not in draft["talk"] or not isinstance(draft["talk"]["providers"], dict):
                draft["talk"]["providers"] = {}
            if provider_id not in draft["talk"]["providers"] or not isinstance(
                draft["talk"]["providers"][provider_id], dict
            ):
                draft["talk"]["providers"][provider_id] = {}
            draft["talk"]["providers"][provider_id]["voiceId"] = chosen.id

        await runtime.config.mutate_config_file(
            after_write={"mode": "auto"},
            mutate=_mutate,
        )

        name = chosen.name.strip() if chosen.name else "(unnamed)"
        return {"text": f"✅ {provider_label} Talk voice set to {name}\n{chosen.id}"}

    return {
        "text": "\n".join(
            [
                "Voice commands:",
                "",
                f"{command_label} status",
                f"{command_label} list [limit]",
                f"{command_label} set <voiceId|name>",
            ]
        )
    }
