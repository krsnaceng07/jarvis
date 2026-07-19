"""Pytest configuration for JARVIS.

Currently a no-op stub. Used to live here for transitional warning filters
during PR 0.4; the filter now lives in the root `pyproject.toml`
(`[tool.pytest.ini_options].filterwarnings`), which is the canonical location.

This file is kept so that future per-test setup (fixtures, markers, plugins)
has an obvious home. See `tests/README.md` for the test layout.
"""
from __future__ import annotations
