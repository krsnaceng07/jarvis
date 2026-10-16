"""Channel status reactions controller — agent turn progression emojis.

Mirrors OpenClaw's ``src/channels/status-reactions.ts``.

Features:
- Standard status reaction emojis (👀 queued, 🧠 thinking, 🛠️ tool, 💻 coding,
  🌐 web, 🛫 deploy, 🏗️ build, 💁 concierge, ✅ done, ❌ error, ⏳ stall soft,
  ⚠️ stall hard, 🗜️ compacting).
- Debouncing of intermediate states (default 700ms) to prevent platform rate limits.
- Soft (10s) and hard (30s) stall warning timers.
- Terminal state protection (done/error cannot be overwritten by late tool calls).
- Async promise-chain serialization to eliminate race conditions.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

_log = logging.getLogger("jarvis_channels.status_reactions")


@runtime_checkable
class StatusReactionAdapter(Protocol):
    """Adapter implemented by channels that expose message reaction updates."""

    async def set_reaction(self, emoji: str) -> None:
        """Set or replace the current status reaction emoji."""
        ...

    async def clear_reaction(self) -> None:
        """Clear the reaction (for single-slot platforms such as WhatsApp)."""
        ...

    async def remove_reaction(self, emoji: str) -> None:
        """Remove a specific reaction emoji (for Discord-style platforms)."""
        ...


@dataclass(frozen=True, slots=True)
class StatusReactionEmojis:
    """Emoji configuration for status reactions."""

    queued: str = "👀"
    thinking: str = "🧠"
    tool: str = "🛠️"
    coding: str = "💻"
    web: str = "🌐"
    deploy: str = "🛫"
    build: str = "🏗️"
    concierge: str = "💁"
    done: str = "✅"
    error: str = "❌"
    stall_soft: str = "⏳"
    stall_hard: str = "⚠️"
    compacting: str = "🗜️"


DEFAULT_EMOJIS = StatusReactionEmojis()


@dataclass(frozen=True, slots=True)
class StatusReactionTiming:
    """Timing controls for debounced status reactions and stall warnings."""

    debounce_ms: float = 700.0
    stall_soft_ms: float = 10_000.0
    stall_hard_ms: float = 30_000.0
    done_hold_ms: float = 1500.0
    error_hold_ms: float = 2500.0


DEFAULT_TIMING = StatusReactionTiming()

CODING_TOOL_TOKENS: tuple[str, ...] = (
    "exec",
    "process",
    "read",
    "write",
    "edit",
    "session_status",
    "bash",
)

WEB_TOOL_TOKENS: tuple[str, ...] = (
    "web_search",
    "web-search",
    "web_fetch",
    "web-fetch",
    "browser",
)

DEPLOY_TOOL_TOKENS: tuple[str, ...] = (
    "fastlane",
    "deploy",
    "upload",
    "testflight",
    "ship",
    "release",
    "publish",
    "distribute",
)

BUILD_TOOL_TOKENS: tuple[str, ...] = (
    "build",
    "compile",
    "xcode",
    "swift",
    "gradle",
    "cargo",
    "make",
    "cmake",
    "webpack",
    "vite",
    "tsc",
    "lint",
)

CONCIERGE_TOOL_TOKENS: tuple[str, ...] = (
    "navigate",
    "click",
    "fill",
    "screenshot",
    "scroll",
    "page",
    "form",
    "puppeteer",
    "playwright",
    "selenium",
    "chromedp",
)


def resolve_tool_emoji(
    tool_name: str | None,
    emojis: StatusReactionEmojis = DEFAULT_EMOJIS,
    overrides: dict[str, str] | None = None,
) -> str:
    """Resolve the appropriate status emoji for a tool invocation."""
    if not tool_name:
        return emojis.tool

    normalized = tool_name.strip().lower()

    category = "tool"
    if any(t in normalized for t in DEPLOY_TOOL_TOKENS):
        category = "deploy"
    elif any(t in normalized for t in BUILD_TOOL_TOKENS):
        category = "build"
    elif any(t in normalized for t in CONCIERGE_TOOL_TOKENS):
        category = "concierge"
    elif any(t in normalized for t in WEB_TOOL_TOKENS):
        category = "web"
    elif any(t in normalized for t in CODING_TOOL_TOKENS):
        category = "coding"

    if overrides and category in overrides:
        return overrides[category]

    return getattr(emojis, category, emojis.tool)


class StatusReactionController:
    """Controls status reaction lifecycle with debouncing and stall detection."""

    def __init__(
        self,
        adapter: StatusReactionAdapter,
        enabled: bool = True,
        initial_emoji: str | None = None,
        presentation: str = "activity",  # "activity" | "acknowledgement"
        emojis: StatusReactionEmojis | None = None,
        timing: StatusReactionTiming | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self.adapter = adapter
        self.enabled = enabled
        self.presentation = presentation
        self.emojis = emojis or DEFAULT_EMOJIS
        self.timing = timing or DEFAULT_TIMING
        self.initial_emoji = initial_emoji or self.emojis.queued
        self.on_error = on_error

        self._current_emoji: str | None = None
        self._pending_emoji: str | None = None
        self._finished = False
        self._debounce_task: asyncio.Task | None = None
        self._stall_soft_task: asyncio.Task | None = None
        self._stall_hard_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._active_emojis: set[str] = set()

    @property
    def current_emoji(self) -> str | None:
        return self._current_emoji

    @property
    def is_finished(self) -> bool:
        return self._finished

    def cancel_pending(self) -> None:
        """Cancel any pending debounced emoji task."""
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
            self._debounce_task = None
        self._pending_emoji = None

    def _clear_stall_timers(self) -> None:
        if self._stall_soft_task and not self._stall_soft_task.done():
            self._stall_soft_task.cancel()
            self._stall_soft_task = None
        if self._stall_hard_task and not self._stall_hard_task.done():
            self._stall_hard_task.cancel()
            self._stall_hard_task = None

    def _restart_stall_timers(self) -> None:
        self._clear_stall_timers()
        if self._finished or not self.enabled:
            return

        async def _soft_stall() -> None:
            try:
                await asyncio.sleep(self.timing.stall_soft_ms / 1000.0)
                if not self._finished and self.presentation != "acknowledgement":
                    await self._apply_emoji(self.emojis.stall_soft)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                _log.debug("Soft stall reaction failed: %s", e)

        async def _hard_stall() -> None:
            try:
                await asyncio.sleep(self.timing.stall_hard_ms / 1000.0)
                if not self._finished and self.presentation != "acknowledgement":
                    await self._apply_emoji(self.emojis.stall_hard)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                _log.debug("Hard stall reaction failed: %s", e)

        try:
            loop = asyncio.get_running_loop()
            self._stall_soft_task = loop.create_task(_soft_stall())
            self._stall_hard_task = loop.create_task(_hard_stall())
        except RuntimeError:
            pass

    async def _apply_emoji(self, emoji: str, is_terminal: bool = False) -> None:
        if not self.enabled:
            return
        if self._finished and not is_terminal:
            return
        if self._current_emoji == emoji:
            return

        async with self._lock:
            try:
                await self.adapter.set_reaction(emoji)
                self._current_emoji = emoji
                self._active_emojis.add(emoji)
            except Exception as err:
                if self.on_error:
                    self.on_error(err)
                _log.debug("Failed to set reaction '%s': %s", emoji, err)

    def _schedule_debounced(self, emoji: str) -> None:
        if not self.enabled or self._finished:
            return
        if self.presentation == "acknowledgement":
            return

        self.cancel_pending()
        self._pending_emoji = emoji

        async def _do_debounce() -> None:
            try:
                await asyncio.sleep(self.timing.debounce_ms / 1000.0)
                if self._pending_emoji and not self._finished:
                    target = self._pending_emoji
                    self._pending_emoji = None
                    await self._apply_emoji(target)
                    self._restart_stall_timers()
            except asyncio.CancelledError:
                pass

        try:
            loop = asyncio.get_running_loop()
            self._debounce_task = loop.create_task(_do_debounce())
        except RuntimeError:
            pass

    async def set_queued(self) -> None:
        """Mark turn as queued."""
        if self._finished:
            return
        self.cancel_pending()
        await self._apply_emoji(self.initial_emoji)
        self._restart_stall_timers()

    async def set_thinking(self) -> None:
        """Mark turn as thinking."""
        if self._finished or self.presentation == "acknowledgement":
            return
        self._schedule_debounced(self.emojis.thinking)

    async def set_tool(self, tool_name: str | None = None) -> None:
        """Mark turn as running a tool with category emoji."""
        if self._finished or self.presentation == "acknowledgement":
            return
        emoji = resolve_tool_emoji(tool_name, self.emojis)
        self._schedule_debounced(emoji)

    async def set_compacting(self) -> None:
        """Mark turn as compacting context."""
        if self._finished or self.presentation == "acknowledgement":
            return
        self._schedule_debounced(self.emojis.compacting)

    async def set_done(self) -> None:
        """Mark turn as successfully finished (terminal)."""
        if self._finished:
            return
        self._finished = True
        self.cancel_pending()
        self._clear_stall_timers()
        await self._apply_emoji(self.emojis.done, is_terminal=True)

    async def set_error(self) -> None:
        """Mark turn as errored (terminal)."""
        if self._finished:
            return
        self._finished = True
        self.cancel_pending()
        self._clear_stall_timers()
        await self._apply_emoji(self.emojis.error, is_terminal=True)

    async def clear(self) -> None:
        """Clear all reactions and release resources."""
        self._finished = True
        self.cancel_pending()
        self._clear_stall_timers()
        if not self.enabled:
            return

        async with self._lock:
            try:
                if hasattr(self.adapter, "clear_reaction"):
                    await self.adapter.clear_reaction()
                elif hasattr(self.adapter, "remove_reaction") and self._current_emoji:
                    await self.adapter.remove_reaction(self._current_emoji)
                self._current_emoji = None
            except Exception as err:
                if self.on_error:
                    self.on_error(err)
                _log.debug("Failed to clear reaction: %s", err)

    async def restore_initial(self) -> None:
        """Restore the initial reaction emoji."""
        if not self.enabled or self._finished:
            return
        self.cancel_pending()
        await self._apply_emoji(self.initial_emoji)


def create_status_reaction_controller(
    adapter: StatusReactionAdapter,
    enabled: bool = True,
    initial_emoji: str | None = None,
    presentation: str = "activity",
    emojis: StatusReactionEmojis | None = None,
    timing: StatusReactionTiming | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> StatusReactionController:
    """Factory helper to construct a StatusReactionController."""
    return StatusReactionController(
        adapter=adapter,
        enabled=enabled,
        initial_emoji=initial_emoji,
        presentation=presentation,
        emojis=emojis,
        timing=timing,
        on_error=on_error,
    )


__all__ = [
    "BUILD_TOOL_TOKENS",
    "CODING_TOOL_TOKENS",
    "CONCIERGE_TOOL_TOKENS",
    "DEFAULT_EMOJIS",
    "DEFAULT_TIMING",
    "DEPLOY_TOOL_TOKENS",
    "StatusReactionAdapter",
    "StatusReactionController",
    "StatusReactionEmojis",
    "StatusReactionTiming",
    "WEB_TOOL_TOKENS",
    "create_status_reaction_controller",
    "resolve_tool_emoji",
]
