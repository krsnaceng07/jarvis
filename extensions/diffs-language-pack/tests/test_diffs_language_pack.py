"""Tests for diffs-language-pack plugin."""

from __future__ import annotations

from unittest.mock import MagicMock
from extensions.diffs_language_pack.plugin import diffs_language_pack_plugin


def test_diffs_language_pack_descriptor() -> None:
    assert diffs_language_pack_plugin.id == "diffs-language-pack"
    assert diffs_language_pack_plugin.kind == "infra"


def test_diffs_language_pack_init() -> None:
    ctx = MagicMock()
    diffs_language_pack_plugin.init(ctx)
    ctx.register_http_route.assert_called_once()
