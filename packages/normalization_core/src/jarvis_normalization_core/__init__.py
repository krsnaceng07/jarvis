"""jarvis_normalization_core — Shared normalization utilities.

OpenClaw parity: mirrors
``packages/normalization-core/src/`` (string-coerce, utf16-slice,
result, json-store, etc.).
"""

from __future__ import annotations

# Re-export the public surface from each module.
from .number_coerce import (  # noqa: F401
    MAX_DATE_TIMESTAMP_MS,
    MAX_TIMER_TIMEOUT_MS,
    MAX_TIMER_TIMEOUT_SECONDS,
    as_finite_number,
    as_finite_number_in_range,
    as_non_negative_finite_number,
    as_positive_finite_number,
    as_positive_safe_integer,
    as_safe_integer_in_range,
    parse_finite_number,
    parse_strict_finite_number,
    parse_strict_integer,
)
from .json_coerce import safe_parse_json, safe_parse_json_record  # noqa: F401
from .string_coerce import (  # noqa: F401
    as_optional_record,
    lowercase_preserving_whitespace,
    normalize_lowercase_string_or_empty,
    normalize_optional_string,
    normalize_optional_trimmed_string_list,
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
    # number_coerce
    "MAX_DATE_TIMESTAMP_MS",
    "MAX_TIMER_TIMEOUT_MS",
    "MAX_TIMER_TIMEOUT_SECONDS",
    "as_finite_number",
    "as_finite_number_in_range",
    "as_non_negative_finite_number",
    "as_positive_finite_number",
    "as_positive_safe_integer",
    "as_safe_integer_in_range",
    "parse_finite_number",
    "parse_strict_finite_number",
    "parse_strict_integer",
    # json_coerce
    "safe_parse_json",
    "safe_parse_json_record",
    # string_coerce
    "as_optional_record",
    "lowercase_preserving_whitespace",
    "normalize_lowercase_string_or_empty",
    "normalize_optional_string",
    "normalize_optional_trimmed_string_list",
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
