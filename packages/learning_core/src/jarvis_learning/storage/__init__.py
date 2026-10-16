"""jarvis_learning.storage — SQLite persistence layer.

Dedicated ``learning.sqlite`` database separate from the shared
JARVIS state DB.  Uses WAL mode and the same FIFO write pattern
as ``jarvis_state_core``.  Tables are created lazily on first use
(no schema version bump).
"""
