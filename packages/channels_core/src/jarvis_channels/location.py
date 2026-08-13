"""Location normalization and formatting.

Mirrors OpenClaw's location handling, which formats coordinates into a terse
string appended to the user body, and passes structured metadata (name, address,
caption) as untrusted metadata block for the context payload.
"""

from __future__ import annotations

import json
from typing import Any

from .types import NormalizedLocation


def format_inbound_location(text: str, loc: NormalizedLocation) -> str:
    """Format a location for the inbound message text block.
    
    Appends the terse coordinate string and the untrusted JSON metadata
    block to the message body.
    """
    lines = []
    if text.strip():
        lines.append(text.strip())
        lines.append("")
        
    # 1. Terse string
    if loc.is_live:
        prefix = "🛰 Live location"
    else:
        prefix = "📍"
        
    coords = f"{loc.latitude:.6f}, {loc.longitude:.6f}"
    acc = f" ±{loc.accuracy_m}m" if loc.accuracy_m is not None else ""
    lines.append(f"{prefix} {coords}{acc}")
    
    # 2. Structured JSON block
    metadata: dict[str, Any] = {
        "LocationLat": loc.latitude,
        "LocationLon": loc.longitude,
        "LocationSource": loc.source,
        "LocationIsLive": loc.is_live,
    }
    
    if loc.accuracy_m is not None:
        metadata["LocationAccuracy"] = loc.accuracy_m
    if loc.name is not None:
        metadata["LocationName"] = loc.name
    if loc.address is not None:
        metadata["LocationAddress"] = loc.address
    if loc.caption is not None:
        metadata["LocationCaption"] = loc.caption
        
    lines.append("")
    lines.append("Location (untrusted metadata):")
    lines.append("```json")
    lines.append(json.dumps(metadata, indent=2))
    lines.append("```")
    
    return "\n".join(lines)
