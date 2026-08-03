"""jarvis.shared.env_var_candidates — environment-variable candidate helpers.

OpenClaw parity: mirrors ``openclaw-main/src/shared/env-var-candidates.ts``.
"""
from __future__ import annotations

from typing import Dict, Iterable, List


def append_unique_env_var_candidates(
    target: Dict[str, List[str]],
    owner_id: str,
    keys: Iterable[str],
) -> None:
    """Append normalized, unique environment-variable candidates to a bucket.

    Mirrors :func:`appendUniqueEnvVarCandidates`
    (``shared/env-var-candidates.ts``).
    """
    normalized_owner = owner_id.strip()
    keys_list = list(keys)
    if not normalized_owner or len(keys_list) == 0:
        return
    bucket = target.setdefault(normalized_owner, [])
    seen = set(bucket)
    for key in keys_list:
        normalized_key = key.strip() if isinstance(key, str) else ""
        if not normalized_key or normalized_key in seen:
            continue
        seen.add(normalized_key)
        bucket.append(normalized_key)


__all__ = ["append_unique_env_var_candidates"]
