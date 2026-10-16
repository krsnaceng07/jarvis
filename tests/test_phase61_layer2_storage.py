"""Phase 6.1 — Layer 2 storage primitives.

These tests prove the Phase-6.1 storage-primitive
modules in ``src/agents/sessions/`` match the
OpenClaw source contract for:

- ``storage_lock`` — ``acquire_lock_sync_with_retry``,
  ``MAX_LOCK_ATTEMPTS``, ``LOCK_RETRY_DELAY_MS``
- ``http_dispatcher`` — ``DEFAULT_HTTP_IDLE_TIMEOUT_MS``,
  ``parse_http_idle_timeout_ms`` (string / number /
  ``"disabled"`` / invalid)
- ``exec`` — ``exec_command`` subprocess wrapper
  (stdout/stderr capture, exit code, kill on
  timeout, max_output_chars cap)
- ``bash_executor`` — ``BashExecutorOptions``,
  ``BashResult``, ``BashOperations`` protocol,
  ``execute_bash_with_operations``, output sanitizer
- ``keybindings`` — ``KEYBINDINGS`` table (41
  entries), ``KEYBINDING_NAME_MIGRATIONS`` (59),
  ``to_keybindings_config``,
  ``migrate_keybindings_config``,
  ``_order_keybindings_config``, ``KeybindingsManager``,
  ``load_raw_config``
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time

import pytest

# Project root on sys.path so ``src.agents.sessions``
# imports work without an editable install.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from src.agents.sessions import (  # noqa: E402
    DEFAULT_HTTP_IDLE_TIMEOUT_MS,
    DEFAULT_OUTPUT_LIMIT_CHARS,
    FORCE_KILL_GRACE_MS,
    KEYBINDINGS,
    KEYBINDING_NAME_MIGRATIONS,
    LOCK_RETRY_DELAY_MS,
    MAX_LOCK_ATTEMPTS,
    BashExecutorOptions,
    BashOperations,
    BashResult,
    KeybindingsManager,
    OutputAccumulator,
    acquire_lock_sync_with_retry,
    create_streaming_binary_output_sanitizer,
    exec_command,
    execute_bash_with_operations,
    is_legacy_keybinding_name,
    load_raw_config,
    migrate_keybindings_config,
    parse_http_idle_timeout_ms,
    to_keybindings_config,
)


# ── storage_lock ──────────────────────────────────────


class TestStorageLock:
    def test_constants_match_openclaw(self) -> None:
        """Mirrors ``storage-lock.ts:3-4``."""
        assert MAX_LOCK_ATTEMPTS == 10
        assert LOCK_RETRY_DELAY_MS == 20

    def test_basic_acquire_release(self, tmp_path) -> None:
        """Mirrors the happy path of
        ``acquireLockSyncWithRetry``
        (``storage-lock.ts:6-21``)."""
        lock_path = str(tmp_path / "test.lock")
        unlock = acquire_lock_sync_with_retry(lock_path)
        # The file was created.
        assert os.path.exists(lock_path)
        # Releasing the lock does not raise.
        unlock()
        # Calling again on a fresh lock works.
        unlock2 = acquire_lock_sync_with_retry(lock_path)
        unlock2()

    def test_concurrent_acquire_eventually_unblocks(
        self, tmp_path
    ) -> None:
        """Two ``acquire`` calls on the same path —
        the second waits for the first to release."""
        lock_path = str(tmp_path / "concurrent.lock")
        unlock1 = acquire_lock_sync_with_retry(lock_path)
        # Schedule a release in a background thread
        # after a short delay.
        def _release() -> None:
            time.sleep(0.05)
            unlock1()

        t = threading.Thread(target=_release, daemon=True)
        t.start()
        # The second acquire must wait ~50ms (well
        # under the 10-attempt * 20ms = 200ms total
        # budget) and then succeed.
        start = time.monotonic()
        unlock2 = acquire_lock_sync_with_retry(lock_path)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.04, f"acquire returned too fast: {elapsed}s"
        assert elapsed < 0.5, f"acquire took too long: {elapsed}s"
        unlock2()
        t.join(timeout=1)

    def test_unlock_idempotent(self, tmp_path) -> None:
        """Calling ``unlock`` twice is a no-op
        (matches the OpenClaw source's
        ``proper-lockfile`` unlock semantics)."""
        lock_path = str(tmp_path / "idempotent.lock")
        unlock = acquire_lock_sync_with_retry(lock_path)
        unlock()
        # Second call must not raise.
        unlock()


# ── http_dispatcher ───────────────────────────────────


class TestHttpDispatcher:
    def test_default_is_5_minutes(self) -> None:
        """Mirrors ``DEFAULT_HTTP_IDLE_TIMEOUT_MS = 300_000``
        (``http-dispatcher.ts:8``)."""
        assert DEFAULT_HTTP_IDLE_TIMEOUT_MS == 300_000

    def test_disabled_string_returns_zero(self) -> None:
        """Mirrors the ``"disabled"`` sentinel branch
        (``http-dispatcher.ts:13-15``)."""
        for v in ("disabled", "DISABLED", "Disabled", "  disabled  "):
            assert parse_http_idle_timeout_ms(v) == 0, v

    def test_empty_string_returns_none(self) -> None:
        """Mirrors the empty-string branch
        (``http-dispatcher.ts:17-19``)."""
        assert parse_http_idle_timeout_ms("") is None
        assert parse_http_idle_timeout_ms("   ") is None

    def test_numeric_string_returns_int(self) -> None:
        """Mirrors the strict-integer parse
        (``http-dispatcher.ts:20``)."""
        assert parse_http_idle_timeout_ms("0") == 0
        assert parse_http_idle_timeout_ms("1000") == 1000
        assert parse_http_idle_timeout_ms("300000") == 300_000

    def test_non_digit_string_returns_none(self) -> None:
        assert parse_http_idle_timeout_ms("abc") is None
        assert parse_http_idle_timeout_ms("-1") is None
        assert parse_http_idle_timeout_ms("1.5") is None
        assert parse_http_idle_timeout_ms("1e3") is None

    def test_number_input(self) -> None:
        assert parse_http_idle_timeout_ms(0) == 0
        assert parse_http_idle_timeout_ms(1500) == 1500
        assert parse_http_idle_timeout_ms(1500.7) == 1500  # floor
        assert parse_http_idle_timeout_ms(0.5) == 0

    def test_invalid_number_returns_none(self) -> None:
        assert parse_http_idle_timeout_ms(-1) is None
        assert parse_http_idle_timeout_ms(float("nan")) is None
        assert parse_http_idle_timeout_ms(float("inf")) is None

    def test_bool_returns_none(self) -> None:
        # Booleans are a subtype of ``int`` in Python;
        # the OpenClaw source's ``typeof !== "number"``
        # excludes booleans explicitly. Match that.
        assert parse_http_idle_timeout_ms(True) is None
        assert parse_http_idle_timeout_ms(False) is None

    def test_other_types_return_none(self) -> None:
        assert parse_http_idle_timeout_ms(None) is None
        assert parse_http_idle_timeout_ms([]) is None
        assert parse_http_idle_timeout_ms({}) is None


# ── exec ──────────────────────────────────────────────


def _python_executable() -> str:
    """Return the path to the running Python
    interpreter. Used as a ``command`` for
    ``exec_command`` since it's available on every
    test host and behaves predictably.
    """
    return sys.executable


class TestExec:
    def test_constants_match_openclaw(self) -> None:
        """Mirrors ``exec.ts:11-12``."""
        assert DEFAULT_OUTPUT_LIMIT_CHARS == 16 * 1024 * 1024
        assert FORCE_KILL_GRACE_MS == 5_000

    def test_simple_command_runs(self) -> None:
        """Mirrors the happy path (``exec.ts:85-236``)."""
        result = exec_command(
            _python_executable(),
            ["-c", "print('hello world')"],
            cwd=os.getcwd(),
        )
        assert result.code == 0
        assert "hello world" in result.stdout
        assert result.killed is False

    def test_captures_stderr(self) -> None:
        result = exec_command(
            _python_executable(),
            ["-c", "import sys; sys.stderr.write('err-msg\\n')"],
            cwd=os.getcwd(),
        )
        assert "err-msg" in result.stderr

    def test_nonzero_exit_code(self) -> None:
        result = exec_command(
            _python_executable(),
            ["-c", "import sys; sys.exit(42)"],
            cwd=os.getcwd(),
        )
        assert result.code == 42
        assert result.killed is False

    def test_cwd_is_honored(self, tmp_path) -> None:
        result = exec_command(
            _python_executable(),
            ["-c", "import os; print(os.getcwd())"],
            cwd=str(tmp_path),
        )
        assert str(tmp_path) in result.stdout or str(tmp_path).replace(
            "\\", "/"
        ) in result.stdout

    def test_timeout_kills_long_running_process(self) -> None:
        """Mirrors the timeout branch
        (``exec.ts:191-195``)."""
        from src.agents.sessions import ExecOptions
        start = time.monotonic()
        result = exec_command(
            _python_executable(),
            ["-c", "import time; time.sleep(10)"],
            cwd=os.getcwd(),
            options=ExecOptions(timeout=0.2),
        )
        elapsed = time.monotonic() - start
        assert result.killed is True
        assert elapsed < 3.0  # well under 10s sleep

    def test_abort_signal_cancels(self) -> None:
        """Mirrors the abort-signal branch
        (``exec.ts:182-188``)."""
        from src.agents.sessions import ExecOptions
        signal = asyncio.Event()
        # Schedule the abort after a short delay.
        def _abort_later() -> None:
            time.sleep(0.1)
            signal.set()

        t = threading.Thread(target=_abort_later, daemon=True)
        t.start()
        start = time.monotonic()
        result = exec_command(
            _python_executable(),
            ["-c", "import time; time.sleep(10)"],
            cwd=os.getcwd(),
            options=ExecOptions(signal=signal),
        )
        elapsed = time.monotonic() - start
        assert result.killed is True
        assert elapsed < 3.0
        t.join(timeout=1)

    def test_max_output_chars_truncate(self) -> None:
        """Mirrors the truncate-tail branch
        (``exec.ts:67-78``). When ``max_output_chars``
        is provided, the output is silently truncated
        to the cap."""
        from src.agents.sessions import ExecOptions
        result = exec_command(
            _python_executable(),
            ["-c", "print('x' * 200)"],
            cwd=os.getcwd(),
            options=ExecOptions(max_output_chars=50),
        )
        # The output is at most ~50 chars; the actual
        # value can be up to ``max_output_chars`` plus
        # a tiny buffer for the trailing newline.
        assert len(result.stdout) <= 60
        # ``truncated_chars`` is set when the cap
        # is exceeded.
        if result.stdout_truncated_chars is not None:
            assert result.stdout_truncated_chars > 0


# ── bash_executor ──────────────────────────────────────


class _LocalBashOperations:
    """A minimal ``BashOperations`` implementation
    that delegates to :func:`exec_command`. Mirrors
    the *shape* of the Phase 6.10
    ``LocalBashOperations`` (which uses the full
    streaming pipeline)."""

    async def exec(self, command: str, cwd: str, options: dict) -> dict:
        on_data = options.get("on_data")
        signal = options.get("signal")

        # Synchronous ``exec_command`` cannot
        # participate in a real streaming pipeline;
        # we run the whole command then deliver the
        # final output in one ``on_data`` chunk. The
        # Phase 6.10 port replaces this with a true
        # line-buffered stream.
        from src.agents.sessions import ExecOptions
        result = exec_command(
            _python_executable(),
            ["-c", command],
            cwd=cwd,
            options=ExecOptions(signal=signal),
        )
        if on_data is not None and result.stdout:
            on_data(result.stdout.encode("utf-8"))
        # The full BashOperations result is a typed
        # dataclass; this minimal stub returns a
        # dict to match the Phase 6.1 protocol
        # surface (``BashOperationsExecResult`` is
        # an attribute protocol in Phase 6.1).
        return _StubBashOpsResult(result.code)


class _StubBashOpsResult:
    """Minimal :class:`BashOperationsExecResult`
    stub for the test back-end. The real class is
    wired in Phase 6.10; the Phase 6.1 protocol
    only requires ``.exit_code``."""

    def __init__(self, exit_code: Optional[int]) -> None:
        self.exit_code = exit_code


class TestBashExecutor:
    def test_sanitizer_strips_cr(self) -> None:
        """Mirrors the
        ``sanitizeOutput(...).replace(/\\r/g, "")``
        call in ``bash-executor.ts:54``."""
        sanitize = create_streaming_binary_output_sanitizer()
        assert sanitize("hello\r\nworld") == "hello\nworld"

    def test_sanitizer_replaces_control_chars(self) -> None:
        sanitize = create_streaming_binary_output_sanitizer()
        # NUL → "?" per the Phase 6.1 sanitizer's
        # ``[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f]``
        # pattern. (Phase 6.10 may refine the
        # replacement policy.)
        result = sanitize("hello\x00world\x01")
        assert "hello" in result
        assert "world" in result
        assert "\x00" not in result
        assert "\x01" not in result

    def test_options_dataclass_fields(self) -> None:
        opts = BashExecutorOptions()
        assert opts.on_chunk is None
        assert opts.signal is None
        opts2 = BashExecutorOptions(
            on_chunk=lambda _c: None,
            signal=asyncio.Event(),
        )
        assert callable(opts2.on_chunk)
        assert opts2.signal is not None

    def test_execute_bash_happy_path(self) -> None:
        """Mirrors ``executeBashWithOperations``
        (``bash-executor.ts:45-104``)."""
        ops = _LocalBashOperations()
        chunks: list[str] = []
        result = asyncio.run(
            execute_bash_with_operations(
                "print('hi from bash')",
                cwd=os.getcwd(),
                operations=ops,
                options=BashExecutorOptions(
                    on_chunk=chunks.append,
                ),
            )
        )
        assert isinstance(result, BashResult)
        assert result.cancelled is False
        assert "hi from bash" in result.output
        assert result.exit_code == 0

    def test_execute_bash_cancellation(self) -> None:
        """Mirrors the cancellation branch
        (``bash-executor.ts:96-97``)."""
        signal = asyncio.Event()
        signal.set()  # pre-cancelled

        class _NoopOps:
            async def exec(self, *args, **kwargs):
                return _StubBashOpsResult(0)

        result = asyncio.run(
            execute_bash_with_operations(
                "true",
                cwd=os.getcwd(),
                operations=_NoopOps(),
                options=BashExecutorOptions(signal=signal),
            )
        )
        assert result.cancelled is True
        assert result.exit_code is None

    def test_bash_operations_is_a_protocol(self) -> None:
        # The protocol surface stays stable so a
        # later Phase 6.10 implementation can
        # implement it without touching this module.
        assert hasattr(BashOperations, "exec")
        assert callable(BashOperations.exec)

    def test_output_accumulator_basic(self) -> None:
        """Mirrors the ``OutputAccumulator`` shape
        (``bash-executor.ts:11`` via the Phase 6.10
        ``tools/output-accumulator.js``)."""
        acc = OutputAccumulator()
        acc.append(b"hello ")
        acc.append(b"world")
        result = acc.finish()
        assert result == "hello world"


# ── keybindings ───────────────────────────────────────


class TestKeybindings:
    def test_table_size(self) -> None:
        """Mirrors the canonical 41-entry table
        (``keybindings.ts:69-208``)."""
        assert len(KEYBINDINGS) == 41

    def test_known_entries_match_openclaw(self) -> None:
        """Spot-check a few key entries against the
        OpenClaw source values."""
        assert (
            KEYBINDINGS["app.interrupt"].default_keys == "escape"
        )
        assert (
            KEYBINDINGS["app.interrupt"].description
            == "Cancel or abort"
        )
        assert (
            KEYBINDINGS["app.clear"].default_keys == "ctrl+c"
        )
        assert (
            KEYBINDINGS["app.thinking.cycle"].default_keys
            == "shift+tab"
        )
        assert (
            KEYBINDINGS["app.tree.foldOrUp"].default_keys
            == ["ctrl+left", "alt+left"]
        )
        # Platform-specific entries
        if sys.platform == "win32":
            assert KEYBINDINGS["app.suspend"].default_keys == []
            assert (
                KEYBINDINGS["app.clipboard.pasteImage"].default_keys
                == "alt+v"
            )
        else:
            assert (
                KEYBINDINGS["app.suspend"].default_keys == "ctrl+z"
            )
            assert (
                KEYBINDINGS["app.clipboard.pasteImage"].default_keys
                == "ctrl+v"
            )

    def test_migration_table_size(self) -> None:
        """Mirrors the 59-entry table
        (``keybindings.ts:210-270``)."""
        assert len(KEYBINDING_NAME_MIGRATIONS) == 59

    def test_known_migrations(self) -> None:
        """Spot-check a few renames."""
        assert (
            KEYBINDING_NAME_MIGRATIONS["cursorUp"]
            == "tui.editor.cursorUp"
        )
        assert (
            KEYBINDING_NAME_MIGRATIONS["interrupt"]
            == "app.interrupt"
        )
        assert (
            KEYBINDING_NAME_MIGRATIONS["followUp"]
            == "app.message.followUp"
        )

    def test_is_legacy_keybinding_name(self) -> None:
        assert is_legacy_keybinding_name("cursorUp") is True
        assert is_legacy_keybinding_name("app.interrupt") is False
        assert is_legacy_keybinding_name("nonexistent") is False

    def test_to_keybindings_config_string(self) -> None:
        """Mirrors the string branch
        (``keybindings.ts:283-285``)."""
        result = to_keybindings_config(
            {"app.interrupt": "ctrl+x", "app.clear": "ctrl+k"}
        )
        assert result == {
            "app.interrupt": "ctrl+x",
            "app.clear": "ctrl+k",
        }

    def test_to_keybindings_config_list(self) -> None:
        """Mirrors the array branch
        (``keybindings.ts:287-289``)."""
        result = to_keybindings_config(
            {"app.tree.foldOrUp": ["ctrl+up", "alt+up"]}
        )
        assert result == {"app.tree.foldOrUp": ["ctrl+up", "alt+up"]}

    def test_to_keybindings_config_drops_non_string_values(
        self,
    ) -> None:
        """Non-string / mixed-array values are
        silently dropped (matches the OpenClaw
        source's behaviour — only strings and
        string-lists are accepted)."""
        result = to_keybindings_config(
            {
                "app.interrupt": "ctrl+x",
                "app.clear": 42,
                "app.exit": [1, 2, 3],
                "app.tools.expand": ["ctrl+a", 5],
            }
        )
        assert result == {"app.interrupt": "ctrl+x"}

    def test_to_keybindings_config_non_dict(self) -> None:
        assert to_keybindings_config(None) == {}
        assert to_keybindings_config("not a dict") == {}
        assert to_keybindings_config([1, 2, 3]) == {}

    def test_migrate_renames_legacy(self) -> None:
        """Mirrors ``migrateKeybindingsConfig``
        (``keybindings.ts:295-316``)."""
        migrated, was_migrated = migrate_keybindings_config(
            {"cursorUp": "ctrl+x", "app.clear": "ctrl+k"}
        )
        assert was_migrated is True
        assert "tui.editor.cursorUp" in migrated
        assert "cursorUp" not in migrated

    def test_migrate_passes_through_modern(self) -> None:
        migrated, was_migrated = migrate_keybindings_config(
            {"app.interrupt": "ctrl+x", "app.clear": "ctrl+k"}
        )
        assert was_migrated is False
        assert migrated == {
            "app.interrupt": "ctrl+x",
            "app.clear": "ctrl+k",
        }

    def test_migrate_prefers_new_over_legacy(self) -> None:
        """When both legacy and migrated names are
        present, the new name wins
        (``keybindings.ts:307-311``)."""
        migrated, was_migrated = migrate_keybindings_config(
            {
                "cursorUp": "ctrl+x",  # legacy
                "tui.editor.cursorUp": "ctrl+y",  # new
            }
        )
        # Both renames happen; the new name wins.
        assert was_migrated is True
        assert migrated.get("tui.editor.cursorUp") == "ctrl+y"

    def test_migrate_orders_known_first(self) -> None:
        """Mirrors ``orderKeybindingsConfig``
        (``keybindings.ts:318-334``). Known
        keybinding ids come before unknown extras."""
        migrated, _ = migrate_keybindings_config(
            {
                "zzz_extras": "ctrl+z",
                "app.interrupt": "ctrl+x",
                "aaa_extras": "ctrl+a",
            }
        )
        keys = list(migrated.keys())
        # Known id comes first; extras are sorted.
        assert keys[0] == "app.interrupt"
        assert "aaa_extras" in keys
        assert "zzz_extras" in keys
        assert keys.index("aaa_extras") < keys.index("zzz_extras")

    def test_load_raw_config_missing_file(self, tmp_path) -> None:
        assert load_raw_config(str(tmp_path / "missing.json")) is None

    def test_load_raw_config_valid(self, tmp_path) -> None:
        path = tmp_path / "keybindings.json"
        path.write_text(
            json.dumps(
                {"app.interrupt": "ctrl+x", "app.clear": "ctrl+k"}
            ),
            encoding="utf-8",
        )
        result = load_raw_config(str(path))
        assert result == {
            "app.interrupt": "ctrl+x",
            "app.clear": "ctrl+k",
        }

    def test_load_raw_config_invalid_json(self, tmp_path) -> None:
        path = tmp_path / "keybindings.json"
        path.write_text("not json", encoding="utf-8")
        assert load_raw_config(str(path)) is None

    def test_load_raw_config_non_dict(self, tmp_path) -> None:
        path = tmp_path / "keybindings.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert load_raw_config(str(path)) is None

    def test_keybindings_manager_create_loads_file(
        self, tmp_path
    ) -> None:
        """Mirrors ``KeybindingsManager.create``
        (``keybindings.ts:358-362``)."""
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        config_path = agent_dir / "keybindings.json"
        config_path.write_text(
            json.dumps(
                {
                    "cursorUp": "ctrl+x",  # legacy
                    "app.clear": "ctrl+k",
                }
            ),
            encoding="utf-8",
        )
        mgr = KeybindingsManager.create(agent_dir=str(agent_dir))
        # Defaults are merged in.
        effective = mgr.get_effective_config()
        assert effective["app.clear"] == "ctrl+k"
        # The legacy ``cursorUp`` was migrated to
        # ``tui.editor.cursorUp``.
        assert effective.get("tui.editor.cursorUp") == "ctrl+x"

    def test_keybindings_manager_reload(self, tmp_path) -> None:
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        config_path = agent_dir / "keybindings.json"
        config_path.write_text(
            json.dumps({"app.clear": "ctrl+k"}),
            encoding="utf-8",
        )
        mgr = KeybindingsManager.create(agent_dir=str(agent_dir))
        assert mgr.get_effective_config()["app.clear"] == "ctrl+k"
        # Rewrite the file.
        config_path.write_text(
            json.dumps({"app.clear": "ctrl+y"}),
            encoding="utf-8",
        )
        mgr.reload()
        assert mgr.get_effective_config()["app.clear"] == "ctrl+y"

    def test_keybindings_manager_reload_without_path(
        self,
    ) -> None:
        mgr = KeybindingsManager()  # no config path
        mgr.reload()  # no-op
        # Defaults are still available.
        assert mgr.get_effective_config()["app.interrupt"] == "escape"

    def test_keybindings_manager_set_user_bindings(
        self, tmp_path
    ) -> None:
        mgr = KeybindingsManager.create(
            agent_dir=str(tmp_path / "agent")
        )
        mgr.set_user_bindings({"app.clear": "ctrl+z"})
        assert mgr.get_effective_config()["app.clear"] == "ctrl+z"

    def test_keybindings_manager_load_from_file_method(
        self, tmp_path
    ) -> None:
        path = tmp_path / "kb.json"
        path.write_text(
            json.dumps({"app.clear": "ctrl+w"}),
            encoding="utf-8",
        )
        result = KeybindingsManager.load_from_file(str(path))
        assert result == {"app.clear": "ctrl+w"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
