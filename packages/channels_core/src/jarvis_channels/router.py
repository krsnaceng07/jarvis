"""Channel routing logic and session key derivation.

Mirrors OpenClaw's routing precedence and session key formation.
"""

from __future__ import annotations

import logging

from jarvis_config_core import JarvisConfig
from .types import InboundMessage

_log = logging.getLogger("jarvis.channels.router")

def resolve_agent(msg: InboundMessage, config: JarvisConfig) -> str:
    """Resolve the target agent_id for an inbound message based on bindings.
    
    Precedence (first match wins):
    1. Exact peer match
    2. Parent peer match (skipped: usually for thread inheritance if we have thread info, but mapped as exact match here)
    3. Peer wildcard match
    4. Guild + roles match
    5. Guild match
    6. Team match
    7. Account match
    8. Channel match
    9. Default agent
    """
    bindings = config.bindings
    
    # 1. Exact peer match
    for b in bindings:
        if b.match.channel == msg.channel_id and b.match.peer_kind == msg.peer_kind and b.match.peer_id == msg.peer_id:
            return b.agent_id
            
    # 3. Peer wildcard match
    for b in bindings:
        if b.match.channel == msg.channel_id and b.match.peer_kind == msg.peer_kind and b.match.peer_id == "*":
            return b.agent_id
            
    # 4 & 5. Guild match (Discord)
    if msg.guild_id:
        for b in bindings:
            if b.match.channel == msg.channel_id and b.match.guild_id == msg.guild_id:
                # Role matching would go here, skipping for now
                return b.agent_id
                
    # 6. Team match (Slack)
    if msg.team_id:
        for b in bindings:
            if b.match.channel == msg.channel_id and b.match.team_id == msg.team_id:
                return b.agent_id
                
    # 7. Account match
    if msg.account_id:
        for b in bindings:
            if b.match.channel == msg.channel_id and b.match.account_id == msg.account_id:
                return b.agent_id
                
    # 8. Channel match
    for b in bindings:
        if b.match.channel == msg.channel_id and (b.match.account_id is None or b.match.account_id == "*"):
            return b.agent_id
            
    # 9. Default agent
    # Check agents list for a default, else use the first, else "main"
    agents_list = config.agents.get("list", [])
    for a in agents_list:
        if a.default:
            return a.id
    if agents_list:
        return agents_list[0].id
        
    return "main"


def get_dm_scope(msg: InboundMessage, agent_id: str, config: JarvisConfig) -> str:
    """Find the DM scope for a message. Can be overridden by binding."""
    # Check if a specific binding overrides dmScope
    for b in config.bindings:
        if b.agent_id == agent_id and b.match.channel == msg.channel_id and b.match.peer_kind == msg.peer_kind and b.match.peer_id == msg.peer_id:
            if b.session_dm_scope:
                return b.session_dm_scope
    return config.session.dm_scope


def derive_session_key(msg: InboundMessage, agent_id: str, config: JarvisConfig) -> str:
    """Derive the deterministic session key.
    
    Follows OpenClaw rules:
    - DM scope handling for users
    - Groups: agent:<agentId>:<channel>:group:<id>
    - Threads/topics appended
    """
    base_key = ""
    
    if msg.peer_kind == "user":
        scope = get_dm_scope(msg, agent_id, config)
        if scope == "main":
            # agent:main:main (default)
            base_key = f"agent:{agent_id}:main"
        elif scope == "per-peer":
            base_key = f"agent:{agent_id}:peer:{msg.peer_id}"
        elif scope == "per-channel-peer":
            base_key = f"agent:{agent_id}:{msg.channel_id}:peer:{msg.peer_id}"
        elif scope == "per-account-channel-peer":
            account = msg.account_id or "default"
            base_key = f"agent:{agent_id}:{account}:{msg.channel_id}:peer:{msg.peer_id}"
        else:
            # fallback
            base_key = f"agent:{agent_id}:main"
            
    else:
        # group, channel, etc.
        kind = msg.peer_kind or "group"
        peer_id = msg.peer_id or msg.conversation_id
        base_key = f"agent:{agent_id}:{msg.channel_id}:{kind}:{peer_id}"
        
    if msg.thread_id:
        # Generic fallback for threads/topics
        # OpenClaw differentiates Slack `:thread:` vs Telegram `:topic:`
        # We use a generic append for now, or match if we know the channel.
        separator = "topic" if msg.channel_id == "telegram" else "thread"
        base_key += f":{separator}:{msg.thread_id}"
        
    return base_key
