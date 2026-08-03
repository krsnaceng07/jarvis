"""jarvis.agents.embedded_agent_runner.run.payloads_test_helpers — test helpers for run payloads.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/payloads.test-helpers.ts``.

Public surface:

- :func:`build_payloads`
- :func:`expect_single_payload_text`
- :func:`expect_single_tool_error_payload`

Phase 7.6h-7 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


# Installable hooks ---------------------------------------------------------

_build_payloads_hook = None
_build_embedded_run_payloads_fn: Optional[Callable[..., Any]] = None


def set_build_payloads_hook(fn) -> None:
    global _build_payloads_hook
    _build_payloads_hook = fn


def set_build_embedded_run_payloads_fn(fn) -> None:
    """Set the underlying ``build_embedded_run_payloads`` used by the test helper."""
    global _build_embedded_run_payloads_fn
    _build_embedded_run_payloads_fn = fn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_payloads(overrides: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Build a default embedded-run payload list for tests.

    Mirrors :func:`buildPayloads` (``payloads.test-helpers.ts``).
    """
    if _build_payloads_hook is not None:
        return _build_payloads_hook(overrides) or []
    overrides = overrides or {}
    if _build_embedded_run_payloads_fn is None:
        return []
    base: Dict[str, Any] = {
        "assistantTexts": [],
        "toolMetas": [],
        "lastAssistant": None,
        "isCronTrigger": False,
        "sessionKey": "session:telegram",
        "inlineToolResultsAllowed": False,
        "verboseLevel": "off",
        "reasoningLevel": "off",
        "toolResultFormat": "plain",
    }
    if "currentAssistant" not in overrides:
        base["currentAssistant"] = overrides.get("lastAssistant")
    merged = {**base, **overrides}
    return _build_embedded_run_payloads_fn(merged) or []


def expect_single_payload_text(
    payloads: List[Dict[str, Any]],
    text: str,
    expected_error: Optional[bool] = None,
) -> None:
    """Assert that ``payloads`` has a single entry whose text matches ``text``.

    Mirrors :func:`expectSinglePayloadText` (``payloads.test-helpers.ts``).
    """
    assert len(payloads) == 1, f"expected 1 payload, got {len(payloads)}"
    actual_text = payloads[0].get("text")
    assert actual_text == text, f"expected text {text!r}, got {actual_text!r}"
    if expected_error is not None:
        assert payloads[0].get("isError") is expected_error


def expect_single_tool_error_payload(
    payloads: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> None:
    """Assert that ``payloads`` is a single tool-error payload.

    Mirrors :func:`expectSingleToolErrorPayload`
    (``payloads.test-helpers.ts``).
    """
    assert len(payloads) == 1, f"expected 1 payload, got {len(payloads)}"
    assert payloads[0].get("isError") is True
    text = payloads[0].get("text", "")
    title = params.get("title")
    if title is not None:
        assert title in text, f"expected title {title!r} in {text!r}"
    detail = params.get("detail")
    if detail is not None:
        assert detail in text, f"expected detail {detail!r} in {text!r}"
    absent_detail = params.get("absentDetail")
    if absent_detail is not None:
        assert absent_detail not in text, f"unexpected absentDetail {absent_detail!r} in {text!r}"


__all__ = [
    "build_payloads",
    "expect_single_payload_text",
    "expect_single_tool_error_payload",
    "set_build_payloads_hook",
    "set_build_embedded_run_payloads_fn",
]
