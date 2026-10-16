"""Collect configured model references from config-shaped objects.

OpenClaw parity:
``packages/model-catalog-core/src/configured-model-refs.ts``.
Visits raw selector refs without changing values, order, or fallback
indices — collection is read-only evidence for doctor/validation, never
a rewrite pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

#: Agent config keys that can contain direct model references.
AGENT_MODEL_CONFIG_KEYS: tuple[str, ...] = (
    "model",
    "utilityModel",
    "imageModel",
    "voiceModel",
    "pdfModel",
)

_ModelRole = Literal["primary", "fallback"]


@dataclass(frozen=True, slots=True)
class ConfiguredModelRef:
    """One configured model reference plus its config path."""

    path: str
    value: str


def _as_record(value: Any) -> dict[str, Any] | None:
    """Narrow ``unknown`` JSON to a string-keyed record (``None`` when not one)."""
    if not isinstance(value, dict):
        return None
    narrowed: dict[str, Any] = value
    return narrowed


def visit_model_selector_refs(
    value: object,
    path: str,
    visit: Callable[[str, str, _ModelRole], None],
) -> None:
    """Visit raw selector refs: plain string, or primary/fallbacks mapping."""
    if isinstance(value, str):
        visit(path, value, "primary")
        return
    record = _as_record(value)
    if record is None:
        return
    primary = record.get("primary")
    if isinstance(primary, str):
        visit(f"{path}.primary", primary, "primary")
    if isinstance(record.get("fallbacks"), list):
        fallbacks: list[Any] = record.get("fallbacks") or []
        for index, fallback in enumerate(fallbacks):
            if isinstance(fallback, str):
                visit(f"{path}.fallbacks.{index}", fallback, "fallback")


def list_model_refs_from_config_value(value: object) -> list[str]:
    """List raw refs from one string or primary/fallback model selector."""
    refs: list[str] = []
    visit_model_selector_refs(value, "", lambda _path, ref, _role: refs.append(ref))
    return refs


def collect_configured_model_refs(
    config: object,
    *,
    include_channel_model_overrides: bool = True,
) -> list[ConfiguredModelRef]:
    """Collect configured model references from agents, tools, channels, hooks."""
    refs: list[ConfiguredModelRef] = []

    def push_model_ref(path: str, value: object) -> None:
        if isinstance(value, str) and value.strip():
            refs.append(ConfiguredModelRef(path=path, value=value.strip()))

    def collect_model_config(path: str, value: object) -> None:
        visit_model_selector_refs(value, path, lambda p, v, _role: push_model_ref(p, v))

    def collect_from_agent(path: str, agent: object, include_entry_selectors: bool = False) -> None:
        record = _as_record(agent)
        if record is None:
            return
        for key in AGENT_MODEL_CONFIG_KEYS:
            collect_model_config(f"{path}.{key}", record.get(key))
        media_models = _as_record(record.get("mediaModels")) or {}
        for capability in ("image", "video", "music"):
            collect_model_config(f"{path}.mediaModels.{capability}", media_models.get(capability))
        heartbeat = _as_record(record.get("heartbeat"))
        push_model_ref(f"{path}.heartbeat.model", heartbeat.get("model") if heartbeat else None)
        subagents = _as_record(record.get("subagents"))
        collect_model_config(
            f"{path}.subagents.model", subagents.get("model") if subagents else None
        )
        compaction = _as_record(record.get("compaction"))
        if compaction is not None:
            push_model_ref(f"{path}.compaction.model", compaction.get("model"))
            memory_flush = _as_record(compaction.get("memoryFlush"))
            push_model_ref(
                f"{path}.compaction.memoryFlush.model",
                memory_flush.get("model") if memory_flush else None,
            )
        models = _as_record(record.get("models"))
        if models is not None:
            for model_ref in models:
                push_model_ref(f"{path}.models.{model_ref}", model_ref)
        if include_entry_selectors:
            tools = _as_record(record.get("tools")) or {}
            exec_block = _as_record(tools.get("exec")) or {}
            reviewer = _as_record(exec_block.get("reviewer"))
            collect_model_config(
                f"{path}.tools.exec.reviewer.model",
                reviewer.get("model") if reviewer else None,
            )
            tts = _as_record(record.get("tts"))
            push_model_ref(f"{path}.tts.summaryModel", tts.get("summaryModel") if tts else None)

    root = _as_record(config) or {}
    tools = _as_record(root.get("tools")) or {}
    exec_block = _as_record(tools.get("exec")) or {}
    reviewer = _as_record(exec_block.get("reviewer"))
    collect_model_config("tools.exec.reviewer.model", reviewer.get("model") if reviewer else None)
    media = _as_record(tools.get("media")) or {}
    for capability in ("image", "audio", "video"):
        entry = _as_record(media.get(capability))
        push_model_ref(
            f"tools.media.{capability}.preferredModel",
            entry.get("preferredModel") if entry else None,
        )
    agents = _as_record(root.get("agents")) or {}
    collect_from_agent("agents.defaults", agents.get("defaults"))
    if "entries" in agents:
        entries = _as_record(agents.get("entries")) or {}
        for agent_id, entry in entries.items():
            collect_from_agent(f"agents.entries.{agent_id}", entry, True)
    elif isinstance(agents.get("list"), list):
        entries_list: list[Any] = agents.get("list") or []
        for index, entry in enumerate(entries_list):
            collect_from_agent(f"agents.list.{index}", entry, True)
    if include_channel_model_overrides:
        channels = _as_record(root.get("channels")) or {}
        model_by_channel = _as_record(channels.get("modelByChannel")) or {}
        for channel_id, channel_map in model_by_channel.items():
            record = _as_record(channel_map)
            if record is None:
                continue
            for target_id, model_ref in record.items():
                push_model_ref(f"channels.modelByChannel.{channel_id}.{target_id}", model_ref)
    hooks = _as_record(root.get("hooks")) or {}
    if isinstance(hooks.get("mappings"), list):
        mappings: list[Any] = hooks.get("mappings") or []
        for index, mapping in enumerate(mappings):
            record = _as_record(mapping)
            push_model_ref(f"hooks.mappings.{index}.model", record.get("model") if record else None)
    gmail = _as_record(hooks.get("gmail"))
    push_model_ref("hooks.gmail.model", gmail.get("model") if gmail else None)
    tts_root = _as_record(root.get("tts"))
    push_model_ref("tts.summaryModel", tts_root.get("summaryModel") if tts_root else None)

    def collect_discord_voice(path: str, value: object) -> None:
        voice = _as_record(value) or {}
        push_model_ref(f"{path}.model", voice.get("model"))
        voice_tts = _as_record(voice.get("tts"))
        push_model_ref(
            f"{path}.tts.summaryModel", voice_tts.get("summaryModel") if voice_tts else None
        )

    channels_block = _as_record(root.get("channels")) or {}
    discord = _as_record(channels_block.get("discord")) or {}
    collect_discord_voice("channels.discord.voice", discord.get("voice"))
    accounts = _as_record(discord.get("accounts")) or {}
    for account_id, account in accounts.items():
        record = _as_record(account)
        collect_discord_voice(
            f"channels.discord.accounts.{account_id}.voice",
            record.get("voice") if record else None,
        )
    return refs


def collect_configured_model_ref_values(
    config: object,
    *,
    include_channel_model_overrides: bool = True,
) -> list[str]:
    """Collect only configured model reference values."""
    return [
        ref.value
        for ref in collect_configured_model_refs(
            config, include_channel_model_overrides=include_channel_model_overrides
        )
    ]


__all__ = [
    "AGENT_MODEL_CONFIG_KEYS",
    "ConfiguredModelRef",
    "collect_configured_model_ref_values",
    "collect_configured_model_refs",
    "list_model_refs_from_config_value",
    "visit_model_selector_refs",
]
