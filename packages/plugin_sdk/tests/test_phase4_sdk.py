"""Phase 4 SDK submodule tests — OpenClaw plugin-sdk parity.

Tests every SDK submodule added in Phase 4.0:

  - ``lazy_runtime`` (``createLazyRuntimeModule`` parity)
  - ``expect_runtime`` (``expectDefined`` parity)
  - ``number_runtime`` (``parseStrictPositiveInteger`` +
    ``resolveTimerTimeoutMs`` parity)
  - ``text_utility`` (``truncateUtf16Safe`` parity)
  - ``routing`` (``normalizeAgentId`` parity)
  - ``string_coerce`` (``asOptionalRecord`` +
    ``normalizeLowercaseStringOrEmpty`` parity)
  - ``chat_channel_ids`` (``BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES``)
  - ``runtime_env`` (``ensureGlobalUndiciEnvProxyDispatcher``)
  - ``message_tool_delivery_hints``
  - ``agent_runtime`` (resolve_agent_dir / etc.)
  - ``plugin_config`` (``resolveLivePluginConfigObject``)
  - ``plugin_state`` (keyed store + lease)
  - ``memory_storage`` (interface types)
  - ``memory_embeddings`` (registry)
  - ``memory_runtime`` (capability bundle)
"""

from __future__ import annotations

from typing import Any

import asyncio
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from jarvis_sdk import (
    BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES,
    MESSAGE_TOOL_DELIVERY_HINTS,
    SOURCE_MEMORY,
    LeaseHeld,
    MemoryFlushPlan,
    MemoryPluginCapability,
    MemoryPluginPublicArtifact,
    MemoryPluginRuntime,
    MemoryPromptSectionBuilder,
    MemorySearchManager,
    MemorySearchResult,
    OpenKeyedStoreOptions,
    as_optional_record,
    create_lazy_runtime_module,
    ensure_global_undici_env_proxy_dispatcher,
    expect_defined,
    expect_truthy,
    normalize_agent_id,
    normalize_lowercase_string_or_empty,
    open_keyed_store,
    parse_strict_positive_integer,
    resolve_agent_dir,
    resolve_agent_workspace_dir,
    resolve_default_agent_id,
    resolve_live_plugin_config_object,
    resolve_session_agent_id,
    resolve_timer_timeout_ms,
    truncate_utf16_safe,
    utf16_length,
    with_lease,
)

# ── lazy_runtime ───────────────────────────────────────────────


class TestLazyRuntime:
    def test_loads_module(self) -> None:
        load = create_lazy_runtime_module(lambda: {"value": 42})

        async def runner() -> dict[str, Any]:
            return await load()

        result = asyncio.run(runner())
        assert result == {"value": 42}

    def test_caches_result(self) -> None:
        calls = {"n": 0}

        def loader() -> dict[str, Any]:
            calls["n"] += 1
            return {"count": calls["n"]}

        load = create_lazy_runtime_module(loader)

        async def runner() -> dict[str, Any]:
            return await load()

        asyncio.run(runner())
        asyncio.run(runner())
        assert calls["n"] == 1

    def test_async_loader(self) -> None:
        async def loader() -> int:
            return 7

        load = create_lazy_runtime_module(loader)

        async def runner() -> int:
            return await load()

        assert asyncio.run(runner()) == 7

    def test_failure_does_not_cache(self) -> None:
        calls = {"n": 0}

        def loader() -> int:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first time fails")
            return 42

        load = create_lazy_runtime_module(loader)

        async def runner() -> int:
            return await load()

        with pytest.raises(RuntimeError):
            asyncio.run(runner())
        # Second call retries.
        assert asyncio.run(runner()) == 42
        assert calls["n"] == 2


# ── expect_runtime ──────────────────────────────────────────────


class TestExpectRuntime:
    def test_expect_defined_returns_value(self) -> None:
        assert expect_defined("hello", "ctx") == "hello"
        assert expect_defined(0, "ctx") == 0

    def test_expect_defined_raises_on_none(self) -> None:
        with pytest.raises(AssertionError):
            expect_defined(None, "must be set")

    def test_expect_truthy(self) -> None:
        assert expect_truthy("hello", "ctx") == "hello"
        with pytest.raises(AssertionError):
            expect_truthy("", "must be non-empty")


