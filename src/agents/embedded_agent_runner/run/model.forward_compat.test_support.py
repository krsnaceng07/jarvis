"""Compatibility wrapper: re-export the `_test_support` implementation.

The canonical Python test-support implementation lives in
``model_forward_compat_test_support.py``; this module re-exports the
same symbols so code that expects the ``.test_support`` filename keeps
working.
"""
from __future__ import annotations

from .model_forward_compat_test_support import *  # noqa: F401,F403

__all__ = [name for name in globals().keys() if not name.startswith("_")]
