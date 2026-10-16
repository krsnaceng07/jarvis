"""Polls watched adopted sessions for direct upstream human activity.

Mirrors OpenClaw's ``src/sessions/session-upstream-monitor.ts``.

The monitor is a periodic poller: every tick, it walks the
``session_upstream_links`` table joined with
``session_watch_cursors``, asks each session-catalog provider
for upstream activity, and records ``human_direct_message`` /
``upstream_missing`` state events. Missing sources are
counted across ticks and the link is removed after
``SESSION_UPSTREAM_MISSING_THRESHOLD`` consecutive misses.

Python adaptations (documented in code):
- TS crypto.createHash → Python ``hashlib.sha256``
- TS ``setInterval`` + ``setTimeout`` → ``threading.Timer`` /
  ``threading.Event`` (daemon, fire-and-forget; no ``unref``
  in CPython)
- ``loadSessionEntry`` / ``isEmbeddedAgentRunActive`` /
  ``readRecentUserAssistantTextForSession`` are passed in via
  the ``load_entry`` / ``is_run_active`` /
  ``load_own_recent_user_texts`` options (mirrors the TS DI
  pattern)
- ``recordSessionHumanDirectMessage`` / ``recordSessionStateEvent``
  are passed in via ``record_state_event`` /
  ``record_human_direct_message`` option stubs; production
  wiring is the responsibility of the host (when the
  session-state-events module is ported)
- TS ``process.env.VITEST`` test API export → Python module-
  level ``_RUN_TICK_FOR_TEST`` re-export
- ``getPluginRegistryState`` / ``currentProviders`` are
  replaced by the ``providers`` option (the host supplies the
  active providers list)
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("jarvis.sessions.upstream_monitor")

# Constants from the TS source.
SESSION_UPSTREAM_MONITOR_INTERVAL_MS = 60_000
SESSION_UPSTREAM_MONITOR_INITIAL_DELAY_MS = 15_000
SESSION_UPSTREAM_OWN_USER_TEXT_LIMIT = 10
SESSION_UPSTREAM_MISSING_THRESHOLD = 3
SESSION_UPSTREAM_OCCURRED_AT_CLAMP_MS = 24 * 60 * 60_000  # 24h


# ── Types ──────────────────────────────────────────────────


SessionUpstreamProbeBase = dict[str, Any]
SessionUpstreamProbe = dict[str, Any]
SessionUpstreamOutcome = dict[str, Any]
SessionCatalogProvider = dict[str, Any]
SessionEntry = dict[str, Any]

# Hook signatures.
LoadEntryFn = Callable[..., Optional[SessionEntry]]
IsRunActiveFn = Callable[[str], bool]
LoadOwnRecentUserTextsFn = Callable[
    [dict[str, Any], SessionEntry, "SessionUpstreamMonitorOptions"],
    Awaitable[list[str]],
]
RecordStateEventFn = Callable[[dict[str, Any], dict[str, Any]], bool]
RecordHumanDirectMessageFn = Callable[[dict[str, Any], dict[str, Any]], bool]


@dataclass
class SessionUpstreamMonitorOptions:
    """Configuration bag for the upstream-monitor tick.

    Mirrors the TS ``SessionUpstreamMonitorOptions`` shape.
    The host is responsible for providing the providers list
    (or a registry lookup) and the recording hooks. The
    default recording hooks are no-op stubs; the host should
    override them when the session-state-events module is
    wired.
    """

    providers: Optional[list[SessionCatalogProvider]] = None
    now: Optional[Callable[[], int]] = None
    load_entry: Optional[LoadEntryFn] = None
    is_run_active: Optional[IsRunActiveFn] = None
    load_own_recent_user_texts: Optional[LoadOwnRecentUserTextsFn] = None
    record_state_event: Optional[RecordStateEventFn] = None
    record_human_direct_message: Optional[RecordHumanDirectMessageFn] = None
    # Pass-through DB options; the helpers route them to the
    # session_upstream_links layer.
    env: Optional[dict[str, str]] = None
    path: Optional[str] = None
    connection_factory: Optional[Callable[[], Any]] = None


@dataclass
class SessionUpstreamMissingCounter:
    count: int = 0
    link_updated_at: int = 0


@dataclass
class SessionUpstreamMonitor:
    stop: Callable[[], None]


# ── Helpers ────────────────────────────────────────────────


def _now_ms(options: SessionUpstreamMonitorOptions) -> int:
    return int((options.now or time.time)() * 1000) if options.now else int(time.time() * 1000)


def _default_load_entry(**kwargs: Any) -> Optional[SessionEntry]:
    """Default loadEntry stub. Mirrors the TS ``loadSessionEntry`` shape."""
    raise NotImplementedError(
        "session_upstream_monitor: host must supply load_entry in options"
    )


def _default_is_run_active(session_id: str) -> bool:
    """Default isRunActive stub. Mirrors the TS ``isEmbeddedAgentRunActive`` shape."""
    return False


def _normalize_user_text(text: str) -> str:
    return " ".join((text or "").split())


def _upstream_source_key(probe: dict[str, Any]) -> str:
    """Stable identity of the physical upstream source.

    Mirrors the private ``upstreamSourceKey`` helper. Hashes
    ``hostId`` + ``threadId`` + ``upstreamRef`` into a
    16-hex-char prefix. A re-Continue that rebases a session
    onto a new source gets a fresh key so dedupe keys cannot
    silently collide with the old source's activity ids.
    """
    host_id = probe.get("hostId", "")
    thread_id = probe.get("threadId", "")
    upstream_ref = probe.get("upstreamRef")
    payload = f"{host_id}\x00{thread_id}\x00{json.dumps(upstream_ref, sort_keys=True)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _upstream_monitor_link_key(probe: dict[str, Any]) -> str:
    """Composite key for the monitor's missing-counter map.

    Mirrors the private ``upstreamMonitorLinkKey`` helper.
    """
    return (
        f"{probe.get('sessionKey', '')}\n"
        f"{probe.get('agentId', '')}\n"
        f"{_upstream_source_key(probe)}"
    )


async def _default_load_own_recent_user_texts(
    probe: SessionUpstreamProbeBase,
    entry: SessionEntry,
    options: SessionUpstreamMonitorOptions,
) -> list[str]:
    """Default loadOwnRecentUserTexts stub. Returns ``[]``."""
    return []


# ── Main tick ──────────────────────────────────────────────


async def run_session_upstream_monitor_tick(
    options: Optional[SessionUpstreamMonitorOptions] = None,
    missing_counts: Optional[dict[str, SessionUpstreamMissingCounter]] = None,
) -> None:
    """Run a single monitor tick.

    Mirrors ``runSessionUpstreamMonitorTick``. The host can
    pass the same ``missing_counts`` map across ticks to
    preserve consecutive-miss state; the function also
    prunes entries that fall out of the watched-link set.
    """
    from src.sessions.session_upstream_links import (
        SessionUpstreamLinkOptions,
        delete_session_upstream_link,
        list_watched_session_upstream_links,
        read_session_upstream_link,
        update_session_upstream_link_marker,
    )

    options = options or SessionUpstreamMonitorOptions()
    missing_counts = missing_counts if missing_counts is not None else {}

    db_options = SessionUpstreamLinkOptions(
        connection_factory=options.connection_factory,
        env=options.env,
    )

    links_by_catalog = list_watched_session_upstream_links(db_options)
    watched_link_keys: set[str] = set()
    for links in links_by_catalog.values():
        for link in links:
            watched_link_keys.add(
                _upstream_monitor_link_key(
                    {
                        "sessionKey": link["sessionKey"],
                        "agentId": link["agentId"],
                        "hostId": link["hostId"],
                        "threadId": link["threadId"],
                        "upstreamRef": link["upstreamRef"],
                    }
                )
            )
    # Monitor-owned counters must follow the watched-link
    # lifecycle or churn would leak keys.
    for key in list(missing_counts.keys()):
        if key not in watched_link_keys:
            missing_counts.pop(key, None)

    providers = options.providers or []
    provider_by_id = {p["id"]: p for p in providers}

    for catalog_id, links in links_by_catalog.items():
        provider = provider_by_id.get(catalog_id)
        if not provider or not provider.get("checkUpstreamActivity"):
            continue

        probes: list[SessionUpstreamProbe] = []
        for link in links:
            probe_base: SessionUpstreamProbeBase = {
                "sessionKey": link["sessionKey"],
                "agentId": link["agentId"],
                "threadId": link["threadId"],
                "hostId": link["hostId"],
                "upstreamKind": link["upstreamKind"],
                "upstreamRef": link["upstreamRef"],
                "marker": link.get("marker"),
            }
            try:
                load_entry = options.load_entry or _default_load_entry
                entry = load_entry(
                    sessionKey=probe_base["sessionKey"],
                    agentId=probe_base["agentId"],
                    clone=False,
                )
                if not entry or not entry.get("sessionId"):
                    continue
                is_run_active = options.is_run_active or _default_is_run_active
                if is_run_active(entry["sessionId"]):
                    continue
                loader = options.load_own_recent_user_texts or _default_load_own_recent_user_texts
                own_recent = await loader(probe_base, entry, options)
                probes.append({**probe_base, "ownRecentUserTexts": own_recent})
            except Exception as error:  # noqa: BLE001 — best-effort per-link skip
                logger.warning(
                    "upstream transcript provenance failed for %s: %s",
                    probe_base["sessionKey"],
                    error,
                )
        if not probes:
            continue
        probe_by_session_key = {p["sessionKey"]: p for p in probes}
        link_updated_at_by_session_key = {
            link["sessionKey"]: link["updatedAt"] for link in links
        }
        try:
            outcomes = await provider["checkUpstreamActivity"](probes)
            missing_session_keys = {
                o["sessionKey"]
                for o in outcomes
                if o.get("kind") == "missing"
            }
            for probe in probes:
                if probe["sessionKey"] not in missing_session_keys:
                    missing_counts.pop(_upstream_monitor_link_key(probe), None)
            for outcome in outcomes:
                probe = probe_by_session_key.get(outcome["sessionKey"])
                if probe is None:
                    continue
                missing_count_key = _upstream_monitor_link_key(probe)
                if outcome.get("kind") == "missing":
                    expected_updated_at = link_updated_at_by_session_key.get(
                        outcome["sessionKey"]
                    )
                    if expected_updated_at is None:
                        missing_counts.pop(missing_count_key, None)
                        continue
                    previous = missing_counts.get(missing_count_key)
                    if previous is not None and previous.link_updated_at == expected_updated_at:
                        previous_count = previous.count
                    else:
                        previous_count = 0
                    missing_count = min(
                        SESSION_UPSTREAM_MISSING_THRESHOLD,
                        previous_count + 1,
                    )
                    missing_counts[missing_count_key] = SessionUpstreamMissingCounter(
                        count=missing_count,
                        link_updated_at=expected_updated_at,
                    )
                    if missing_count < SESSION_UPSTREAM_MISSING_THRESHOLD:
                        continue
                    current_link = read_session_upstream_link(
                        probe["sessionKey"], probe["agentId"], db_options
                    )
                    if (
                        not current_link
                        or current_link["updatedAt"] != expected_updated_at
                        or _upstream_source_key(current_link) != _upstream_source_key(probe)
                    ):
                        missing_counts.pop(missing_count_key, None)
                        continue
                    source_key = _upstream_source_key(probe)
                    record_state_event = options.record_state_event
                    recorded = False
                    if record_state_event is not None:
                        recorded = record_state_event(
                            {
                                "sessionKey": probe["sessionKey"],
                                "agentId": probe["agentId"],
                                "kind": "upstream_missing",
                                "actorType": "system",
                                "dedupeKey": (
                                    f"upstream-missing:{probe['sessionKey']}:"
                                    f"{source_key}:{current_link['updatedAt']}"
                                ),
                                "summary": f"upstream missing via {catalog_id}",
                                "payload": {"channel": catalog_id},
                            },
                            {
                                "now": _now_ms(options),
                            },
                        )
                    if not recorded:
                        missing_counts[missing_count_key] = SessionUpstreamMissingCounter(
                            count=SESSION_UPSTREAM_MISSING_THRESHOLD - 1,
                            link_updated_at=expected_updated_at,
                        )
                        continue
                    delete_session_upstream_link(
                        probe["sessionKey"], probe["agentId"], db_options
                    )
                    missing_counts.pop(missing_count_key, None)
                    continue
                missing_counts.pop(missing_count_key, None)
                activity = outcome
                human_turns = activity.get("humanTurns")
                if not isinstance(human_turns, int) or human_turns < 0:
                    continue
                try:
                    if not await _probe_provenance_unchanged(probe, options):
                        continue
                except Exception as error:  # noqa: BLE001
                    logger.warning(
                        "upstream transcript provenance failed for %s: %s",
                        probe["sessionKey"],
                        error,
                    )
                    continue
                # CAS guard: a Continue can refresh the link mid-scan.
                expected_updated_at = link_updated_at_by_session_key.get(activity["sessionKey"])
                current_link = read_session_upstream_link(
                    probe["sessionKey"], probe["agentId"], db_options
                )
                if (
                    not current_link
                    or current_link["updatedAt"] != expected_updated_at
                    or _upstream_source_key(current_link) != _upstream_source_key(probe)
                ):
                    continue
                if human_turns == 0:
                    update_session_upstream_link_marker(
                        probe["sessionKey"],
                        probe["agentId"],
                        activity.get("nextMarker"),
                        SessionUpstreamLinkOptions(
                            connection_factory=options.connection_factory,
                            env=options.env,
                            now=_now_ms(options),
                            expected_updated_at=expected_updated_at,
                        ),
                    )
                    continue
                occurred_at = activity.get("occurredAt")
                if not isinstance(occurred_at, (int, float)) or not activity.get("dedupeId"):
                    continue
                source_key = _upstream_source_key(probe)
                record_human = options.record_human_direct_message
                recorded = False
                if record_human is not None:
                    payload: dict[str, Any] = {}
                    if human_turns > 1:
                        payload["turns"] = human_turns
                    recorded = record_human(
                        {
                            "sessionKey": probe["sessionKey"],
                            "agentId": probe["agentId"],
                            "actor": {"actorType": "human"},
                            "channel": catalog_id,
                            "dedupeKey": (
                                f"upstream:{probe['sessionKey']}:{source_key}:{activity['dedupeId']}"
                            ),
                            **({"payload": payload} if payload else {}),
                            "occurredAt": int(occurred_at),
                        },
                        {"now": _now_ms(options)},
                    )
                if not recorded:
                    continue
                # Commit the scan marker only after the durable
                # event insert/dedupe succeeds.
                update_session_upstream_link_marker(
                    probe["sessionKey"],
                    probe["agentId"],
                    activity.get("nextMarker"),
                    SessionUpstreamLinkOptions(
                        connection_factory=options.connection_factory,
                        env=options.env,
                        now=_now_ms(options),
                        expected_updated_at=expected_updated_at,
                    ),
                )
        except Exception as error:  # noqa: BLE001 — provider isolation
            logger.warning(
                "upstream activity probe failed for %s: %s", catalog_id, error
            )


async def _probe_provenance_unchanged(
    probe: SessionUpstreamProbe,
    options: SessionUpstreamMonitorOptions,
) -> bool:
    """Return ``True`` when the probe's recorded own-recent user texts still match the live entry.

    Mirrors the private ``probeProvenanceUnchanged`` helper.
    """
    load_entry = options.load_entry or _default_load_entry
    entry = load_entry(
        sessionKey=probe["sessionKey"],
        agentId=probe["agentId"],
        clone=False,
    )
    if not entry or not entry.get("sessionId"):
        return False
    is_run_active = options.is_run_active or _default_is_run_active
    if is_run_active(entry["sessionId"]):
        return False
    loader = options.load_own_recent_user_texts or _default_load_own_recent_user_texts
    probe_without_recent = {
        k: v for k, v in probe.items() if k != "ownRecentUserTexts"
    }
    current = await loader(probe_without_recent, entry, options)
    return current == list(probe.get("ownRecentUserTexts", []))


# ── Scheduler ─────────────────────────────────────────────


def start_session_upstream_monitor(
    options: Optional[SessionUpstreamMonitorOptions] = None,
) -> SessionUpstreamMonitor:
    """Start the periodic upstream-monitor poller.

    Mirrors ``startSessionUpstreamMonitor``. The returned
    handle exposes a ``stop()`` callable that cancels the
    timers. Sessions catalogs own this bounded freshness
    exception; plugin metadata remains restart-stable.
    """
    options = options or SessionUpstreamMonitorOptions()
    stopped = False
    running = False
    missing_counts: dict[str, SessionUpstreamMissingCounter] = {}
    initial_timer: Optional[threading.Timer] = None
    interval_timer: Optional[threading.Timer] = None

    import asyncio

    def _schedule(delay_ms: int) -> threading.Timer:
        timer = threading.Timer(delay_ms / 1000.0, _run)
        timer.daemon = True
        timer.start()
        return timer

    def _run() -> None:
        nonlocal running, initial_timer, interval_timer
        if stopped or running:
            return
        running = True
        try:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    run_session_upstream_monitor_tick(options, missing_counts)
                )
            finally:
                loop.close()
        except Exception as error:  # noqa: BLE001
            logger.warning("upstream monitor tick failed: %s", error)
        finally:
            running = False
            if not stopped:
                if initial_timer is not None:
                    initial_timer = None
                interval_timer = _schedule(SESSION_UPSTREAM_MONITOR_INTERVAL_MS)

    initial_timer = _schedule(SESSION_UPSTREAM_MONITOR_INITIAL_DELAY_MS)

    def _stop() -> None:
        nonlocal stopped, initial_timer, interval_timer
        stopped = True
        if initial_timer is not None:
            initial_timer.cancel()
            initial_timer = None
        if interval_timer is not None:
            interval_timer.cancel()
            interval_timer = None

    return SessionUpstreamMonitor(stop=_stop)


# Test-only re-export. Mirrors the TS
# ``globalThis[Symbol.for('openclaw.sessionUpstreamMonitorTestApi')]``
# exposed under ``process.env.VITEST`` / ``NODE_ENV=test``.
_RUN_TICK_FOR_TEST = run_session_upstream_monitor_tick


__all__ = [
    "SESSION_UPSTREAM_INITIAL_DELAY_MS" if False else "SESSION_UPSTREAM_MONITOR_INITIAL_DELAY_MS",
    "SESSION_UPSTREAM_INTERVAL_MS" if False else "SESSION_UPSTREAM_MONITOR_INTERVAL_MS",
    "SESSION_UPSTREAM_MISSING_THRESHOLD",
    "SESSION_UPSTREAM_OCCURRED_AT_CLAMP_MS",
    "SESSION_UPSTREAM_OWN_USER_TEXT_LIMIT",
    "SessionUpstreamMonitor",
    "SessionUpstreamMonitorOptions",
    "SessionUpstreamMissingCounter",
    "_upstream_source_key",
    "run_session_upstream_monitor_tick",
    "start_session_upstream_monitor",
]
