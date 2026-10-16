"""PluginContext — runtime context passed to a plugin on init.

Mirrors OpenClaw's `OpenClawPluginToolContext` and the broader runtime
handed to plugins via the host. This is what plugins see of the world;
nothing else leaks through.

For Phase 1B, this is a minimal shape. Phase 1C adds:
- ``http`` (SSRF-checked HTTP client)
- ``fs`` (path-containment filesystem)
- full config view (typed via pydantic)
- secret resolver
- event bus emit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class PluginContext:
    """Runtime context given to every plugin.

    Plugins receive this once on ``init()`` and may stash fields they
    need (e.g. ``self._http = ctx.http``). The host is responsible for
    keeping the context fields valid for the plugin's lifetime.
    """

    # ── Identity ─────────────────────────────────────────────────────
    plugin_id: str
    plugin_kind: str

    # ── Host services ────────────────────────────────────────────────
    config: Any = None  # read-only view of user config; full pydantic model in 1C
    secrets: Any = None  # secret resolver (in 1C; None for now = use env vars)
    logger: Any = None  # structured logger (in 1C; default = stdlib logging)

    # ── Filesystem ───────────────────────────────────────────────────
    data_dir: Path = field(default_factory=Path.cwd)
    workspace: Path = field(default_factory=Path.cwd)

    # ── Capability accessors (None in 1B; filled in 1C) ──────────────
    http: Any = None  # SSRF-checked HTTP client
    fs: Any = None  # path-containment filesystem
    emit_event: Callable[[str, dict[str, object]], None] = field(
        default_factory=lambda: lambda *_: None
    )

    def log(self, msg: str, *, level: str = "info") -> None:
        """Best-effort log; falls back to print if no logger is wired."""
        if self.logger is not None:
            log_fn = getattr(self.logger, level, self.logger.info)
            log_fn(msg)
        else:
            print(f"[{self.plugin_id}] {level}: {msg}")


__all__ = ["PluginContext"]
