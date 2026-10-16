"""jarvis_channels.transports: Server-side channel transport integration for Track 3.5.

Enforces:
- Invariant T35-04: External channels run server-side within channels_core.
- Invariant T35-05: Server-authoritative route triples (channel_id, external_user_id, external_thread_id).
- Invariant T35-06: Typed presentation actions rather than raw string inference.
- Invariant T35-15: 6-state outbound delivery tracking.
- Invariant T35-16: SQLite WAL atomic claim deduplication.
"""

from jarvis_channels.transports.adapters.discord import DiscordTransportAdapter
from jarvis_channels.transports.adapters.slack import SlackTransportAdapter
from jarvis_channels.transports.adapters.telegram import TelegramTransportAdapter
from jarvis_channels.transports.base import BaseChannelTransport
from jarvis_channels.transports.deduplication import (
    ChannelInboundDeduplicator,
    InboundClaimState,
)
from jarvis_channels.transports.delivery import (
    ChannelDeliveryRecord,
    ChannelDeliveryStatus,
    ChannelDeliveryTracker,
)
from jarvis_channels.transports.identity import (
    ChannelRouteIdentity,
    synthesize_route_triple,
)
from jarvis_channels.transports.reconciliation import ChannelDeliveryReconciler

__all__ = [
    # Identity & Routing
    "ChannelRouteIdentity",
    "synthesize_route_triple",
    # Deduplication
    "InboundClaimState",
    "ChannelInboundDeduplicator",
    # Delivery
    "ChannelDeliveryStatus",
    "ChannelDeliveryRecord",
    "ChannelDeliveryTracker",
    "ChannelDeliveryReconciler",
    # Base Transport
    "BaseChannelTransport",
    # Concrete Adapters
    "TelegramTransportAdapter",
    "DiscordTransportAdapter",
    "SlackTransportAdapter",
]
