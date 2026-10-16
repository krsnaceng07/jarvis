"""Reef friend trust store and peer relations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ReefFriend:
    peer_id: str
    nickname: str = ""
    trusted: bool = True
    capabilities: list[str] = field(default_factory=list)


class ReefTrustStore:
    """Stores and verifies trusted peer connections."""

    def __init__(self) -> None:
        self.friends: dict[str, ReefFriend] = {}

    def add_friend(self, peer_id: str, nickname: str = "", trusted: bool = True) -> ReefFriend:
        friend = ReefFriend(peer_id=peer_id, nickname=nickname, trusted=trusted)
        self.friends[peer_id] = friend
        return friend

    def is_trusted(self, peer_id: str) -> bool:
        friend = self.friends.get(peer_id)
        return bool(friend and friend.trusted)
