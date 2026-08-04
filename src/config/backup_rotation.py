"""jarvis.config.backup_rotation — config backup ring rotation and maintenance.

OpenClaw parity: mirrors ``openclaw-main/src/config/backup-rotation.ts``.
"""
from __future__ import annotations

import os
from typing import Awaitable, Callable, Optional, Protocol


CONFIG_BACKUP_COUNT = 5


class BackupRotationFs(Protocol):
    async def unlink(self, path: str) -> None: ...
    async def rename(self, src: str, dst: str) -> None: ...
    async def chmod(self, path: str, mode: int) -> None: ...
    async def readdir(self, path: str) -> list: ...


class BackupMaintenanceFs(BackupRotationFs, Protocol):
    async def copy_file(self, src: str, dst: str) -> None: ...


async def rotate_config_backups(config_path: str, io_fs: BackupRotationFs) -> None:
    """Advance the config ``.bak`` ring before a new primary backup is copied in.

    Mirrors :func:`rotateConfigBackups`
    (``shared/config/backup-rotation.ts``).
    """
    if CONFIG_BACKUP_COUNT <= 1:
        return
    backup_base = f"{config_path}.bak"
    max_index = CONFIG_BACKUP_COUNT - 1
    try:
        await io_fs.unlink(f"{backup_base}.{max_index}")
    except Exception:
        pass
    for index in range(max_index - 1, 0, -1):
        try:
            await io_fs.rename(f"{backup_base}.{index}", f"{backup_base}.{index + 1}")
        except Exception:
            pass
    try:
        await io_fs.rename(backup_base, f"{backup_base}.1")
    except Exception:
        pass


async def harden_backup_permissions(config_path: str, io_fs: BackupRotationFs) -> None:
    """Set owner-only permissions on every backup slot when chmod exists."""
    if not hasattr(io_fs, "chmod"):
        return
    backup_base = f"{config_path}.bak"
    try:
        await io_fs.chmod(backup_base, 0o600)
    except Exception:
        pass
    for i in range(1, CONFIG_BACKUP_COUNT):
        try:
            await io_fs.chmod(f"{backup_base}.{i}", 0o600)
        except Exception:
            pass


async def clean_orphan_backups(config_path: str, io_fs: BackupRotationFs) -> None:
    """Prune stale ``.bak.*`` files that are outside the managed numbered ring."""
    if not hasattr(io_fs, "readdir"):
        return
    dir_name = os.path.dirname(config_path)
    base = os.path.basename(config_path)
    bak_prefix = f"{base}.bak."
    valid_suffixes = {str(i) for i in range(1, CONFIG_BACKUP_COUNT)}
    try:
        entries = await io_fs.readdir(dir_name)
    except Exception:
        return
    for entry in entries:
        if not entry.startswith(bak_prefix):
            continue
        suffix = entry[len(bak_prefix):]
        if suffix in valid_suffixes:
            continue
        try:
            await io_fs.unlink(os.path.join(dir_name, entry))
        except Exception:
            pass


class PreUpdateSnapshotFs(Protocol):
    async def write_file(self, path: str, content: str, **kwargs) -> None: ...
    async def read_file(self, path: str, encoding: str) -> str: ...
    def exists_sync(self, path: str) -> bool: ...


_pre_update_snapshots_written: set = set()


async def create_pre_update_config_snapshot(params: dict) -> None:
    """Capture the first on-disk config state for an update attempt.

    Mirrors :func:`createPreUpdateConfigSnapshot`
    (``shared/config/backup-rotation.ts``).
    """
    config_path = params["configPath"]
    fs = params["fs"]
    if not fs.exists_sync(config_path):
        return
    snapshot_key = os.path.abspath(config_path)
    if snapshot_key in _pre_update_snapshots_written:
        return
    _pre_update_snapshots_written.add(snapshot_key)
    snapshot_path = f"{config_path}.pre-update"
    try:
        content = await fs.read_file(config_path, "utf-8")
        await fs.write_file(snapshot_path, content, mode=0o600, flag="w", encoding="utf-8")
    except Exception:
        _pre_update_snapshots_written.discard(snapshot_key)


async def maintain_config_backups(config_path: str, io_fs: BackupMaintenanceFs) -> None:
    """Run rotation, primary copy, permission hardening, then orphan pruning."""
    await rotate_config_backups(config_path, io_fs)
    try:
        await io_fs.copy_file(config_path, f"{config_path}.bak")
    except Exception:
        pass
    await harden_backup_permissions(config_path, io_fs)
    await clean_orphan_backups(config_path, io_fs)


__all__ = [
    "CONFIG_BACKUP_COUNT",
    "rotate_config_backups",
    "harden_backup_permissions",
    "clean_orphan_backups",
    "create_pre_update_config_snapshot",
    "maintain_config_backups",
]
