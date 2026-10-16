"""jarvis.trajectory.runtime — Trajectory runtime recorder.

OpenClaw parity: mirrors ``openclaw-main/src/trajectory/runtime.ts``.
"""
import json
from typing import Any, Dict, List, Optional, Set

from src.logging.secret_redaction_registry import redact_registered_secret_values
from src.trajectory.paths import (
    TRAJECTORY_RUNTIME_EVENT_MAX_BYTES,
)
from src.trajectory.runtime_store_sqlite import (
    create_sqlite_trajectory_runtime_sink,
)
from src.trajectory.types import TrajectoryEvent


TRAJECTORY_RUNTIME_DATA_STRING_MAX_CHARS = 32_768
TRAJECTORY_RUNTIME_DATA_ARRAY_MAX_ITEMS = 64
TRAJECTORY_RUNTIME_DATA_OBJECT_MAX_KEYS = 64
TRAJECTORY_RUNTIME_DATA_MAX_DEPTH = 6
TRAJECTORY_RUNTIME_OVERSIZE_PRESERVED_DATA_KEYS = {"usage", "promptCache"}


def truncated_trajectory_value(reason: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    res: Dict[str, Any] = {"truncated": True, "reason": reason}
    if details:
        res.update(details)
    return res


def limit_trajectory_payload_value(value: Any, depth: int = 0, seen: Optional[Set[int]] = None) -> Any:
    if seen is None:
        seen = set()

    if isinstance(value, str):
        if len(value) > TRAJECTORY_RUNTIME_DATA_STRING_MAX_CHARS:
            return truncated_trajectory_value(
                "trajectory-field-size-limit",
                {
                    "originalChars": len(value),
                    "limitChars": TRAJECTORY_RUNTIME_DATA_STRING_MAX_CHARS,
                },
            )
        return value

    if not isinstance(value, (dict, list)) or value is None:
        return value

    obj_id = id(value)
    if obj_id in seen:
        return truncated_trajectory_value("trajectory-circular-reference")

    if depth >= TRAJECTORY_RUNTIME_DATA_MAX_DEPTH:
        return truncated_trajectory_value(
            "trajectory-depth-limit",
            {"limitDepth": TRAJECTORY_RUNTIME_DATA_MAX_DEPTH},
        )

    seen.add(obj_id)

    if isinstance(value, list):
        limited: List[Any] = [
            limit_trajectory_payload_value(item, depth + 1, seen)
            for item in value[:TRAJECTORY_RUNTIME_DATA_ARRAY_MAX_ITEMS]
        ]
        if len(value) > TRAJECTORY_RUNTIME_DATA_ARRAY_MAX_ITEMS:
            limited.append(
                truncated_trajectory_value(
                    "trajectory-array-size-limit",
                    {
                        "originalLength": len(value),
                        "limitItems": TRAJECTORY_RUNTIME_DATA_ARRAY_MAX_ITEMS,
                    },
                )
            )
        seen.remove(obj_id)
        return limited

    if isinstance(value, dict):
        keys = list(value.keys())
        limited_dict: Dict[str, Any] = {}
        for key in keys[:TRAJECTORY_RUNTIME_DATA_OBJECT_MAX_KEYS]:
            limited_dict[key] = limit_trajectory_payload_value(value[key], depth + 1, seen)

        if len(keys) > TRAJECTORY_RUNTIME_DATA_OBJECT_MAX_KEYS:
            limited_dict["_truncated"] = truncated_trajectory_value(
                "trajectory-object-size-limit",
                {
                    "originalKeys": len(keys),
                    "limitKeys": TRAJECTORY_RUNTIME_DATA_OBJECT_MAX_KEYS,
                },
            )
        seen.remove(obj_id)
        return limited_dict

    seen.remove(obj_id)
    return value


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        return redact_registered_secret_values(value, lambda x: "<REDACTED>")
    if isinstance(value, list):
        return [redact_secrets(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_secrets(v) for k, v in value.items()}
    return value


def sanitize_trajectory_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    # We apply limit first, then redact secrets.
    limited = limit_trajectory_payload_value(data)
    redacted = redact_secrets(limited)
    return redacted


def truncate_oversized_trajectory_event(event: TrajectoryEvent, line: str) -> Optional[str]:
    bytes_len = len(line.encode("utf-8"))
    if bytes_len <= TRAJECTORY_RUNTIME_EVENT_MAX_BYTES:
        return line

    original_data = event.get("data") or {}
    original_data_keys = list(original_data.keys())
    preserved_data_keys: Set[str] = set()

    base_data = {
        "truncated": True,
        "originalBytes": bytes_len,
        "limitBytes": TRAJECTORY_RUNTIME_EVENT_MAX_BYTES,
        "reason": "trajectory-event-size-limit",
    }

    def build_truncated_event_line(include_dropped_fields: bool) -> Optional[str]:
        data: Dict[str, Any] = dict(base_data)
        for key in TRAJECTORY_RUNTIME_OVERSIZE_PRESERVED_DATA_KEYS:
            if key in preserved_data_keys:
                data[key] = original_data[key]
        if include_dropped_fields:
            dropped_fields = [k for k in original_data_keys if k not in preserved_data_keys]
            if dropped_fields:
                data["droppedFields"] = dropped_fields

        truncated_event = dict(event)
        truncated_event["data"] = data
        try:
            truncated = json.dumps(truncated_event)
            if len(truncated.encode("utf-8")) <= TRAJECTORY_RUNTIME_EVENT_MAX_BYTES:
                return truncated
        except Exception:
            pass
        return None

    best = build_truncated_event_line(True) or build_truncated_event_line(False)
    if not best:
        return None

    for key in TRAJECTORY_RUNTIME_OVERSIZE_PRESERVED_DATA_KEYS:
        if key not in original_data:
            continue
        preserved_data_keys.add(key)
        next_best = build_truncated_event_line(True) or build_truncated_event_line(False)
        if next_best:
            best = next_best
            continue
        preserved_data_keys.remove(key)

    return best


class TrajectoryRuntimeRecorder:
    def __init__(self, sink: Any, env_metadata: Dict[str, Any]):
        self.sink = sink
        self.env_metadata = env_metadata
        self.enabled = True
        self.seq = 1
        
        import uuid
        self.trace_id = str(uuid.uuid4())

    def record_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        if not self.sink:
            return

        ts = ""
        import datetime
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        event: TrajectoryEvent = {
            "traceSchema": "openclaw-trajectory",
            "schemaVersion": 1,
            "traceId": self.trace_id,
            "source": "runtime",
            "type": event_type,
            "ts": ts,
            "seq": self.seq,
            "sessionId": self.env_metadata.get("sessionId", ""),
            "sessionKey": self.env_metadata.get("sessionKey"),
            "runId": self.env_metadata.get("runId"),
            "workspaceDir": self.env_metadata.get("workspaceDir"),
            "provider": self.env_metadata.get("provider"),
            "modelId": self.env_metadata.get("modelId"),
            "modelApi": self.env_metadata.get("modelApi"),
        }
        self.seq += 1

        if data:
            event["data"] = sanitize_trajectory_payload(data)

        # Remove None values
        event = {k: v for k, v in event.items() if v is not None} # type: ignore
        
        line = json.dumps(event)
        truncated_line = truncate_oversized_trajectory_event(event, line)
        
        if truncated_line:
            self.sink.write(event, truncated_line)

    async def flush(self) -> None:
        if self.sink and hasattr(self.sink, "flush"):
            await self.sink.flush()


def create_trajectory_runtime_recorder(params: Dict[str, Any]) -> Optional[TrajectoryRuntimeRecorder]:
    sink = create_sqlite_trajectory_runtime_sink(params)
    if not sink:
        return None
    return TrajectoryRuntimeRecorder(sink, params)
