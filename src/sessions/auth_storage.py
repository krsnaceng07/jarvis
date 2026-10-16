from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
import os


class AuthStorage:
    """Simple auth profile storage for model auth profiles.

    Loads key/credential mappings from a JSON file such as
    `config/api_keys.json`. The format is intentionally permissive: keys
    map to either primitive values or nested objects. Consumers should
    interpret fields (eg. `gemini_api_key`) according to provider needs.
    """

    def __init__(self, profiles: Dict[str, Any] | None = None) -> None:
        self._profiles: Dict[str, Any] = profiles or {}

    @classmethod
    def load_from_file(cls, path: Path | str) -> "AuthStorage":
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return cls()
            # Normalize common top-level credential keys to provider profiles
            normalized = cls._normalize_profiles(raw)
            return cls(normalized)
        except Exception:
            return cls()

    @staticmethod
    def _normalize_profiles(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize common credential shapes into provider profiles.

        Examples handled:
        - { "gemini_api_key": "..." } -> { "gemini": { "api_key": "..." } }
        - { "openrouter_api_key": "..." } -> { "openrouter": "..." }
        - Already-normalized shapes are preserved.
        """
        out: Dict[str, Any] = {}

        # Preserve explicit provider entries first
        for k, v in raw.items():
            if k in ("gemini", "google", "openrouter", "anthropic", "openai", "azure"):
                out[k] = v

        # Map common flattened keys
        gemini_key = raw.get("gemini_api_key") or raw.get("google_api_key")
        if gemini_key:
            if "gemini" not in out:
                out["gemini"] = {"api_key": gemini_key}
            if "google" not in out:
                out["google"] = {"api_key": gemini_key}
        if "openrouter_api_key" in raw and "openrouter" not in out:
            out["openrouter"] = raw["openrouter_api_key"]
        if "anthropic_api_key" in raw and "anthropic" not in out:
            out["anthropic"] = {"api_key": raw["anthropic_api_key"]}
        if "openai_api_key" in raw and "openai" not in out:
            out["openai"] = {"api_key": raw["openai_api_key"]}

        # Fallback: copy any remaining unknown keys through as-is
        for k, v in raw.items():
            if k in out:
                continue
            # skip known flattened keys we've already handled
            if k.endswith("_api_key"):
                continue
            out.setdefault(k, v)

        return out

    def get(self, profile_id: str) -> Optional[Any]:
        """Return the raw profile value (dict or primitive) for `profile_id`.

        Returns None when not found.
        """
        return self._profiles.get(profile_id)

    def get_credentials(self, provider: str, profile_id: Optional[str] = None) -> Optional[Any]:
        """Resolve credentials for a provider with precedence:

        1. Environment variables: `JARVIS_<PROVIDER>_API_KEY` or `<PROVIDER>_API_KEY` (including google/gemini aliases).
        2. If `profile_id` provided, lookup that profile in loaded profiles.
        3. Fallback to a profile keyed by provider name (or alias).

        Returns the raw stored value (primitive or dict) or None when not found.
        """
        prov_upper = provider.upper()
        candidates = [f"JARVIS_{prov_upper}_API_KEY", f"{prov_upper}_API_KEY"]
        if provider in ("google", "gemini"):
            candidates.extend(["GEMINI_API_KEY", "GOOGLE_API_KEY", "JARVIS_GEMINI_API_KEY", "JARVIS_GOOGLE_API_KEY"])

        for key_env in candidates:
            if key_env in os.environ and os.environ[key_env]:
                return os.environ[key_env]

        # If a specific profile id was requested, prefer that
        if profile_id:
            val = self.get(profile_id)
            if val is not None:
                if isinstance(val, dict) and "api_key" in val:
                    return val["api_key"]
                return val

        # Finally, try provider-named profile (with google <-> gemini alias)
        val = self.get(provider)
        if val is None and provider == "google":
            val = self.get("gemini")
        elif val is None and provider == "gemini":
            val = self.get("google")

        if val is not None:
            if isinstance(val, dict) and "api_key" in val:
                return val["api_key"]
            return val
        return None


__all__ = ["AuthStorage"]
