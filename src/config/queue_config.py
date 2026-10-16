"""jarvis.config.queue_config — inbound message queue mode and drop-policy resolution.

OpenClaw parity: mirrors
``openclaw-main/src/config/queue-config.ts`` and
``openclaw-main/src/utils/queue-helpers.ts``.

Features:
- Defaults: mode="steer", cap=20, drop="summarize", debounce_ms=500.
- Mode resolution order:
  1. Per-session override (`/queue <mode>`).
  2. Channel override (`messages.queue.byChannel.<channel>`).
  3. Global mode (`messages.queue.mode`).
  4. Default "steer".
- Slash command parser: ``parse_queue_command()``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

QueueMode = Literal["steer", "followup", "collect", "interrupt"]
QueueDropPolicy = Literal["summarize", "old", "new"]

DEFAULT_QUEUE_MODE: QueueMode = "steer"
DEFAULT_QUEUE_CAP: int = 20
DEFAULT_QUEUE_DROP: QueueDropPolicy = "summarize"
DEFAULT_QUEUE_DEBOUNCE_MS: int = 500

_VALID_QUEUE_MODES: frozenset[str] = frozenset({"steer", "followup", "collect", "interrupt"})
_VALID_DROP_POLICIES: frozenset[str] = frozenset({"summarize", "old", "new"})


@dataclass
class ResolvedQueueConfig:
    mode: QueueMode = DEFAULT_QUEUE_MODE
    cap: int = DEFAULT_QUEUE_CAP
    drop: QueueDropPolicy = DEFAULT_QUEUE_DROP
    debounce_ms: int = DEFAULT_QUEUE_DEBOUNCE_MS

    def __getitem__(self, key: str) -> Any:
        if key == "mode":
            return self.mode
        if key == "cap":
            return self.cap
        if key == "drop":
            return self.drop
        if key == "debounce_ms" or key == "debounceMs":
            return self.debounce_ms
        raise KeyError(key)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return (
                self.mode == other.get("mode")
                and self.cap == other.get("cap")
                and self.drop == other.get("drop")
            )
        if isinstance(other, ResolvedQueueConfig):
            return (
                self.mode == other.mode
                and self.cap == other.cap
                and self.drop == other.drop
                and self.debounce_ms == other.debounce_ms
            )
        return False


def parse_time_duration_ms(val: str | int | float) -> int:
    """Parse time string like '500ms', '0.5s', '2m' into milliseconds."""
    if isinstance(val, (int, float)):
        return max(0, int(val))

    s = str(val).strip().lower()
    if not s:
        return DEFAULT_QUEUE_DEBOUNCE_MS

    match = re.match(r"^([\d.]+)\s*(ms|s|m|h|d)?$", s)
    if not match:
        return DEFAULT_QUEUE_DEBOUNCE_MS

    num_str, unit = match.groups()
    try:
        num = float(num_str)
    except ValueError:
        return DEFAULT_QUEUE_DEBOUNCE_MS

    if unit == "s":
        return int(num * 1000)
    elif unit == "m":
        return int(num * 60 * 1000)
    elif unit == "h":
        return int(num * 3600 * 1000)
    elif unit == "d":
        return int(num * 86400 * 1000)
    else:  # ms or empty
        return int(num)


def parse_queue_command(cmd_text: str) -> dict[str, Any] | None:
    """Parse a ``/queue`` command line.

    Examples:
    - ``/queue steer`` -> ``{"mode": "steer"}``
    - ``/queue collect debounce:0.5s cap:25 drop:summarize``
    - ``/queue reset`` or ``/queue default`` -> ``{"reset": True}``
    """
    if not cmd_text or not isinstance(cmd_text, str):
        return None

    cleaned = cmd_text.strip()
    if not cleaned.startswith("/queue"):
        return None

    parts = cleaned.split()
    if len(parts) < 2:
        return None

    subcmd = parts[1].lower()
    if subcmd in ("reset", "default"):
        return {"reset": True}

    res: dict[str, Any] = {}

    if subcmd in _VALID_QUEUE_MODES:
        res["mode"] = subcmd

    # Parse key:value options (e.g. debounce:0.5s cap:25 drop:summarize)
    for token in parts[2:]:
        if ":" in token:
            k, v = token.split(":", 1)
            k = k.strip().lower()
            v = v.strip().lower()
            if k == "debounce":
                res["debounce_ms"] = parse_time_duration_ms(v)
            elif k == "cap":
                try:
                    res["cap"] = max(1, int(v))
                except ValueError:
                    pass
            elif k == "drop" and v in _VALID_DROP_POLICIES:
                res["drop"] = v

    return res if res else None


def _get_queue_block(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if not cfg or not isinstance(cfg, dict):
        return {}
    msg_block = cfg.get("messages")
    if isinstance(msg_block, dict):
        q = msg_block.get("queue")
        if isinstance(q, dict):
            return q
    return {}


def resolve_queue_mode(
    cfg: dict[str, Any] | None,
    channel: str | None = None,
    session_override_mode: str | None = None,
) -> QueueMode:
    """Resolve queue mode using OpenClaw precedence cascade:

    1. Session override (`/queue <mode>`)
    2. Channel override (`messages.queue.byChannel.<channel>`)
    3. Global mode (`messages.queue.mode`)
    4. Default `steer`
    """
    if session_override_mode and session_override_mode in _VALID_QUEUE_MODES:
        return session_override_mode  # type: ignore[return-value]

    q_block = _get_queue_block(cfg)

    if channel:
        by_chan = q_block.get("byChannel")
        if isinstance(by_chan, dict):
            chan_mode = by_chan.get(channel.lower())
            if isinstance(chan_mode, str) and chan_mode.lower() in _VALID_QUEUE_MODES:
                return chan_mode.lower()  # type: ignore[return-value]

    mode_val = q_block.get("mode")
    if isinstance(mode_val, str) and mode_val.lower() in _VALID_QUEUE_MODES:
        return mode_val.lower()  # type: ignore[return-value]

    return DEFAULT_QUEUE_MODE


def resolve_queue_cap(cfg: dict[str, Any] | None) -> int:
    """Resolve queue cap from config (messages.queue.cap).

    Values <= 0 or non-positive integers clamp to 1.
    Missing/invalid values fall back to DEFAULT_QUEUE_CAP.
    """
    q_block = _get_queue_block(cfg)
    cap = q_block.get("cap")
    if isinstance(cap, (int, float)) and cap == cap:
        return max(1, int(cap))
    return DEFAULT_QUEUE_CAP


def resolve_queue_drop(cfg: dict[str, Any] | None) -> QueueDropPolicy:
    """Resolve queue drop policy from config (messages.queue.drop)."""
    q_block = _get_queue_block(cfg)
    drop = q_block.get("drop")
    if isinstance(drop, str) and drop.lower() in _VALID_DROP_POLICIES:
        return drop.lower()  # type: ignore[return-value]
    return DEFAULT_QUEUE_DROP


def resolve_queue_config(
    cfg: dict[str, Any] | None,
    channel: str | None = None,
    session_override: dict[str, Any] | None = None,
) -> ResolvedQueueConfig:
    """Resolve full ResolvedQueueConfig block with precedence cascade."""
    sess_mode = session_override.get("mode") if session_override else None
    mode = resolve_queue_mode(cfg, channel=channel, session_override_mode=sess_mode)

    cap = session_override.get("cap") if session_override else None
    if cap is None:
        cap = resolve_queue_cap(cfg)

    drop = session_override.get("drop") if session_override else None
    if drop is None:
        drop = resolve_queue_drop(cfg)

    debounce = session_override.get("debounce_ms") if session_override else None
    if debounce is None:
        q_block = _get_queue_block(cfg)
        if channel:
            by_chan_deb = q_block.get("debounceMsByChannel")
            if isinstance(by_chan_deb, dict):
                d_val = by_chan_deb.get(channel.lower())
                if isinstance(d_val, (int, float)):
                    debounce = int(d_val)
        if debounce is None:
            raw_d = q_block.get("debounceMs")
            if isinstance(raw_d, (int, float)):
                debounce = int(raw_d)
            else:
                debounce = DEFAULT_QUEUE_DEBOUNCE_MS

    return ResolvedQueueConfig(
        mode=mode,
        cap=cap,
        drop=drop,
        debounce_ms=debounce,
    )


__all__ = [
    "DEFAULT_QUEUE_CAP",
    "DEFAULT_QUEUE_DEBOUNCE_MS",
    "DEFAULT_QUEUE_DROP",
    "DEFAULT_QUEUE_MODE",
    "QueueDropPolicy",
    "QueueMode",
    "ResolvedQueueConfig",
    "parse_queue_command",
    "parse_time_duration_ms",
    "resolve_queue_cap",
    "resolve_queue_config",
    "resolve_queue_drop",
    "resolve_queue_mode",
]
