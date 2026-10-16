"""jarvis.trajectory.export — Trajectory export and manifest builder.

OpenClaw parity: mirrors ``openclaw-main/src/trajectory/export.ts``.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from src.trajectory.runtime_store_sqlite import load_sqlite_trajectory_runtime_event_rows_sync
from src.trajectory.types import TrajectoryBundleManifest


def resolve_os_summary() -> str:
    import platform
    return f"{platform.system()} {platform.release()} {platform.machine()}"


def build_trajectory_run_metadata(params: Dict[str, Any]) -> Dict[str, Any]:
    """Gather diagnostic host/plugin metadata."""
    import datetime

    
    return {
        "capturedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "harness": {
            "type": "jarvis",
            "name": "Jarvis",
            "version": "1.0.0",
            "os": resolve_os_summary(),
        },
        "plugins": {
            "source": "jarvis",
            "entries": []
        }
    }


def export_trajectory_bundle(
    session_id: str,
    store_path: str,
    output_dir: str,
    env: Optional[Dict[str, str]] = None
) -> str:
    """Export the runtime events to a JSONL file + manifest.
    Returns the path to the written bundle manifest.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    events_jsonl_path = out_path / f"{session_id}.events.jsonl"
    manifest_path = out_path / f"{session_id}.manifest.json"
    
    rows = load_sqlite_trajectory_runtime_event_rows_sync({
        "sessionId": session_id,
        "storePath": store_path,
        "env": env
    })
    
    event_count = 0
    with events_jsonl_path.open("w", encoding="utf-8") as f:
        for row in rows:
            event = row["event"]
            f.write(json.dumps(event) + "\n")
            event_count += 1
            
    manifest: TrajectoryBundleManifest = {
        "traceSchema": "openclaw-trajectory",
        "schemaVersion": 1,
        "generatedAt": build_trajectory_run_metadata({}).get("capturedAt", ""),
        "traceId": "t-123",
        "sessionId": session_id,
        "sessionKey": None,
        "workspaceDir": "",
        "leafId": None,
        "eventCount": event_count,
        "runtimeEventCount": event_count,
        "transcriptEventCount": 0,
        "sourceFiles": {
            "session": store_path,
            "runtime": store_path
        },
        "contents": [
            {
                "path": events_jsonl_path.name,
                "mediaType": "application/x-ndjson",
                "bytes": events_jsonl_path.stat().st_size
            }
        ]
    }
    
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    return str(manifest_path)
