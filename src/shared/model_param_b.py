"""jarvis.shared.model_param_b — ``<n>b`` parameter-size inference.

OpenClaw parity: mirrors ``openclaw-main/src/shared/model-param-b.ts``.
"""
from __future__ import annotations

import re

#: Match ``<num>b`` token; trailing boundary is a lookahead so two adjacent
#: tokens sharing one delimiter (e.g. "8b 70b" / "8b-70b") both match.
_PARAM_B_RE = re.compile(r"(?:^|[^a-z0-9])[a-z]?(\d+(?:\.\d+)?)b(?=[^a-z0-9]|$)")


def infer_param_b_from_id_or_name(text: str):
    """Infer the largest ``<n>b`` parameter-size token from a model id/name.

    Mirrors :func:`inferParamBFromIdOrName` (``shared/model-param-b.ts``).
    """
    if not isinstance(text, str):
        return None
    raw = text.lower()
    best = None
    for match in _PARAM_B_RE.finditer(raw):
        num_raw = match.group(1)
        if not num_raw:
            continue
        try:
            value = float(num_raw)
        except ValueError:
            continue
        if value <= 0:
            continue
        if best is None or value > best:
            best = value
    return best


__all__ = ["infer_param_b_from_id_or_name"]
