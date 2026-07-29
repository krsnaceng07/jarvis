"""JARVIS Device Pair infra extension (Phase 5.16 partial port).

Re-exports the plugin ``entry`` so the loader's
``importlib.import_module("extensions.device-pair").entry``
access works for hyphened directory names (where the
``extensions.device_pair`` dotted path is unresolvable).

The full port lives in ``plugin.py`` and ``src/``.
"""
from __future__ import annotations

from .plugin import entry, device_pair_plugin

__all__ = ["entry", "device_pair_plugin"]
