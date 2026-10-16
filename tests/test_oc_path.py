"""Tests for src/plugins/oc_path.py.

Mirrors tests of extensions/oc-path/src/oc-path/sentinel.ts in OpenClaw.
"""

from __future__ import annotations

import pytest

from src.plugins.oc_path import (
    OC_PATH_FILE_KINDS,
    OC_PATH_PLUGIN_ID,
    OC_PATH_VERBS,
    REDACTED_SENTINEL_OPENCLAW,
    JarvisEmitSentinelError,
    detect_file_kind,
    guard_sentinel,
    parse_oc_uri,
)


def test_oc_path_constants():
    assert OC_PATH_PLUGIN_ID == "oc-path"
    assert "markdown" in OC_PATH_FILE_KINDS
    assert "jsonc" in OC_PATH_FILE_KINDS
    assert "jsonl" in OC_PATH_FILE_KINDS
    assert "yaml" in OC_PATH_FILE_KINDS
    assert "resolve" in OC_PATH_VERBS
    assert "set" in OC_PATH_VERBS


def test_guard_sentinel_clean():
    guard_sentinel("clean text without sentinel", "oc://AGENTS.md/tools")


def test_guard_sentinel_trigger():
    with pytest.raises(JarvisEmitSentinelError, match="emit refused to write"):
        guard_sentinel(f"secret: {REDACTED_SENTINEL_OPENCLAW}", "oc://config.jsonc/key")


def test_parse_oc_uri():
    f, leaf = parse_oc_uri("oc://AGENTS.md/tools/gh")
    assert f == "AGENTS.md"
    assert leaf == "tools/gh"

    f_solo, leaf_solo = parse_oc_uri("oc://config.jsonc")
    assert f_solo == "config.jsonc"
    assert leaf_solo == ""


def test_parse_oc_uri_invalid():
    with pytest.raises(ValueError, match="Must start with 'oc://'"):
        parse_oc_uri("file://AGENTS.md")


def test_detect_file_kind():
    assert detect_file_kind("AGENTS.md") == "markdown"
    assert detect_file_kind("session.jsonl") == "jsonl"
    assert detect_file_kind("workflow.yaml") == "yaml"
    assert detect_file_kind("config.jsonc") == "jsonc"
    assert detect_file_kind("config.json") == "jsonc"
