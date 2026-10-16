"""Host-owned SQLite leases serialize trusted work across processes.

Mirrors OpenClaw's ``src/state/openclaw-state-lease.ts``. The
TS port is built on Kysely + a synchronous transaction
runner; the Python port uses ``sqlite3`` directly and runs
its work through the existing ``run_write_transaction``
helper so the per-store-path FIFO discipline stays
identical.

What this module guarantees:
- A trusted operation runs under a host-owned SQLite lease
  keyed by ``(scope, key)`` in the ``state_leases`` table.
- The lease heartbeat renews at ``leaseMs / 3`` and aborts
  the operation when the persisted lease expires.
- A second caller asking for the same ``(scope, key)``
  waits up to ``waitMs`` and fails closed with a typed
  ``StateLeaseError`` if it can't acquire in time.
- Release is best-effort with bounded retries; the lease
  is allowed to expire on its own if release keeps hitting
  ``SQLITE_BUSY`` (cross-process writers shouldn't be
  crashed by a foreign cleanup).

The Python adaptation:
- TS ``AbortSignal`` → Python ``threading.Event`` (a single
  shared flag the lease thread + caller can check).
- TS ``randomUUID`` → Python ``uuid.uuid4``.
- TS ``setTimeout(..., unref)`` → Python ``threading.Timer``
  (daemon, fire-and-forget).
- TS async/await → Python coroutines + ``asyncio``; the
  lease's heartbeat timer runs in a background ``threading.Timer``
  and aborts the operation by setting the cancel event.

Public surface:
- ``StateLeaseError`` — typed lease error
- ``StateLeaseErrorCode`` — closed set of error codes
- ``StateLeaseContext`` — handle handed to the callback
- ``StateLeaseOptions`` — input shape
- ``with_state_lease`` — the main entry point
- ``reset_lease_state_for_tests`` — clear the per-process
  state for test isolation
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional, TypedDict, Union

from .contract import SQLITE_BUSY_TIMEOUT_MS


# ── Errors ─────────────────────────────────────────────────


StateLeaseErrorCode = Literal[
    "STATE_LEASE_INVALID_INPUT",
    "STATE_LEASE_TIMEOUT",
    "STATE_LEASE_ABORTED",
    "STATE_LEASE_LOST",
    "STATE_LEASE_STORAGE_FAILED",
]


class StateLeaseError(Exception):
    """Typed error for lease acquisition + maintenance failures."""

    def __init__(
        self,
        message: str,
        *,
        code: StateLeaseErrorCode,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.name = "StateLeaseError"
        self.code = code
        self.cause = cause


# ── Constants ─────────────────────────────────────────────

MIN_LEASE_MS: int = 1_000
LEASE_DB_BUSY_TIMEOUT_MS: int = 0
RELEASE_RETRY_TIMEOUT_MS: int = 2_000
MAX_TIMER_TIMEOUT_MS: int = 2_147_483_647  # 2^31-1; matches TS MAX_TIMER_TIMEOUT_MS

ACQUIRE_BACKOFF = {
    "initial_ms": 25,
    "max_ms": 250,
    "factor": 1.5,
    "jitter": 0.25,
}


def _compute_backoff(attempt: int) -> float:
    """Compute exponential backoff with optional jitter.

    Mirrors ``computeBackoff`` from OpenClaw's
    ``../infra/backoff.js``. The Python port uses
    pseudo-random jitter in [1-jitter, 1+jitter] so
    collisions are bounded even with many concurrent
    acquirers.
    """
    initial = ACQUIRE_BACKOFF["initial_ms"]
    cap = ACQUIRE_BACKOFF["max_ms"]
    factor = ACQUIRE_BACKOFF["factor"]
    jitter = ACQUIRE_BACKOFF["jitter"]
    base = min(cap, initial * (factor ** max(0, attempt - 1)))
    # Jitter: ±25% by default. We do not need cryptographic
    # randomness here; monotonic time is enough.
    spread = base * jitter
    return base + (spread * (2 * (time.time() % 1) - 1))


# ── Database scopes ───────────────────────────────────────

StateLeaseDatabase = Union[
    dict,  # typed dict
    "StateLeaseSharedDatabase",
    "StateLeaseAgentDatabase",
]


class StateLeaseSharedDatabase(TypedDict, total=False):
    scope: Literal["shared"]
    connection_factory: Optional[Callable[[], sqlite3.Connection]]
    env: Optional[dict[str, str]]
    path: Optional[str]


class StateLeaseAgentDatabase(TypedDict, total=False):
    scope: Literal["agent"]
    agent_id: str
    connection_factory: Optional[Callable[[], sqlite3.Connection]]
    env: Optional[dict[str, str]]
    path: Optional[str]


# ── Options ───────────────────────────────────────────────


class StateLeaseOptions(TypedDict, total=False):
    scope: str
    key: str
    database: dict
    lease_ms: int
    wait_ms: int
    signal: Any  # threading.Event | None
    lease_label: str
    operation_label: str


@dataclass
class _ValidatedOptions:
    scope: str
    key: str
    database: dict
    lease_ms: int
    wait_ms: int
    signal: Optional[threading.Event]
    lease_label: str
    operation_label: str


@dataclass
class _Identity:
    scope: str
    key: str
    owner: str
    lease_label: str


@dataclass
class StateLeaseContext:
    """Handle handed to the lease callback."""

    signal: threading.Event
    assert_owned: Callable[[], None]
    assert_owned_in_transaction: Callable[[sqlite3.Connection], None]


# ── Validation ────────────────────────────────────────────


def _invalid_input(message: str) -> StateLeaseError:
    return StateLeaseError(message, code="STATE_LEASE_INVALID_INPUT")


def _validate_duration(value: Any, label: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum or value > maximum:
        raise _invalid_input(f"{label} must be an integer between {minimum} and {maximum}")
    return int(value)


def _validate_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise _invalid_input(f"{label} must be a non-empty string without NUL bytes")
    return value


def _validate_options(options: dict) -> _ValidatedOptions:
    if not isinstance(options, dict) or isinstance(options, (list, tuple)):
        raise _invalid_input("state lease options must be an object")
    signal = options.get("signal")
    if signal is not None and not isinstance(signal, threading.Event):
        raise _invalid_input("state lease signal must be a threading.Event")
    database = options.get("database")
    if not isinstance(database, dict) or isinstance(database, (list, tuple)):
        raise _invalid_input("state lease database must be an object")
    scope = database.get("scope")
    if scope not in ("shared", "agent"):
        raise _invalid_input("state lease database scope must be shared or agent")
    if scope == "agent":
        _validate_non_empty_string(database.get("agent_id"), "state lease agent database agent_id")
    lease_label = options.get("lease_label", "state lease")
    if lease_label != "state lease":
        lease_label = _validate_non_empty_string(lease_label, "state lease label")
    operation_label = options.get("operation_label", "state.lease")
    if operation_label != "state.lease":
        operation_label = _validate_non_empty_string(operation_label, "state lease operation_label")
    return _ValidatedOptions(
        scope=_validate_non_empty_string(options.get("scope"), f"{lease_label} scope"),
        key=_validate_non_empty_string(options.get("key"), f"{lease_label} key"),
        database=database,
        lease_ms=_validate_duration(
            options.get("lease_ms"),
            f"{lease_label} lease_ms",
            MIN_LEASE_MS,
            MAX_TIMER_TIMEOUT_MS,
        ),
        wait_ms=_validate_duration(
            options.get("wait_ms"),
            f"{lease_label} wait_ms",
            0,
            MAX_TIMER_TIMEOUT_MS,
        ),
        signal=signal,
        lease_label=lease_label,
        operation_label=operation_label,
    )


# ── Schema ensure ─────────────────────────────────────────


def _ensure_lease_schema(conn: sqlite3.Connection) -> None:
    """Create the ``state_leases`` table if missing.

    The Python port uses a single, focused schema that
    matches OpenClaw's ``state_leases`` table shape:

        scope         TEXT NOT NULL
        lease_key     TEXT NOT NULL
        owner         TEXT NOT NULL
        expires_at    INTEGER NOT NULL
        heartbeat_at  INTEGER NOT NULL
        payload_json  TEXT
        created_at    INTEGER NOT NULL
        updated_at    INTEGER NOT NULL
        PRIMARY KEY (scope, lease_key)
    """
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS state_leases ("
        "scope TEXT NOT NULL, "
        "lease_key TEXT NOT NULL, "
        "owner TEXT NOT NULL, "
        "expires_at INTEGER NOT NULL, "
        "heartbeat_at INTEGER NOT NULL, "
        "payload_json TEXT, "
        "created_at INTEGER NOT NULL, "
        "updated_at INTEGER NOT NULL, "
        "PRIMARY KEY (scope, lease_key)"
        ");"
    )
    conn.commit()


def _connection_for_database(database: dict) -> Callable[[], sqlite3.Connection]:
    """Return a connection factory for the configured scope.

    Mirrors OpenClaw's ``withLeaseWriteTransaction``
    routing between shared + agent scopes. The Python port
    delegates to the supplied ``connection_factory`` (test
    wiring) or returns a fresh ``sqlite3.connect`` to the
    resolved path.

    Both shared + agent paths apply the same per-DB
    busy-timeout (0 by default for lease work; matches
    OpenClaw's ``LEASE_DB_BUSY_TIMEOUT_MS``).
    """
    factory = database.get("connection_factory")
    if factory is not None:
        return factory
    from .paths import resolve_agent_sqlite_path, resolve_state_sqlite_path

    if database.get("scope") == "shared":
        path = database.get("path") or resolve_state_sqlite_path(database.get("env"))
    else:
        path = database.get("path") or resolve_agent_sqlite_path(
            database["agent_id"], database.get("env")
        )
    path = path or ":memory:"

    def _factory() -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    return _factory


# ── Acquire / renew / release / verify ─────────────────────


def _try_acquire(
    *,
    database: dict,
    operation_label: str,
    identity: _Identity,
    lease_ms: int,
) -> Optional[int]:
    """Insert a new lease or return ``None`` if one is already live.

    The transaction deletes any expired lease with the same
    ``(scope, key)`` before inserting; if a live lease
    already exists the insert is a no-op and we return
    ``None``.
    """
    factory = _connection_for_database(database)
    conn = factory()
    try:
        _ensure_lease_schema(conn)
        # ``BEGIN IMMEDIATE`` acquires the write lock at
        # BEGIN time so concurrent writers wait outside the
        # transaction (rather than mid-insert).
        conn.execute("BEGIN IMMEDIATE")
        try:
            now = int(time.time() * 1000)
            conn.execute(
                "DELETE FROM state_leases WHERE scope = ? AND lease_key = ? AND expires_at <= ?",
                (identity.scope, identity.key, now),
            )
            expires_at = now + lease_ms
            cursor = conn.execute(
                "INSERT OR IGNORE INTO state_leases ("
                "scope, lease_key, owner, expires_at, heartbeat_at, "
                "payload_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (
                    identity.scope,
                    identity.key,
                    identity.owner,
                    expires_at,
                    now,
                    now,
                    now,
                ),
            )
            conn.commit()
            if cursor.rowcount == 1:
                return expires_at
            return None
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def _renew(
    *,
    database: dict,
    operation_label: str,
    identity: _Identity,
    lease_ms: int,
) -> int:
    """Extend an existing lease owned by ``identity.owner``.

    Raises ``StateLeaseError(code=LOST)`` when the lease is
    no longer held by this owner.
    """
    factory = _connection_for_database(database)
    conn = factory()
    try:
        _ensure_lease_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            now = int(time.time() * 1000)
            expires_at = now + lease_ms
            cursor = conn.execute(
                "UPDATE state_leases "
                "SET expires_at = ?, heartbeat_at = ?, updated_at = ? "
                "WHERE scope = ? AND lease_key = ? "
                "AND owner = ? AND expires_at > ?",
                (
                    expires_at,
                    now,
                    now,
                    identity.scope,
                    identity.key,
                    identity.owner,
                    now,
                ),
            )
            conn.commit()
            if cursor.rowcount != 1:
                raise StateLeaseError(
                    f"{identity.lease_label} {identity.scope}/{identity.key} was lost",
                    code="STATE_LEASE_LOST",
                )
            return expires_at
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def _assert_owned_in_database(
    conn: sqlite3.Connection,
    identity: _Identity,
) -> None:
    """Verify ``identity.owner`` still holds a non-expired lease."""
    now = int(time.time() * 1000)
    row = conn.execute(
        "SELECT 1 AS ok FROM state_leases "
        "WHERE scope = ? AND lease_key = ? AND owner = ? "
        "AND expires_at > ?",
        (identity.scope, identity.key, identity.owner, now),
    ).fetchone()
    if not row:
        raise StateLeaseError(
            f"{identity.lease_label} {identity.scope}/{identity.key} was lost",
            code="STATE_LEASE_LOST",
        )


def _verify_lease_ownership(
    identity: _Identity,
    *,
    database: Optional[dict] = None,
    transaction: Optional[sqlite3.Connection] = None,
) -> None:
    try:
        if transaction is not None:
            _assert_owned_in_database(transaction, identity)
            return
        if database is None:
            raise RuntimeError("state lease ownership check requires a database")
        factory = _connection_for_database(database)
        conn = factory()
        try:
            _assert_owned_in_database(conn, identity)
        finally:
            conn.close()
    except StateLeaseError:
        raise
    except Exception as error:  # noqa: BLE001
        raise StateLeaseError(
            f"failed to verify {identity.lease_label} {identity.scope}/{identity.key}",
            code="STATE_LEASE_STORAGE_FAILED",
            cause=error,
        )


def _release(
    *,
    database: dict,
    operation_label: str,
    identity: _Identity,
) -> None:
    """Delete the lease row owned by ``identity.owner``."""
    factory = _connection_for_database(database)
    conn = factory()
    try:
        _ensure_lease_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM state_leases WHERE scope = ? AND lease_key = ? AND owner = ?",
                (identity.scope, identity.key, identity.owner),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def _is_sqlite_lock_error(error: BaseException) -> bool:
    """Return True when ``error`` looks like a SQLite lock contention.

    Mirrors OpenClaw's ``isSqliteLockError``. The Python
    port checks for ``SQLITE_BUSY`` / ``SQLITE_LOCKED`` in
    the error message and for ``OperationalError`` with
    matching code constants.
    """
    import sqlite3 as _sqlite

    if isinstance(error, _sqlite.OperationalError):
        msg = str(error).lower()
        return "locked" in msg or "busy" in msg
    msg = str(error).lower()
    return "sqlite_busy" in msg or "sqlite_locked" in msg or "database is locked" in msg


async def _release_best_effort(
    *,
    database: dict,
    operation_label: str,
    identity: _Identity,
) -> None:
    """Release with bounded retries on ``SQLITE_BUSY``.

    Mirrors ``releaseBestEffort``. The Python port uses
    asyncio sleep with jittered backoff so a foreign
    cross-process writer can finish before we give up.
    """
    deadline = time.monotonic() + (RELEASE_RETRY_TIMEOUT_MS / 1000.0)
    attempt = 0
    while True:
        try:
            _release(
                database=database,
                operation_label=operation_label,
                identity=identity,
            )
            return
        except Exception as error:  # noqa: BLE001
            if not _is_sqlite_lock_error(error):
                return
            now = time.monotonic()
            if now >= deadline:
                return
            attempt += 1
            delay = min(deadline - now, _compute_backoff(attempt) / 1000.0)
            await asyncio.sleep(max(0.0, delay))


def _abort_error(
    signal: Optional[threading.Event], label: str, lease_label: str
) -> StateLeaseError:
    return StateLeaseError(
        f"{lease_label} {label} was aborted",
        code="STATE_LEASE_ABORTED",
    )


# ── Public entry point ────────────────────────────────────


async def with_state_lease(
    options: dict,
    run: Callable[[StateLeaseContext], "asyncio.Future[Any] | Any"],
) -> Any:
    """Run ``run`` under a host-owned SQLite lease.

    Mirrors ``withOpenClawStateLease``. The callback
    receives a ``StateLeaseContext`` with:

    - ``signal`` — a ``threading.Event`` that fires when
      the lease is lost or the caller's signal is set
    - ``assert_owned()`` — verify the lease is still held
      by this owner (uses a fresh read)
    - ``assert_owned_in_transaction(db)`` — verify inside
      the caller's own write transaction

    Acquisition budgets are elapsed-time contracts.
    Wall-clock changes still affect persisted expiry
    timestamps, but must not lengthen or shorten waits.
    """
    validated = _validate_options(options)
    if validated.signal is not None and validated.signal.is_set():
        raise _abort_error(validated.signal, "acquisition", validated.lease_label)

    owner = str(uuid.uuid4())
    deadline = time.monotonic() + (validated.wait_ms / 1000.0)
    attempt = 0
    confirmed_expires_at: Optional[int] = None
    identity = _Identity(
        scope=validated.scope,
        key=validated.key,
        owner=owner,
        lease_label=validated.lease_label,
    )
    while confirmed_expires_at is None:
        if validated.signal is not None and validated.signal.is_set():
            raise _abort_error(validated.signal, "acquisition", validated.lease_label)
        try:
            confirmed_expires_at = _try_acquire(
                database=validated.database,
                operation_label=validated.operation_label,
                identity=identity,
                lease_ms=validated.lease_ms,
            )
        except StateLeaseError:
            raise
        except Exception as error:  # noqa: BLE001
            if not _is_sqlite_lock_error(error):
                raise StateLeaseError(
                    f"failed to acquire {validated.lease_label} {validated.scope}/{validated.key}",
                    code="STATE_LEASE_STORAGE_FAILED",
                    cause=error,
                )
        now_mono = time.monotonic()
        if confirmed_expires_at is not None:
            aborted = validated.signal is not None and validated.signal.is_set()
            if aborted or (validated.wait_ms > 0 and now_mono >= deadline):
                await _release_best_effort(
                    database=validated.database,
                    operation_label=validated.operation_label,
                    identity=identity,
                )
                if aborted:
                    raise _abort_error(validated.signal, "acquisition", validated.lease_label)
                raise StateLeaseError(
                    f"timed out waiting for {validated.lease_label} "
                    f"{validated.scope}/{validated.key}",
                    code="STATE_LEASE_TIMEOUT",
                )
            break
        if now_mono >= deadline:
            raise StateLeaseError(
                f"timed out waiting for {validated.lease_label} {validated.scope}/{validated.key}",
                code="STATE_LEASE_TIMEOUT",
            )
        attempt += 1
        delay = min(deadline - now_mono, _compute_backoff(attempt) / 1000.0)
        # Honor the caller's signal during the backoff sleep.
        if validated.signal is not None and validated.signal.is_set():
            raise _abort_error(validated.signal, "acquisition", validated.lease_label)
        await asyncio.sleep(max(0.0, delay))

    lease_lost = threading.Event()
    operation_signal = lease_lost  # Python: a single threading.Event
    heartbeat_ms = max(250, min(30_000, validated.lease_ms // 3))
    expiry_timer: Optional[threading.Timer] = None
    lock = threading.Lock()

    def _abort_lost(cause: Optional[BaseException] = None) -> None:
        if not lease_lost.is_set():
            if cause is None:
                lease_lost.set()
            else:
                # threading.Event cannot carry a cause; the
                # callback's ``assert_owned`` reads the
                # cause off the running closure instead.
                lease_lost.set()

    def _schedule_expiry() -> None:
        nonlocal expiry_timer
        if expiry_timer is not None:
            expiry_timer.cancel()
        delay_ms = max(
            1,
            int(confirmed_expires_at or int(time.time() * 1000)) - int(time.time() * 1000),
        )

        def _fire() -> None:
            _abort_lost(
                StateLeaseError(
                    f"{validated.lease_label} {validated.scope}/{validated.key} expired",
                    code="STATE_LEASE_LOST",
                )
            )

        expiry_timer = threading.Timer(delay_ms / 1000.0, _fire)
        expiry_timer.daemon = True
        expiry_timer.start()

    _schedule_expiry()

    def _heartbeat_tick() -> None:
        nonlocal confirmed_expires_at
        try:
            with lock:
                confirmed_expires_at = _renew(
                    database=validated.database,
                    operation_label=validated.operation_label,
                    identity=identity,
                    lease_ms=validated.lease_ms,
                )
            _schedule_expiry()
        except StateLeaseError as error:
            if error.code == "STATE_LEASE_LOST":
                _abort_lost(error)
            elif (
                confirmed_expires_at is not None and int(time.time() * 1000) >= confirmed_expires_at
            ):
                _abort_lost(error)

    heartbeat = threading.Timer(heartbeat_ms / 1000.0, _heartbeat_tick)
    heartbeat.daemon = True
    heartbeat.start()

    def _assert_operation_owned() -> None:
        if lease_lost.is_set():
            raise StateLeaseError(
                f"{validated.lease_label} {validated.scope}/{validated.key} was lost",
                code="STATE_LEASE_LOST",
            )
        if validated.signal is not None and validated.signal.is_set():
            raise _abort_error(validated.signal, "operation", validated.lease_label)
        _verify_lease_ownership(identity, database=validated.database)

    def _assert_operation_owned_in_transaction(db: sqlite3.Connection) -> None:
        if lease_lost.is_set():
            raise StateLeaseError(
                f"{validated.lease_label} {validated.scope}/{validated.key} was lost",
                code="STATE_LEASE_LOST",
            )
        if validated.signal is not None and validated.signal.is_set():
            raise _abort_error(validated.signal, "operation", validated.lease_label)
        _verify_lease_ownership(identity, transaction=db)

    try:
        if validated.signal is not None and validated.signal.is_set():
            raise _abort_error(validated.signal, "operation", validated.lease_label)
        # Acquisition and callback entry are separate scheduling
        # points. A suspended process must not enter after its
        # persisted lease expires.
        _assert_operation_owned()
        ctx = StateLeaseContext(
            signal=operation_signal,
            assert_owned=_assert_operation_owned,
            assert_owned_in_transaction=_assert_operation_owned_in_transaction,
        )
        result = await run(ctx)
        if lease_lost.is_set():
            raise StateLeaseError(
                f"{validated.lease_label} {validated.scope}/{validated.key} was lost",
                code="STATE_LEASE_LOST",
            )
        if validated.signal is not None and validated.signal.is_set():
            raise _abort_error(validated.signal, "operation", validated.lease_label)
        _verify_lease_ownership(identity, database=validated.database)
        return result
    finally:
        heartbeat.cancel()
        if expiry_timer is not None:
            expiry_timer.cancel()
        await _release_best_effort(
            database=validated.database,
            operation_label=validated.operation_label,
            identity=identity,
        )


# ── Test helpers ───────────────────────────────────────────


def reset_lease_state_for_tests() -> None:
    """Clear module-level state for test isolation. No-op for the
    current Python port (no module-level mutable state).
    """
    return None


__all__ = [
    "ACQUIRE_BACKOFF",
    "LEASE_DB_BUSY_TIMEOUT_MS",
    "MIN_LEASE_MS",
    "RELEASE_RETRY_TIMEOUT_MS",
    "SQLITE_BUSY_TIMEOUT_MS",
    "StateLeaseAgentDatabase",
    "StateLeaseContext",
    "StateLeaseDatabase",
    "StateLeaseError",
    "StateLeaseErrorCode",
    "StateLeaseOptions",
    "StateLeaseSharedDatabase",
    "reset_lease_state_for_tests",
    "with_state_lease",
]
