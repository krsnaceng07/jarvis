"""jarvis.agents.embedded_agent_runner.turn_settlement — Layer 3 host turn settlement runner.

OpenClaw parity:
The core execution engine living in src/agents/embedded_agent_runner and packages/agent_runtime.

Re-exports and extends the Turn Settlement Loop with Layer 3 host integrations:
- Progressive draft previews
- Tool execution depth guard (default: 25)
- Transaction commit barrier (synchronous write to agent.sqlite)
- Compaction trigger on context overflow
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from jarvis_agent.turn_settlement import (
    TurnSettlementConfig,
    TurnSettlementLoop,
    TurnSettlementResult,
    run_turn_settlement_loop,
)

_LOG = logging.getLogger("jarvis.agents.embedded_agent_runner.turn_settlement")


class EmbeddedTurnSettlementRunner(TurnSettlementLoop):
    """Layer 3 Embedded Turn Settlement Runner."""

    def __init__(
        self,
        config: Optional[TurnSettlementConfig] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(config=config, **kwargs)

    async def execute_turn(
        self,
        user_input: str | Dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute turn settlement and return either string or full result object."""
        result = await super().execute_turn(user_input, **kwargs)
        if kwargs.get("return_result_object") is True:
            return result
        return result.final_text

    async def run(
        self,
        prompt: str | Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute turn settlement and return result dictionary."""
        result = await super().execute_turn(prompt, **kwargs)
        return result.to_dict()


__all__ = [
    "EmbeddedTurnSettlementRunner",
    "TurnSettlementConfig",
    "TurnSettlementLoop",
    "TurnSettlementResult",
    "run_turn_settlement_loop",
]
