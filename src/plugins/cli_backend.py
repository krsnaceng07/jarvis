"""jarvis.plugins.cli_backend — CLI backend plugin contracts & configuration.

OpenClaw parity: mirrors
``openclaw-main/src/plugins/cli-backend.types.ts`` and
``openclaw-main/src/plugin-sdk/cli-backend.ts``.

Features:
- `CliBundleMcpMode`: `"claude-config-file"` | `"codex-config-overrides"` | `"gemini-system-settings"`
- `CliBackendExecutionMode`: `"agent"` | `"side-question"`
- `CliBackendThinkingLevel`: `"off"` | `"minimal"` | `"low"` | `"medium"` | `"high"` | `"xhigh"` | `"adaptive"` | `"max"`
- `CliBackendOutput`: `"json"` | `"jsonl"` | `"text"`
- `CliBackendJsonlDialect`: `"claude-stream-json"` | `"gemini-stream-json"`
- `CliBackendInput`: `"arg"` | `"stdin"`
- `CliBackendSessionMode`: `"always"` | `"existing"` | `"none"`
- `CliBackendSystemPromptMode`: `"append"` | `"replace"`
- `CliBackendSystemPromptWhen`: `"first"` | `"always"` | `"never"`
- `CliBackendImageMode`: `"repeat"` | `"list"`
- `CliBackendNativeToolMode`: `"absent"` | `"always-on"` | `"selectable"`
- `CliBackendConfig`: Plugin configuration dataclass.
- `CliBackendPlugin`: CLI backend plugin contract dataclass.
- `resolve_cli_backend_plugin()`: Resolves and defaults CLI backend plugin options.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CliBundleMcpMode = Literal["claude-config-file", "codex-config-overrides", "gemini-system-settings"]
CliBackendExecutionMode = Literal["agent", "side-question"]
CliBackendThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh", "adaptive", "max"]
CliBackendOutput = Literal["json", "jsonl", "text"]
CliBackendJsonlDialect = Literal["claude-stream-json", "gemini-stream-json"]
CliBackendInput = Literal["arg", "stdin"]
CliBackendSessionMode = Literal["always", "existing", "none"]
CliBackendSystemPromptMode = Literal["append", "replace"]
CliBackendSystemPromptWhen = Literal["first", "always", "never"]
CliBackendImageMode = Literal["repeat", "list"]
CliBackendNativeToolMode = Literal["absent", "always-on", "selectable"]

CLI_FRESH_WATCHDOG_DEFAULTS: dict[str, int] = {
    "initialSilenceTimeoutMs": 120_000,
    "idleTimeoutMs": 60_000,
}

CLI_RESUME_WATCHDOG_DEFAULTS: dict[str, int] = {
    "initialSilenceTimeoutMs": 180_000,
    "idleTimeoutMs": 90_000,
}


@dataclass
class CliBackendConfig:
    command: str
    args: list[str] = field(default_factory=list)
    resumeArgs: list[str] = field(default_factory=list)
    output: CliBackendOutput = "jsonl"
    resumeOutput: CliBackendOutput = "jsonl"
    jsonlDialect: CliBackendJsonlDialect = "gemini-stream-json"
    input: CliBackendInput = "arg"
    maxPromptArgChars: int = 16000
    modelArg: str | None = "--model"
    modelAliases: dict[str, str] = field(default_factory=dict)
    sessionArgs: list[str] = field(default_factory=list)
    sessionMode: CliBackendSessionMode = "existing"
    sessionIdFields: list[str] = field(default_factory=lambda: ["session_id", "conversation_id"])
    systemPromptArg: str | None = None
    systemPromptFileArg: str | None = "--system-file"
    systemPromptMode: CliBackendSystemPromptMode = "append"
    systemPromptWhen: CliBackendSystemPromptWhen = "first"
    imageArg: str | None = "--image"
    imageMode: CliBackendImageMode = "repeat"
    serialize: bool = True


@dataclass
class CliBackendPlugin:
    id: str
    config: CliBackendConfig
    liveTest: dict[str, Any] = field(default_factory=dict)
    bundleMcp: bool = False
    bundleMcpMode: CliBundleMcpMode | None = None
    ownsNativeCompaction: bool = False
    nativeToolMode: CliBackendNativeToolMode = "absent"


def resolve_cli_backend_plugin(backend_cfg: dict[str, Any] | None) -> CliBackendPlugin:
    """Resolve and validate a CLI backend plugin configuration."""
    val = backend_cfg if isinstance(backend_cfg, dict) else {}

    backend_id = str(val.get("id") or "custom-cli").strip()
    config_raw = val.get("config") if isinstance(val.get("config"), dict) else {}

    cmd = str(config_raw.get("command") or backend_id).strip()
    args = [str(x) for x in config_raw.get("args", []) if isinstance(x, str)]
    resume_args = [str(x) for x in config_raw.get("resumeArgs", []) if isinstance(x, str)]

    raw_output = str(config_raw.get("output") or "jsonl").lower()
    output: CliBackendOutput = (
        raw_output if raw_output in ("json", "jsonl", "text") else "jsonl"  # type: ignore[assignment]
    )

    raw_dialect = str(config_raw.get("jsonlDialect") or "gemini-stream-json").lower()
    dialect: CliBackendJsonlDialect = (
        raw_dialect if raw_dialect in ("claude-stream-json", "gemini-stream-json") else "gemini-stream-json"  # type: ignore[assignment]
    )

    raw_input = str(config_raw.get("input") or "arg").lower()
    inp: CliBackendInput = (
        raw_input if raw_input in ("arg", "stdin") else "arg"  # type: ignore[assignment]
    )

    aliases_raw = config_raw.get("modelAliases")
    clean_aliases = {str(k): str(v) for k, v in aliases_raw.items()} if isinstance(aliases_raw, dict) else {}

    parsed_config = CliBackendConfig(
        command=cmd,
        args=args,
        resumeArgs=resume_args,
        output=output,
        resumeOutput=output,
        jsonlDialect=dialect,
        input=inp,
        maxPromptArgChars=int(config_raw.get("maxPromptArgChars", 16000)),
        modelArg=config_raw.get("modelArg"),
        modelAliases=clean_aliases,
        sessionArgs=[str(x) for x in config_raw.get("sessionArgs", []) if isinstance(x, str)],
        systemPromptArg=config_raw.get("systemPromptArg"),
        systemPromptFileArg=config_raw.get("systemPromptFileArg"),
        imageArg=config_raw.get("imageArg"),
        serialize=bool(config_raw.get("serialize", True)),
    )

    raw_mcp_mode = str(val.get("bundleMcpMode")).lower() if val.get("bundleMcpMode") else None
    mcp_mode: CliBundleMcpMode | None = (
        raw_mcp_mode if raw_mcp_mode in ("claude-config-file", "codex-config-overrides", "gemini-system-settings") else None  # type: ignore[assignment]
    )

    raw_native = str(val.get("nativeToolMode") or "absent").lower()
    native_mode: CliBackendNativeToolMode = (
        raw_native if raw_native in ("absent", "always-on", "selectable") else "absent"  # type: ignore[assignment]
    )

    return CliBackendPlugin(
        id=backend_id,
        config=parsed_config,
        liveTest=val.get("liveTest") if isinstance(val.get("liveTest"), dict) else {},
        bundleMcp=bool(val.get("bundleMcp", False)),
        bundleMcpMode=mcp_mode,
        ownsNativeCompaction=bool(val.get("ownsNativeCompaction", False)),
        nativeToolMode=native_mode,
    )


__all__ = [
    "CLI_FRESH_WATCHDOG_DEFAULTS",
    "CLI_RESUME_WATCHDOG_DEFAULTS",
    "CliBackendConfig",
    "CliBackendExecutionMode",
    "CliBackendImageMode",
    "CliBackendInput",
    "CliBackendJsonlDialect",
    "CliBackendNativeToolMode",
    "CliBackendOutput",
    "CliBackendPlugin",
    "CliBackendSessionMode",
    "CliBackendSystemPromptMode",
    "CliBackendSystemPromptWhen",
    "CliBackendThinkingLevel",
    "CliBundleMcpMode",
    "resolve_cli_backend_plugin",
]