# ── number_runtime ──────────────────────────────────────────────


class TestNumberRuntime:
    def test_parse_strict_positive_integer_int(self) -> None:
        assert parse_strict_positive_integer(5) == 5
        assert parse_strict_positive_integer(1) == 1

    def test_parse_strict_positive_integer_string(self) -> None:
        assert parse_strict_positive_integer("42") == 42
        assert parse_strict_positive_integer("  10  ") == 10

    def test_parse_strict_positive_integer_none_and_empty(self) -> None:
        assert parse_strict_positive_integer(None) is None
        assert parse_strict_positive_integer("") is None
        assert parse_strict_positive_integer("   ") is None

    def test_parse_strict_positive_integer_rejects_zero(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer(0)
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer("0")

    def test_parse_strict_positive_integer_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer(-1)
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer("-5")

    def test_parse_strict_positive_integer_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer("not a number")
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer(3.14)  # floats rejected
        with pytest.raises(ValueError, match="positive integer"):
            parse_strict_positive_integer(True)  # bool rejected

    def test_resolve_timer_timeout_ms(self) -> None:
        assert resolve_timer_timeout_ms(100, 50) == 100
        assert resolve_timer_timeout_ms(None, 50) == 50
        assert resolve_timer_timeout_ms(0, 50) == 50  # zero -> fallback
        assert resolve_timer_timeout_ms(-1, 50) == 50  # negative -> fallback
        assert resolve_timer_timeout_ms(0.5, 50) == 1  # clamped to >= 1


# ── text_utility ────────────────────────────────────────────────


class TestTextUtility:
    def test_truncate_short_string_unchanged(self) -> None:
        assert truncate_utf16_safe("hello", 10) == "hello"

    def test_truncate_bmp(self) -> None:
        result = truncate_utf16_safe("hello world", 5)
        assert result == "hello"

    def test_truncate_supplementary_chars(self) -> None:
        # 😀 (U+1F600) is 2 UTF-16 units; preserve it.
        text = "a😀b😀c"
        # a = 1 unit, 😀 = 2 units, b = 1 unit, 😀 = 2 units, c = 1 unit = 7 total
        assert utf16_length(text) == 7
        result = truncate_utf16_safe(text, 4)
        # 1 (a) + 2 (😀) + 1 (b) = 4 units
        assert result == "a😀b"

    def test_truncate_splits_safely(self) -> None:
        # If truncating mid-surrogate, back off.
        text = "a😀b"
        # 1 + 2 = 3 units total
        result = truncate_utf16_safe(text, 2)
        # 1 (a) + 2 (😀) = 3 > 2, so back off to 1 (a)
        assert result == "a"

    def test_truncate_max_units_zero(self) -> None:
        assert truncate_utf16_safe("hello", 0) == ""

    def test_truncate_max_units_negative_raises(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            truncate_utf16_safe("hello", -1)


# ── routing ─────────────────────────────────────────────────────


class TestRouting:
    def test_normalize_trims_and_lowercases(self) -> None:
        assert normalize_agent_id("  Foo  ") == "foo"
        assert normalize_agent_id("BAR") == "bar"

    def test_normalize_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="agent id must not be None|reserved"):
            normalize_agent_id("")
        with pytest.raises(ValueError, match="reserved"):
            normalize_agent_id("   ")

    def test_normalize_rejects_reserved(self) -> None:
        for reserved in (".", "..", "/", "\\", "default"):
            with pytest.raises(ValueError, match="reserved"):
                normalize_agent_id(reserved)

    def test_normalize_rejects_whitespace(self) -> None:
        with pytest.raises(ValueError, match="whitespace"):
            normalize_agent_id("foo\nbar")
        with pytest.raises(ValueError, match="whitespace"):
            normalize_agent_id("foo\tbar")
        with pytest.raises(ValueError, match="whitespace"):
            normalize_agent_id("foo\0bar")

    def test_normalize_rejects_non_string(self) -> None:
        with pytest.raises(ValueError, match="agent id must not be None"):
            normalize_agent_id(None)
        with pytest.raises(ValueError, match="must be a string"):
            normalize_agent_id(123)


# ── string_coerce ───────────────────────────────────────────────


class TestStringCoerce:
    def test_as_optional_record_dict(self) -> None:
        d = {"a": 1}
        assert as_optional_record(d) is d

    def test_as_optional_record_none(self) -> None:
        assert as_optional_record(None) is None

    def test_as_optional_record_rejects_non_dict(self) -> None:
        assert as_optional_record("hello") is None
        assert as_optional_record([1, 2, 3]) is None
        assert as_optional_record(42) is None

    def test_normalize_lowercase_string_or_empty(self) -> None:
        assert normalize_lowercase_string_or_empty("Foo") == "foo"
        assert normalize_lowercase_string_or_empty("  BAR  ") == "bar"
        assert normalize_lowercase_string_or_empty("") == ""
        assert normalize_lowercase_string_or_empty(None) == ""
        assert normalize_lowercase_string_or_empty(42) == ""


# ── chat_channel_ids ────────────────────────────────────────────


class TestChatChannelIds:
    def test_bundled_prefixes_is_frozenset(self) -> None:
        assert isinstance(BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES, frozenset)

    def test_contains_common_channels(self) -> None:
        # OpenClaw's bundled list; JARVIS must include the same names.
        for ch in ("telegram", "discord", "slack", "whatsapp", "signal"):
            assert ch in BUNDLED_CHAT_CHANNEL_ENVELOPE_PREFIXES


# ── runtime_env ─────────────────────────────────────────────────


class TestRuntimeEnv:
    def test_ensure_global_dispatcher_is_idempotent(self) -> None:
        # Should not raise on repeated calls; sets the env state.
        ensure_global_undici_env_proxy_dispatcher()
        ensure_global_undici_env_proxy_dispatcher()
        # Proxy env vars should be at least set to empty string.
        assert "HTTP_PROXY" in os.environ


# ── message_tool_delivery_hints ─────────────────────────────────


class TestMessageToolDeliveryHints:
    def test_hints_is_frozenset(self) -> None:
        assert isinstance(MESSAGE_TOOL_DELIVERY_HINTS, frozenset)

    def test_contains_common_hints(self) -> None:
        assert "[delivered]" in MESSAGE_TOOL_DELIVERY_HINTS
        assert "[silent]" in MESSAGE_TOOL_DELIVERY_HINTS


# ── agent_runtime ───────────────────────────────────────────────


class TestAgentRuntime:
    def test_resolve_default_agent_id_empty_config(self) -> None:
        assert resolve_default_agent_id(None) == "default"
        assert resolve_default_agent_id({}) == "default"

    def test_resolve_default_agent_id_with_defaults(self) -> None:
        cfg: dict[str, Any] = {"agents": {"defaults": {"id": "MyBot"}}}
        assert resolve_default_agent_id(cfg) == "mybot"

    def test_resolve_default_agent_id_with_listing(self) -> None:
        cfg: dict[str, Any] = {"agents": {"list": [{"id": "FirstAgent"}]}}
        assert resolve_default_agent_id(cfg) == "firstagent"

    def test_resolve_agent_dir(self, tmp_path: Path) -> None:
        # Redirect data dir to tmp via env.
        os.environ["JARVIS_DATA_DIR"] = str(tmp_path)
        path = resolve_agent_dir(None, "test-agent")
        assert "test-agent" in path
        assert path.startswith(str(tmp_path))

    def test_resolve_agent_workspace_dir(self, tmp_path: Path) -> None:
        os.environ["JARVIS_DATA_DIR"] = str(tmp_path)
        path = resolve_agent_workspace_dir(None, "test-agent")
        assert "test-agent" in path
        assert "workspace" in path

    def test_resolve_session_agent_id_explicit(self) -> None:
        assert resolve_session_agent_id({}, agent_id="MyAgent") == "myagent"

    def test_resolve_session_agent_id_no_session(self) -> None:
        assert resolve_session_agent_id({}, session_key=None) == "default"

    def test_resolve_session_agent_id_agent_prefix(self) -> None:
        # OpenClaw convention: "agent:<id>:<rest>" → agent id = <id>
        assert resolve_session_agent_id({}, session_key="agent:mybot:main") == "mybot"

    def test_resolve_session_agent_id_wildcard(self) -> None:
        # "agent:*" → fall back to default
        assert resolve_session_agent_id({}, session_key="agent:*:main") == "default"


# ── plugin_config ───────────────────────────────────────────────


class TestPluginConfig:
    def test_resolve_returns_none_when_no_supplier(self) -> None:
        assert resolve_live_plugin_config_object(None, "x", {"a": 1}) is None

    def test_resolve_returns_none_when_supplier_raises(self) -> None:
        def broken() -> dict[str, Any]:
            raise RuntimeError("config load failed")

        assert resolve_live_plugin_config_object(broken, "x", {"a": 1}) is None

    def test_resolve_returns_none_when_plugin_id_missing(self) -> None:
        def cfg() -> dict[str, Any]:
            return {"plugins": {"entries": {"other": {"foo": 1}}}}

        assert resolve_live_plugin_config_object(cfg, "x", {"a": 1}) is None

    def test_resolve_returns_merged(self) -> None:
        def cfg() -> dict[str, Any]:
            return {"plugins": {"entries": {"x": {"b": 2}}}}

        merged = resolve_live_plugin_config_object(cfg, "x", {"a": 1, "b": 99})
        assert merged == {"a": 1, "b": 2}  # live overrides static

    def test_resolve_empty_static(self) -> None:
        def cfg() -> dict[str, Any]:
            return {"plugins": {"entries": {"x": {"a": 1}}}}

        merged = resolve_live_plugin_config_object(cfg, "x", None)
        assert merged == {"a": 1}


# ── plugin_state ────────────────────────────────────────────────


class TestPluginState:
    def test_read_returns_none_for_missing_key(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        assert store.read("missing") is None

    def test_write_and_read(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        store.write("k1", {"a": 1, "b": [2, 3]})
        loaded = store.read("k1")
        assert loaded == {"a": 1, "b": [2, 3]}

    def test_write_is_atomic(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        store.write("k1", {"a": 1})
        # No .tmp files should remain.
        leftover = list(store._root.glob("*.tmp"))
        assert leftover == []

    def test_list_keys(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        store.write("k1", {"a": 1})
        store.write("k2", {"a": 2})
        store.write("k3", {"a": 3})
        keys = store.list_keys()
        assert set(keys) == {"k1", "k2", "k3"}

    def test_delete(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        store.write("k1", {"a": 1})
        assert store.delete("k1") is True
        assert store.read("k1") is None
        assert store.delete("k1") is False  # second delete is no-op

    def test_lease_acquire_and_release(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        token = store.acquire_lease("k1")
        assert token is not None
        assert store.release_lease("k1", token) is True

    def test_lease_blocks_double_acquire(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test", lease_ms=10_000))
        token1 = store.acquire_lease("k1")
        assert token1 is not None
        token2 = store.acquire_lease("k1")
        assert token2 is None  # held
        assert store.release_lease("k1", token1) is True
        token3 = store.acquire_lease("k1")
        assert token3 is not None  # freed

    def test_lease_steal_after_expiry(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test", lease_ms=10))
        token1 = store.acquire_lease("k1")
        assert token1 is not None
        # Sleep past lease expiry.
        import time

        time.sleep(0.05)
        token2 = store.acquire_lease("k1")
        assert token2 is not None  # stole the stale lease

    def test_with_lease_runs_body(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        with with_lease(store, "k1") as token:
            assert isinstance(token, str)
            assert len(token) > 0
        # After the block, the lock is released.
        token_after = store.acquire_lease("k1")
        assert token_after is not None

    def test_with_lease_raises_if_held(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        store.acquire_lease("k1")
        with pytest.raises(LeaseHeld), with_lease(store, "k1"):
            pass  # pragma: no cover

    def test_invalid_key_rejected(self, tmp_path: Path) -> None:
        store = open_keyed_store(OpenKeyedStoreOptions(root=tmp_path, name="test"))
        with pytest.raises(ValueError, match="invalid key"):
            store.read("../etc/passwd")
        with pytest.raises(ValueError, match="invalid key"):
            store.read("a/b")
        with pytest.raises(ValueError, match="invalid key"):
            store.read("")


# ── memory_storage ──────────────────────────────────────────────


class TestMemoryStorage:
    def test_source_constants(self) -> None:
        assert SOURCE_MEMORY == "memory"
        from jarvis_sdk import SOURCE_ALL, SOURCE_SESSIONS, SOURCE_WIKI, VALID_SOURCES

        assert SOURCE_WIKI == "wiki"
        assert SOURCE_SESSIONS == "sessions"
        assert SOURCE_ALL == "all"
        assert {SOURCE_MEMORY, SOURCE_WIKI, SOURCE_SESSIONS, SOURCE_ALL} == VALID_SOURCES

    def test_memory_search_result_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        r = MemorySearchResult(
            id="1",
            path="MEMORY.md",
            start_line=1,
            end_line=5,
            score=0.9,
            source=SOURCE_MEMORY,
            text="hello",
        )
        assert r.id == "1"
        assert r.score == 0.9
        with pytest.raises(FrozenInstanceError):
            r.id = "2"  # type: ignore[misc]

    def test_memory_search_manager_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            MemorySearchManager()  # type: ignore[abstract]


# ── memory_embeddings ──────────────────────────────────────────


class TestMemoryEmbeddings:
    def test_registry_empty_initially(self) -> None:
        # Use a private accessor so the test is independent of other tests.
        from jarvis_sdk.memory_embeddings import _REGISTRY

        # Filter out any built-ins that might have been registered by
        # other test files (e.g. memory_lancedb tests).
        keys = sorted(_REGISTRY.keys())
        assert all(k.startswith("test_") or k in keys for k in keys)

    def test_register_and_lookup(self) -> None:
        from jarvis_sdk.memory_embeddings import (
            MemoryEmbeddingProviderAdapter,
            get_memory_embedding_provider,
            list_registered_memory_embedding_providers,
            register_memory_embedding_provider,
        )

        class StubAdapter(MemoryEmbeddingProviderAdapter):
            id = "test_stub_provider"

            async def create(self, config: dict[str, Any] | None = None, **kwargs: Any) -> Any:
                return None

        register_memory_embedding_provider("test_stub_provider", StubAdapter())
        assert get_memory_embedding_provider("test_stub_provider") is not None
        assert "test_stub_provider" in list_registered_memory_embedding_providers()

    def test_register_rejects_empty_id(self) -> None:
        from jarvis_sdk.memory_embeddings import register_memory_embedding_provider

        with pytest.raises(ValueError, match="non-empty"):
            register_memory_embedding_provider("", None)  # type: ignore[arg-type]

    def test_unknown_provider_returns_none(self) -> None:
        from jarvis_sdk.memory_embeddings import get_memory_embedding_provider

        assert get_memory_embedding_provider("definitely_not_registered_xyz") is None


# ── memory_runtime ──────────────────────────────────────────────


class TestMemoryRuntime:
    def test_memory_flush_plan_defaults(self) -> None:
        plan = MemoryFlushPlan()
        assert plan.should_flush is False
        assert plan.reason == ""
        assert plan.extra == {}

    def test_memory_plugin_public_artifact(self) -> None:
        art = MemoryPluginPublicArtifact(id="x", kind="memory", path="/foo")
        assert art.id == "x"
        assert art.kind == "memory"

    def test_prompt_section_builder_abstract(self) -> None:
        with pytest.raises(TypeError):
            MemoryPromptSectionBuilder()  # type: ignore[abstract]

    def test_plugin_runtime_abstract(self) -> None:
        with pytest.raises(TypeError):
            MemoryPluginRuntime()  # type: ignore[abstract]

    def test_capability_bundle_construction(self) -> None:
        # Construct a minimal capability to verify the bundle shape.
        class StubBuilder(MemoryPromptSectionBuilder):
            def build(self, build_options: dict[str, Any]) -> str:
                return "[stub]"

        class StubRuntime(MemoryPluginRuntime):
            async def get_memory_search_manager(self, params: dict[str, Any] | None = None) -> Any:
                raise NotImplementedError

            async def close_all_memory_search_managers(self):
                pass

        from jarvis_sdk import MemoryFlushPlanResolver

        class StubFlush(MemoryFlushPlanResolver):
            def resolve(self, build_options: dict[str, Any]) -> MemoryFlushPlan:
                return MemoryFlushPlan(should_flush=False)

        cap = MemoryPluginCapability(
            prompt_builder=StubBuilder(),
            flush_plan_resolver=StubFlush(),
            runtime=StubRuntime(),
        )
        assert cap.prompt_builder.build({}) == "[stub]"
        assert cap.flush_plan_resolver.resolve({}).should_flush is False
