"""jarvis_learning.datasets.resource_limits — DoS and payload limits.

Protects dataset builder against denial-of-service, recursive JSON attacks,
and memory exhaustion from giant webpages or binary payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Configurable ceilings for dataset pipeline processing."""

    max_sample_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_string_length: int = 500_000  # 500k characters
    max_tool_output_length: int = 100_000  # 100k characters
    max_json_depth: int = 20
    max_samples_per_build: int = 100_000
    max_total_dataset_bytes: int = 5 * 1024 * 1024 * 1024  # 5 GB


def check_json_depth(obj: Any, current_depth: int = 0, max_depth: int = 20) -> bool:
    """Verify object does not exceed maximum nested depth."""
    if current_depth > max_depth:
        return False
    if isinstance(obj, dict):
        return all(check_json_depth(v, current_depth + 1, max_depth) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(check_json_depth(item, current_depth + 1, max_depth) for item in obj)
    return True


def validate_resource_bounds(
    data: Any,
    limits: ResourceLimits | None = None,
) -> tuple[bool, str]:
    """Validate data against resource limits.

    Returns (True, "") if within limits, or (False, reason) if rejected.
    """
    cfg = limits or ResourceLimits()

    if not check_json_depth(data, max_depth=cfg.max_json_depth):
        return False, f"REJECTED_TOO_LARGE: nested JSON depth exceeds {cfg.max_json_depth}"

    try:
        serialized = json.dumps(data)
        if len(serialized) > cfg.max_sample_bytes:
            return (
                False,
                f"REJECTED_TOO_LARGE: sample size {len(serialized)} bytes exceeds limit {cfg.max_sample_bytes}",
            )
    except Exception as e:
        return False, f"REJECTED_SERIALIZATION_ERROR: {e}"

    # Check string fields
    if isinstance(data, dict):
        user_input = data.get("user_input", "")
        if isinstance(user_input, str) and len(user_input) > cfg.max_string_length:
            return (
                False,
                f"REJECTED_TOO_LARGE: string length {len(user_input)} exceeds {cfg.max_string_length}",
            )

        tool_output = data.get("tool_result", "")
        if isinstance(tool_output, str) and len(tool_output) > cfg.max_tool_output_length:
            return (
                False,
                f"REJECTED_TOO_LARGE: tool_result length {len(tool_output)} exceeds {cfg.max_tool_output_length}",
            )

    return True, ""
