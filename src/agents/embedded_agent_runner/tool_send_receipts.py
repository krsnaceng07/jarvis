"""jarvis.agents.embedded_agent_runner.tool_send_receipts — embedded tool-send receipt registry.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-send-receipts.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`record_embedded_tool_send_receipt` — store a tool-send
  receipt for a given tool call id.
- :func:`consume_embedded_tool_send_receipt` — pop a previously
  stored tool-send receipt.

Phase 7.4a — focused minimal port.

The OpenClaw source uses
:func:`createSessionManagerRuntimeRegistry` from
``agent-hooks/session-manager-runtime-registry.js``. The Python
port keeps the same surface but uses a process-local WeakMap so
the host can plug in the real session-manager runtime registry
when the agent-hooks layer lands.
"""
from __future__ import annotations

import threading
import weakref
from typing import Any, Dict, Optional


#: Session-manager to receipt-map registry. Mirrors the OpenClaw
#: ``Map<string, ToolSendReceiptResult>`` registry. The Python
#: port uses a WeakMap-style dict (the keys are session-manager
#: objects; the values are inner dicts).
_RECEIPTS: "weakref.WeakKeyDictionary[Any, Dict[str, Dict[str, Any]]]" = (
    weakref.WeakKeyDictionary()
)
_RECEIPTS_LOCK = threading.Lock()


def _get_or_create_receipts(
    session_manager: Any,
) -> Dict[str, Dict[str, Any]]:
    if session_manager is None:
        return {}
    with _RECEIPTS_LOCK:
        receipts = _RECEIPTS.get(session_manager)
        if receipts is None:
            receipts = {}
            _RECEIPTS[session_manager] = receipts
        return receipts


def record_embedded_tool_send_receipt(
    session_manager: Any,
    tool_call_id: str,
    tool_send: Any,
) -> None:
    """Store a tool-send receipt for ``tool_call_id``.

    Mirrors :func:`recordEmbeddedToolSendReceipt``
    (``tool-send-receipts.ts:11-19``).
    """
    receipts = _get_or_create_receipts(session_manager)
    receipts[tool_call_id] = {"details": {"toolSend": tool_send}}


def consume_embedded_tool_send_receipt(
    session_manager: Any,
    tool_call_id: str,
) -> Optional[Dict[str, Any]]:
    """Pop a previously stored tool-send receipt.

    Mirrors :func:`consumeEmbeddedToolSendReceipt``
    (``tool-send-receipts.ts:21-35``).
    """
    if session_manager is None:
        return None
    with _RECEIPTS_LOCK:
        receipts = _RECEIPTS.get(session_manager)
        if not receipts:
            return None
        receipt = receipts.get(tool_call_id)
        if receipt is None:
            return None
        receipts.pop(tool_call_id, None)
        if not receipts:
            _RECEIPTS.pop(session_manager, None)
        return receipt


__all__ = [
    "consume_embedded_tool_send_receipt",
    "record_embedded_tool_send_receipt",
]
