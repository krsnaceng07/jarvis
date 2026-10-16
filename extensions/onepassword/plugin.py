"""1Password infra plugin definition, SecretRef resolver, and agent tool.

OpenClaw parity: mirrors @openclaw/onepassword infra extension:
- Managed exec SecretRef provider (`op://<vault>/<item>/<field>`)
- Policy-controlled agent tool `onepassword`
- SQLite state storage for audit logs and standing grants
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis_sdk import Plugin

from .src.config import OnepasswordConfig, parse_onepassword_config
from .src.doctor import run_doctor_checks
from .src.op_cli import OpCliRunner
from .src.policy import PolicyEvaluator
from .src.secretref import SecretRefResolver
from .src.storage import OnepasswordStorage
from .src.tool import OnepasswordTool
from .src.types import SecretRefResolution


@dataclass(frozen=True, slots=True)
class _1PasswordPlugin(Plugin):
    """1Password infra plugin descriptor."""

    id: str = "onepassword"
    name: str = "1Password"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = (
        "1Password secret store integration, SecretRef exec provider, and agent tool."
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any = None) -> None:
        """Initialize plugin runtime, storage, tool, and SecretRef resolver."""
        raw_config = getattr(ctx, "config", {}) if ctx else {}
        if isinstance(raw_config, dict) and "plugins" in raw_config:
            raw_config = (
                raw_config.get("plugins", {})
                .get("entries", {})
                .get("onepassword", {})
                .get("config", {})
            )
        elif isinstance(raw_config, dict) and "onepassword" in raw_config:
            raw_config = raw_config["onepassword"]

        config = parse_onepassword_config(raw_config)
        state_dir = getattr(ctx, "state_dir", None)
        if isinstance(state_dir, str):
            state_dir = Path(state_dir)

        storage = OnepasswordStorage(
            db_path=(state_dir / "state" / "jarvis.sqlite") if state_dir else None
        )
        op_runner = OpCliRunner(
            op_bin=config.op_bin,
            state_dir=state_dir,
            default_timeout_ms=config.op_timeout_ms,
        )
        policy_evaluator = PolicyEvaluator(
            config=config,
            storage=storage,
        )
        tool = OnepasswordTool(
            config=config,
            storage=storage,
            op_runner=op_runner,
            policy_evaluator=policy_evaluator,
        )
        secretref_resolver = SecretRefResolver(op_runner=op_runner)

        self.metadata["config"] = config
        self.metadata["storage"] = storage
        self.metadata["op_runner"] = op_runner
        self.metadata["policy_evaluator"] = policy_evaluator
        self.metadata["tool"] = tool
        self.metadata["secretref_resolver"] = secretref_resolver

        # Register doctor contract
        if hasattr(ctx, "register_doctor_contract"):
            ctx.register_doctor_contract(
                "onepassword",
                lambda raw_cfg, fix=False: run_doctor_checks(
                    raw_config=raw_cfg,
                    state_dir=state_dir,
                ),
            )

        # Register agent tool
        if hasattr(ctx, "register_tool"):
            ctx.register_tool(
                name=tool.get_tool_declaration()["name"],
                description=tool.get_tool_declaration()["description"],
                parameters=tool.get_tool_declaration()["parameters"],
                handler=tool.execute,
            )

        # Register secretref exec provider
        if hasattr(ctx, "register_secretref_provider"):
            ctx.register_secretref_provider(
                "onepassword",
                secretref_resolver.resolve,
            )

    async def resolve_secret_ref(self, ref_id: str) -> SecretRefResolution:
        """Resolve a 1Password secret reference URI."""
        resolver: SecretRefResolver = self.metadata.get("secretref_resolver") or SecretRefResolver()
        return await resolver.resolve(ref_id)

    def get_tool(self) -> OnepasswordTool:
        """Get the onepassword agent tool instance."""
        return self.metadata.get("tool") or OnepasswordTool(
            config=OnepasswordConfig(),
            storage=OnepasswordStorage(),
        )


onepassword_plugin = _1PasswordPlugin()
entry = onepassword_plugin
