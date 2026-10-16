import uuid
import time
from pathlib import Path
from typing import Any, Dict, Optional
from jarvis_sdk.plugin_state import KeyedStore, OpenKeyedStoreOptions


class DiffArtifactStore:
    def __init__(self, root_dir: str):
        options = OpenKeyedStoreOptions(root=Path(root_dir), name="diffs", lease_ms=30_000)
        self.store = KeyedStore(options)

    async def create_artifact(
        self, html: str, title: Optional[str], input_kind: str, ttl_ms: int = 1800000
    ) -> Dict[str, Any]:
        artifact_id = uuid.uuid4().hex[:10]
        token = uuid.uuid4().hex[:24]
        now = int(time.time() * 1000)

        metadata = {
            "version": 1,
            "kind": "viewer",
            "title": title or "",
            "inputKind": input_kind,
            "html": html,
            "createdAt": now,
            "expiresAt": now + ttl_ms,
        }

        self.store.write(artifact_id, metadata)

        return {
            "id": artifact_id,
            "token": token,
            "viewerPath": f"/plugins/diffs/view/{artifact_id}/{token}",
            "title": title or "",
            "inputKind": input_kind,
            "fileCount": 1,
        }

    async def read_authorized_viewer(
        self, artifact_id: str, token: str
    ) -> Optional[Dict[str, Any]]:
        metadata = self.store.read(artifact_id)
        if not metadata:
            return None

        now = int(time.time() * 1000)
        if now > metadata.get("expiresAt", 0):
            self.store.delete(artifact_id)
            return None

        return {
            "artifact": {
                "title": metadata.get("title", ""),
                "inputKind": metadata.get("inputKind", ""),
            },
            "html": metadata.get("html", ""),
        }

    async def create_standalone_file_artifact(
        self, format: str = "png", ttl_ms: int = 1800000
    ) -> Dict[str, Any]:
        artifact_id = uuid.uuid4().hex[:10]
        now = int(time.time() * 1000)

        metadata = {
            "version": 1,
            "kind": "rendered_file",
            "format": format,
            "createdAt": now,
            "expiresAt": now + ttl_ms,
        }

        self.store.write(artifact_id, metadata)

        # We will save the file in the same directory as the store for simplicity
        artifact_dir = self.store._root / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(artifact_dir / f"preview.{format}")

        return {"id": artifact_id, "filePath": file_path, "expiresAt": metadata["expiresAt"]}

    async def complete_file_artifact(self, artifact_id: str) -> None:
        pass

    async def delete_file_artifact(self, artifact_id: str) -> None:
        self.store.delete(artifact_id)
