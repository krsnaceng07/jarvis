"""jarvis_normalization_core — Shared normalization utilities.

OpenClaw parity: mirrors
``packages/normalization-core/src/`` (string-coerce, utf16-slice,
result, json-store, etc.).
"""
from __future__ import annotations

# Re-export the public surface from each module.
from .string_coerce import (  # noqa: F401
    as_optional_record,
    lowercase_preserving_whitespace,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
    normalize_single_or_trimmed_string_list,
    normalize_string_entries,
    normalize_trimmed_string_list,
    unique_strings,
)
from .text_utility import (  # noqa: F401
    truncate_utf16_safe,
    utf16_length,
)
from .result import Err, Ok, Result, ResultNone  # noqa: F401
from .json_store import (  # noqa: F401
    load_json_file,
    read_json_file_with_fallback,
    save_json_file,
    write_json_file_atomically,
)

__all__ = [
    # string_coerce
    "as_optional_record",
    "lowercase_preserving_whitespace",
    "normalize_lowercase_string_or_empty",
    "normalize_optional_string",
    "normalize_single_or_trimmed_string_list",
    "normalize_string_entries",
    "normalize_trimmed_string_list",
    "unique_strings",
    # text_utility
    "truncate_utf16_safe",
    "utf16_length",
    # result
    "Err",
    "Ok",
    "Result",
    "ResultNone",
    # json_store
    "load_json_file",
    "read_json_file_with_fallback",
    "save_json_file",
    "write_json_file_atomically",
]
