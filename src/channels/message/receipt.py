"""jarvis.channels.message.receipt — normalized message receipt builder.

OpenClaw parity: mirrors ``src/channels/message/receipt.ts``.
"""

from __future__ import annotations

import time
from typing import Sequence

from src.channels.message.types import (
    MessageReceipt,
    MessageReceiptPart,
    MessageReceiptSourceResult,
)


def resolve_receipt_message_id(result: MessageReceiptSourceResult) -> str | None:
    return (
        result.message_id
        or result.chat_id
        or result.channel_id
        or result.room_id
        or result.conversation_id
        or result.to_jid
        or result.poll_id
    )


def create_message_receipt_from_outbound_results(
    results: Sequence[MessageReceiptSourceResult],
    *,
    kind: str = "unknown",
    thread_id: str | None = None,
    reply_to_id: str | None = None,
    sent_at: int | None = None,
) -> MessageReceipt:
    """Build one normalized MessageReceipt from platform send results.

    Mirrors ``createMessageReceiptFromOutboundResults`` (``receipt.ts``).
    """
    platform_ids: list[str] = []
    parts: list[MessageReceiptPart] = []

    part_index = 0
    for res in results:
        if res.receipt and (res.receipt.parts or res.receipt.platform_message_ids):
            for sub_part in res.receipt.parts:
                if sub_part.platform_message_id not in platform_ids:
                    platform_ids.append(sub_part.platform_message_id)
                parts.append(
                    MessageReceiptPart(
                        platform_message_id=sub_part.platform_message_id,
                        kind=sub_part.kind or kind,
                        index=part_index,
                        thread_id=sub_part.thread_id or thread_id,
                        reply_to_id=sub_part.reply_to_id or reply_to_id,
                    )
                )
                part_index += 1
            for pid in res.receipt.platform_message_ids:
                if pid not in platform_ids:
                    platform_ids.append(pid)
        else:
            msg_id = resolve_receipt_message_id(res)
            if msg_id:
                if msg_id not in platform_ids:
                    platform_ids.append(msg_id)
                parts.append(
                    MessageReceiptPart(
                        platform_message_id=msg_id,
                        kind=kind,
                        index=part_index,
                        thread_id=thread_id,
                        reply_to_id=reply_to_id,
                    )
                )
                part_index += 1

    primary_id = platform_ids[0] if platform_ids else None
    ts = sent_at if sent_at is not None else int(time.time() * 1000)

    return MessageReceipt(
        platform_message_ids=platform_ids,
        primary_platform_message_id=primary_id,
        parts=parts,
        sent_at=ts,
    )


__all__ = [
    "create_message_receipt_from_outbound_results",
    "resolve_receipt_message_id",
]
