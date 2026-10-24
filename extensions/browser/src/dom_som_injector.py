"""DOM Set-of-Mark (SoM) and interactive element injection engine for JARVIS Browser.

Identifies visible interactive DOM elements, assigns deterministic integer reference IDs
([ref=1], [ref=2], ...), optionally renders non-intrusive Set-of-Mark visual badges
for vision/screenshots, and extracts a compact, token-efficient element map for LLMs.
"""

from __future__ import annotations

from typing import Any


SOM_INJECTOR_JS = """(annotate) => {
    // 1. Remove existing badges if any
    document.querySelectorAll('.jarvis-som-badge').forEach(b => b.remove());

    const isVisible = (el) => {
        if (!el || el.nodeType !== 1) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        
        // Element must be within or near the visible viewport
        const vh = window.innerHeight || document.documentElement.clientHeight;
        const vw = window.innerWidth || document.documentElement.clientWidth;
        return (
            rect.bottom >= -50 &&
            rect.right >= -50 &&
            rect.top <= vh + 150 &&
            rect.left <= vw + 150
        );
    };

    const interactiveSelectors = [
        'a[href]', 'button', 'input:not([type="hidden"])', 'textarea', 'select',
        '[role="button"]', '[role="link"]', '[role="tab"]', '[role="menuitem"]',
        '[role="checkbox"]', '[role="switch"]', '[role="searchbox"]', '[role="textbox"]',
        '[role="combobox"]', '[role="option"]', '[contenteditable="true"]',
        '[tabindex]:not([tabindex="-1"])', '[onclick]', 'summary',
        // YouTube specific interactive selectors
        '#video-title', 'ytd-thumbnail a', '#search-icon-legacy'
    ];

    const rawElements = Array.from(document.querySelectorAll(interactiveSelectors.join(', ')));
    const visibleElements = [];
    const seen = new Set();

    for (const el of rawElements) {
        if (seen.has(el)) continue;
        if (!isVisible(el)) continue;
        seen.add(el);
        visibleElements.push(el);
        if (visibleElements.length >= 75) break;
    }

    const results = [];
    visibleElements.forEach((el, index) => {
        const ref = index + 1;
        el.setAttribute('data-jarvis-ref', String(ref));
        el.setAttribute('data-ref', `e${ref}`);

        // Compute accessible, clean label
        const tag = el.tagName.toLowerCase();
        const type = el.getAttribute('type') || undefined;
        const placeholder = el.getAttribute('placeholder') || undefined;
        const ariaLabel = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || undefined;
        const title = el.getAttribute('title') || undefined;
        const name = el.getAttribute('name') || undefined;
        const role = el.getAttribute('role') || undefined;
        const innerText = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 90);

        const label = ariaLabel || placeholder || title || innerText || name || el.getAttribute('value') || '';

        const rect = el.getBoundingClientRect();
        results.push({
            ref: ref,
            tag: tag,
            type: type,
            role: role,
            label: label,
            placeholder: placeholder,
            bbox: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                width: Math.round(rect.width),
                height: Math.round(rect.height)
            }
        });

        // If annotate=True, draw Set-of-Mark numbered badge on top of element
        if (annotate) {
            const badge = document.createElement('div');
            badge.className = 'jarvis-som-badge';
            badge.innerText = `[${ref}]`;
            badge.style.position = 'fixed';
            badge.style.left = `${Math.max(0, Math.round(rect.left))}px`;
            badge.style.top = `${Math.max(0, Math.round(rect.top))}px`;
            badge.style.background = '#e60049';
            badge.style.color = '#ffffff';
            badge.style.fontSize = '11px';
            badge.style.fontFamily = 'monospace, sans-serif';
            badge.style.fontWeight = 'bold';
            badge.style.padding = '1px 4px';
            badge.style.borderRadius = '3px';
            badge.style.zIndex = '2147483647';
            badge.style.pointerEvents = 'none';
            badge.style.boxShadow = '0 1px 3px rgba(0,0,0,0.8)';
            badge.style.lineHeight = '14px';
            document.body.appendChild(badge);
        }
    });

    return results;
}"""


SOM_CLEANUP_JS = """() => {
    document.querySelectorAll('.jarvis-som-badge').forEach(b => b.remove());
}"""


async def inject_set_of_marks(
    page: Any,
    annotate: bool = False,
    max_elements: int = 75,
) -> list[dict[str, Any]]:
    """Inject Set-of-Mark attributes and extract interactive element map."""
    try:
        raw_elements = await page.evaluate(SOM_INJECTOR_JS, annotate)
        if isinstance(raw_elements, list):
            return raw_elements[:max_elements]
    except Exception:
        pass
    return []


async def cleanup_set_of_marks(page: Any) -> None:
    """Remove temporary visual Set-of-Mark overlay badges from the page."""
    try:
        await page.evaluate(SOM_CLEANUP_JS)
    except Exception:
        pass


def format_som_elements_summary(
    elements: list[dict[str, Any]],
    title: str = "",
    url: str = "",
    max_items: int = 40,
) -> str:
    """Format extracted interactive elements into a concise LLM prompt summary."""
    lines: list[str] = []
    if title or url:
        lines.append(f"Webpage: {title or 'Untitled'} ({url or 'about:blank'})")
    lines.append(
        "Interactive Elements (Use browser(action='click', ref=X) or browser(action='type', ref=X, value='...')):"
    )

    for el in elements[:max_items]:
        ref = el.get("ref")
        tag = el.get("tag", "element")
        t_type = el.get("type")
        label = str(el.get("label") or "").strip()
        ph = str(el.get("placeholder") or "").strip()

        type_str = f" ({t_type})" if t_type else ""
        ph_str = f" [placeholder: '{ph}']" if ph and ph != label else ""
        label_str = f' "{label}"' if label else ""
        lines.append(f"  [{ref}] {tag}{type_str}:{label_str}{ph_str}")

    if len(elements) > max_items:
        lines.append(f"  ... and {len(elements) - max_items} more interactive elements.")

    return "\n".join(lines)
