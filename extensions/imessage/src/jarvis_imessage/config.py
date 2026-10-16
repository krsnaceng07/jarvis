from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

DEFAULT_ACCOUNT_ID = "default"


@dataclass(frozen=True)
class IMessageGroupConfig:
    requireMention: bool = False


@dataclass(frozen=True)
class IMessageConfig:
    cliPath: Optional[str] = None
    dbPath: Optional[str] = None
    dmPolicy: Literal["pairing", "allowlist"] = "pairing"
    allowFrom: List[str] = field(default_factory=list)
    groupPolicy: Literal["allowlist"] = "allowlist"
    groupAllowFrom: List[str] = field(default_factory=list)
    groups: Dict[str, IMessageGroupConfig] = field(default_factory=dict)
    includeAttachments: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IMessageConfig":
        groups = {}
        for k, v in data.get("groups", {}).items():
            groups[k] = IMessageGroupConfig(requireMention=v.get("requireMention", False))

        return cls(
            cliPath=data.get("cliPath"),
            dbPath=data.get("dbPath"),
            dmPolicy=data.get("dmPolicy", "pairing"),
            allowFrom=data.get("allowFrom", []),
            groupPolicy=data.get("groupPolicy", "allowlist"),
            groupAllowFrom=data.get("groupAllowFrom", []),
            groups=groups,
            includeAttachments=data.get("includeAttachments", False),
        )


@dataclass(frozen=True)
class ResolvedIMessageAccount:
    accountId: str
    name: str
    enabled: bool
    configured: bool
    config: IMessageConfig


def resolve_imessage_account(cfg: Any, accountId: Optional[str] = None) -> ResolvedIMessageAccount:
    # In a real implementation this reads from PluginContext.config
    # For now we create a shim to represent the resolved account.
    config_dict = cfg.get("channels", {}).get("imessage", {}) if hasattr(cfg, "get") else {}
    enabled = config_dict.get("enabled", False)

    return ResolvedIMessageAccount(
        accountId=accountId or DEFAULT_ACCOUNT_ID,
        name="iMessage",
        enabled=enabled,
        configured=True,
        config=IMessageConfig.from_dict(config_dict),
    )
