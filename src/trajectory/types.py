"""jarvis.trajectory.types — Trajectory types.

OpenClaw parity: mirrors ``openclaw-main/src/trajectory/types.ts``.
"""
from typing import Any, Dict, List, Literal, Optional, TypedDict

TrajectoryEventSource = Literal["runtime", "transcript", "export"]


class TrajectoryToolDefinition(TypedDict, total=False):
    """Serializes tool definition captured with compiled context events."""
    name: str
    description: Optional[str]
    parameters: Optional[Any]


class TrajectoryEvent(TypedDict, total=False):
    """Versioned event envelope for runtime and transcript-derived trajectory rows."""
    traceSchema: Literal["openclaw-trajectory"]
    schemaVersion: Literal[1]
    traceId: str
    source: TrajectoryEventSource
    type: str
    ts: str
    seq: int
    sourceSeq: Optional[int]
    sessionId: str
    sessionKey: Optional[str]
    runId: Optional[str]
    workspaceDir: Optional[str]
    provider: Optional[str]
    modelId: Optional[str]
    modelApi: Optional[str]
    entryId: Optional[str]
    parentEntryId: Optional[str]
    data: Optional[Dict[str, Any]]


class TrajectoryBundleWarning(TypedDict, total=False):
    """Parse/export warnings are grouped in the manifest with sample row numbers."""
    source: Literal["session", "runtime"]
    code: Literal[
        "invalid-session-json",
        "invalid-session-row",
        "incomplete-session-branch",
        "cyclic-session-branch",
        "invalid-runtime-json",
        "invalid-runtime-event",
    ]
    count: int
    rows: List[int]
    message: str


class TrajectoryBundleManifestContent(TypedDict):
    path: str
    mediaType: str
    bytes: int


class TrajectoryBundleManifestSourceFiles(TypedDict, total=False):
    session: str
    runtime: Optional[str]


class TrajectoryBundleManifest(TypedDict, total=False):
    """Bundle manifest written beside events.jsonl in trajectory exports."""
    traceSchema: Literal["openclaw-trajectory"]
    schemaVersion: Literal[1]
    generatedAt: str
    traceId: str
    sessionId: str
    sessionKey: Optional[str]
    workspaceDir: str
    leafId: Optional[str]
    eventCount: int
    runtimeEventCount: int
    transcriptEventCount: int
    sourceFiles: TrajectoryBundleManifestSourceFiles
    contents: Optional[List[TrajectoryBundleManifestContent]]
    supplementalFiles: Optional[List[str]]
    warnings: Optional[List[TrajectoryBundleWarning]]
