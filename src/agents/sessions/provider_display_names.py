"""jarvis.agents.sessions.provider_display_names — built-in provider labels.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/provider-display-names.ts``.

Built-in provider labels shown in session / model UI
when plugin metadata does not supply a display name.

Parity
======
- ``BUILT_IN_PROVIDER_DISPLAY_NAMES: dict[str, str]``
  (``provider-display-names.ts:5-37``) — every key
  and every value is byte-identical to the OpenClaw
  source.

Phase 6.0 — scaffolding + helpers + small types.

Adaptations
-----------
- Python uses ``dict[str, str]`` (PEP 585) instead of
  TS ``Record<string, string>``. The same ordering
  (insertion order) is preserved so the UI listing
  matches the OpenClaw source.
- Provider id ``"minimax"`` + ``"minimax-cn"`` are
  preserved verbatim — they were renamed in upstream
  OpenClaw to a generic provider placeholder; the
  JARVIS port keeps the upstream literal values so
  future provider plugins can register against them.
"""
from __future__ import annotations

#: Built-in provider labels. Mirrors
#: ``BUILT_IN_PROVIDER_DISPLAY_NAMES``
#: (``provider-display-names.ts:5-37``). Insertion
#: order is preserved so the UI listing matches the
#: OpenClaw source.
BUILT_IN_PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "anthropic": "Anthropic",
    "amazon-bedrock": "Amazon Bedrock",
    "azure-openai-responses": "Azure OpenAI Responses",
    "cerebras": "Cerebras",
    "cloudflare-ai-gateway": "Cloudflare AI Gateway",
    "cloudflare-workers-ai": "Cloudflare Workers AI",
    "deepseek": "Deepseek",
    "fireworks": "Fireworks",
    "google": "Google Gemini",
    "google-vertex": "Google Vertex AI",
    "groq": "Groq",
    "huggingface": "Hugging Face",
    "kimi-coding": "Kimi For Coding",
    "meta": "Meta",
    "mistral": "Mistral",
    "minimax": "MiniMax",
    "minimax-cn": "MiniMax (China)",
    "moonshotai": "Moonshot AI",
    "moonshotai-cn": "Moonshot AI (China)",
    "opencode": "OpenCode Zen",
    "opencode-go": "OpenCode Go",
    "openai": "OpenAI",
    "openrouter": "OpenRouter",
    "together": "Together AI",
    "vercel-ai-gateway": "Vercel AI Gateway",
    "xai": "xAI",
    "zai": "ZAI",
    "xiaomi": "Xiaomi MiMo",
    "xiaomi-token-plan-cn": "Xiaomi MiMo Token Plan (China)",
    "xiaomi-token-plan-ams": "Xiaomi MiMo Token Plan (Amsterdam)",
    "xiaomi-token-plan-sgp": "Xiaomi MiMo Token Plan (Singapore)",
}


__all__ = [
    "BUILT_IN_PROVIDER_DISPLAY_NAMES",
]
