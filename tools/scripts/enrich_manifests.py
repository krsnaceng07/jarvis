import json
from pathlib import Path

EXTENSIONS = Path("extensions")

CHANNELS = {
    "discord",
    "telegram",
    "slack",
    "whatsapp",
    "signal",
    "feishu",
    "matrix",
    "msteams",
    "line",
    "googlechat",
    "mattermost",
    "nextcloud-talk",
    "synology-chat",
    "irc",
    "twitch",
    "zalo",
    "zalouser",
    "nostr",
    "tlon",
    "clickclack",
    "sms",
    "imessage",
    "qa-channel",
    "qa_channel",
    "buzz",
    "a2a",
}

PROVIDERS = {
    "openai",
    "anthropic",
    "deepseek",
    "groq",
    "mistral",
    "together",
    "cohere",
    "openrouter",
    "google",
    "xai",
    "qwen",
    "cerebras",
    "amazon-bedrock",
    "amazon-bedrock-mantle",
    "alibaba",
    "minimax",
    "moonshot",
    "novita",
    "nvidia",
    "ollama",
    "stepfun",
    "volcengine",
    "voyage",
    "azure-speech",
    "deepgram",
    "elevenlabs",
    "fish-audio-speech",
    "fal",
    "runway",
    "pixverse",
    "sglang",
    "vllm",
    "inworld",
    "arcee",
    "baseten",
    "byteplus",
    "chutes",
    "cloudflare-ai-gateway",
    "featherless",
    "featherless-x",
    "fireworks",
    "gmi",
    "gradium",
    "huggingface",
    "kilocode",
    "kimi-coding",
    "litellm",
    "llama-cpp",
    "lmstudio",
    "longcat",
    "meta",
    "microsoft",
    "microsoft-foundry",
    "opencode",
    "opencode-go",
    "qianfan",
    "synthetic",
    "tencent",
    "venice",
    "vercel-ai-gateway",
    "vydra",
    "xiaomi",
    "zai",
    "deepinfra",
    "perplexity",
    "clawrouter",
    "anthropic-vertex",
}

MEMORY = {"active_memory", "memory_core", "memory_lancedb", "memory_wiki", "honcho"}

INFRA = {
    "admin-http-rpc",
    "bonjour",
    "cron",
    "onepassword",
    "vault",
    "webhooks",
    "device-pair",
    "diagnostics-otel",
    "diagnostics-prometheus",
    "linux-node",
    "openshell",
    "policy",
    "raft",
    "reef",
    "visitor-access",
    "beam",
    "browser",
}

MIGRATION = {"migrate-claude", "migrate-hermes"}

# All others default to "tool"


def classify_extension(name: str) -> str:
    if name in CHANNELS:
        return "channel"
    if name in PROVIDERS:
        return "provider"
    if name in MEMORY:
        return "memory"
    if name in INFRA:
        return "infra"
    if name in MIGRATION:
        return "migration"
    return "tool"


updated = 0
for ext_dir in sorted(EXTENSIONS.iterdir()):
    if not ext_dir.is_dir() or ext_dir.name.startswith("."):
        continue

    kind = classify_extension(ext_dir.name)

    for manifest_name in ["jarvis.plugin.json", "openclaw.plugin.json"]:
        manifest_path = ext_dir / manifest_name
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                if data.get("kind") != kind:
                    data["kind"] = kind
                    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    updated += 1
            except Exception as e:
                print(f"Error updating {manifest_path}: {e}")

print(f"Enriched manifests count: {updated}")
