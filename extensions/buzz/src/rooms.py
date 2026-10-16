"""Buzz gossip room management and message ring cache."""

from __future__ import annotations


from .protocol import BuzzMessage


class BuzzRoomManager:
    """Manages peer room subscriptions and seen messages."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.rooms: set[str] = set()
        self._seen_messages: set[str] = set()

    def join_room(self, room_id: str) -> None:
        self.rooms.add(room_id)

    def leave_room(self, room_id: str) -> None:
        self.rooms.discard(room_id)

    def broadcast(self, room_id: str, content: str) -> BuzzMessage:
        msg = BuzzMessage(room_id=room_id, sender_id=self.node_id, content=content)
        self._seen_messages.add(msg.message_id)
        return msg

    def is_message_seen(self, message_id: str) -> bool:
        return message_id in self._seen_messages

    def mark_message_seen(self, message_id: str) -> None:
        self._seen_messages.add(message_id)
