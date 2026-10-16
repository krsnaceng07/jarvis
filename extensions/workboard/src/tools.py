"""Workboard agent tool definitions and handlers."""

from __future__ import annotations

from typing import Any

from .store import WorkboardStore


def register_workboard_tools(api: Any, store: WorkboardStore) -> None:
    """Register all workboard tools with the plugin API."""
    if not hasattr(api, "register_tool"):
        return

    # 1. workboard_list
    api.register_tool(
        name="workboard_list",
        description="List Workboard cards filtered by board, status, or agent.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "boardId": {"type": "STRING", "description": "Board ID filter."},
                "status": {
                    "type": "STRING",
                    "description": "Status filter (todo, running, blocked, done, etc.).",
                },
                "agentId": {"type": "STRING", "description": "Agent ID filter."},
            },
        },
        execute=lambda params: _handle_workboard_list(params, store),
    )

    # 2. workboard_create
    api.register_tool(
        name="workboard_create",
        description="Create a new task card on the Workboard.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Card title."},
                "boardId": {"type": "STRING", "description": "Board ID (default: 'default')."},
                "notes": {"type": "STRING", "description": "Detailed notes or task specification."},
                "priority": {
                    "type": "STRING",
                    "enum": ["low", "normal", "high", "urgent"],
                    "description": "Priority.",
                },
                "status": {"type": "STRING", "description": "Initial status (default: 'todo')."},
                "labels": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Tags or labels.",
                },
            },
            "required": ["title"],
        },
        execute=lambda params: _handle_workboard_create(params, store),
    )

    # 3. workboard_read
    api.register_tool(
        name="workboard_read",
        description="Read detailed card information including comments, proof, attachments, and events.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID to read."},
            },
            "required": ["cardId"],
        },
        execute=lambda params: _handle_workboard_read(params, store),
    )

    # 4. workboard_claim
    api.register_tool(
        name="workboard_claim",
        description="Claim a Workboard card for execution by a worker.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID to claim."},
                "ownerId": {
                    "type": "STRING",
                    "description": "Worker / Agent ID claiming the card.",
                },
                "timeoutSeconds": {
                    "type": "NUMBER",
                    "description": "Claim duration in seconds (default: 300).",
                },
            },
            "required": ["cardId", "ownerId"],
        },
        execute=lambda params: _handle_workboard_claim(params, store),
    )

    # 5. workboard_heartbeat
    api.register_tool(
        name="workboard_heartbeat",
        description="Renew worker claim on a Workboard card.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
                "ownerId": {"type": "STRING", "description": "Worker ID."},
                "token": {"type": "STRING", "description": "Claim authorization token."},
                "timeoutSeconds": {"type": "NUMBER", "description": "Renewal duration in seconds."},
            },
            "required": ["cardId", "ownerId", "token"],
        },
        execute=lambda params: _handle_workboard_heartbeat(params, store),
    )

    # 6. workboard_complete
    api.register_tool(
        name="workboard_complete",
        description="Mark a claimed Workboard card as complete (done).",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
                "ownerId": {"type": "STRING", "description": "Worker ID."},
                "token": {"type": "STRING", "description": "Claim token."},
            },
            "required": ["cardId", "ownerId", "token"],
        },
        execute=lambda params: _handle_workboard_complete(params, store),
    )

    # 7. workboard_move
    api.register_tool(
        name="workboard_move",
        description="Move card to a new column status.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
                "toStatus": {
                    "type": "STRING",
                    "description": "Target status (triage, backlog, todo, ready, running, review, blocked, done).",
                },
            },
            "required": ["cardId", "toStatus"],
        },
        execute=lambda params: _handle_workboard_move(params, store),
    )

    # 8. workboard_block & unblock
    api.register_tool(
        name="workboard_block",
        description="Mark a card as blocked with a reason.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
                "reason": {"type": "STRING", "description": "Reason for blocking."},
            },
            "required": ["cardId", "reason"],
        },
        execute=lambda params: _handle_workboard_block(params, store),
    )
    api.register_tool(
        name="workboard_unblock",
        description="Unblock a card, returning it to ready status.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
            },
            "required": ["cardId"],
        },
        execute=lambda params: _handle_workboard_unblock(params, store),
    )

    # 9. workboard_comment & proof
    api.register_tool(
        name="workboard_comment",
        description="Add a comment to a Workboard card.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
                "body": {"type": "STRING", "description": "Comment markdown text."},
            },
            "required": ["cardId", "body"],
        },
        execute=lambda params: _handle_workboard_comment(params, store),
    )
    api.register_tool(
        name="workboard_proof",
        description="Attach verification proof to a Workboard card.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "cardId": {"type": "STRING", "description": "Card ID."},
                "status": {
                    "type": "STRING",
                    "enum": ["passed", "failed", "skipped", "unknown"],
                    "description": "Proof status.",
                },
                "label": {"type": "STRING", "description": "Proof label."},
                "command": {"type": "STRING", "description": "Command run."},
                "url": {"type": "STRING", "description": "Verification URL."},
                "note": {"type": "STRING", "description": "Verification details."},
            },
            "required": ["cardId", "status"],
        },
        execute=lambda params: _handle_workboard_proof(params, store),
    )

    # 10. workboard_boards & stats
    api.register_tool(
        name="workboard_boards",
        description="List all available workboards.",
        parameters={"type": "OBJECT", "properties": {}},
        execute=lambda params: _handle_workboard_boards(params, store),
    )
    api.register_tool(
        name="workboard_stats",
        description="Get summary card metrics across statuses.",
        parameters={
            "type": "OBJECT",
            "properties": {
                "boardId": {"type": "STRING", "description": "Optional board ID filter."},
            },
        },
        execute=lambda params: _handle_workboard_stats(params, store),
    )


