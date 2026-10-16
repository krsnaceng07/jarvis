"""Strategy Compatibility Fingerprinting and Expiration Governance.

Prevents applying strategies when:
1. Tool argument or return schemas have evolved (schema hash mismatch)
2. Operating system or runtime architecture differs
3. Strategies have exceeded their maximum validity TTL without live re-verification
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


DEFAULT_STRATEGY_MAX_AGE_DAYS = 90.0


@dataclass(slots=True)
class CompatibilityFingerprint:
    """Represents the environment and tool definition state when a strategy was formed."""

    tool_name: str
    tool_schema_hash: str
    os_platform: str
    python_version: str = sys.version.split()[0]
    created_timestamp: float = field(default_factory=time.time)
    last_verified_timestamp: float = field(default_factory=time.time)

    @classmethod
    def compute_schema_hash(cls, schema: Dict[str, Any]) -> str:
        """Compute deterministic SHA-256 digest of tool schema."""
        canonical_json = json.dumps(schema, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]

    def check_compatibility(
        self,
        current_schema_hash: Optional[str] = None,
        max_age_days: float = DEFAULT_STRATEGY_MAX_AGE_DAYS,
        current_time: Optional[float] = None,
    ) -> Tuple[bool, Optional[str]]:
        now = current_time if current_time is not None else time.time()

        # 1. OS check
        current_os = sys.platform
        if not current_os.startswith(self.os_platform[:3]):
            return (
                False,
                f"OS platform mismatch: recorded {self.os_platform}, running on {current_os}",
            )

        # 2. Tool schema evolution check
        if current_schema_hash and current_schema_hash != self.tool_schema_hash:
            return (
                False,
                f"Tool schema evolved for '{self.tool_name}': hash {current_schema_hash} != recorded {self.tool_schema_hash}",
            )

        # 3. Staleness / TTL check
        age_days = (now - self.last_verified_timestamp) / 86400.0
        if age_days > max_age_days:
            return (
                False,
                f"Strategy is stale: {age_days:.1f} days since last verification exceeds {max_age_days} days limit",
            )

        return True, None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "tool_schema_hash": self.tool_schema_hash,
            "os_platform": self.os_platform,
            "python_version": self.python_version,
            "created_timestamp": self.created_timestamp,
            "last_verified_timestamp": self.last_verified_timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CompatibilityFingerprint:
        return cls(
            tool_name=data["tool_name"],
            tool_schema_hash=data["tool_schema_hash"],
            os_platform=data["os_platform"],
            python_version=data.get("python_version", sys.version.split()[0]),
            created_timestamp=float(data.get("created_timestamp", time.time())),
            last_verified_timestamp=float(data.get("last_verified_timestamp", time.time())),
        )
