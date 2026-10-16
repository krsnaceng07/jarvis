"""Bundled session-memory hook initialization."""

from .sync import sync_session_memory_to_disk
from src.agents.embedded_agent_runner.compaction_hooks import set_memory_sync_sink

# Register the sync sink for post-compaction transcript extraction
set_memory_sync_sink(sync_session_memory_to_disk)
