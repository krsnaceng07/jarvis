"""Tests for ``jarvis_agent.runtime_deps``.

OpenClaw source: ``packages/agent-core/src/runtime-deps.ts`` (45 lines).
Upstream has no dedicated test file; cases are derived from the source:
explicit ``streamFn`` wins over injected deps, missing deps raise with the
exact configured-dependency message, and the completion resolver has no
override parameter at all.
"""

from __future__ import annotations

import pytest

from jarvis_agent.runtime_deps import (
    AgentCoreCompletionRuntimeDeps,
    AgentCoreRuntimeDeps,
    AgentCoreStreamRuntimeDeps,
    resolve_agent_core_complete_fn,
    resolve_agent_core_stream_fn,
)


def _stream_a(*args: object, **kwargs: object) -> None:  # pragma: no cover - marker
    raise NotImplementedError


def _stream_b(*args: object, **kwargs: object) -> None:  # pragma: no cover - marker
    raise NotImplementedError


def _complete_a(*args: object, **kwargs: object) -> None:  # pragma: no cover - marker
    raise NotImplementedError


class TestResolveStreamFn:
    def test_explicit_stream_fn_wins_over_runtime(self) -> None:
        # TS: `if (streamFn) return streamFn;` runs before the runtime check.
        runtime = AgentCoreRuntimeDeps(stream_simple=_stream_a)
        assert resolve_agent_core_stream_fn(runtime, _stream_b) is _stream_b

    def test_falls_back_to_runtime_stream_simple(self) -> None:
        runtime = AgentCoreRuntimeDeps(stream_simple=_stream_a)
        assert resolve_agent_core_stream_fn(runtime) is _stream_a

    def test_explicit_fn_with_no_runtime(self) -> None:
        # TS: `runtime?.streamSimple` — undefined runtime is fine if streamFn given.
        assert resolve_agent_core_stream_fn(None, _stream_b) is _stream_b

    def test_missing_both_raises_with_exact_message(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            resolve_agent_core_stream_fn(None)
        assert str(exc_info.value) == (
            '@openclaw/agent-core runtime dependency "streamSimple" is not '
            "configured. Pass an AgentCoreRuntimeDeps instance or a streamFn "
            "explicitly."
        )

    def test_runtime_present_but_stream_none_raises(self) -> None:
        # A deps object built for completion-only use must not satisfy
        # the streaming resolver.
        runtime = AgentCoreRuntimeDeps(complete_simple=_complete_a)
        with pytest.raises(RuntimeError, match='"streamSimple"'):
            resolve_agent_core_stream_fn(runtime)


class TestResolveCompleteFn:
    def test_resolves_from_runtime(self) -> None:
        runtime = AgentCoreRuntimeDeps(complete_simple=_complete_a)
        assert resolve_agent_core_complete_fn(runtime) is _complete_a

    def test_none_runtime_raises_with_exact_message(self) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            resolve_agent_core_complete_fn(None)
        assert str(exc_info.value) == (
            '@openclaw/agent-core runtime dependency "completeSimple" is not '
            "configured. Pass an AgentCoreRuntimeDeps instance or a streamFn "
            "explicitly."
        )

    def test_runtime_present_but_complete_none_raises(self) -> None:
        runtime = AgentCoreRuntimeDeps(stream_simple=_stream_a)
        with pytest.raises(RuntimeError, match='"completeSimple"'):
            resolve_agent_core_complete_fn(runtime)

    def test_has_no_override_parameter(self) -> None:
        # TS resolveAgentCoreCompleteFn takes only `runtime`. If an override
        # parameter ever appears here, the signatures have diverged.
        import inspect

        params = list(inspect.signature(resolve_agent_core_complete_fn).parameters)
        assert params == ["runtime"]


class TestDepsShape:
    def test_subset_aliases_are_the_same_class(self) -> None:
        # TS expresses the subsets as Pick<>; Python reuses one dataclass.
        assert AgentCoreStreamRuntimeDeps is AgentCoreRuntimeDeps
        assert AgentCoreCompletionRuntimeDeps is AgentCoreRuntimeDeps

    def test_fields_default_to_none(self) -> None:
        deps = AgentCoreRuntimeDeps()
        assert deps.stream_simple is None
        assert deps.complete_simple is None

    def test_frozen(self) -> None:
        deps = AgentCoreRuntimeDeps(stream_simple=_stream_a)
        with pytest.raises(Exception):  # noqa: B017, PT011 - FrozenInstanceError
            deps.stream_simple = _stream_b  # type: ignore[misc]
