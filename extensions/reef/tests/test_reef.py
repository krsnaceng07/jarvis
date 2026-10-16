"""Unit tests for Reef extension."""

from __future__ import annotations

import pytest

from extensions.reef.src.friends import ReefTrustStore
from extensions.reef.src.flow import FlowPacket, FlowReceipt
from extensions.reef.plugin import reef_plugin


def test_reef_trust_store() -> None:
    store = ReefTrustStore()
    assert store.is_trusted("peer_unknown") is False

    store.add_friend("peer_alice", nickname="Alice", trusted=True)
    assert store.is_trusted("peer_alice") is True


def test_reef_flow_packet() -> None:
    packet = FlowPacket(sender_id="node_a", recipient_id="node_b", payload={"key": "val"})
    assert packet.sender_id == "node_a"
    assert packet.recipient_id == "node_b"
    assert len(packet.compute_hash()) == 64

    receipt = FlowReceipt(flow_id=packet.flow_id, recipient_id="node_b")
    assert receipt.status == "delivered"


@pytest.mark.asyncio
async def test_plugin_send() -> None:
    res = await reef_plugin.send("peer_bob", "Decentralized data stream")
    assert res.is_ok
    data = res.unwrap()
    assert data["status"] == "delivered"
    assert data["target"] == "peer_bob"
