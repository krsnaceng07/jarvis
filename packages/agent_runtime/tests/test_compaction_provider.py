"""Tests for compaction_provider.py — process-global registry."""

from __future__ import annotations

from typing import Any

import pytest

from jarvis_agent.compaction_provider import (
    CompactionProvider,
    RegisteredCompactionProvider,
    clear_compaction_providers,
    get_compaction_provider,
    get_registered_compaction_provider,
    list_registered_compaction_providers,
    register_compaction_provider,
    restore_registered_compaction_providers,
)


# ---------------------------------------------------------------------------
# Test fixture: always reset registry before each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    clear_compaction_providers()
    yield
    clear_compaction_providers()


# ---------------------------------------------------------------------------
# Stub provider
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal provider satisfying the CompactionProvider protocol."""

    def __init__(self, provider_id: str, label: str = "Stub") -> None:
        self.id = provider_id
        self.label = label

    async def summarize(self, *, messages: list[Any], **kwargs: Any) -> str:
        return f"stub summary from {self.id}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_get(self) -> None:
        provider = _StubProvider("my-provider")
        register_compaction_provider(provider, owner_plugin_id="my-plugin")
        result = get_compaction_provider("my-provider")
        assert result is provider

    def test_get_unknown_returns_none(self) -> None:
        assert get_compaction_provider("no-such-provider") is None

    def test_register_twice_overwrites(self) -> None:
        p1 = _StubProvider("same-id", label="First")
        p2 = _StubProvider("same-id", label="Second")
        register_compaction_provider(p1)
        register_compaction_provider(p2)
        assert get_compaction_provider("same-id") is p2

    def test_get_registered_includes_owner(self) -> None:
        provider = _StubProvider("plugin-provider")
        register_compaction_provider(provider, owner_plugin_id="owner-plugin")
        entry = get_registered_compaction_provider("plugin-provider")
        assert entry is not None
        assert entry.provider is provider
        assert entry.owner_plugin_id == "owner-plugin"

    def test_no_owner_plugin_id(self) -> None:
        provider = _StubProvider("anon-provider")
        register_compaction_provider(provider)
        entry = get_registered_compaction_provider("anon-provider")
        assert entry is not None
        assert entry.owner_plugin_id is None


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class TestList:
    def test_empty_initially(self) -> None:
        assert list_registered_compaction_providers() == []

    def test_list_returns_all_registered(self) -> None:
        p1 = _StubProvider("a")
        p2 = _StubProvider("b")
        register_compaction_provider(p1)
        register_compaction_provider(p2)
        entries = list_registered_compaction_providers()
        provider_ids = {e.provider.id for e in entries}
        assert provider_ids == {"a", "b"}


# ---------------------------------------------------------------------------
# Lifecycle: clear / restore
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_clear_removes_all(self) -> None:
        register_compaction_provider(_StubProvider("x"))
        register_compaction_provider(_StubProvider("y"))
        clear_compaction_providers()
        assert list_registered_compaction_providers() == []

    def test_restore_replaces_all(self) -> None:
        register_compaction_provider(_StubProvider("existing"))
        p1 = _StubProvider("restored-a")
        p2 = _StubProvider("restored-b")
        snapshot = [
            RegisteredCompactionProvider(provider=p1, owner_plugin_id="plugin-x"),
            RegisteredCompactionProvider(provider=p2, owner_plugin_id=None),
        ]
        restore_registered_compaction_providers(snapshot)
        assert get_compaction_provider("existing") is None
        assert get_compaction_provider("restored-a") is p1
        assert get_compaction_provider("restored-b") is p2

    def test_restore_then_list(self) -> None:
        providers = [_StubProvider(f"p{i}") for i in range(5)]
        entries = [RegisteredCompactionProvider(provider=p) for p in providers]
        restore_registered_compaction_providers(entries)
        listed = list_registered_compaction_providers()
        assert len(listed) == 5


# ---------------------------------------------------------------------------
# Protocol check
# ---------------------------------------------------------------------------


class TestProtocol:
    def test_stub_satisfies_protocol(self) -> None:
        p = _StubProvider("test")
        assert isinstance(p, CompactionProvider)
