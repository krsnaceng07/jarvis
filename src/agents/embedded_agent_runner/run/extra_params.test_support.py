"""Compatibility wrapper: re-export the `_test_support` implementation.

The canonical Python test-support implementation lives in
``extra_params_test_support.py``; this module re-exports the same
symbols so code that expects the ``.test_support`` filename keeps
working.
"""
from __future__ import annotations

from .extra_params_test_support import testing  # type: ignore

__all__ = ["testing"]
