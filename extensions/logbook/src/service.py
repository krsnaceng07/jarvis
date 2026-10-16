"""Logbook background service: snapshot capture loop, batch analysis, retention.

Mirrors OpenClaw's ``extensions/logbook/src/service.ts``.
"""

from __future__ import annotations

import asyncio
import base64
import datetime
import hashlib
import inspect
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable, Coroutine, Optional, Set

from .analyze import (
    CARD_LOOKBACK_MS,
    MAX_FRAMES_PER_CALL,
    parse_cards_json,
    parse_observation_segments,
    pick_keyframe_id,
    revision_window,
    sample_frames,
    select_batch_frames,
    validate_card_coverage,
)
from .logbook_config import LogbookConfig, parse_model_ref
from .logbook_types import LogbookBatch, LogbookStatus
from .prompts import (
    OBSERVATION_JSON_SCHEMA,
    build_ask_prompt,
    build_cards_correction_prompt,
    build_cards_prompt,
    build_observation_instructions,
    build_standup_prompt,
)
from .store import LogbookStore, day_key_for

ANALYSIS_TICK_MS: int = 60 * 1000
PRUNE_TICK_MS: int = 60 * 60 * 1000
MODEL_MISSING_MESSAGE: str = (
    "no vision model: set plugins.entries.logbook.config.visionModel or configure tools.media"
)
MODEL_MISSING_LOG_INTERVAL_MS: int = 10 * 60 * 1000
CAPTURE_FAILURE_PAUSE_TICKS: int = 10
CAPTURE_FAILURE_THRESHOLD: int = 3
JPEG_QUALITY: float = 0.6
STRUCTURED_MEDIA_PROVIDER: str = "codex"

CAPTURE_COMMANDS: tuple[str, ...] = ("screen.snapshot", "logbook.snapshot")


def unwrap_invoke_payload(raw: Any) -> Optional[dict[str, Any]]:
    """Unwrap node.invoke response envelope containing {payload, payloadJSON}."""
    if not raw or not isinstance(raw, dict):
        return None
    if "payload" in raw and isinstance(raw["payload"], dict):
        return raw["payload"]
    if isinstance(raw.get("payloadJSON"), str) and raw["payloadJSON"]:
        try:
            import json

            parsed = json.loads(raw["payloadJSON"])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    if "base64" in raw or "error" in raw:
        return raw
    return None


