"""Compatibility package for the QA channel extension.

The source tree keeps the canonical extension folder name as ``qa-channel``
(hyphenated) because it matches the OpenClaw extension id, but tests and some
callers import the Python module name with underscores. This shim re-exports the
canonical implementation under the underscore form expected by the runtime.
"""

from __future__ import annotations

from importlib import import_module

_module = import_module("extensions.qa-channel")

for _name in getattr(_module, "__all__", []):
    globals()[_name] = getattr(_module, _name)

__all__ = list(getattr(_module, "__all__", []))
