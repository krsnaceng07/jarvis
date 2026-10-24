"""extensions/cua-computer/src/verifier.py

Visual verification and action loop detection for JARVIS computer use.
Prevents infinite clicking loops and verifies UI state transitions.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import io
import logging
from typing import Tuple


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ActionSignature:
    action_name: str
    target_id: int | None
    target_coord: Tuple[int, int] | None
    text: str | None


class ActionLoopDetector:
    """Detects when an agent repeatedly executes the exact same failing action."""

    def __init__(self, loop_threshold: int = 3, max_history: int = 12) -> None:
        self.loop_threshold = loop_threshold
        self.history: deque[ActionSignature] = deque(maxlen=max_history)

    def record_and_check(
        self,
        action_name: str,
        target_id: int | None = None,
        target_coord: Tuple[int, int] | None = None,
        text: str | None = None,
    ) -> bool:
        """Record action and return True if an action loop is detected."""
        # Non-mutating actions don't count towards loop detection
        if action_name in ("screenshot", "inspect_ui", "wait", "cursor_position"):
            return False

        sig = ActionSignature(
            action_name=action_name,
            target_id=target_id,
            target_coord=target_coord,
            text=text,
        )
        self.history.append(sig)

        if len(self.history) < self.loop_threshold:
            return False

        # Check if the last N actions are identical
        recent = list(self.history)[-self.loop_threshold:]
        first = recent[0]
        if all(r == first for r in recent):
            logger.warning("Action loop detected: action '%s' repeated %d times", action_name, self.loop_threshold)
            return True

        return False

    def reset(self) -> None:
        self.history.clear()


class VisualActionVerifier:
    """Verifies that an action caused a visible difference on screen."""

    def __init__(self, min_changed_pixels_ratio: float = 0.0005) -> None:
        self.min_ratio = min_changed_pixels_ratio

    def grab_screenshot_bytes(self) -> bytes | None:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None

    def compare(self, before_bytes: bytes | None, after_bytes: bytes | None) -> Tuple[bool, float]:
        """Compare before and after screenshot images.

        Returns (state_changed, difference_ratio).
        """
        if not before_bytes or not after_bytes:
            return True, 0.0

        if before_bytes == after_bytes:
            return False, 0.0

        try:
            from PIL import Image, ImageChops

            img1 = Image.open(io.BytesIO(before_bytes)).convert("RGB")
            img2 = Image.open(io.BytesIO(after_bytes)).convert("RGB")

            diff = ImageChops.difference(img1, img2)
            bbox = diff.getbbox()
            if not bbox:
                return False, 0.0

            # Compute approximate diff ratio
            stat = diff.histogram()
            non_zero = sum(stat[1:])  # Ignore 0-diff pixels
            total = img1.width * img1.height * 3
            ratio = non_zero / float(total) if total > 0 else 0.0
            return ratio >= self.min_ratio, ratio
        except Exception as e:
            logger.debug("Visual verification fallback: %s", e)
            return True, 0.0


__all__ = ["ActionLoopDetector", "ActionSignature", "VisualActionVerifier"]