class LogbookService:
    """Background service managing screen capture, analysis batches, and retention."""

    def __init__(
        self,
        config: Optional[LogbookConfig | dict[str, Any]] = None,
        deps: Optional[Any] = None,
        runtime: Any = None,
        full_config: Any = None,
        logger: Any = None,
        data_dir: str = "",
    ) -> None:
        self.config: dict[str, Any] = dict(config or {})
        if deps is None:
            self.runtime = runtime
            self.full_config = full_config or {}
            self.logger = logger or logging.getLogger("jarvis.logbook")
            self.data_dir = data_dir
        elif isinstance(deps, dict):
            self.runtime = deps.get("runtime")
            self.full_config = deps.get("fullConfig") or deps.get("full_config") or {}
            self.logger = deps.get("logger") or logging.getLogger("jarvis.logbook")
            self.data_dir = deps.get("dataDir") or deps.get("data_dir") or ""
        else:
            self.runtime = getattr(deps, "runtime", None)
            self.full_config = getattr(deps, "fullConfig", getattr(deps, "full_config", {}))
            self.logger = getattr(deps, "logger", logging.getLogger("jarvis.logbook"))
            self.data_dir = getattr(deps, "dataDir", getattr(deps, "data_dir", ""))

        self.store: Optional[LogbookStore] = None
        self._operations: Set[asyncio.Task[Any]] = set()
        self._stopping: Optional[asyncio.Future[None]] = None
        self._capture_task: Optional[asyncio.Task[None]] = None
        self._analysis_task: Optional[asyncio.Task[None]] = None
        self._prune_task: Optional[asyncio.Task[None]] = None

        self._capture_in_flight = False
        self._analysis_in_flight = False
        self._capture_paused = False
        self._capture_failures = 0
        self._capture_backoff_ticks = 0
        self._last_capture_at_ms: Optional[int] = None
        self._last_capture_error: Optional[str] = None
        self._last_model_missing_log_ms = 0

        self._cached_node: Optional[dict[str, Any]] = None
        self._failed_node_ids: set[str] = set()

    def start(self) -> None:
        """Initialize database store and start background loops."""
        self._stopping = None
        if self.data_dir:
            self.store = LogbookStore(self.data_dir)
            self.store.reset_running_batches()

        # Try to schedule background tasks if an event loop is running
        try:
            loop = asyncio.get_running_loop()
            self._capture_task = loop.create_task(self._run_capture_loop())
            self._analysis_task = loop.create_task(self._run_analysis_loop())
            self._prune_task = loop.create_task(self._run_prune_loop())
        except RuntimeError:
            pass

        self.prune()
        if hasattr(self.logger, "info"):
            self.logger.info(
                f"logbook: started (capture every {self.config.get('captureIntervalSeconds', 30)}s, "
                f"analysis window {self.config.get('analysisIntervalMinutes', 15)}m, data {self.data_dir})"
            )

    async def _run_capture_loop(self) -> None:
        interval = max(5, self.config.get("captureIntervalSeconds", 30))
        while self._stopping is None:
            await asyncio.sleep(interval)
            if self._stopping is not None:
                break
            try:
                await self.capture_tick()
            except Exception as e:
                if hasattr(self.logger, "error"):
                    self.logger.error(f"logbook: capture loop error: {e}")

    async def _run_analysis_loop(self) -> None:
        while self._stopping is None:
            await asyncio.sleep(ANALYSIS_TICK_MS / 1000.0)
            if self._stopping is not None:
                break
            try:
                await self.analysis_tick()
            except Exception as e:
                if hasattr(self.logger, "error"):
                    self.logger.error(f"logbook: analysis loop error: {e}")

    async def _run_prune_loop(self) -> None:
        while self._stopping is None:
            await asyncio.sleep(PRUNE_TICK_MS / 1000.0)
            if self._stopping is not None:
                break
            self.prune()

    def stop(self) -> Any:
        """Cancel background loops, await inflight operations, and close store."""
        if self._stopping is not None:
            return self._stopping

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass

        if loop is not None:
            self._stopping = loop.create_future()
        else:
            self._stopping = asyncio.Future()

        for t in (self._capture_task, self._analysis_task, self._prune_task):
            if t is not None:
                t.cancel()
        self._capture_task = None
        self._analysis_task = None
        self._prune_task = None

        store = self.store

        async def _drain() -> None:
            try:
                if self._operations:
                    await asyncio.gather(*list(self._operations), return_exceptions=True)
            finally:
                if store is not None:
                    store.close()
                self.store = None
                if not self._stopping.done():
                    self._stopping.set_result(None)

        if loop is not None:
            loop.create_task(_drain())
        else:
            if store is not None:
                store.close()
            self.store = None
            self._stopping.set_result(None)

        return self._stopping

    def _track_operation(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        loop = asyncio.get_running_loop()
        task = loop.create_task(coro)
        self._operations.add(task)
        task.add_done_callback(lambda t: self._operations.discard(t))
        return task

    def _require_store(self) -> LogbookStore:
        if self._stopping is not None or self.store is None:
            raise RuntimeError("Logbook service is not running")
        return self.store

    def set_capture_paused(self, paused: bool) -> None:
        """Pause or resume the screen snapshot loop."""
        self._capture_paused = paused
        if not paused:
            self._capture_backoff_ticks = 0
            self._capture_failures = 0

    setCapturePaused = set_capture_paused

    async def _resolve_node(self) -> dict[str, Any]:
        if self._cached_node is not None:
            return {"node": self._cached_node}

        if self.runtime is None or not hasattr(self.runtime, "nodes"):
            return {"reason": "runtime nodes api is not available"}

        nodes_list_fn = self.runtime.nodes.list
        res = nodes_list_fn({"connected": True}) if callable(nodes_list_fn) else None
        if inspect.isawaitable(res):
            res = await res

        nodes: list[dict[str, Any]] = res.get("nodes", []) if isinstance(res, dict) else []

        def get_capture_command(node: dict[str, Any]) -> Optional[str]:
            cmds = node.get("commands") or []
            for c in CAPTURE_COMMANDS:
                if c in cmds:
                    return c
            return None

        candidates = [n for n in nodes if get_capture_command(n) is not None]

        def command_rank(n: dict[str, Any]) -> int:
            cmd = get_capture_command(n)
            return CAPTURE_COMMANDS.index(cmd) if cmd in CAPTURE_COMMANDS else 99

        candidates.sort(key=lambda n: (command_rank(n), str(n.get("nodeId", ""))))

        wanted = self.config.get("nodeId", "").strip().lower() if self.config.get("nodeId") else None
        pool = [n for n in candidates if n.get("nodeId") not in self._failed_node_ids]
        if not pool:
            self._failed_node_ids.clear()
            pool = candidates

        picked = None
        if wanted:
            for n in candidates:
                if (
                    str(n.get("nodeId", "")).lower() == wanted
                    or str(n.get("displayName", "")).lower() == wanted
                ):
                    picked = n
                    break
        elif pool:
            picked = pool[0]

        command = get_capture_command(picked) if picked else None
        if not picked or not command:
            inv_items = [
                f"{n.get('displayName') or n.get('nodeId')}({'/'.join(n.get('commands', [])) or 'no commands'})"
                for n in nodes
            ]
            inventory = ", ".join(inv_items) or "none"
            return {"reason": f"no connected node exposes {' or '.join(CAPTURE_COMMANDS)}; connected: {inventory}"}

        self._cached_node = {
            "nodeId": picked["nodeId"],
            "displayName": picked.get("displayName"),
            "command": command,
        }
        return {"node": self._cached_node}

    async def capture_tick(self) -> None:
        """Perform one periodic screen capture iteration."""
        store = self.store
        if (
            self._stopping is not None
            or not self.config.get("captureEnabled", True)
            or self._capture_paused
            or self._capture_in_flight
            or store is None
        ):
            return

        if self._capture_backoff_ticks > 0:
            self._capture_backoff_ticks -= 1
            return

        self._capture_in_flight = True

        async def _do_capture() -> None:
            try:
                resolved = await self._resolve_node()
                if "reason" in resolved:
                    reason = resolved["reason"]
                    if self._last_capture_error != reason:
                        if hasattr(self.logger, "warn"):
                            self.logger.warn(f"logbook: {reason}")
                    self._last_capture_error = reason
                    return

                node = resolved["node"]
                invoke_fn = self.runtime.nodes.invoke
                invoke_args = {
                    "nodeId": node["nodeId"],
                    "command": node["command"],
                    "params": {
                        "screenIndex": self.config.get("screenIndex", 0),
                        "maxWidth": self.config.get("maxWidth", 1440),
                        "quality": JPEG_QUALITY,
                        "format": "jpeg",
                    },
                    "timeoutMs": 30000,
                }
                invoked = invoke_fn(invoke_args) if callable(invoke_fn) else None
                if inspect.isawaitable(invoked):
                    invoked = await invoked

                raw = unwrap_invoke_payload(invoked)
                if not raw:
                    raise ValueError(f"{node['command']} returned no image payload")
                if raw.get("error"):
                    raise ValueError(raw["error"])

                raw_base64 = raw.get("base64")
                if raw_base64 is None or raw_base64 == "":
                    raise ValueError(f"{node['command']} returned no image payload")
                if not isinstance(raw_base64, str):
                    raise ValueError(f"{node['command']} returned invalid image payload")

                try:
                    buffer = base64.b64decode(raw_base64, validate=True)
                except Exception:
                    raise ValueError(f"{node['command']} returned invalid image payload")

                captured_at_ms = int(time.time() * 1000)
                day = day_key_for(captured_at_ms)
                content_hash = hashlib.sha256(buffer).hexdigest()

                last_f = store.last_frame()
                idle = last_f is not None and last_f.get("contentHash") == content_hash

                file_path = store.frame_file_path(day, captured_at_ms)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                try:
                    os.chmod(os.path.dirname(file_path), 0o700)
                except OSError:
                    pass

                with open(file_path, "wb") as f:
                    f.write(buffer)
                try:
                    os.chmod(file_path, 0o600)
                except OSError:
                    pass

                store.insert_frame({
                    "capturedAtMs": captured_at_ms,
                    "day": day,
                    "path": file_path,
                    "screenIndex": self.config.get("screenIndex", 0),
                    "width": raw.get("width"),
                    "height": raw.get("height"),
                    "byteSize": len(buffer),
                    "contentHash": content_hash,
                    "idle": idle,
                })

                self._last_capture_at_ms = captured_at_ms
                self._last_capture_error = None
                self._capture_failures = 0
                self._failed_node_ids.clear()
            except Exception as err:
                self._capture_failures += 1
                if self._cached_node:
                    self._failed_node_ids.add(self._cached_node["nodeId"])
                self._cached_node = None
                self._last_capture_error = str(err)
                if self._capture_failures >= CAPTURE_FAILURE_THRESHOLD:
                    self._capture_backoff_ticks = CAPTURE_FAILURE_PAUSE_TICKS
                    if hasattr(self.logger, "warn"):
                        self.logger.warn(
                            f"logbook: capture failing ({self._last_capture_error}); backing off for {CAPTURE_FAILURE_PAUSE_TICKS} ticks"
                        )
            finally:
                self._capture_in_flight = False

        task = self._track_operation(_do_capture())
        await task

    captureTick = capture_tick

    def _resolve_vision_model(self) -> dict[str, Any]:
        if self.config.get("visionModel"):
            ref = parse_model_ref(self.config["visionModel"])
            return {"ref": ref, "source": "config"} if ref else {"source": "missing"}

        full_cfg = self.full_config
        tools = full_cfg.get("tools") if isinstance(full_cfg, dict) else getattr(full_cfg, "tools", None)
        media = (tools.get("media") if isinstance(tools, dict) else getattr(tools, "media", None)) or {}
        image_cfg = (media.get("image") if isinstance(media, dict) else getattr(media, "image", None)) or {}

        # Operators who disabled image understanding must not have screenshots routed
        if (image_cfg.get("enabled") if isinstance(image_cfg, dict) else getattr(image_cfg, "enabled", True)) is False:
            return {"source": "missing"}

        entries = (media.get("models") if isinstance(media, dict) else getattr(media, "models", None)) or []
        for entry in entries:
            entry_dict = entry if isinstance(entry, dict) else entry.__dict__
            provider = str(entry_dict.get("provider", "")).strip().lower()
            model = entry_dict.get("model")
            capabilities = entry_dict.get("capabilities")
            mtype = entry_dict.get("type")

            usable = (
                mtype != "cli"
                and provider == STRUCTURED_MEDIA_PROVIDER
                and isinstance(model, str)
                and (not capabilities or "image" in capabilities)
            )
            if usable:
                return {
                    "ref": {
                        "provider": STRUCTURED_MEDIA_PROVIDER,
                        "model": model,
                        "profile": entry_dict.get("profile"),
                        "preferredProfile": entry_dict.get("preferredProfile"),
                    },
                    "source": "media-defaults",
                }

        return {"source": "missing"}

    async def analyze_now(self) -> dict[str, Any]:
        """Force-close current window and trigger analysis immediately."""
        store = self._require_store()
        if self._analysis_in_flight:
            return {"started": False, "reason": "analysis already running"}

        vision = self._resolve_vision_model()
        if not vision.get("ref"):
            return {"started": False, "reason": MODEL_MISSING_MESSAGE}

        store.reset_error_batches()
        if not store.next_pending_batch():
            if not self._enqueue_next_batch(store, force=True):
                return {"started": False, "reason": "no unanalyzed activity captured yet"}

        # Track analysis pass
        self._track_operation(self.analysis_tick())
        return {"started": True}

    analyzeNow = analyze_now

    async def analysis_tick(self) -> None:
        """Run batch analysis for pending frames."""
        store = self.store
        if self._stopping is not None or self._analysis_in_flight or store is None:
            return

        vision = self._resolve_vision_model()
        if not vision.get("ref"):
            now = int(time.time() * 1000)
            if now - self._last_model_missing_log_ms > MODEL_MISSING_LOG_INTERVAL_MS:
                self._last_model_missing_log_ms = now
                if hasattr(self.logger, "warn"):
                    self.logger.warn(f"logbook: analysis paused; {MODEL_MISSING_MESSAGE}")
            return

        self._analysis_in_flight = True

        async def _do_analysis() -> None:
            try:
                if self._stopping is not None:
                    return
                self._enqueue_elapsed_window(store)
                for _ in range(4):
                    if self._stopping is not None:
                        break
                    batch = store.next_pending_batch()
                    if not batch:
                        break
                    await self._run_batch(store, batch)
            except Exception as err:
                if hasattr(self.logger, "error"):
                    self.logger.error(f"logbook: analysis tick failed: {err}")
            finally:
                self._analysis_in_flight = False

        task = self._track_operation(_do_analysis())
        await task

    analysisTick = analysis_tick

    def _enqueue_next_batch(self, store: LogbookStore, force: bool = False) -> bool:
        selection = select_batch_frames(
            frames=store.unbatched_active_frames(2000),  # type: ignore[arg-type]
            window_ms=self.config.get("analysisIntervalMinutes", 15) * 60000,
            now_ms=int(time.time() * 1000),
            force=force,
        )
        if not selection:
            return False

        store.create_batch(
            day=day_key_for(selection["startMs"]),
            start_ms=selection["startMs"],
            end_ms=selection["endMs"],
            frame_ids=selection["frameIds"],
        )
        return True

    def _enqueue_elapsed_window(self, store: LogbookStore) -> None:
        while self._enqueue_next_batch(store):
            pass

    async def _run_batch(self, store: LogbookStore, batch: LogbookBatch) -> None:
        vision = self._resolve_vision_model()
        if not vision.get("ref"):
            return

        v_ref = vision["ref"]
        store.set_batch_status(
            batch["id"],
            "running",
            None,
            f"{v_ref['provider']}/{v_ref['model']}",
        )

        try:
            frames = store.batch_frames(batch["id"])
            sampled = sample_frames(frames, MAX_FRAMES_PER_CALL)
            images = []
            for frame in sampled:
                with open(frame["path"], "rb") as f:
                    buf = f.read()
                images.append({
                    "type": "image",
                    "buffer": buf,
                    "fileName": os.path.basename(frame["path"]),
                    "mime": "image/jpeg",
                })

            media_understanding = getattr(self.runtime, "mediaUnderstanding", getattr(self.runtime, "media_understanding", None))
            extract_fn = getattr(media_understanding, "extractStructuredWithModel", getattr(media_understanding, "extract_structured_with_model", None))
            if not callable(extract_fn):
                raise RuntimeError("mediaUnderstanding.extractStructuredWithModel is not available")

            instructions = build_observation_instructions(
                frame_times=[f["capturedAtMs"] for f in sampled],
                start_ms=batch["startMs"],
                end_ms=batch["endMs"],
            )

            extract_args = {
                "provider": v_ref["provider"],
                "model": v_ref["model"],
                "profile": v_ref.get("profile"),
                "preferredProfile": v_ref.get("preferredProfile"),
                "input": images,
                "instructions": instructions,
                "schemaName": "logbook.observations",
                "jsonSchema": OBSERVATION_JSON_SCHEMA,
                "cfg": self.full_config,
                "timeoutMs": 180000,
            }

            observation_result = extract_fn(extract_args)
            if inspect.isawaitable(observation_result):
                observation_result = await observation_result

            raw_text = (
                observation_result.get("text", "")
                if isinstance(observation_result, dict)
                else getattr(observation_result, "text", "")
            )

            segments = parse_observation_segments(
                raw=raw_text,
                day=batch["day"],
                start_ms=batch["startMs"],
                end_ms=batch["endMs"],
            )
            if not segments:
                store.set_batch_status(batch["id"], "error", "vision model returned no usable segments")
                return

            store.replace_observations(batch["id"], batch["day"], segments)
            await self._revise_cards(store, batch)
            store.set_batch_status(batch["id"], "done")
        except Exception as err:
            message = str(err)
            store.set_batch_status(batch["id"], "error", message)
            if hasattr(self.logger, "warn"):
                self.logger.warn(f"logbook: batch {batch['id']} failed: {message}")

    async def _revise_cards(self, store: LogbookStore, batch: LogbookBatch) -> None:
        lookback_start = batch["startMs"] - CARD_LOOKBACK_MS
        previous_cards = store.cards_for_day(
            batch["day"],
            {"startMs": lookback_start, "endMs": batch["endMs"]},
        )
        observations = store.observations_in_range(
            batch["day"],
            min(lookback_start, batch["startMs"]),
            batch["endMs"],
        )
        window = revision_window(
            batch_start_ms=batch["startMs"],
            batch_end_ms=batch["endMs"],
            previous_cards=previous_cards,  # type: ignore[arg-type]
        )
        prompt = build_cards_prompt(
            day=batch["day"],
            observations=observations,
            previous_cards=previous_cards,
            window_start_ms=window["startMs"],
            window_end_ms=window["endMs"],
        )

        required_spans = [
            {"startMs": c["startMs"], "endMs": c["endMs"]}
            for c in previous_cards
        ] + [{"startMs": batch["startMs"], "endMs": batch["endMs"]}]

        def evaluate(raw: str) -> dict[str, Any]:
            parsed = parse_cards_json(
                raw=raw,
                day=batch["day"],
                window_start_ms=window["startMs"],
                window_end_ms=window["endMs"],
            )
            if not parsed.get("ok"):
                return parsed
            coverage = validate_card_coverage(
                drafts=parsed.get("drafts", []),
                required_spans=required_spans,
                window_start_ms=window["startMs"],
                window_end_ms=window["endMs"],
            )
            return parsed if coverage.get("ok") else {"ok": False, "error": coverage.get("error", "")}

        llm = getattr(self.runtime, "llm", None)
        complete_fn = getattr(llm, "complete", None)
        if not callable(complete_fn):
            raise RuntimeError("runtime.llm.complete is not available")

        first_res = complete_fn({
            "messages": [{"role": "user", "content": prompt}],
            "purpose": "logbook.cards",
            "maxTokens": 4000,
        })
        if inspect.isawaitable(first_res):
            first_res = await first_res

        first_text = (
            first_res.get("text", "")
            if isinstance(first_res, dict)
            else getattr(first_res, "text", "")
        )
        parsed = evaluate(first_text)

        if not parsed.get("ok"):
            retry_res = complete_fn({
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": first_text},
                    {"role": "user", "content": build_cards_correction_prompt(parsed.get("error", ""))},
                ],
                "purpose": "logbook.cards.repair",
                "maxTokens": 4000,
            })
            if inspect.isawaitable(retry_res):
                retry_res = await retry_res
            retry_text = (
                retry_res.get("text", "")
                if isinstance(retry_res, dict)
                else getattr(retry_res, "text", "")
            )
            parsed = evaluate(retry_text)

        if not parsed.get("ok"):
            raise ValueError(f"card synthesis failed validation: {parsed.get('error')}")

        window_frames = [
            {"id": f["id"], "capturedAtMs": f["capturedAtMs"]}
            for f in store.frames_in_range(window["startMs"], window["endMs"])
        ]
        drafts = []
        for draft in parsed.get("drafts", []):
            d = dict(draft)
            d["keyframeId"] = pick_keyframe_id(d, window_frames)
            drafts.append(d)

        store.replace_cards_in_window(batch["day"], window["startMs"], window["endMs"], drafts)  # type: ignore[arg-type]

    def standup(self, day: str, refresh: bool = False) -> Any:
        """Return cached or newly generated standup summary for the day."""
        if self._stopping is not None:
            raise RuntimeError("Logbook service is not running")
        if self.store is None:
            return {
                "day": day,
                "summary": "",
                "cards": self.cards_for_day(day),
            }

        store = self.store

        async def _do_standup() -> dict[str, Any]:
            if not refresh:
                cached = store.get_standup(day)
                if cached:
                    return cached

            # Calculate yesterday's day key safely
            dt = datetime.date.fromisoformat(day)
            prev_dt = dt - datetime.timedelta(days=1)
            previous_day = prev_dt.isoformat()

            llm = getattr(self.runtime, "llm", None)
            complete_fn = getattr(llm, "complete", None)
            if not callable(complete_fn):
                raise RuntimeError("runtime.llm.complete is not available")

            prompt = build_standup_prompt(
                day=day,
                cards=store.cards_for_day(day),
                previous_day_cards=store.cards_for_day(previous_day),
            )
            res = complete_fn({
                "messages": [{"role": "user", "content": prompt}],
                "purpose": "logbook.standup",
                "maxTokens": 800,
            })
            if inspect.isawaitable(res):
                res = await res

            text = (
                res.get("text", "").strip()
                if isinstance(res, dict)
                else getattr(res, "text", "").strip()
            )
            store.save_standup(day, text)
            saved = store.get_standup(day)
            if not saved:
                raise RuntimeError("standup save failed")
            return saved

        task = self._track_operation(_do_standup())
        return task

    def ask(self, day: str, question: str) -> Any:
        """Answer a free-form question about the tracked day using stored observations and cards."""
        if self._stopping is not None:
            raise RuntimeError("Logbook service is not running")
        if self.store is None:
            return {
                "day": day,
                "question": question,
                "answer": "Logbook ask is not yet ported in this JARVIS build.",
            }

        store = self.store

        async def _do_ask() -> str:
            observations = store.observations_in_range(day, 0, 9223372036854775807, 200)
            cards = store.cards_for_day(day)
            prompt = build_ask_prompt(
                day=day,
                cards=cards,
                observations=observations,
                question=question,
            )

            llm = getattr(self.runtime, "llm", None)
            complete_fn = getattr(llm, "complete", None)
            if not callable(complete_fn):
                raise RuntimeError("runtime.llm.complete is not available")

            res = complete_fn({
                "messages": [{"role": "user", "content": prompt}],
                "purpose": "logbook.ask",
                "maxTokens": 600,
            })
            if inspect.isawaitable(res):
                res = await res

            text = (
                res.get("text", "").strip()
                if isinstance(res, dict)
                else getattr(res, "text", "").strip()
            )
            return text

        task = self._track_operation(_do_ask())
        return task

    def timeline_for_day(self, day: str) -> dict[str, Any]:
        if self.store is None:
            return {
                "day": day,
                "cards": [],
                "stats": {
                    "trackedMs": 0,
                    "distractionMs": 0,
                    "categories": [],
                    "apps": [],
                },
            }
        return self.store.timeline_for_day(day)

    timelineForDay = timeline_for_day

    def list_days(self) -> list[Any]:
        if self.store is None:
            return []
        return self.store.list_days()

    listDays = list_days

    def cards_for_day(self, day: str) -> list[dict[str, Any]]:
        if self.store is None:
            return []
        return self.store.cards_for_day(day)  # type: ignore[return-value]

    cardsForDay = cards_for_day

    def day_stats(self, day: str) -> dict[str, Any]:
        return self.timeline_for_day(day).get("stats", {
            "trackedMs": 0,
            "distractionMs": 0,
            "categories": [],
            "apps": [],
        })

    dayStats = day_stats

    def frame_by_id(self, frame_id: int) -> Optional[dict[str, Any]]:
        if self.store is None:
            return None
        return self.store.frame_by_id(frame_id)  # type: ignore[return-value]

    frameById = frame_by_id

    def frames_in_range(self, start_ms: int, end_ms: int) -> list[dict[str, Any]]:
        if self.store is None:
            return []
        return self.store.frames_in_range(start_ms, end_ms)  # type: ignore[return-value]

    framesInRange = frames_in_range

    def status(self) -> dict[str, Any]:
        today = day_key_for(int(time.time() * 1000))
        tz_name = time.tzname[time.daylight] if (time.daylight and len(time.tzname) > 1) else time.tzname[0]

        if self.store is None:
            return {
                "running": True,
                "paused": self._capture_paused,
                "captureEnabled": self.config.get("captureEnabled", True),
                "captureIntervalSeconds": self.config.get("captureIntervalSeconds", 30),
                "analysisIntervalMinutes": self.config.get("analysisIntervalMinutes", 15),
                "retentionDays": self.config.get("retentionDays", 14),
                "nodeId": self.config.get("nodeId"),
                "day": today,
                "today": today,
                "pendingFrames": 0,
                "analysisRunning": False,
                "todayCards": 0,
                "visionModelSource": "missing",
                "timeZone": tz_name,
            }

        store = self.store
        latest_batch = store.latest_batch()
        vision = self._resolve_vision_model()

        v_ref = vision.get("ref")
        vision_model_str = f"{v_ref['provider']}/{v_ref['model']}" if v_ref else None

        return {
            "running": True,
            "paused": self._capture_paused,
            "captureEnabled": self.config.get("captureEnabled", True),
            "capturePaused": self._capture_paused,
            "captureIntervalSeconds": self.config.get("captureIntervalSeconds", 30),
            "analysisIntervalMinutes": self.config.get("analysisIntervalMinutes", 15),
            "retentionDays": self.config.get("retentionDays", 14),
            "nodeId": self._cached_node["nodeId"] if self._cached_node else self.config.get("nodeId"),
            "nodeName": self._cached_node.get("displayName") if self._cached_node else None,
            "lastCaptureAtMs": self._last_capture_at_ms,
            "lastCaptureError": self._last_capture_error,
            "pendingFrames": store.count_unbatched_active_frames(),
            "analysisRunning": self._analysis_in_flight,
            "lastBatch": {
                "id": latest_batch["id"],
                "day": latest_batch["day"],
                "status": latest_batch["status"],
                "endMs": latest_batch["endMs"],
                "error": latest_batch.get("error"),
            }
            if latest_batch
            else None,
            "visionModel": vision_model_str,
            "visionModelSource": vision.get("source", "missing"),
            "today": today,
            "day": today,
            "todayCards": store.count_cards_for_day(today),
            "timeZone": tz_name,
        }

    def prune(self) -> None:
        if self.store is None:
            return
        cutoff = int(time.time() * 1000) - self.config.get("retentionDays", 14) * 24 * 60 * 60 * 1000
        removed = self.store.prune_frames(cutoff)
        if removed > 0 and hasattr(self.logger, "info"):
            self.logger.info(
                f"logbook: pruned {removed} frames older than {self.config.get('retentionDays', 14)}d"
            )


__all__ = [
    "ANALYSIS_TICK_MS",
    "CAPTURE_COMMANDS",
    "CAPTURE_FAILURE_PAUSE_TICKS",
    "CAPTURE_FAILURE_THRESHOLD",
    "JPEG_QUALITY",
    "LogbookService",
    "MODEL_MISSING_LOG_INTERVAL_MS",
    "MODEL_MISSING_MESSAGE",
    "PRUNE_TICK_MS",
    "STRUCTURED_MEDIA_PROVIDER",
    "unwrap_invoke_payload",
]
