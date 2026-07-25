"""jarvis_normalization_core — Shared normalization utilities.

OpenClaw parity: mirrors
``packages/normalization-core/src/`` (string-coerce, utf16-slice,
result, json-store, etc.).

This package re-exports the 4 modules originally ported
into ``packages/plugin_sdk/src/jarvis_sdk/``. The re-export
shim is temporary: a follow-up phase will physically move
the modules here and update all
``jarvis_sdk.{string_coerce,text_utility,result,json_store}``
import sites to ``jarvis_normalization_core.*``.
"""
from __future__ import annotations

# Re-export the public surface from each module.
from jarvis_sdk.string_coerce import (  # noqa: F401
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
)
from jarvis_sdk.text_utility import (  # noqa: F401
    truncate_utf16_safe,
    utf16_length,
)
from jarvis_sdk.result import Result  # noqa: F401
from jarvis_sdk.json_store import (  # noqa: F401
    load_json_file,
    read_json_file_with_fallback,
    save_json_file,
    write_json_file_atomically,
)
