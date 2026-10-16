"""Field-level hardware provenance tracking.

Every hardware attribute (name, VRAM, temperature, driver) carries its discovery
source and confidence rating, preventing untraceable hardware claims.
"""

from __future__ import annotations

import dataclasses
import datetime
import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclasses.dataclass(frozen=True)
class ProvenanceValue(Generic[T]):
    """Wraps a hardware attribute with authoritative origin and confidence."""

    value: T
    source: str
    confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    captured_at_mono_ns: int = dataclasses.field(default_factory=time.monotonic_ns)
    captured_at_utc: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert provenance container to audit-grade dictionary."""
        val = self.value
        if hasattr(val, "value"):
            val = getattr(val, "value")
        return {
            "value": val,
            "source": self.source,
            "confidence": self.confidence,
            "captured_at_mono_ns": self.captured_at_mono_ns,
            "captured_at_utc": self.captured_at_utc,
        }


__all__ = ["ProvenanceValue"]
