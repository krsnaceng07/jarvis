"""Pre-reboot manifest builder and file inventory hasher.

Captures an authoritative inventory of all committed persistent files, their sizes,
and SHA-256 digests prior to reboot arming.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from jarvis_learning.persistence.boot_session import BootSessionIdentity
from jarvis_learning.persistence.models import PointerState
from jarvis_learning.persistence.transaction import RebootTransaction


@dataclasses.dataclass(frozen=True)
class FileInventoryEntry:
    """Individual file descriptor with relative path, size, and SHA-256 digest."""

    relative_path: str
    size_bytes: int
    sha256_digest: str
    durability_level: str = "OS_FLUSHED"
    is_committed: bool = True

    def __init__(
        self,
        relative_path: str,
        sha256_digest: str = "",
        size_bytes: int = 0,
        file_size_bytes: int | None = None,
        durability_level: str = "OS_FLUSHED",
        is_committed: bool = True,
        **extra: Any,
    ) -> None:
        object.__setattr__(self, "relative_path", relative_path)
        object.__setattr__(self, "sha256_digest", sha256_digest)
        actual_size = file_size_bytes if file_size_bytes is not None else size_bytes
        object.__setattr__(self, "size_bytes", actual_size)
        object.__setattr__(self, "durability_level", durability_level)
        object.__setattr__(self, "is_committed", is_committed)

    @property
    def file_size_bytes(self) -> int:
        return self.size_bytes

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "file_size_bytes": self.size_bytes,
            "sha256_digest": self.sha256_digest,
            "durability_level": self.durability_level,
            "is_committed": self.is_committed,
        }


@dataclasses.dataclass(frozen=True)
class PreRebootManifest:
    """Immutable baseline manifest captured prior to physical OS reboot."""

    transaction: RebootTransaction | None = None
    pre_boot_session: BootSessionIdentity | None = None
    committed_files: list[FileInventoryEntry] = dataclasses.field(default_factory=list)
    staging_files: list[FileInventoryEntry] = dataclasses.field(default_factory=list)
    active_pointer: PointerState | None = None
    manifest_digest: str = ""
    transaction_id: str = ""
    boot_session_id: str = ""
    manifest_version: str = "1.0.0"
    created_at_utc: str = ""
    manifest_signature: str = ""
    files: list[FileInventoryEntry] = dataclasses.field(default_factory=list)

    def __init__(
        self,
        transaction: RebootTransaction | None = None,
        pre_boot_session: BootSessionIdentity | None = None,
        committed_files: list[FileInventoryEntry] | None = None,
        staging_files: list[FileInventoryEntry] | None = None,
        active_pointer: PointerState | None = None,
        manifest_digest: str = "",
        transaction_id: str = "",
        boot_session_id: str = "",
        manifest_version: str = "1.0.0",
        created_at_utc: str = "",
        manifest_signature: str = "",
        files: list[FileInventoryEntry] | None = None,
        active_generation: int = 1,
        **extra: Any,
    ) -> None:
        c_files = list(committed_files or [])
        s_files = list(staging_files or [])
        all_files = list(files or [])

        if not c_files and all_files:
            c_files = [f for f in all_files if f.is_committed]
            s_files = [f for f in all_files if not f.is_committed]
        elif not all_files:
            all_files = c_files + s_files

        tx_id = transaction.transaction_id if transaction else (transaction_id or "TX_UNKNOWN")
        boot_id = (
            pre_boot_session.boot_session_id
            if pre_boot_session
            else (boot_session_id or "BOOT_UNKNOWN")
        )
        now_utc = created_at_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()

        object.__setattr__(self, "transaction", transaction)
        object.__setattr__(self, "pre_boot_session", pre_boot_session)
        object.__setattr__(self, "committed_files", c_files)
        object.__setattr__(self, "staging_files", s_files)
        object.__setattr__(self, "active_pointer", active_pointer)
        object.__setattr__(self, "manifest_digest", manifest_digest)
        object.__setattr__(self, "transaction_id", tx_id)
        object.__setattr__(self, "boot_session_id", boot_id)
        object.__setattr__(self, "manifest_version", manifest_version)
        object.__setattr__(self, "created_at_utc", now_utc)
        object.__setattr__(self, "manifest_signature", manifest_signature)
        object.__setattr__(self, "files", all_files)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "transaction_id": self.transaction_id,
            "boot_session_id": self.boot_session_id,
            "created_at_utc": self.created_at_utc,
            "manifest_digest": self.manifest_digest,
            "manifest_signature": self.manifest_signature,
            "committed_files": [f.to_dict() for f in self.committed_files],
            "staging_files": [f.to_dict() for f in self.staging_files],
            "files": [f.to_dict() for f in self.files],
        }
        if self.transaction:
            d["transaction"] = self.transaction.to_dict()
        if self.pre_boot_session:
            d["pre_boot_session"] = self.pre_boot_session.to_dict()
        if self.active_pointer:
            d["active_pointer"] = self.active_pointer.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PreRebootManifest:
        tx = RebootTransaction.from_dict(data["transaction"]) if data.get("transaction") else None
        boot = (
            BootSessionIdentity(**data["pre_boot_session"])
            if data.get("pre_boot_session")
            else None
        )

        committed_raw = data.get("committed_files") or [
            f for f in data.get("files", []) if f.get("is_committed", True)
        ]
        staging_raw = data.get("staging_files") or [
            f for f in data.get("files", []) if not f.get("is_committed", True)
        ]

        committed = [FileInventoryEntry(**f) for f in committed_raw]
        staging = [FileInventoryEntry(**f) for f in staging_raw]
        files = [FileInventoryEntry(**f) for f in data.get("files", [])] or (committed + staging)

        ptr = PointerState(**data["active_pointer"]) if data.get("active_pointer") else None
        digest = data.get("manifest_digest", "")

        return cls(
            transaction=tx,
            pre_boot_session=boot,
            committed_files=committed,
            staging_files=staging,
            active_pointer=ptr,
            manifest_digest=digest,
            transaction_id=data.get("transaction_id", tx.transaction_id if tx else ""),
            boot_session_id=data.get("boot_session_id", boot.boot_session_id if boot else ""),
            manifest_version=data.get("manifest_version", "1.0.0"),
            created_at_utc=data.get("created_at_utc", ""),
            manifest_signature=data.get("manifest_signature", ""),
            files=files,
        )


class PreRebootManifestBuilder:
    """Scans state directory, hashes all artifacts, and seals pre-reboot manifest."""

    MANIFEST_FILE = "pre_reboot_manifest.json"

    def __init__(
        self,
        transaction_id: str,
        boot_session_id: str,
        active_gen: int = 1,
    ) -> None:
        self.transaction_id = transaction_id
        self.boot_session_id = boot_session_id
        self.active_gen = active_gen
        self.files: list[FileInventoryEntry] = []

    def add_file(
        self,
        root_dir: Path,
        relative_path: str,
        sha256_digest: str,
        file_size_bytes: int,
        durability_level: str = "OS_FLUSHED",
        is_committed: bool = True,
    ) -> None:
        """Add file to manifest builder inventory."""
        self.files.append(
            FileInventoryEntry(
                relative_path=relative_path,
                sha256_digest=sha256_digest,
                size_bytes=file_size_bytes,
                durability_level=durability_level,
                is_committed=is_committed,
            )
        )

    def build(self) -> PreRebootManifest:
        """Build PreRebootManifest from added files."""
        committed = [f for f in self.files if f.is_committed]
        staging = [f for f in self.files if not f.is_committed]

        manifest = PreRebootManifest(
            transaction_id=self.transaction_id,
            boot_session_id=self.boot_session_id,
            committed_files=committed,
            staging_files=staging,
            files=self.files,
        )
        raw = json.dumps(manifest.to_dict(), sort_keys=True)
        manifest_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        return PreRebootManifest(
            transaction_id=self.transaction_id,
            boot_session_id=self.boot_session_id,
            committed_files=committed,
            staging_files=staging,
            files=self.files,
            manifest_digest=manifest_digest,
        )

    @classmethod
    def build_manifest(
        cls,
        tx: RebootTransaction,
        boot_session: BootSessionIdentity,
        root_dir: Path,
        active_pointer: PointerState | None = None,
    ) -> PreRebootManifest:
        """Scan committed and staging directories, hashing every file."""
        committed_entries: list[FileInventoryEntry] = []
        staging_entries: list[FileInventoryEntry] = []

        artifacts_dir = root_dir / "artifacts"
        staging_dir = root_dir / "_staging"

        if artifacts_dir.exists():
            for p in artifacts_dir.rglob("*"):
                if p.is_file():
                    rel = str(p.relative_to(root_dir)).replace("\\", "/")
                    digest = hashlib.sha256(p.read_bytes()).hexdigest()
                    committed_entries.append(
                        FileInventoryEntry(
                            relative_path=rel,
                            size_bytes=p.stat().st_size,
                            sha256_digest=digest,
                            is_committed=True,
                        )
                    )

        if staging_dir.exists():
            for p in staging_dir.glob("*"):
                if p.is_file():
                    rel = str(p.relative_to(root_dir)).replace("\\", "/")
                    digest = hashlib.sha256(p.read_bytes()).hexdigest()
                    staging_entries.append(
                        FileInventoryEntry(
                            relative_path=rel,
                            size_bytes=p.stat().st_size,
                            sha256_digest=digest,
                            is_committed=False,
                        )
                    )

        manifest = PreRebootManifest(
            transaction=tx,
            pre_boot_session=boot_session,
            transaction_id=tx.transaction_id,
            boot_session_id=boot_session.boot_session_id,
            committed_files=sorted(committed_entries, key=lambda x: x.relative_path),
            staging_files=sorted(staging_entries, key=lambda x: x.relative_path),
            active_pointer=active_pointer,
        )

        raw = json.dumps(manifest.to_dict(), sort_keys=True)
        manifest_digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        return PreRebootManifest(
            transaction=tx,
            pre_boot_session=boot_session,
            transaction_id=tx.transaction_id,
            boot_session_id=boot_session.boot_session_id,
            committed_files=manifest.committed_files,
            staging_files=manifest.staging_files,
            active_pointer=active_pointer,
            manifest_digest=manifest_digest,
        )

    @classmethod
    def save_manifest(cls, manifest: PreRebootManifest, root_dir: Path) -> Path:
        dest = root_dir / cls.MANIFEST_FILE
        dest.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
        return dest

    @classmethod
    def load_manifest(cls, root_dir: Path) -> PreRebootManifest | None:
        dest = root_dir / cls.MANIFEST_FILE
        if not dest.exists():
            return None
        try:
            data = json.loads(dest.read_text(encoding="utf-8"))
            return PreRebootManifest.from_dict(data)
        except Exception:
            return None


__all__ = ["FileInventoryEntry", "PreRebootManifest", "PreRebootManifestBuilder"]
