"""Compatibility package for the QA lab extension."""

from __future__ import annotations

from importlib import import_module

_module = import_module("extensions.qa-lab")

for _name in getattr(_module, "__all__", []):
    globals()[_name] = getattr(_module, _name)

__all__ = list(getattr(_module, "__all__", []))
