"""UI-Element Grounding & Set-of-Mark (SoM) Engine.

OpenClaw parity:
- UI element discovery & interactive control extraction via Windows UIAutomation
- Deterministic UIElementCache for target resolution by ID or name
- Set-of-Mark (SoM) visual annotations on screenshots
"""

from __future__ import annotations

import io
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont


@dataclass(slots=True)
class UIElement:
    """Represents a grounded interactive desktop UI control."""

    id: int
    name: str
    control_type: str
    bbox: tuple[int, int, int, int]  # (left, top, right, bottom)
    center: tuple[int, int]  # (center_x, center_y)
    is_enabled: bool = True
    class_name: str = ""
    window_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "control_type": self.control_type,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "is_enabled": self.is_enabled,
            "window_title": self.window_title,
        }


# Color mapping by control type for high-contrast visual Set-of-Mark badges
_CONTROL_TYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "Button": (0, 230, 118),  # Vibrant Emerald Green
    "SplitButton": (0, 230, 118),
    "Edit": (41, 121, 255),  # Electric Blue
    "Document": (41, 121, 255),
    "Hyperlink": (255, 145, 0),  # Vivid Amber
    "TabItem": (255, 145, 0),
    "CheckBox": (0, 229, 255),  # Cyan
    "RadioButton": (0, 229, 255),
    "MenuItem": (224, 64, 251),  # Magenta
    "ListItem": (224, 64, 251),
    "DataItem": (224, 64, 251),  # Magenta for File Explorer / Desktop items
    "TreeItem": (224, 64, 251),
    "Text": (255, 235, 59),  # Yellow
    "Custom": (129, 199, 132),  # Light Green
    "Group": (179, 157, 219),  # Light Purple
    "ComboBox": (255, 214, 0),  # Bright Yellow
    "Slider": (255, 82, 82),  # Coral Red
    "ScrollBar": (158, 158, 158),  # Gray
}
_DEFAULT_MARK_COLOR = (0, 230, 118)