# Handler implementations
async def _handle_workboard_list(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    cards = store.list_cards(
        board_id=params.get("boardId"),
        status=params.get("status"),
        agent_id=params.get("agentId"),
    )
    lines = [f"Workboard cards ({len(cards)}):"]
    for c in cards:
        claim_str = f" [Claimed by {c.claim.owner_id}]" if c.claim else ""
        lines.append(f"- [{c.status.upper()}] {c.title} (ID: {c.id}){claim_str}")
    return {
        "content": [{"type": "text", "text": "\n".join(lines)}],
        "details": {"cards": cards, "count": len(cards)},
    }


async def _handle_workboard_create(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    card = store.create_card(
        title=str(params["title"]),
        board_id=str(params.get("boardId", "default")),
        notes=params.get("notes"),
        priority=params.get("priority", "normal"),
        status=params.get("status", "todo"),
        labels=params.get("labels"),
    )
    return {
        "content": [
            {
                "type": "text",
                "text": f"Created Workboard card '{card.title}' (ID: {card.id}) in [{card.status}]",
            }
        ],
        "details": {"card": card, "cardId": card.id},
    }


async def _handle_workboard_read(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    card = store.get_card(str(params["cardId"]))
    if not card:
        return {"error": f"Card not found: {params['cardId']}"}
    lines = [
        f"Card: {card.title} ({card.id})",
        f"Status: {card.status} | Priority: {card.priority} | Board: {card.board_id}",
    ]
    if card.notes:
        lines.append(f"Notes:\n{card.notes}")
    if card.claim:
        lines.append(f"Claimed by: {card.claim.owner_id} (expires: {card.claim.expires_at})")
    if card.comments:
        lines.append(f"Comments ({len(card.comments)}):")
        for c in card.comments:
            lines.append(f"  - {c.body}")
    if card.proof:
        lines.append(f"Proof ({len(card.proof)}):")
        for p in card.proof:
            lines.append(f"  - [{p.status.upper()}] {p.label or p.note or p.command}")
    return {"content": [{"type": "text", "text": "\n".join(lines)}], "details": {"card": card}}


async def _handle_workboard_claim(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    success, token_or_err, card = store.claim_card(
        card_id=str(params["cardId"]),
        owner_id=str(params["ownerId"]),
        timeout_seconds=int(params.get("timeoutSeconds", 300)),
    )
    if not success:
        return {"error": token_or_err or "Failed to claim card"}
    return {
        "content": [
            {
                "type": "text",
                "text": f"Successfully claimed card {params['cardId']}.\nToken: {token_or_err}",
            }
        ],
        "details": {"token": token_or_err, "card": card},
    }


async def _handle_workboard_heartbeat(
    params: dict[str, Any], store: WorkboardStore
) -> dict[str, Any]:
    success = store.heartbeat_card(
        card_id=str(params["cardId"]),
        owner_id=str(params["ownerId"]),
        token=str(params["token"]),
        timeout_seconds=int(params.get("timeoutSeconds", 300)),
    )
    if not success:
        return {"error": "Heartbeat failed (invalid claim or token)"}
    return {
        "content": [{"type": "text", "text": "Heartbeat renewed successfully"}],
        "details": {"success": True},
    }


async def _handle_workboard_complete(
    params: dict[str, Any], store: WorkboardStore
) -> dict[str, Any]:
    success = store.complete_card(
        card_id=str(params["cardId"]),
        owner_id=str(params["ownerId"]),
        token=str(params["token"]),
    )
    if not success:
        return {"error": "Completion failed (invalid claim or token)"}
    return {
        "content": [{"type": "text", "text": f"Card {params['cardId']} marked as DONE."}],
        "details": {"success": True},
    }


async def _handle_workboard_move(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    card = store.move_card(str(params["cardId"]), to_status=params["toStatus"])
    if not card:
        return {"error": f"Card not found: {params['cardId']}"}
    return {
        "content": [{"type": "text", "text": f"Moved card {card.id} to [{card.status}]"}],
        "details": {"card": card},
    }


async def _handle_workboard_block(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    card = store.block_card(str(params["cardId"]), reason=str(params["reason"]))
    if not card:
        return {"error": f"Card not found: {params['cardId']}"}
    return {
        "content": [{"type": "text", "text": f"Card {card.id} blocked: {params['reason']}"}],
        "details": {"card": card},
    }


async def _handle_workboard_unblock(
    params: dict[str, Any], store: WorkboardStore
) -> dict[str, Any]:
    card = store.unblock_card(str(params["cardId"]))
    if not card:
        return {"error": f"Card not found: {params['cardId']}"}
    return {
        "content": [{"type": "text", "text": f"Card {card.id} unblocked and returned to [ready]"}],
        "details": {"card": card},
    }


async def _handle_workboard_comment(
    params: dict[str, Any], store: WorkboardStore
) -> dict[str, Any]:
    comment = store.add_comment(str(params["cardId"]), body=str(params["body"]))
    return {
        "content": [{"type": "text", "text": f"Added comment to card {params['cardId']}"}],
        "details": {"comment": comment},
    }


async def _handle_workboard_proof(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    proof = store.add_proof(
        card_id=str(params["cardId"]),
        status=params["status"],
        label=params.get("label"),
        command=params.get("command"),
        url=params.get("url"),
        note=params.get("note"),
    )
    return {
        "content": [
            {
                "type": "text",
                "text": f"Attached {proof.status.upper()} proof to card {params['cardId']}",
            }
        ],
        "details": {"proof": proof},
    }


async def _handle_workboard_boards(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    boards = store.list_boards()
    lines = [f"Workboards ({len(boards)}):"]
    for b in boards:
        lines.append(f"- {b.name} (ID: {b.id})")
    return {"content": [{"type": "text", "text": "\n".join(lines)}], "details": {"boards": boards}}


async def _handle_workboard_stats(params: dict[str, Any], store: WorkboardStore) -> dict[str, Any]:
    stats = store.get_stats(board_id=params.get("boardId"))
    lines = [
        "Workboard Statistics:",
        f"- Total cards: {stats['total']}",
        f"- Active cards: {stats['active']}",
        f"- Completed: {stats['done']}",
    ]
    return {"content": [{"type": "text", "text": "\n".join(lines)}], "details": stats}
