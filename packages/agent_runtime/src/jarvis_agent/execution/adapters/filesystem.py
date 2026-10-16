"""Atomic Filesystem Execution Adapter for Track 3.2.

Provides hardened filesystem operations:
- Path canonicalization and directory traversal boundary checks.
- Atomic write with temp file, fsync, and atomic rename (os.replace).
- Pre- and post-write SHA-256 cryptographic digests for tamper-evident provenance.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import tempfile

from jarvis_agent.execution.adapters.base import (
    AdapterExecutionOutput,
    BaseExecutionAdapter,
)
from jarvis_agent.execution.sandbox.host_adapter import SandboxContext
from jarvis_agent.orchestration.models.command import ExecutionCommand

logger = logging.getLogger(__name__)


class FilesystemAdapter(BaseExecutionAdapter):
    """Execution adapter for filesystem operations."""

    def __init__(self, allowed_roots: list[str | Path] | None = None) -> None:
        self.allowed_roots = [
            Path(r).resolve() for r in (allowed_roots or [Path.cwd()])
        ]

    @property
    def adapter_name(self) -> str:
        return "filesystem"

    def can_handle(self, capability_id: str) -> bool:
        return capability_id in (
            "filesystem.read",
            "filesystem.write",
            "filesystem.delete",
        )

    def _resolve_and_check_path(self, raw_path: str) -> tuple[Path | None, str | None]:
        """Canonicalize path and verify it sits within allowed roots."""
        try:
            target = Path(raw_path).resolve()
        except Exception as ex:
            return None, f"Invalid path '{raw_path}': {ex}"

        # If allowed_roots configured, enforce root containment
        if self.allowed_roots:
            is_contained = any(
                target == root or root in target.parents for root in self.allowed_roots
            )
            if not is_contained:
                return None, f"Path '{target}' is outside allowed roots: {self.allowed_roots}"

        return target, None

    def execute(
        self,
        command: ExecutionCommand,
        sandbox_ctx: SandboxContext | None = None,
    ) -> AdapterExecutionOutput:
        args = command.arguments
        raw_path = str(args.get("path", ""))
        target_path, err = self._resolve_and_check_path(raw_path)
        if not target_path or err:
            return AdapterExecutionOutput(
                success=False,
                error_message=err or "Path resolution failed",
            )

        if command.capability_target == "filesystem.read":
            return self._handle_read(target_path)
        elif command.capability_target == "filesystem.write":
            content = str(args.get("content", ""))
            overwrite = bool(args.get("overwrite", True))
            return self._handle_write(target_path, content, overwrite)
        elif command.capability_target == "filesystem.delete":
            return self._handle_delete(target_path)
        else:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Unsupported capability '{command.capability_target}' in FilesystemAdapter",
            )

    def _handle_read(self, path: Path) -> AdapterExecutionOutput:
        if not path.is_file():
            return AdapterExecutionOutput(
                success=False,
                error_message=f"File not found: {path}",
            )
        try:
            raw_bytes = path.read_bytes()
            content = raw_bytes.decode("utf-8", errors="replace")
            sha256 = hashlib.sha256(raw_bytes).hexdigest()
            stat = path.stat()
            return AdapterExecutionOutput(
                success=True,
                output_data={"content": content, "size_bytes": len(raw_bytes)},
                raw_evidence={
                    "path": str(path),
                    "sha256": sha256,
                    "size_bytes": len(raw_bytes),
                    "mtime": stat.st_mtime,
                },
            )
        except Exception as ex:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Failed to read file {path}: {ex}",
            )

    def _handle_write(self, path: Path, content: str, overwrite: bool) -> AdapterExecutionOutput:
        pre_sha256: str | None = None
        if path.exists():
            if not overwrite:
                return AdapterExecutionOutput(
                    success=False,
                    error_message=f"File already exists and overwrite=False: {path}",
                )
            if path.is_file():
                try:
                    pre_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                except Exception:
                    pass

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            encoded = content.encode("utf-8")
            post_sha256 = hashlib.sha256(encoded).hexdigest()

            # Atomic write pattern: write to temp file in target directory, fsync, then replace
            temp_fd, temp_path_str = tempfile.mkstemp(
                dir=str(path.parent), prefix=".tmp_jarvis_"
            )
            temp_path = Path(temp_path_str)
            try:
                with open(temp_fd, "wb") as f:
                    f.write(encoded)
                    f.flush()
                    os.fsync(f.fileno())

                # Atomic swap
                os.replace(temp_path, path)
            except Exception:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)
                raise

            stat = path.stat()
            return AdapterExecutionOutput(
                success=True,
                output_data={"written_bytes": len(encoded), "path": str(path)},
                raw_evidence={
                    "path": str(path),
                    "pre_sha256": pre_sha256,
                    "post_sha256": post_sha256,
                    "size_bytes": len(encoded),
                    "mtime": stat.st_mtime,
                },
            )
        except Exception as ex:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Failed to write file {path}: {ex}",
            )

    def _handle_delete(self, path: Path) -> AdapterExecutionOutput:
        if not path.exists():
            return AdapterExecutionOutput(
                success=False,
                error_message=f"File not found: {path}",
            )
        try:
            pre_sha256 = None
            if path.is_file():
                pre_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            path.unlink()
            return AdapterExecutionOutput(
                success=True,
                output_data={"deleted_path": str(path)},
                raw_evidence={
                    "path": str(path),
                    "pre_sha256": pre_sha256,
                    "deleted": True,
                },
            )
        except Exception as ex:
            return AdapterExecutionOutput(
                success=False,
                error_message=f"Failed to delete file {path}: {ex}",
            )


__all__ = ["FilesystemAdapter"]
