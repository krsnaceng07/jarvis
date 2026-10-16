"""parse_model_ref delegates strict splitting to jarvis_model_catalog.

Locks the exact legacy behavior (verbatim segments, default-provider
fallback, garbage-in tolerance) across the delegation.
"""

from __future__ import annotations

import pytest

from jarvis_sdk.agent_runtime import DEFAULT_PROVIDER, parse_model_ref


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("openai/gpt-5", ("openai", "gpt-5")),
        ("  openai / gpt-5  ", ("openai", "gpt-5")),
        ("a/b/c", ("a", "b/c")),
        ("gpt-5", (DEFAULT_PROVIDER, "gpt-5")),
        ("a/", (DEFAULT_PROVIDER, "a/")),
        ("/b", (DEFAULT_PROVIDER, "/b")),
        (" / ", (DEFAULT_PROVIDER, "/")),
    ],
)
def test_parse_model_ref_vectors(raw: str, expected: tuple[str, str]) -> None:
    assert parse_model_ref(raw) == {"provider": expected[0], "model": expected[1]}


@pytest.mark.parametrize("raw", [None, 42, "", "   "])
def test_parse_model_ref_rejects_empty(raw: object) -> None:
    assert parse_model_ref(raw) is None
