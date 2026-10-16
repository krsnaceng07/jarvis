from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TelegramConfig(BaseModel):
    """Configuration for the Telegram channel plugin.

    This matches the schema defined in openclaw.plugin.json.
    """

    botToken: str = Field(description="Telegram Bot API token")
    transport: Literal["polling", "webhook"] = Field(default="polling")
    pollingIntervalSec: int = Field(default=1, ge=1)

    # DM Policy
    dmPolicy: Literal["open", "pairing", "allowlist", "deny", "block", "disabled"] = Field(
        default="open"
    )
    allowFrom: list[str] = Field(default_factory=list)

    # Group Policy
    groupPolicy: Literal["require_mention", "allowlist", "deny"] = Field(default="require_mention")
    groupAllowFrom: list[str] = Field(default_factory=list)

    # Voice Policy
    voiceReplies: bool = Field(default=True, description="Whether to send voice note replies alongside text")

    @property
    def is_valid(self) -> bool:
        """Return True if the config has a valid bot token."""
        return bool(self.botToken and self.botToken.strip())
