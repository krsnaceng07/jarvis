"""Provider-declared context-window selection normalization.

OpenClaw parity:
``packages/model-catalog-core/src/model-catalog-context-windows.ts``.
Options and default are one atomic tuple: options without a valid
default would advertise a capability the picker cannot render a
selection for, so a missing or invalid default drops the option
list with it.
"""

from __future__ import annotations

from typing import Any

from jarvis_normalization_core.string_coerce import normalize_optional_string

from .model_catalog_types import (
    MODEL_CATALOG_MAX_CONTEXT_WINDOWS,
    ModelCatalogContextWindowOption,
)


def _normalize_positive_integer(value: object) -> int | None:
    # TS `Number.isInteger` accepts integer-valued floats (e.g. 131072.0).
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value.is_integer() and value > 0:
        return int(value)
    return None


def _normalize_context_windows(value: object) -> list[ModelCatalogContextWindowOption] | None:
    if not isinstance(value, list):
        return None
    seen: set[str] = set()
    options: list[ModelCatalogContextWindowOption] = []
    candidates: Any = value[:MODEL_CATALOG_MAX_CONTEXT_WINDOWS]
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        option_id = normalize_optional_string(entry.get("id")) or ""
        label = normalize_optional_string(entry.get("label")) or ""
        context_window = _normalize_positive_integer(entry.get("contextWindow"))
        if not option_id or not label or context_window is None or option_id in seen:
            continue
        seen.add(option_id)
        options.append(
            ModelCatalogContextWindowOption(
                id=option_id, label=label, context_window=context_window
            )
        )
    if not options:
        return None
    return sorted(options, key=lambda option: (option.context_window, option.id))


def normalize_model_catalog_context_window_selection(value: dict[str, object]) -> dict[str, object]:
    """Normalize ``{contextWindows, contextWindowDefault}`` as one atomic tuple."""
    context_windows = _normalize_context_windows(value.get("contextWindows"))
    default = normalize_optional_string(value.get("contextWindowDefault"))
    if context_windows and default and any(option.id == default for option in context_windows):
        return {"contextWindows": context_windows, "contextWindowDefault": default}
    return {}


__all__ = ["normalize_model_catalog_context_window_selection"]
