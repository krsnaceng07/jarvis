"""Configuration compatibility and legacy migration helpers for Voice Call."""

from __future__ import annotations

from typing import Any


def migrate_legacy_voice_call_config(raw_config: dict[str, Any]) -> dict[str, Any]:
    """Migrate deprecated or legacy config keys into the modern canonical schema.

    Canonical OpenClaw migration rules:
    - `provider: "log"` -> `provider: "mock"`
    - `twilio.from` -> `fromNumber`
    - `streaming.sttProvider` -> `streaming.provider`
    - `streaming.openaiApiKey` -> `streaming.providers.openai.apiKey`
    - `streaming.sttModel` -> `streaming.providers.openai.model`
    - `streaming.silenceDurationMs` -> `streaming.providers.openai.silenceDurationMs`
    - `streaming.vadThreshold` -> `streaming.providers.openai.vadThreshold`
    - `realtime.agentContext.includeSystemPrompt` -> removed
    """
    if not isinstance(raw_config, dict):
        return {}

    migrated = dict(raw_config)

    # 1. provider: "log" -> "mock"
    if str(migrated.get("provider", "")).strip().lower() == "log":
        migrated["provider"] = "mock"

    # 2. callerId alias -> fromNumber
    if "callerId" in migrated and "fromNumber" not in migrated:
        migrated["fromNumber"] = migrated.pop("callerId")

    # 3. targetNumber alias -> toNumber
    if "targetNumber" in migrated and "toNumber" not in migrated:
        migrated["toNumber"] = migrated.pop("targetNumber")

    # 4. twilio.from -> fromNumber
    twilio = dict(migrated.get("twilio", {})) if isinstance(migrated.get("twilio"), dict) else {}
    if "from" in twilio:
        if "fromNumber" not in migrated:
            migrated["fromNumber"] = twilio.pop("from")
        else:
            twilio.pop("from", None)

    # Flat Twilio legacy keys
    if "twilioAccountSid" in migrated and "accountSid" not in twilio:
        twilio["accountSid"] = migrated.pop("twilioAccountSid")
    if "twilioAuthToken" in migrated and "authToken" not in twilio:
        twilio["authToken"] = migrated.pop("twilioAuthToken")
    if "twilioApiKey" in migrated and "apiKey" not in twilio:
        twilio["apiKey"] = migrated.pop("twilioApiKey")
    if "twilioApiSecret" in migrated and "apiSecret" not in twilio:
        twilio["apiSecret"] = migrated.pop("twilioApiSecret")
    if twilio:
        migrated["twilio"] = twilio

    # 5. Streaming migrations
    streaming = (
        dict(migrated.get("streaming", {})) if isinstance(migrated.get("streaming"), dict) else {}
    )
    if "sttProvider" in streaming and "provider" not in streaming:
        streaming["provider"] = streaming.pop("sttProvider")

    st_providers = (
        dict(streaming.get("providers", {})) if isinstance(streaming.get("providers"), dict) else {}
    )
    st_openai = (
        dict(st_providers.get("openai", {})) if isinstance(st_providers.get("openai"), dict) else {}
    )

    if "openaiApiKey" in streaming:
        if "apiKey" not in st_openai:
            st_openai["apiKey"] = streaming.pop("openaiApiKey")
        else:
            streaming.pop("openaiApiKey", None)

    if "sttModel" in streaming:
        if "model" not in st_openai:
            st_openai["model"] = streaming.pop("sttModel")
        else:
            streaming.pop("sttModel", None)

    if "silenceDurationMs" in streaming:
        if "silenceDurationMs" not in st_openai:
            st_openai["silenceDurationMs"] = streaming.pop("silenceDurationMs")
        else:
            streaming.pop("silenceDurationMs", None)

    if "vadThreshold" in streaming:
        if "vadThreshold" not in st_openai:
            st_openai["vadThreshold"] = streaming.pop("vadThreshold")
        else:
            streaming.pop("vadThreshold", None)

    if st_openai:
        st_providers["openai"] = st_openai
    if st_providers:
        streaming["providers"] = st_providers
    if streaming:
        migrated["streaming"] = streaming

    # 6. Realtime migrations: remove realtime.agentContext.includeSystemPrompt
    realtime = (
        dict(migrated.get("realtime", {})) if isinstance(migrated.get("realtime"), dict) else {}
    )
    if "agentContext" in realtime and isinstance(realtime["agentContext"], dict):
        agent_ctx = dict(realtime["agentContext"])
        agent_ctx.pop("includeSystemPrompt", None)
        if not agent_ctx:
            realtime.pop("agentContext", None)
        else:
            realtime["agentContext"] = agent_ctx
        migrated["realtime"] = realtime

    # 7. Flat Telnyx legacy keys
    telnyx = dict(migrated.get("telnyx", {})) if isinstance(migrated.get("telnyx"), dict) else {}
    if "telnyxApiKey" in migrated and "apiKey" not in telnyx:
        telnyx["apiKey"] = migrated.pop("telnyxApiKey")
    if "telnyxConnectionId" in migrated and "connectionId" not in telnyx:
        telnyx["connectionId"] = migrated.pop("telnyxConnectionId")
    if telnyx:
        migrated["telnyx"] = telnyx

    return migrated
