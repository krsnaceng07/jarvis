"""extensions/browser/selenium_dom_engine.py
OpenClaw-compliant Selenium WebDriver & Dynamic DOM Manipulation Engine for JARVIS.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    InvalidSessionIdException,
    NoSuchElementException,
    NoSuchWindowException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger("jarvis.browser.selenium_dom")


@dataclass(frozen=True)
class SeleniumBrowserConfig:
    headless: bool = False
    detach_browser: bool = True
    start_maximized: bool = True
    user_data_dir: Path = field(
        default_factory=lambda: Path.home() / ".jarvis" / "browser" / "chrome_profile"
    )
    page_load_timeout: int = 25
    explicit_wait_timeout: int = 12
    poll_frequency: float = 0.25
    max_dom_elements: int = 60
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )


class SeleniumDOMEngine:
    """Stateful, thread-safe Selenium WebDriver engine that manipulates web pages

    through direct DOM tree inspection, explicit waits, and Set-of-Mark (ref) tagging.
    """

    def __init__(self, config: SeleniumBrowserConfig | None = None) -> None:
        self.config = config or SeleniumBrowserConfig()
        self.driver: webdriver.Chrome | None = None
        self.wait: WebDriverWait | None = None
        self._lock = threading.RLock()

    def _ensure_driver(self) -> webdriver.Chrome:
        """Initializes or recovers the persistent Chrome WebDriver session."""
        with self._lock:
            if self.driver is not None:
                try:
                    _ = self.driver.current_url
                    return self.driver
                except (InvalidSessionIdException, NoSuchWindowException, WebDriverException):
                    logger.info("Chrome session disconnected; re-initializing WebDriver...")
                    self.quit()

            opts = Options()
            if self.config.headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--remote-debugging-port=0")
                opts.add_argument("--no-sandbox")
            if self.config.start_maximized:
                opts.add_argument("--start-maximized")
            if self.config.detach_browser and not self.config.headless:
                opts.add_experimental_option("detach", True)

            self.config.user_data_dir.mkdir(parents=True, exist_ok=True)
            opts.add_argument(f"--user-data-dir={self.config.user_data_dir}")
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_argument("--disable-infobars")
            opts.add_argument("--disable-notifications")
            opts.add_argument("--no-first-run")
            opts.add_argument("--no-default-browser-check")
            opts.add_argument(f"--user-agent={self.config.user_agent}")
            opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            opts.add_experimental_option("useAutomationExtension", False)

            self.driver = webdriver.Chrome(options=opts)
            self.driver.set_page_load_timeout(self.config.page_load_timeout)

            # Remove navigator.webdriver flag via Chrome DevTools Protocol
            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": (
                            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                        )
                    },
                )
            except Exception as exc:
                logger.debug("CDP stealth script injection skipped: %s", exc)

            self.wait = WebDriverWait(
                self.driver,
                timeout=self.config.explicit_wait_timeout,
                poll_frequency=self.config.poll_frequency,
                ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
            )
            return self.driver

    def wait_for_dom_ready(self, timeout: int = 10) -> None:
        driver = self._ensure_driver()
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.debug("DOM readyState wait timed out after %ds.", timeout)

    def safe_click(self, element: WebElement) -> None:
        driver = self._ensure_driver()
        # Antigravity-parity: Visual human-like cursor glide, glowing element outline, and click ripple
        try:
            driver.execute_script(
                """
                const el = arguments[0];
                el.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'smooth'});

                // 1. Injected human-like virtual cursor (neon cyan arrow)
                let cursor = document.getElementById('jarvis-human-cursor');
                if (!cursor) {
                    cursor = document.createElement('div');
                    cursor.id = 'jarvis-human-cursor';
                    cursor.style.cssText = (
                        'position:fixed; z-index:2147483647; pointer-events:none; width:24px; height:24px; ' +
                        'top:20px; left:20px; transition:top 0.24s cubic-bezier(0.25, 1, 0.5, 1), left 0.24s cubic-bezier(0.25, 1, 0.5, 1); ' +
                        'filter:drop-shadow(0 2px 8px rgba(0,229,255,0.85));'
                    );
                    cursor.innerHTML = '<svg viewBox="0 0 24 24" width="24" height="24" fill="#00e5ff" stroke="#000" stroke-width="1.5"><path d="M4 2 L20 10 L12 13 L8 21 Z"/></svg>';
                    document.body.appendChild(cursor);
                }

                // 2. Active DOM Automation Indicator Banner
                let banner = document.getElementById('jarvis-dom-banner');
                if (!banner) {
                    banner = document.createElement('div');
                    banner.id = 'jarvis-dom-banner';
                    banner.style.cssText = (
                        'position:fixed; top:10px; right:16px; z-index:2147483647; background:rgba(8,14,28,0.88); ' +
                        'color:#00e5ff; border:1px solid #00e5ff; border-radius:6px; padding:4px 10px; font:bold 11px monospace; ' +
                        'pointer-events:none; box-shadow:0 0 14px rgba(0,229,255,0.45); backdrop-filter:blur(4px);'
                    );
                    banner.innerText = '⚡ JARVIS DOM ENGINE ACTIVE';
                    document.body.appendChild(banner);
                }

                // 3. Move cursor to element center
                const r = el.getBoundingClientRect();
                const targetX = Math.round(r.left + r.width / 2);
                const targetY = Math.round(r.top + r.height / 2);
                cursor.style.left = targetX + 'px';
                cursor.style.top = targetY + 'px';

                // 4. Highlight target element with glowing outline
                const prevOutline = el.style.outline;
                const prevShadow = el.style.boxShadow;
                el.style.outline = '3px solid #00e5ff';
                el.style.boxShadow = '0 0 16px rgba(0, 229, 255, 0.9)';

                // 5. Visual click ripple wave
                const ripple = document.createElement('div');
                ripple.style.cssText = (
                    'position:fixed; z-index:2147483646; pointer-events:none; border-radius:50%; ' +
                    'border:2px solid #00e5ff; background:rgba(0,229,255,0.35); width:8px; height:8px; ' +
                    'left:' + targetX + 'px; top:' + targetY + 'px; transform:translate(-50%,-50%); transition:all 0.35s ease-out;'
                );
                document.body.appendChild(ripple);
                requestAnimationFrame(() => {
                    ripple.style.width = '40px';
                    ripple.style.height = '40px';
                    ripple.style.opacity = '0';
                });
                setTimeout(() => ripple.remove(), 400);
                setTimeout(() => {
                    el.style.outline = prevOutline;
                    el.style.boxShadow = prevShadow;
                }, 550);
                """,
                element,
            )
        except Exception:
            pass

        time.sleep(0.15)
        try:
            element.click()
        except (ElementClickInterceptedException, WebDriverException):
            driver.execute_script("arguments[0].click();", element)

    # -------------------------------------------------------------------------
    # DOM Set-of-Mark (SoM) Snapshot & Element Indexing
    # -------------------------------------------------------------------------
    def snapshot_dom(self, annotate: bool = False) -> dict[str, Any]:
        """Tags all visible interactive DOM elements with `data-jarvis-ref=\"<int>\"`

        and returns a structured element map for deterministic LLM control.
        """
        driver = self._ensure_driver()
        try:
            elements: list[dict[str, Any]] = driver.execute_script(
                """
                const maxItems = arguments[0];
                const annotate = arguments[1];

                // Remove old visual badges if any
                document.querySelectorAll('.jarvis-som-badge').forEach(el => el.remove());

                const selectors = [
                    'a[href]', 'button', 'input:not([type="hidden"])',
                    'textarea', 'select', '[role="button"]', '[role="link"]',
                    '[role="tab"]', '[role="menuitem"]', '[contenteditable="true"]',
                    'ytd-video-renderer a#video-title'
                ];
                const rawNodes = Array.from(document.querySelectorAll(selectors.join(',')));

                function isVisible(el) {
                    const r = el.getBoundingClientRect();
                    if (r.width < 4 || r.height < 4) return false;
                    if (r.bottom < 0 || r.top > window.innerHeight) return false;
                    const style = window.getComputedStyle(el);
                    return style.visibility !== 'hidden' && style.display !== 'none' && parseFloat(style.opacity || '1') > 0;
                }

                const results = [];
                let refCounter = 1;

                for (const el of rawNodes) {
                    if (!isVisible(el)) continue;
                    const label = (
                        el.innerText ||
                        el.value ||
                        el.getAttribute('aria-label') ||
                        el.getAttribute('placeholder') ||
                        el.getAttribute('title') ||
                        ''
                    ).replace(/\\s+/g, ' ').trim().slice(0, 90);

                    const tag = el.tagName.toLowerCase();
                    if (!label && tag !== 'input' && tag !== 'textarea') continue;

                    const refId = refCounter++;
                    el.setAttribute('data-jarvis-ref', String(refId));

                    if (annotate) {
                        const r = el.getBoundingClientRect();
                        const badge = document.createElement('div');
                        badge.className = 'jarvis-som-badge';
                        badge.textContent = '[' + refId + ']';
                        badge.style.cssText = (
                            'position:fixed;z-index:2147483647;background:#ff0055;color:#fff;' +
                            'font:bold 11px monospace;padding:1px 4px;border-radius:3px;' +
                            'pointer-events:none;top:' + Math.max(0, Math.round(r.top)) + 'px;' +
                            'left:' + Math.max(0, Math.round(r.left)) + 'px;'
                        );
                        document.body.appendChild(badge);
                    }

                    results.push({
                        ref: refId,
                        tag: tag,
                        type: el.getAttribute('type') || '',
                        label: label
                    });

                    if (results.length >= maxItems) break;
                }
                return results;
                """,
                self.config.max_dom_elements,
                annotate,
            )
            return {
                "status": "ok",
                "url": driver.current_url,
                "title": driver.title,
                "tab_count": len(driver.window_handles),
                "elements": elements,
            }
        except WebDriverException as exc:
            logger.error("DOM snapshot failed: %s", exc)
            return {"status": "error", "error": str(exc)}

    # -------------------------------------------------------------------------
    # A) Google Search & Top Result Snippet/Title Extraction
    # -------------------------------------------------------------------------
    def google_search(self, query: str) -> dict[str, Any]:
        driver = self._ensure_driver()
        assert self.wait is not None
        try:
            driver.get("https://www.google.com")
            self.wait_for_dom_ready()

            # Dismiss cookie consent if present
            try:
                consent = driver.find_elements(
                    By.XPATH,
                    "//button[.//div[contains(text(), 'Accept all') or contains(text(), 'I agree')]]",
                )
                if consent:
                    self.safe_click(consent[0])
            except Exception:
                pass

            search_box = self.wait.until(EC.element_to_be_clickable((By.NAME, "q")))
            search_box.clear()
            search_box.send_keys(query)
            search_box.send_keys(Keys.RETURN)

            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div#search, div#rso"))
            )
            self.wait_for_dom_ready()

            # 1. Featured Snippet / Knowledge Panel
            for sel in [
                "div.hgKElc",
                "div[data-attrid='wa:/description']",
                "span.ILfuVd",
                "div.Z0LcW",
            ]:
                for el in driver.find_elements(By.CSS_SELECTOR, sel):
                    txt = el.text.strip()
                    if len(txt) > 25:
                        return {
                            "status": "ok",
                            "query": query,
                            "source": "featured_snippet",
                            "summary": txt[:500],
                            "url": driver.current_url,
                        }

            # 2. Top Organic Result
            for res in driver.find_elements(By.CSS_SELECTOR, "div#rso div.g"):
                try:
                    h3 = res.find_element(By.CSS_SELECTOR, "h3")
                    title = h3.text.strip()
                    if not title:
                        continue
                    snippet = ""
                    for s_sel in ["div.VwiC3b", "span.aCOpRe", "div[data-sncf='1']"]:
                        s_els = res.find_elements(By.CSS_SELECTOR, s_sel)
                        if s_els and s_els[0].text.strip():
                            snippet = s_els[0].text.strip()
                            break
                    return {
                        "status": "ok",
                        "query": query,
                        "source": "organic_top_result",
                        "title": title,
                        "summary": snippet[:500],
                        "url": driver.current_url,
                    }
                except NoSuchElementException:
                    continue

            return {
                "status": "ok",
                "query": query,
                "summary": f"Searched Google for '{query}', results are open on screen.",
                "snapshot": self.snapshot_dom(),
            }
        except Exception as exc:
            logger.error("Google search DOM error: %s", exc)
            return {"status": "error", "error": str(exc)}

    # -------------------------------------------------------------------------
    # B) YouTube Search & Auto-Play First Video
    # -------------------------------------------------------------------------
    def youtube_play(self, query: str) -> dict[str, Any]:
        driver = self._ensure_driver()
        assert self.wait is not None
        try:
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            driver.get(url)
            self.wait_for_dom_ready()

            locator = (By.CSS_SELECTOR, "ytd-video-renderer a#video-title")
            self.wait.until(EC.presence_of_all_elements_located(locator))

            for link in driver.find_elements(*locator):
                if not link.is_displayed():
                    continue
                title = (link.get_attribute("title") or link.text or query).strip()
                href = link.get_attribute("href") or ""
                if "/watch?" in href or "/shorts/" in href:
                    self.safe_click(link)
                    return {
                        "status": "ok",
                        "action": "youtube_play",
                        "playing_title": title,
                        "url": driver.current_url,
                    }

            return {"status": "error", "error": f"No playable video found for '{query}'."}
        except Exception as exc:
            logger.error("YouTube play DOM error: %s", exc)
            return {"status": "error", "error": str(exc)}

    # -------------------------------------------------------------------------
    # C) General Navigation, Dynamic DOM Click, Type, Scroll, Read, Tabs
    # -------------------------------------------------------------------------
    def navigate(self, target: str, annotate: bool = False) -> dict[str, Any]:
        driver = self._ensure_driver()
        cleaned = target.strip()
        lower = cleaned.lower()

        shortcuts = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "github": "https://www.github.com",
            "gmail": "https://mail.google.com",
            "wikipedia": "https://www.wikipedia.org",
            "reddit": "https://www.reddit.com",
            "binance": "https://www.binance.com",
            "daraz": "https://www.daraz.com.np",
        }
        if lower in shortcuts:
            url = shortcuts[lower]
        elif lower.startswith(("http://", "https://", "data:", "file://")):
            url = cleaned
        elif "." in lower and " " not in lower:
            url = f"https://{cleaned}"
        else:
            return self.google_search(cleaned)

        try:
            driver.get(url)
            self.wait_for_dom_ready()
            return self.snapshot_dom(annotate=annotate)
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def click_element(
        self,
        ref: int | None = None,
        text: str | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
        driver = self._ensure_driver()
        try:
            # 1. Click by deterministic DOM Set-of-Mark ref ID
            if ref is not None:
                els = driver.find_elements(By.CSS_SELECTOR, f"[data-jarvis-ref='{int(ref)}']")
                if els:
                    self.safe_click(els[0])
                    self.wait_for_dom_ready(timeout=5)
                    return {
                        "status": "ok",
                        "clicked_ref": ref,
                        "url": driver.current_url,
                        "title": driver.title,
                    }

            # 2. Click by CSS selector
            if selector:
                els = driver.find_elements(By.CSS_SELECTOR, selector)
                if els:
                    self.safe_click(els[0])
                    self.wait_for_dom_ready(timeout=5)
                    return {
                        "status": "ok",
                        "clicked_selector": selector,
                        "url": driver.current_url,
                    }

            # 3. Click by visible text / aria-label / title via JS DOM traversal
            if text:
                matched: WebElement | None = driver.execute_script(
                    """
                    const q = arguments[0].toLowerCase().trim();
                    const nodes = Array.from(document.querySelectorAll(
                        'a, button, input[type="submit"], input[type="button"], [role="button"], [role="link"], [role="tab"], [onclick], span, div'
                    ));
                    function vis(el) {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                    }
                    function lbl(el) {
                        return (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title') || '').toLowerCase().trim();
                    }
                    const v = nodes.filter(vis);
                    for (const el of v) { if (lbl(el) === q) return el; }
                    for (const el of v) { if (lbl(el).startsWith(q)) return el; }
                    for (const el of v) { if (lbl(el).includes(q)) return el; }
                    return null;
                    """,
                    text,
                )
                if matched is not None:
                    self.safe_click(matched)
                    self.wait_for_dom_ready(timeout=5)
                    return {
                        "status": "ok",
                        "clicked_text": text,
                        "url": driver.current_url,
                        "title": driver.title,
                    }

            return {
                "status": "error",
                "error": f"Element not found (ref={ref}, text={text}, selector={selector}).",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def type_text(
        self,
        value: str,
        ref: int | None = None,
        text_hint: str | None = None,
        selector: str | None = None,
        submit: bool = True,
    ) -> dict[str, Any]:
        driver = self._ensure_driver()
        try:
            target_el: WebElement | None = None
            if ref is not None:
                els = driver.find_elements(By.CSS_SELECTOR, f"[data-jarvis-ref='{int(ref)}']")
                if els:
                    target_el = els[0]
            if target_el is None and selector:
                els = driver.find_elements(By.CSS_SELECTOR, selector)
                if els:
                    target_el = els[0]
            if target_el is None:
                target_el = driver.execute_script(
                    """
                    const hint = (arguments[0] || '').toLowerCase().trim();
                    const inputs = Array.from(document.querySelectorAll(
                        'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]), textarea, [contenteditable="true"]'
                    )).filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    if (hint) {
                        for (const el of inputs) {
                            const meta = (
                                (el.getAttribute('placeholder') || '') + ' ' +
                                (el.getAttribute('aria-label') || '') + ' ' +
                                (el.getAttribute('name') || '') + ' ' +
                                (el.id || '')
                            ).toLowerCase();
                            if (meta.includes(hint)) return el;
                        }
                    }
                    const active = document.activeElement;
                    if (active && inputs.includes(active)) return active;
                    return inputs.length > 0 ? inputs[0] : null;
                    """,
                    text_hint or "",
                )

            if target_el is None:
                return {"status": "error", "error": "No visible input field found in DOM."}

            self.safe_click(target_el)
            try:
                target_el.clear()
            except Exception:
                pass
            target_el.send_keys(value)
            if submit:
                target_el.send_keys(Keys.RETURN)
                self.wait_for_dom_ready(timeout=5)

            return {
                "status": "ok",
                "typed": value,
                "submitted": submit,
                "url": driver.current_url,
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def scroll(self, direction: str = "down", amount: int = 650) -> dict[str, Any]:
        driver = self._ensure_driver()
        d = direction.lower().strip()
        if d == "down":
            driver.execute_script(f"window.scrollBy({{top: {amount}, behavior: 'smooth'}});")
        elif d == "up":
            driver.execute_script(f"window.scrollBy({{top: -{amount}, behavior: 'smooth'}});")
        elif d == "top":
            driver.execute_script("window.scrollTo({top: 0, behavior: 'smooth'});")
        elif d == "bottom":
            driver.execute_script(
                "window.scrollTo({top: document.body.scrollHeight, behavior: 'smooth'});"
            )
        return {"status": "ok", "scrolled": d, "url": driver.current_url}

    def extract_text(self, max_chars: int = 4000) -> dict[str, Any]:
        driver = self._ensure_driver()
        body_text: str = driver.execute_script(
            "return (document.querySelector('main, article') || document.body).innerText || '';"
        )
        cleaned = re.sub(r"\n{3,}", "\n\n", body_text.strip())[:max_chars]
        return {
            "status": "ok",
            "title": driver.title,
            "url": driver.current_url,
            "content": cleaned,
        }

    def execute_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Unified dispatcher called by OpenClaw tool_pipeline / app.py."""
        with self._lock:
            action = str(args.get("action") or "navigate").lower().strip()
            url_or_query = str(
                args.get("url") or args.get("query") or args.get("text") or ""
            ).strip()
            ref = (
                int(args["ref"])
                if args.get("ref") is not None and str(args["ref"]).isdigit()
                else None
            )
            selector = args.get("selector")
            annotate = bool(args.get("annotate", False))

            if action in {"google_search", "search_google", "search"}:
                return self.google_search(url_or_query)
            if action in {"youtube_play", "play_youtube", "youtube"}:
                return self.youtube_play(url_or_query)
            if action in {"open", "navigate", "goto"}:
                return self.navigate(url_or_query, annotate=annotate)
            if action in {"snapshot", "inspect", "dom_snapshot", "screenshot"}:
                return self.snapshot_dom(annotate=annotate)
            if action == "click":
                return self.click_element(ref=ref, text=args.get("text"), selector=selector)
            if action in {"type", "fill"}:
                val = str(args.get("value") or args.get("text") or "")
                hint = args.get("field_hint") or args.get("selector")
                submit = bool(args.get("submit", True))
                return self.type_text(
                    value=val,
                    ref=ref,
                    text_hint=hint,
                    selector=selector,
                    submit=submit,
                )
            if action == "act":
                kind = str(args.get("kind") or "click").lower().strip()
                if kind in {"click", "clickcoords"}:
                    return self.click_element(ref=ref, text=args.get("text"), selector=selector)
                if kind in {"type", "fill", "press"}:
                    val = str(args.get("value") or args.get("text") or "")
                    hint = args.get("field_hint") or args.get("selector")
                    submit = bool(args.get("submit", True))
                    return self.type_text(
                        value=val,
                        ref=ref,
                        text_hint=hint,
                        selector=selector,
                        submit=submit,
                    )
                if kind in {"scroll", "scrollintoview"}:
                    return self.scroll(direction=str(args.get("direction") or "down"))
                if kind in {"go_back", "back"}:
                    self._ensure_driver().back()
                    return {
                        "status": "ok",
                        "action": "back",
                        "url": self._ensure_driver().current_url,
                    }
                if kind in {"go_forward", "forward"}:
                    self._ensure_driver().forward()
                    return {
                        "status": "ok",
                        "action": "forward",
                        "url": self._ensure_driver().current_url,
                    }
                if kind in {"reload", "refresh"}:
                    self._ensure_driver().refresh()
                    return {
                        "status": "ok",
                        "action": "reload",
                        "url": self._ensure_driver().current_url,
                    }
                if kind in {"close", "quit"}:
                    self.quit()
                    return {"status": "ok", "action": "closed_browser"}
                return {"status": "error", "error": f"Unsupported act kind: {kind}"}
            if action == "scroll":
                return self.scroll(direction=str(args.get("direction") or "down"))
            if action in {"extract_text", "read_page", "read"}:
                return self.extract_text()
            if action in {"go_back", "back"}:
                self._ensure_driver().back()
                return {"status": "ok", "action": "back", "url": self._ensure_driver().current_url}
            if action in {"go_forward", "forward"}:
                self._ensure_driver().forward()
                return {
                    "status": "ok",
                    "action": "forward",
                    "url": self._ensure_driver().current_url,
                }
            if action in {"reload", "refresh"}:
                self._ensure_driver().refresh()
                return {
                    "status": "ok",
                    "action": "reload",
                    "url": self._ensure_driver().current_url,
                }
            if action in {"close", "quit"}:
                self.quit()
                return {"status": "ok", "action": "closed_browser"}

            return {"status": "error", "error": f"Unsupported browser action: {action}"}

    def quit(self) -> None:
        with self._lock:
            if self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                finally:
                    self.driver = None
                    self.wait = None


_ENGINE_INSTANCE: SeleniumDOMEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_selenium_engine(config: SeleniumBrowserConfig | None = None) -> SeleniumDOMEngine:
    global _ENGINE_INSTANCE
    with _ENGINE_LOCK:
        if _ENGINE_INSTANCE is None:
            _ENGINE_INSTANCE = SeleniumDOMEngine(config=config)
        return _ENGINE_INSTANCE