class UIElementCache:
    """Thread-safe deterministic cache of interactive UI controls on the desktop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: dict[int, UIElement] = {}
        self._elements: list[UIElement] = []
        self._last_scan_time: float = 0.0
        self._window_title: str = ""

    def clear(self) -> None:
        with self._lock:
            self._by_id.clear()
            self._elements.clear()
            self._last_scan_time = 0.0
            self._window_title = ""

    def store(self, elements: Sequence[UIElement], window_title: str = "") -> None:
        with self._lock:
            self._by_id = {elem.id: elem for elem in elements}
            self._elements = list(elements)
            self._last_scan_time = time.time()
            self._window_title = window_title

    def get_by_id(self, target_id: int) -> UIElement | None:
        with self._lock:
            return self._by_id.get(target_id)

    def find_by_name(self, name: str) -> UIElement | None:
        if not name or not name.strip():
            return None
        target = name.strip().lower()

        with self._lock:
            # 1. Exact match
            for elem in self._elements:
                if elem.name.strip().lower() == target:
                    return elem

            # 2. Substring match
            for elem in self._elements:
                elem_name_low = elem.name.strip().lower()
                if elem_name_low and (target in elem_name_low or elem_name_low in target):
                    return elem

            # 3. Token overlap match
            target_tokens = set(target.split())
            best_elem: UIElement | None = None
            max_overlap = 0
            for elem in self._elements:
                elem_tokens = set(elem.name.strip().lower().split())
                overlap = len(target_tokens & elem_tokens)
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_elem = elem

            if best_elem is not None and max_overlap > 0:
                return best_elem

        return None

    def resolve_target(
        self,
        target_id: int | None = None,
        element_name: str | None = None,
    ) -> tuple[int, int] | None:
        """Resolve exact (center_x, center_y) coordinates for target_id or element_name."""
        if target_id is not None:
            elem = self.get_by_id(target_id)
            if elem:
                return elem.center

        if element_name:
            elem = self.find_by_name(element_name)
            if elem:
                return elem.center

        return None

    def get_manifest(self) -> list[dict[str, Any]]:
        with self._lock:
            return [elem.to_dict() for elem in self._elements]

    @property
    def window_title(self) -> str:
        with self._lock:
            return self._window_title

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._elements)


_GLOBAL_UI_CACHE = UIElementCache()


def get_ui_cache() -> UIElementCache:
    """Return the process-wide UI element cache."""
    return _GLOBAL_UI_CACHE


def scan_interactive_elements(
    hwnd: int | None = None,
    max_elements: int = 100,
) -> list[UIElement]:
    """Scan the foreground window (or desktop) for interactive UI controls.

    Extracts Buttons, Edit fields, CheckBoxes, Links, Menus, Tabs, and ComboBoxes.
    Returns a list of UIElement instances with 1-based IDs and bounding boxes.
    """
    if sys.platform != "win32":
        return []

    elements: list[UIElement] = []
    seen_boxes: set[tuple[int, int, int, int]] = set()
    window_title = ""

    try:
        import uiautomation as auto

        root_control = None

        # Determine target window
        if hwnd is not None and hwnd > 0:
            try:
                root_control = auto.ControlFromHandle(hwnd)
            except Exception:
                root_control = None

        if root_control is None:
            try:
                fore_hwnd = auto.GetForegroundWindow()
                if fore_hwnd:
                    root_control = auto.ControlFromHandle(fore_hwnd)
            except Exception:
                root_control = None

        if root_control is None:
            try:
                root_control = auto.GetRootControl()
            except Exception:
                return []

        if root_control is not None:
            window_title = getattr(root_control, "Name", "") or ""

            # Target control types of interest (including File Explorer DataItems, Text labels, and Tree items)
            interactive_type_ids = {
                auto.ControlType.ButtonControl: "Button",
                auto.ControlType.SplitButtonControl: "SplitButton",
                auto.ControlType.EditControl: "Edit",
                auto.ControlType.DocumentControl: "Document",
                auto.ControlType.CheckBoxControl: "CheckBox",
                auto.ControlType.RadioButtonControl: "RadioButton",
                auto.ControlType.HyperlinkControl: "Hyperlink",
                auto.ControlType.ComboBoxControl: "ComboBox",
                auto.ControlType.TabItemControl: "TabItem",
                auto.ControlType.MenuItemControl: "MenuItem",
                auto.ControlType.ListItemControl: "ListItem",
                auto.ControlType.DataItemControl: "DataItem",
                auto.ControlType.TreeItemControl: "TreeItem",
                auto.ControlType.TextControl: "Text",
                auto.ControlType.SliderControl: "Slider",
            }

            # BFS traversal over UI controls with bounded depth (extended for Windows 11 deep XAML trees)
            queue: list[tuple[Any, int]] = [(root_control, 0)]
            visited = 0

            while queue and len(elements) < max_elements and visited < 600:
                current, depth = queue.pop(0)
                visited += 1

                # Check if current control is interactive
                c_type_id = getattr(current, "ControlType", None)
                if c_type_id in interactive_type_ids:
                    rect = getattr(current, "BoundingRectangle", None)
                    if rect is not None:
                        left = int(rect.left)
                        top = int(rect.top)
                        right = int(rect.right)
                        bottom = int(rect.bottom)
                        w = right - left
                        h = bottom - top

                        # Filter out invisible or invalid controls
                        if w >= 8 and h >= 8:
                            box_tuple = (left, top, right, bottom)
                            if box_tuple not in seen_boxes:
                                seen_boxes.add(box_tuple)
                                name = str(getattr(current, "Name", "") or "").strip()
                                type_name = interactive_type_ids[c_type_id]

                                # If name is empty, try HelpText or AutomationId
                                if not name:
                                    name = str(getattr(current, "HelpText", "") or "").strip()
                                if not name and type_name in ("Edit", "Document"):
                                    name = f"Input_{len(elements) + 1}"

                                is_enabled = bool(getattr(current, "IsEnabled", True))
                                center_x = left + (w // 2)
                                center_y = top + (h // 2)

                                elem = UIElement(
                                    id=len(elements) + 1,
                                    name=name or f"{type_name}_{len(elements) + 1}",
                                    control_type=type_name,
                                    bbox=(left, top, right, bottom),
                                    center=(center_x, center_y),
                                    is_enabled=is_enabled,
                                    class_name=str(getattr(current, "ClassName", "") or ""),
                                    window_title=window_title,
                                )
                                elements.append(elem)

                # Add children to traversal queue if depth is bounded (depth 12 for modern Windows nested XAML)
                if depth < 12:
                    try:
                        children = current.GetChildren()
                        for child in children:
                            queue.append((child, depth + 1))
                    except Exception:
                        pass

    except Exception as e:
        # Graceful fallback: do not crash on unexpected automation errors
        print(f"[UI Grounding] Scan warning: {e}")

    # Fallback to win32gui visible windows if uiautomation found nothing
    if not elements:
        try:
            import win32gui

            def _enum_win_cb(h: int, extra: list[UIElement]) -> bool:
                if len(extra) >= max_elements:
                    return False
                if win32gui.IsWindowVisible(h):
                    t = win32gui.GetWindowText(h).strip()
                    cls = win32gui.GetClassName(h)
                    r = win32gui.GetWindowRect(h)
                    w = r[2] - r[0]
                    h_px = r[3] - r[1]
                    if w >= 16 and h_px >= 16 and t:
                        box = (r[0], r[1], r[2], r[3])
                        if box not in seen_boxes:
                            seen_boxes.add(box)
                            c_x = r[0] + (w // 2)
                            c_y = r[1] + (h_px // 2)
                            ctype = "Button" if "button" in cls.lower() else "Window"
                            extra.append(
                                UIElement(
                                    id=len(extra) + 1,
                                    name=t,
                                    control_type=ctype,
                                    bbox=box,
                                    center=(c_x, c_y),
                                    class_name=cls,
                                )
                            )
                return True

            win32gui.EnumWindows(_enum_win_cb, elements)
        except Exception:
            pass

    # Update global cache with freshly scanned elements
    _GLOBAL_UI_CACHE.store(elements, window_title=window_title)
    return elements


def annotate_screenshot_with_marks(
    image: Image.Image,
    elements: Sequence[UIElement],
) -> Image.Image:
    """Draw numbered Set-of-Mark (SoM) bounding boxes and label badges onto a screenshot."""
    if not elements:
        return image

    annotated = image.copy()
    draw = ImageDraw.Draw(annotated)
    img_w, img_h = annotated.size

    # Attempt to load a default or standard font
    font = None
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    for elem in elements:
        left, top, right, bottom = elem.bbox

        # Clamp bounding box coordinates to image dimensions
        left = max(0, min(left, img_w - 1))
        top = max(0, min(top, img_h - 1))
        right = max(left + 2, min(right, img_w))
        bottom = max(top + 2, min(bottom, img_h))

        color = _CONTROL_TYPE_COLORS.get(elem.control_type, _DEFAULT_MARK_COLOR)

        # 1. Draw element bounding box
        draw.rectangle([left, top, right, bottom], outline=color, width=2)

        # 2. Draw numbered badge tag [ID]
        label = f"[{elem.id}]"
        badge_w = 22 + (len(str(elem.id)) * 6)
        badge_h = 16

        # Position badge at top-left of element bounding box
        badge_top = top - badge_h
        if badge_top < 0:
            badge_top = top  # Place inside box if near screen edge
        badge_bottom = badge_top + badge_h
        badge_right = min(left + badge_w, img_w)

        # Draw badge background
        draw.rectangle([left, badge_top, badge_right, badge_bottom], fill=color)

        # Draw badge text in high-contrast black
        text_x = left + 3
        text_y = badge_top + 1
        if font is not None:
            draw.text((text_x, text_y), label, fill=(0, 0, 0), font=font)
        else:
            draw.text((text_x, text_y), label, fill=(0, 0, 0))

    return annotated


def image_to_base64_jpeg(img: Image.Image, quality: int = 80) -> str:
    """Encode PIL Image to base64 JPEG string."""
    import base64

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
