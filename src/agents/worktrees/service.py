from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import uuid
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import json
import logging
import sys
import shutil

from jarvis_state_core import StateDatabase, StateDatabaseOptions, run_write_transaction, table_exists, ensure_column


@dataclass(frozen=True)
class ManagedWorktreeRecord:
    id: str
    name: str
    repo_root: str
    path: Path
    branch: str
    base_ref: str
    owner_kind: str
    owner_id: str | None
    created_at: int
    last_active_at: int
    removed_at: int | None
    provisioned_paths: tuple[str, ...] = ()


class ManagedWorktreeService:
    _NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

    def __init__(self, *, db_path: Path | str, now: Callable[[], int] | None = None) -> None:
        self._db_path = str(db_path)
        self._state_db = StateDatabase(
            StateDatabaseOptions(
                connection_factory=lambda: sqlite3.connect(self._db_path, isolation_level=None),
            )
        )
        self._now = now

    def _current_time(self) -> int:
        if self._now is not None:
            return self._now()
        return int(__import__("time").time() * 1000)

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        # Use schema helpers to probe topology and apply additive changes
        if not table_exists(conn, "worktrees"):
            conn.execute(
                "CREATE TABLE IF NOT EXISTS worktrees ("
                "id TEXT PRIMARY KEY,"
                "name TEXT NOT NULL,"
                "repo_root TEXT NOT NULL,"
                "path TEXT NOT NULL,"
                "branch TEXT NOT NULL,"
                "base_ref TEXT NOT NULL,"
                "owner_kind TEXT NOT NULL,"
                "owner_id TEXT,"
                "created_at INTEGER NOT NULL,"
                "last_active_at INTEGER NOT NULL,"
                "removed_at INTEGER"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_worktrees_owner ON worktrees (owner_kind, owner_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_worktrees_removed_at ON worktrees (removed_at)"
            )
        # Add provisioned_paths_json column if missing (schema additive)
        ensure_column(conn, "worktrees", "provisioned_paths_json TEXT DEFAULT '[]'")
        # Add snapshots table if missing
        if not table_exists(conn, "snapshots"):
            conn.execute(
                "CREATE TABLE IF NOT EXISTS snapshots ("
                "id TEXT PRIMARY KEY,"
                "worktree_id TEXT NOT NULL,"
                "commit_hash TEXT NOT NULL,"
                "message TEXT,"
                "created_at INTEGER NOT NULL"
                ")"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_snapshots_worktree ON snapshots (worktree_id)"
            )

    def _bootstrap_schema(self) -> None:
        # Try bootstrapping via StateDatabase's connection first; if that fails
        # (some environments raise OperationalError on executescript), fall back
        # to a plain sqlite3 connection without the WAL/journal pragmas.
        try:
            conn = self._state_db.open()
            try:
                self._ensure_schema(conn)
                return
            finally:
                conn.close()
        except sqlite3.OperationalError:
            conn2 = sqlite3.connect(self._db_path)
            try:
                self._ensure_schema(conn2)
            finally:
                conn2.close()

    def _validate_name(self, name: str) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("worktree name must be a non-empty string")
        if not self._NAME_RE.fullmatch(name):
            raise ValueError(
                "worktree name must match OpenClaw's [a-z0-9][a-z0-9-]{0,63} contract"
            )

    def _branch_exists(self, repo_root: Path, branch: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def _run_git_worktree_add(self, repo_root: Path, worktree_root: Path, branch: str, base_ref: str) -> None:
        if self._branch_exists(repo_root, branch):
            args = ["git", "-C", str(repo_root), "worktree", "add", str(worktree_root), branch]
        else:
            args = ["git", "-C", str(repo_root), "worktree", "add", "-b", branch, str(worktree_root), base_ref]
        subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
        )

    def _read_worktreeinclude(self, repo_root: Path) -> list[str]:
        f = repo_root / ".worktreeinclude"
        if not f.exists():
            return []
        lines = [l.strip() for l in f.read_text(encoding="utf-8").splitlines()]
        return [l for l in lines if l and not l.startswith("#")]

    def _git_tracked_set(self, repo_root: Path) -> set[str]:
        # return set of tracked file paths (relative to repo_root)
        res = subprocess.run(["git", "-C", str(repo_root), "ls-files"], check=False, capture_output=True, text=True)
        if res.returncode != 0:
            return set()
        return set([p for p in res.stdout.splitlines() if p])

    def _provision_worktree(self, repo_root: Path, worktree_root: Path) -> list[str]:
        """Copy files matched by .worktreeinclude into the worktree path and return relative paths copied."""
        patterns = self._read_worktreeinclude(repo_root)
        if not patterns:
            return []
        tracked = self._git_tracked_set(repo_root)
        provisioned: list[str] = []
        import shutil

        for pat in patterns:
            # simple glob relative matching
            for p in repo_root.rglob(pat):
                if not p.is_file():
                    continue
                rel = str(p.relative_to(repo_root)).replace("\\", "/")
                if rel in tracked:
                    # skip tracked files
                    continue
                dest = worktree_root / p.relative_to(repo_root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                provisioned.append(rel)
        return provisioned

    def create_worktree(
        self,
        *,
        repo_root: Path,
        name: str,
        branch: str,
        owner_kind: str,
        owner_id: str | None = None,
        base_ref: str = "HEAD",
    ) -> ManagedWorktreeRecord:
        self._validate_name(name)
        repo_root = Path(repo_root).resolve()
        worktree_root = repo_root.parent / f"worktree-{name}-{uuid.uuid4().hex[:8]}"
        if worktree_root.exists():
            raise FileExistsError(f"worktree path already exists: {worktree_root}")

        self._run_git_worktree_add(repo_root, worktree_root, branch, base_ref)

        # Provision ignored/untracked files listed in .worktreeinclude
        provisioned = self._provision_worktree(repo_root, worktree_root)

        # Run repository-local setup hook if present
        setup_script = repo_root / ".openclaw" / "worktree-setup.sh"
        if setup_script.exists():
            _log = logging.getLogger("src.agents.worktrees")
            env: dict[str, str] = dict(os.environ)
            env["OPENCLAW_SOURCE_TREE_PATH"] = str(repo_root)
            env["OPENCLAW_WORKTREE_PATH"] = str(worktree_root)
            try:
                # Prefer running with Python interpreter if script hints python
                first_line = setup_script.read_text(encoding="utf-8").splitlines()[0] if setup_script.exists() else ""
                if first_line.startswith("#!") and "python" in first_line:
                    proc = subprocess.run([sys.executable, str(setup_script)], cwd=str(worktree_root), check=True, capture_output=True, text=True, env=env)
                else:
                    try:
                        proc = subprocess.run(["bash", str(setup_script)], cwd=str(worktree_root), check=True, capture_output=True, text=True, env=env)
                    except FileNotFoundError:
                        try:
                            proc = subprocess.run(["sh", str(setup_script)], cwd=str(worktree_root), check=True, capture_output=True, text=True, env=env)
                        except FileNotFoundError:
                            proc = subprocess.run(str(setup_script), cwd=str(worktree_root), check=True, capture_output=True, text=True, env=env, shell=True)
                _log.info("worktree setup hook output: %s", proc.stdout)
            except Exception as e:
                # Clean up the created worktree registration from the git repo
                try:
                    subprocess.run(["git", "-C", str(repo_root), "worktree", "remove", "--force", str(worktree_root)], check=False)
                except Exception:
                    # best-effort remove
                    try:
                        shutil.rmtree(worktree_root, ignore_errors=True)
                    except Exception:
                        pass
                raise RuntimeError(f"worktree setup hook failed: {e}") from e

        record = ManagedWorktreeRecord(
            id=str(uuid.uuid4()),
            name=name,
            repo_root=str(repo_root),
            path=worktree_root,
            branch=branch,
            base_ref=base_ref,
            owner_kind=owner_kind,
            owner_id=owner_id,
            created_at=self._current_time(),
            last_active_at=self._current_time(),
            removed_at=None,
            provisioned_paths=tuple(provisioned),
        )

        # bootstrap schema on a separate connection to avoid nested COMMITs
        try:
            self._bootstrap_schema()
        except Exception:
            logging.getLogger("src.agents.worktrees").warning("schema bootstrap failed; continuing without state DB")

        async def _write(conn: sqlite3.Connection) -> Any:
            conn.execute(
                "INSERT INTO worktrees (id, name, repo_root, path, branch, base_ref, owner_kind, owner_id, created_at, last_active_at, removed_at, provisioned_paths_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    record.id,
                    record.name,
                    record.repo_root,
                    str(record.path),
                    record.branch,
                    record.base_ref,
                    record.owner_kind,
                    record.owner_id,
                    record.created_at,
                    record.last_active_at,
                    record.removed_at,
                    json.dumps(list(record.provisioned_paths), separators=(",",":")),
                ],
            )
            return None

        asyncio.run(run_write_transaction(self._state_db, fn=_write))
        return record

    def list_worktrees(self) -> list[ManagedWorktreeRecord]:
        conn = self._state_db.open()
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT id, name, repo_root, path, branch, base_ref, owner_kind, owner_id, created_at, last_active_at, removed_at, provisioned_paths_json FROM worktrees WHERE removed_at IS NULL ORDER BY created_at DESC"
            ).fetchall()
            return [
                ManagedWorktreeRecord(
                    id=row[0],
                    name=row[1],
                    repo_root=row[2],
                    path=Path(row[3]),
                    branch=row[4],
                    base_ref=row[5],
                    owner_kind=row[6],
                    owner_id=row[7],
                    created_at=row[8],
                    last_active_at=row[9],
                    removed_at=row[10],
                    provisioned_paths=tuple(json.loads(row[11] or "[]")),
                )
                for row in rows
            ]
        finally:
            conn.close()

    def remove_worktree(self, worktree_id: str) -> None:
        record = self._get_worktree(worktree_id)
        if record is None:
            raise KeyError(f"unknown worktree: {worktree_id}")
        subprocess.run(
            ["git", "-C", str(record.repo_root), "worktree", "remove", "--force", str(record.path)],
            check=True,
            capture_output=True,
            text=True,
        )

        async def _write(conn: sqlite3.Connection) -> Any:
            conn.execute(
                "UPDATE worktrees SET removed_at = ? WHERE id = ?",
                [self._current_time(), worktree_id],
            )
            return None

        asyncio.run(run_write_transaction(self._state_db, fn=_write))

    def restore_worktree(self, worktree_id: str) -> ManagedWorktreeRecord:
        """Re-open a managed worktree after a lossless removal.

        The OpenClaw contract stores the worktree's persisted shape in the state DB
        and allows a restore to rebuild the checkout from that contractual identity.
        JARVIS keeps the API small but makes the capability public for callers and tests.
        """
        record = self._get_worktree(worktree_id)
        if record is None:
            raise KeyError(f"unknown worktree: {worktree_id}")
        if record.removed_at is None:
            return record

        repo_root = Path(record.repo_root).resolve()
        worktree_root = Path(record.path)
        if worktree_root.exists():
            # The path is present but stale; keep the lifecycle idempotent for the
            # calling host and skip the duplicate-create branch.
            pass
        else:
            self._run_git_worktree_add(repo_root, worktree_root, record.branch, record.base_ref)

        # bootstrap schema outside the write transaction
        self._bootstrap_schema()

        async def _write(conn: sqlite3.Connection) -> Any:
            conn.execute(
                "UPDATE worktrees SET removed_at = NULL, last_active_at = ? WHERE id = ?",
                [self._current_time(), worktree_id],
            )
            return None

        asyncio.run(run_write_transaction(self._state_db, fn=_write))
        restored = self._get_worktree(worktree_id)
        if restored is None:
            raise RuntimeError(f"failed to refresh restored worktree record: {worktree_id}")
        return restored

    def gc_collect(self, older_than_ms: int) -> list[str]:
        """Garbage-collect worktrees removed longer than `older_than_ms` milliseconds.

        Returns list of removed worktree ids.
        """
        cutoff = self._current_time() - older_than_ms
        conn = self._state_db.open()
        try:
            self._ensure_schema(conn)
            rows = conn.execute(
                "SELECT id, repo_root, path FROM worktrees WHERE removed_at IS NOT NULL AND removed_at < ?",
                (cutoff,),
            ).fetchall()
            removed_ids: list[str] = []
            for row in rows:
                wid, repo_root, path = row[0], row[1], row[2]
                # best-effort remove the worktree checkout
                try:
                    subprocess.run(["git", "-C", str(repo_root), "worktree", "remove", "--force", str(path)], check=False, capture_output=True, text=True)
                except Exception:
                    pass

                # ensure schema before transactional delete
                self._bootstrap_schema()

                async def _delete(conn_inner: sqlite3.Connection) -> Any:
                    conn_inner.execute("DELETE FROM worktrees WHERE id = ?", (wid,))
                    return None

                asyncio.run(run_write_transaction(self._state_db, fn=_delete))
                removed_ids.append(wid)
            return removed_ids
        finally:
            conn.close()

    def create_snapshot(self, worktree_id: str, *, message: str | None = None) -> dict[str, Any]:
        """Create a snapshot commit from the worktree contents and record it under refs/openclaw/snapshots/<id>.

        Returns metadata dict with keys: id, commit, message, created_at
        """
        record = self._get_worktree(worktree_id)
        if record is None:
            raise KeyError(f"unknown worktree: {worktree_id}")

        repo_root = Path(record.repo_root)
        worktree_root = Path(record.path)

        # Ensure index reflects worktree contents
        subprocess.run(["git", "-C", str(worktree_root), "add", "-A"], check=True, capture_output=True, text=True)

        # Write tree from worktree index
        r = subprocess.run(["git", "-C", str(worktree_root), "write-tree"], check=True, capture_output=True, text=True)
        tree_hash = r.stdout.strip()

        # Determine parent commit (try branch HEAD, fallback to HEAD)
        try:
            parent = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--verify", record.branch], check=True, capture_output=True, text=True).stdout.strip()
        except Exception:
            try:
                parent = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
            except Exception:
                parent = None

        commit_args = ["git", "-C", str(repo_root), "commit-tree", tree_hash]
        if parent:
            commit_args.extend(["-p", parent])
        msg = message or f"openclaw snapshot from worktree {worktree_id}"
        proc = subprocess.run(commit_args, input=msg, text=True, capture_output=True)
        if proc.returncode != 0:
            raise RuntimeError(f"failed to create commit-tree: {proc.stderr}")
        commit_hash = proc.stdout.strip()

        snapshot_id = str(uuid.uuid4())
        refname = f"refs/openclaw/snapshots/{snapshot_id}"
        # update ref
        subprocess.run(["git", "-C", str(repo_root), "update-ref", refname, commit_hash], check=True, capture_output=True, text=True)

        created_at = self._current_time()

        # attempt to persist snapshot metadata, but do not fail the snapshot
        # creation if the state DB is unavailable or schema bootstrap fails.
        try:
            self._bootstrap_schema()

            async def _write(conn: sqlite3.Connection) -> Any:
                conn.execute(
                    "INSERT INTO snapshots (id, worktree_id, commit_hash, message, created_at) VALUES (?, ?, ?, ?, ?)",
                    [snapshot_id, worktree_id, commit_hash, msg, created_at],
                )
                return None

            asyncio.run(run_write_transaction(self._state_db, fn=_write))
        except Exception:
            logging.getLogger("src.agents.worktrees").warning("failed to persist snapshot metadata, continuing")

        return {"id": snapshot_id, "commit": commit_hash, "message": msg, "created_at": created_at}

    def _get_worktree(self, worktree_id: str) -> ManagedWorktreeRecord | None:
        conn = self._state_db.open()
        try:
            self._ensure_schema(conn)
            row = conn.execute(
                "SELECT id, name, repo_root, path, branch, base_ref, owner_kind, owner_id, created_at, last_active_at, removed_at, provisioned_paths_json FROM worktrees WHERE id = ?",
                [worktree_id],
            ).fetchone()
            if row is None:
                return None
            return ManagedWorktreeRecord(
                id=row[0],
                name=row[1],
                repo_root=row[2],
                path=Path(row[3]),
                branch=row[4],
                base_ref=row[5],
                owner_kind=row[6],
                owner_id=row[7],
                created_at=row[8],
                last_active_at=row[9],
                removed_at=row[10],
                provisioned_paths=tuple(json.loads(row[11] or "[]")),
            )
        finally:
            conn.close()
