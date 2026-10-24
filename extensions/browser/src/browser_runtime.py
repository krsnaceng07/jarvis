"""Playwright runtime lifecycle, tab management, and page automation.

Mirrors OpenClaw's ``extensions/browser/src/browser/`` subsystem:
- Automatic Chromium/Chrome/Edge executable detection across platforms.
- Isolated persistent contexts with disk space safety.
- Multi-tab tracking by unique targetId.
- ARIA snapshots, screenshot captures, innerText, and interaction dispatch.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        async_playwright,
    )
except ImportError:
    async_playwright = None
    Playwright = Any  # type: ignore[misc,assignment]
    Browser = Any  # type: ignore[misc,assignment]
    BrowserContext = Any  # type: ignore[misc,assignment]
    Page = Any  # type: ignore[misc,assignment]

from .browser_profiles import resolve_browser_config, resolve_profile
from .config import ResolvedBrowserConfig, ResolvedBrowserProfile
from .dom_som_injector import (
    cleanup_set_of_marks,
    format_som_elements_summary,
    inject_set_of_marks,
)


def find_system_chromium() -> str | None:
    """Find installed Chrome or Edge executable across platforms.

    Mirrors OpenClaw's ``chrome.executables.ts``.
    """
    if sys.platform == "win32":
        candidates = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    else:  # linux
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/usr/bin/microsoft-edge-stable",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p

    # Check PATH
    for exe in ("google-chrome", "chrome", "chromium", "msedge"):
        found = shutil.which(exe)
        if found:
            return found

    return None


def is_port_open(host: str = "127.0.0.1", port: int = 9222) -> bool:
    """Fast non-blocking check whether a TCP port is actively listening."""
    import socket

    try:
        with socket.create_connection((host, port), timeout=0.08):
            return True
    except Exception:
        return False


def resolve_space_safe_temp_dir() -> Path:
    """Ensure a temporary directory with sufficient disk space is selected.

    On Windows, if drive C: has low disk space, redirect to workspace or Drive E:.
    """
    candidates = [
        Path("E:/jarvis/.temp"),
        Path.home() / ".jarvis" / "temp",
        Path(os.environ.get("TEMP", "C:/temp")),
    ]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            usage = shutil.disk_usage(d)
            if usage.free > 100 * 1024 * 1024:  # At least 100 MB free
                return d
        except Exception:
            continue

    fallback = Path("E:/jarvis/.temp")
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


@dataclass
class TabRecord:
    target_id: str
    page: Page
    title: str = ""
    url: str = ""
    label: str = ""
    session_key: str = ""


async def _goto_domcontentloaded_best_effort(
    page: Page,
    url: str,
    *,
    timeout_ms: int,
) -> str | None:
    """Navigate without turning heavy-site slow loads into unusable browser failures."""

    last_error: Exception | None = None
    for wait_until in ("domcontentloaded", "commit"):
        try:
            await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            return None
        except Exception as err:
            last_error = err
            if "timeout" not in str(err).lower():
                raise
            if getattr(page, "url", "") and page.url not in ("about:blank",):
                return f"Navigation timed out after page commit; continuing with loaded URL {page.url}."
    return str(last_error) if last_error is not None else None


def clear_chrome_singleton_artifacts(user_data_dir: Path) -> None:
    """Remove stale Chromium lock files that prevent browser initialization after crashes.

    Matches OpenClaw extensions/browser/src/browser/chrome.ts clearStaleChromeSingletonLocks.
    """
    for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"):
        try:
            lock_file = user_data_dir / lock_name
            if lock_file.exists() or lock_file.is_symlink():
                lock_file.unlink(missing_ok=True)
        except Exception:
            pass


_ACT_DEFAULT_TIMEOUT_MS: int = 8000


def _strict_mode_violation(error: Exception) -> bool:
    text = str(error).lower()
    return "strict mode violation" in text or "resolved to" in text and "elements" in text


def _first_locator(locator: Any) -> Any:
    first = getattr(locator, "first", None)
    if first is None:
        return None
    if hasattr(first, "click"):
        return first
    return first() if callable(first) else first


def _chromium_launch_args(config: ResolvedBrowserConfig, *, minimal: bool = False) -> list[str]:
    """Return Chrome launch flags without weakening sandbox by default."""

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
    ]
    if not minimal:
        args.extend(
            [
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-features=Translate,MediaRouter",
                "--disable-session-crashed-bubble",
                "--hide-crash-restore-bubble",
                "--password-store=basic",
            ]
        )
    if config.noSandbox:
        args.append("--no-sandbox")
    args.append("--disable-dev-shm-usage")
    if config.extraArgs:
        for extra_arg in config.extraArgs:
            if extra_arg == "--no-sandbox" and not config.noSandbox:
                continue
            args.append(extra_arg)
    return args


async def _dismiss_overlays_if_present(page: Any) -> None:
    """Auto-dismiss cookie consent, terms, or promotion popups (e.g. YouTube, Google)."""
    try:
        consent_selectors = [
            "button[aria-label*='Accept' i]",
            "button[aria-label*='Agree' i]",
            "ytd-button-renderer:has-text('Accept all')",
            "button:has-text('Accept all')",
            "button:has-text('Reject all')",
            "button:has-text('I agree')",
            "button:has-text('Agree')",
            "#dismiss-button",
        ]
        for sel in consent_selectors:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                try:
                    await loc.click(timeout=1000)
                    await asyncio.sleep(0.1)
                    break
                except Exception:
                    pass
    except Exception:
        pass


async def _wait_for_page_ready(page: Any, max_wait_ms: int = 5000) -> None:
    """Detect page loading states (progress bar, spinners, DOM ready, aria-busy) and wait for completion.

    Prevents blind clicks on slow PCs or while pages are loading.
    """
    try:
        # 1. Wait for DOM load state
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=min(max_wait_ms, 2500))
        except Exception:
            pass

        # 2. Check for active loading indicators in DOM
        loading_script = """() => {
            if (document.readyState === 'loading') return true;

            // YouTube progress bar
            const ytProgress = document.querySelector('yt-page-navigation-progress');
            if (ytProgress) {
                const val = ytProgress.getAttribute('aria-valuenow');
                const isVisible = window.getComputedStyle(ytProgress).display !== 'none' && ytProgress.offsetHeight > 0;
                if ((val && parseInt(val, 10) < 100) || ytProgress.classList.contains('progress') || isVisible) {
                    return true;
                }
            }

            // General & YouTube spinners / busy indicators
            const spinners = document.querySelectorAll(
                'paper-spinner[active], paper-spinner-lite[active], .ytp-spinner:not([style*="display: none"]), ' +
                '.spinner:not([style*="display: none"]), [aria-busy="true"], .loading:not([style*="display: none"])'
            );
            for (const s of spinners) {
                if (s.offsetWidth > 0 && s.offsetHeight > 0 && window.getComputedStyle(s).visibility !== 'hidden') {
                    return true;
                }
            }
            return false;
        }"""

        start = time.monotonic()
        deadline = start + (max_wait_ms / 1000.0)
        had_loading = False
        while time.monotonic() < deadline:
            is_loading = await page.evaluate(loading_script)
            if not is_loading:
                break
            had_loading = True
            await asyncio.sleep(0.08)

        # Brief settle time for render only if page was actively loading
        if had_loading:
            await asyncio.sleep(0.05)
    except Exception:
        pass


def _clean_target_ref(val: Optional[str]) -> str:
    """Clean and strip brackets, quotes, and prefixes from element ref strings."""
    if not val:
        return ""
    s = val.strip()
    # Strip quotes and brackets e.g. ['e1'], "[e1]", (e1), [e2]
    s = re.sub(r"^[\"\'\[\(]+|[\"\'\]\)]+$", "", s).strip()
    if s.lower().startswith("ref=") or s.lower().startswith("ref:"):
        s = s[4:].strip()
    elif s.startswith("@"):
        s = s[1:].strip()
    return s


def _resolve_element_locator(
    page: Any, selector: Optional[str] = None, ref: Optional[str] = None
) -> Optional[Any]:
    """Resolve a selector or OpenClaw ref into a Playwright Locator with smart fallbacks."""
    raw_target = (ref or selector or "").strip()
    if not raw_target:
        return None

    clean_target = _clean_target_ref(raw_target)
    url = getattr(page, "url", "").lower()

    # 1. Check for Set-of-Mark or OpenClaw-style role ref (e.g. 1, e1, [1], [e1], ref-1)
    ref_match = re.match(r"^(?:ref-?)?e?(\d+)$", clean_target, re.I)
    if ref_match:
        num = ref_match.group(1)
        idx = max(0, int(num) - 1)
        ref_id = f"e{idx + 1}"

        if "youtube.com" in url:
            yt_loc = page.locator(
                f"[data-jarvis-ref='{num}'], [data-ref='{ref_id}'], [data-ref='{num}'], "
                "ytd-video-renderer #video-title, "
                "ytd-rich-item-renderer #video-title, "
                "ytd-compact-video-renderer #video-title, "
                "#contents ytd-video-renderer a#thumbnail, "
                "#contents ytd-video-renderer a#video-title-link, "
                "#video-title, a#video-title"
            )
            return yt_loc.nth(idx)
        elif "google.com" in url:
            g_loc = page.locator(
                f"[data-jarvis-ref='{num}'], [data-ref='{ref_id}'], [data-ref='{num}'], #search a h3, #rso a h3, a h3"
            )
            return g_loc.nth(idx)
        else:
            return page.locator(
                f"[data-jarvis-ref='{num}'], [data-ref='{ref_id}'], [data-ref='{num}'], [aria-ref='{ref_id}'], #{ref_id}, "
                "main a:visible, article a:visible, a:visible, button:visible"
            ).nth(idx)

    # 2. Check semantic queries
    semantic = clean_target.lower()
    if "homepage" in semantic or "home page" in semantic:
        return page.locator(
            "a:has-text('Homepage'), a:has-text('Home page'), a:has-text('Home'), "
            "a[href*='deepseek.com'], a[href='/'], header a, nav a"
        ).first
    if "deepseek" in semantic:
        return page.locator(
            "a:has-text('DeepSeek'), a:has-text('DeepSeek AI'), "
            "a[href*='deepseek.com'], button:has-text('DeepSeek')"
        ).first
    if "sign in" in semantic or "signin" in semantic or "login" in semantic:
        return page.locator(
            "a:has-text('Sign in'), button:has-text('Sign in'), "
            "a:has-text('Log in'), button:has-text('Log in'), "
            "[aria-label*='sign in' i], [aria-label*='log in' i]"
        ).first

    # 3. Special YouTube selector normalization
    if "youtube.com" in url:
        if clean_target.lower() in ("#search", "search", "ytd-searchbox", "input#search"):
            return page.locator(
                "input[name='search_query'], input#search, #search input, ytd-searchbox input"
            ).first
        if "search-icon" in clean_target.lower() or clean_target.lower() in (
            "#search-icon-legacy",
            "search-icon-legacy",
        ):
            return page.locator(
                "button#search-icon-legacy, #search-icon-legacy, button[aria-label*='Search' i]"
            ).first

    # 4. Standard CSS selector
    return page.locator(raw_target).first


class BrowserRuntime:
    """Manages Playwright lifecycle, persistent browser contexts, and page actions."""

    def __init__(self, resolved: ResolvedBrowserConfig):
        self.resolved = resolved
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.contexts: Dict[str, BrowserContext] = {}
        self._tabs: Dict[str, TabRecord] = {}
        self._next_tab_id: int = 1
        self._active_tab_id: Optional[str] = None
        self._console_logs: Dict[str, List[str]] = {}
        self._page_errors: Dict[str, List[str]] = {}
        self._lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def default_profile(self) -> ResolvedBrowserProfile:
        """Get default resolved browser profile."""
        return resolve_profile(self.resolved, self.resolved.defaultProfile)

    def _resolve_profile(
        self, profile: Optional[Union[ResolvedBrowserProfile, str]] = None
    ) -> ResolvedBrowserProfile:
        """Resolve profile argument to ResolvedBrowserProfile."""
        if isinstance(profile, ResolvedBrowserProfile):
            return profile
        if isinstance(profile, str) and profile in self.resolved.profiles:
            return resolve_profile(self.resolved, profile)
        return self.default_profile

    @property
    def is_running(self) -> bool:
        """Whether browser contexts are active."""
        return self.playwright is not None and len(self.contexts) > 0

    def get_status(self) -> dict[str, Any]:
        """Return runtime status snapshot."""
        open_tabs = [t for t in self._tabs.values() if not t.page.is_closed()]
        return {
            "running": self.is_running,
            "profile": self.resolved.defaultProfile,
            "tabs_count": len(open_tabs),
            "active_tab_id": self._active_tab_id,
            "contexts_count": len(self.contexts),
        }

    async def ensure_browser(
        self,
        headless: Optional[bool] = None,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
    ) -> BrowserContext:
        """Ensure browser context is started and return it."""
        prof = self._resolve_profile(profile)
        if headless is not None:
            prof = replace(prof, headless=headless)
        return await self.get_or_create_context(prof)

    async def doctor(self) -> dict[str, Any]:
        """Perform comprehensive browser environment diagnostics."""
        checks: list[dict[str, Any]] = []

        has_pw = async_playwright is not None
        checks.append(
            {
                "name": "playwright_installed",
                "ok": has_pw,
                "detail": (
                    "Playwright is installed and importable"
                    if has_pw
                    else "Playwright is not installed (run `uv add playwright`)"
                ),
            }
        )

        chrome_path = self.default_profile.executablePath or find_system_chromium()
        has_chrome = chrome_path is not None and Path(chrome_path).exists()
        checks.append(
            {
                "name": "chromium_executable",
                "ok": has_chrome,
                "detail": (
                    f"Executable found at: {chrome_path}"
                    if has_chrome
                    else "No Chromium/Chrome/Edge executable found on PATH or standard locations"
                ),
            }
        )

        temp_dir = resolve_space_safe_temp_dir()
        free_bytes = 0
        try:
            free_bytes = shutil.disk_usage(temp_dir).free
        except Exception:
            pass
        free_mb = free_bytes / (1024 * 1024)
        space_ok = free_mb > 100
        checks.append(
            {
                "name": "storage_disk_space",
                "ok": space_ok,
                "detail": f"Temp directory {temp_dir} has {free_mb:.1f} MB free",
            }
        )

        all_ok = has_pw and has_chrome and space_ok
        return {
            "ok": all_ok,
            "checks": checks,
            "executablePath": chrome_path,
            "tempDir": str(temp_dir),
            "freeSpaceMb": round(free_mb, 1),
            "profile": self.resolved.defaultProfile,
        }

    async def start(self) -> None:
        """Start the Playwright runtime."""
        if async_playwright is None:
            raise RuntimeError(
                "Playwright is not installed. Install with `uv add playwright` and `uv run playwright install chromium`."
            )

        self._loop = asyncio.get_running_loop()

        # Set space-safe TEMP/TMP directory so Chromium does not crash
        safe_temp = resolve_space_safe_temp_dir()
        os.environ["TEMP"] = str(safe_temp.resolve())
        os.environ["TMP"] = str(safe_temp.resolve())

        if self.playwright is None:
            self.playwright = await async_playwright().start()

    async def get_or_create_context(self, profile: ResolvedBrowserProfile) -> BrowserContext:
        """Get an existing context or launch a persistent context for the profile."""
        async with self._get_lock():
            if profile.name in self.contexts:
                existing_ctx = self.contexts[profile.name]
                is_dead = False
                try:
                    if getattr(existing_ctx, "_is_closed", False):
                        is_dead = True
                    else:
                        _ = existing_ctx.pages
                except Exception:
                    is_dead = True

                if not is_dead and (self.browser is None or self.browser.is_connected()):
                    return existing_ctx
                else:
                    self.contexts.pop(profile.name, None)
                    for tid in list(self._tabs.keys()):
                        self._tabs.pop(tid, None)
                    self._active_tab_id = None

            if not self.playwright:
                await self.start()

            assert self.playwright is not None

            # Handle existing session CDP attachment
            if profile.driver == "existing-session" or profile.attachOnly:
                endpoint_url = profile.cdpUrl or f"http://{profile.cdpHost}:{profile.cdpPort}"
                try:
                    self.browser = await self.playwright.chromium.connect_over_cdp(
                        endpoint_url, timeout=min(self.resolved.remoteCdpHandshakeTimeoutMs, 1000)
                    )
                except Exception:
                    # Graceful fallback: If Chrome is not running with remote debugging,
                    # launch local managed Chrome so browser initialization never permanently fails
                    exec_path = profile.executablePath or find_system_chromium()
                    safe_temp = resolve_space_safe_temp_dir()
                    profile_dir = safe_temp / "browser" / f"{profile.name}_managed_fallback"
                    profile_dir.mkdir(parents=True, exist_ok=True)
                    clear_chrome_singleton_artifacts(profile_dir)
                    launch_args = _chromium_launch_args(self.resolved, minimal=True)
                    context = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir.resolve()),
                        executable_path=exec_path,
                        headless=bool(profile.headless),
                        args=launch_args,
                    )
                    self.contexts[profile.name] = context
                    for page in context.pages:
                        self._register_page(page)
                    context.on("page", lambda new_page: self._register_page(new_page))
                    return context
                assert self.browser is not None
                if self.browser.contexts:
                    context = self.browser.contexts[0]
                else:
                    context = await self.browser.new_context()
            else:
                # Local Chromium launch
                exec_path = profile.executablePath or find_system_chromium()

                # Choose space-safe user data directory for the profile
                safe_temp = resolve_space_safe_temp_dir()
                profile_dir = (
                    Path(profile.userDataDir)
                    if profile.userDataDir
                    else (
                        Path.home() / ".jarvis" / "browser" / "chrome_profile"
                        if profile.name in ("jarvis", "openclaw", "default")
                        else safe_temp / "browser" / profile.name
                    )
                )
                profile_dir.mkdir(parents=True, exist_ok=True)
                clear_chrome_singleton_artifacts(profile_dir)

                cdp_port = getattr(profile, "cdpPort", None) or 9222

                # 0. Fast CDP re-attach ONLY if Chrome is already actively listening on remote debugging port
                if (
                    not profile.headless
                    and profile.name in ("jarvis", "openclaw", "default")
                    and is_port_open("127.0.0.1", cdp_port)
                ):
                    try:
                        self.browser = await self.playwright.chromium.connect_over_cdp(
                            f"http://127.0.0.1:{cdp_port}", timeout=800
                        )
                        if self.browser and self.browser.contexts:
                            context = self.browser.contexts[0]
                        elif self.browser:
                            context = await self.browser.new_context()
                        else:
                            context = None
                        if context:
                            self.contexts[profile.name] = context
                            for page in context.pages:
                                self._register_page(page)
                            context.on("page", lambda new_page: self._register_page(new_page))
                            return context
                    except Exception:
                        pass

                launch_args = _chromium_launch_args(self.resolved)
                port_arg = f"--remote-debugging-port={cdp_port}"
                if port_arg not in launch_args:
                    launch_args.append(port_arg)
                if "--start-maximized" not in launch_args:
                    launch_args.append("--start-maximized")

                try:
                    # Attempt launch using real Chrome channel first (best media codec & login support)
                    context = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(profile_dir.resolve()),
                        channel="chrome",
                        headless=bool(profile.headless),
                        args=launch_args,
                        ignore_default_args=["--enable-automation"],
                        no_viewport=True,
                        timeout=12000,
                    )
                except Exception:
                    # Fallback to direct executable_path or standard launch
                    try:
                        context = await self.playwright.chromium.launch_persistent_context(
                            user_data_dir=str(profile_dir.resolve()),
                            executable_path=exec_path,
                            headless=bool(profile.headless),
                            args=launch_args,
                            ignore_default_args=["--enable-automation"],
                            timeout=12000,
                        )
                    except Exception:
                        if self.browser is None:
                            self.browser = await self.playwright.chromium.launch(
                                executable_path=exec_path,
                                headless=bool(profile.headless),
                                args=launch_args,
                            )
                        context = await self.browser.new_context()

                # Anti-detection stealth init script
                try:
                    await context.add_init_script(
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                    )
                except Exception:
                    pass

            self.contexts[profile.name] = context

            # Register existing pages in the context
            for page in context.pages:
                self._register_page(page)

            # Listen for new pages created by window.open or popups
            context.on("page", lambda new_page: self._register_page(new_page))

            return context

    def _register_page(self, page: Page, label: str = "") -> TabRecord:
        """Register a page as an active tracked tab."""
        for tid, tab in self._tabs.items():
            if tab.page == page:
                return tab

        tab_id = f"tab_{self._next_tab_id}"
        self._next_tab_id += 1

        record = TabRecord(target_id=tab_id, page=page, label=label)
        self._tabs[tab_id] = record
        self._active_tab_id = tab_id
        self._console_logs[tab_id] = []
        self._page_errors[tab_id] = []

        # Wire logging handlers
        def on_console(msg: Any) -> None:
            self._console_logs.setdefault(tab_id, []).append(f"[{msg.type}] {msg.text}")

        def on_page_error(err: Any) -> None:
            self._page_errors.setdefault(tab_id, []).append(str(err))

        def on_close(_: Any) -> None:
            self._tabs.pop(tab_id, None)
            if self._active_tab_id == tab_id:
                self._active_tab_id = next(iter(self._tabs), None)

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("close", on_close)

        return record

    async def get_page(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> Page:
        """Get an active or specified page, launching context if necessary."""
        prof = self._resolve_profile(profile)
        context = await self.get_or_create_context(prof)

        # 1. Explicit target ID or label requested
        if target_id:
            if target_id in self._tabs:
                tab = self._tabs[target_id]
                if not tab.page.is_closed():
                    self._active_tab_id = target_id
                    return tab.page
            for tid, tab in self._tabs.items():
                if (
                    not tab.page.is_closed()
                    and tab.label
                    and tab.label.lower() == target_id.lower()
                ):
                    self._active_tab_id = tid
                    return tab.page

        # 2. Use active tab if set and open
        if self._active_tab_id and self._active_tab_id in self._tabs:
            active_tab = self._tabs[self._active_tab_id]
            if not active_tab.page.is_closed():
                return active_tab.page

        # 3. Find most recently registered or focused non-closed tab
        for tid in reversed(list(self._tabs.keys())):
            tab = self._tabs[tid]
            if not tab.page.is_closed():
                self._active_tab_id = tid
                return tab.page

        # 4. Check existing pages in context
        for p in reversed(context.pages):
            if not p.is_closed():
                rec = self._register_page(p)
                self._active_tab_id = rec.target_id
                return rec.page

        # 5. Create new page
        new_page = await context.new_page()
        rec = self._register_page(new_page)
        self._active_tab_id = rec.target_id
        return rec.page

    async def list_tabs(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        session_key: str | None = None,
    ) -> List[Dict[str, Any]]:
        """List all open tabs across profiles with optional sessionKey filtering."""
        prof = self._resolve_profile(profile)
        await self.get_or_create_context(prof)

        results = []
        for tid, tab in list(self._tabs.items()):
            if tab.page.is_closed():
                continue
            if session_key and tab.session_key and tab.session_key != session_key:
                continue
            try:
                title = await tab.page.title()
            except Exception:
                title = tab.title
            suggested_target_id = tab.label or tid
            results.append(
                {
                    "targetId": tid,
                    "suggestedTargetId": suggested_target_id,
                    "title": title,
                    "url": tab.page.url,
                    "active": tid == self._active_tab_id,
                    "label": tab.label,
                    "sessionKey": tab.session_key,
                }
            )
        return results

    async def open_tab(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        url: Optional[str] = None,
        label: str = "",
        force_new_tab: bool = False,
        session_key: str = "",
    ) -> dict[str, Any]:
        """Open a tab or reuse an existing tab with matching label or domain."""
        if isinstance(profile, str) and (
            url is None or profile.startswith("http") or profile == "about:blank"
        ):
            url = profile
            prof = self.default_profile
        else:
            prof = self._resolve_profile(profile)

        # Normalize bare domain URLs (e.g. "youtube.com" -> "https://www.youtube.com")
        if url and not url.startswith(
            ("http://", "https://", "about:", "data:", "chrome:", "edge:", "file:")
        ):
            if url.lower().startswith("www.") or "." in url:
                url = f"https://{url}"
            elif url.lower() in (
                "youtube",
                "google",
                "github",
                "twitter",
                "x",
                "reddit",
                "spotify",
            ):
                url = f"https://www.{url.lower()}.com"

        # 0. Ensure context is initialized and sync any unrecorded pages into self._tabs
        try:
            context = await self.get_or_create_context(prof)
            for page in getattr(context, "pages", []):
                if not getattr(page, "is_closed", lambda: False)():
                    self._register_page(page)
        except Exception:
            pass

        # 1. Reuse existing tab by explicit label if provided
        if label and not force_new_tab:
            for tid, tab in list(self._tabs.items()):
                if not tab.page.is_closed() and tab.label and tab.label.lower() == label.lower():
                    self._active_tab_id = tid
                    if session_key:
                        tab.session_key = session_key
                    await tab.page.bring_to_front()
                    if url and tab.page.url != url:
                        from urllib.parse import urlparse

                        tab_p = urlparse(tab.page.url)
                        target_p = urlparse(url)
                        tab_h = tab_p.netloc.lower().removeprefix("www.")
                        target_h = target_p.netloc.lower().removeprefix("www.")
                        if tab_h == target_h and target_p.path in ("", "/"):
                            pass  # Already on target site, avoid destructive page reload
                        else:
                            await _goto_domcontentloaded_best_effort(
                                tab.page,
                                url,
                                timeout_ms=self.resolved.actionTimeoutMs,
                            )
                    t_title = await tab.page.title()
                    return {
                        "ok": True,
                        "targetId": tid,
                        "suggestedTargetId": label,
                        "url": tab.page.url,
                        "title": t_title,
                        "reused": True,
                    }

        # 2. Domain-based tab reuse optimization (e.g. reuse existing YouTube/Google tab instead of opening duplicates)
        if url and not force_new_tab:
            try:
                from urllib.parse import urlparse

                target_parsed = urlparse(url)
                target_host = target_parsed.netloc.lower().removeprefix("www.")
                if target_host:
                    for tid, tab in list(self._tabs.items()):
                        if not tab.page.is_closed():
                            tab_parsed = urlparse(tab.page.url)
                            tab_host = tab_parsed.netloc.lower().removeprefix("www.")
                            if tab_host and (
                                tab_host == target_host
                                or target_host in tab_host
                                or tab_host in target_host
                            ):
                                self._active_tab_id = tid
                                if label and not tab.label:
                                    tab.label = label
                                await tab.page.bring_to_front()
                                # Do not destructive reload if target is root URL and tab is already on that site
                                if tab.page.url != url:
                                    if target_parsed.path in ("", "/") and tab_parsed.path != "":
                                        pass  # Keep active search or watch page
                                    else:
                                        await _goto_domcontentloaded_best_effort(
                                            tab.page,
                                            url,
                                            timeout_ms=self.resolved.actionTimeoutMs,
                                        )
                                t_title = await tab.page.title()
                                return {
                                    "ok": True,
                                    "targetId": tid,
                                    "suggestedTargetId": tab.label or tid,
                                    "url": tab.page.url,
                                    "title": t_title,
                                    "reused": True,
                                }
            except Exception:
                pass

        for attempt in range(2):
            try:
                context = await self.get_or_create_context(prof)
                # Reuse initial blank tab created during persistent context launch to prevent duplicate tabs/windows
                reusable_page = None
                if not force_new_tab and getattr(context, "pages", None):
                    for p in context.pages:
                        if not p.is_closed() and p.url in ("about:blank", "", "data:,"):
                            already_used = any(
                                t.page == p and t.page.url not in ("about:blank", "", "data:,")
                                for t in self._tabs.values()
                            )
                            if not already_used:
                                reusable_page = p
                                break
                if reusable_page is not None:
                    page = reusable_page
                else:
                    page = await context.new_page()
                rec = self._register_page(page, label=label)
                if session_key:
                    rec.session_key = session_key
                self._active_tab_id = rec.target_id
                navigation_warning = None
                if url:
                    navigation_warning = await _goto_domcontentloaded_best_effort(
                        page,
                        url,
                        timeout_ms=self.resolved.actionTimeoutMs,
                    )
                t_title = await page.title()
                result = {
                    "ok": True,
                    "targetId": rec.target_id,
                    "suggestedTargetId": label or rec.target_id,
                    "url": page.url,
                    "title": t_title,
                }
                if url and navigation_warning:
                    result["warning"] = navigation_warning
                return result
            except Exception as e:
                err_msg = str(e).lower()
                if attempt == 0 and any(
                    kw in err_msg for kw in ("closed", "target page", "disconnected", "crash")
                ):
                    self.contexts.pop(prof.name, None)
                    self._tabs.clear()
                    self._active_tab_id = None
                    if self.browser:
                        try:
                            await self.browser.close()
                        except Exception:
                            pass
                        self.browser = None
                    continue
                raise

    async def close_tab(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Close a specific or current tab without terminating other tabs or browser context."""
        if isinstance(profile, str) and target_id is None and profile not in self.resolved.profiles:
            target_id = profile
            prof = self.default_profile
        else:
            prof = self._resolve_profile(profile)

        # 1. Search active tabs by label, url, or domain if tid is not a direct key
        tid = target_id
        if tid and tid not in self._tabs:
            for tab_key, tab in list(self._tabs.items()):
                if not tab.page.is_closed():
                    if tab.label and tab.label.lower() == tid.lower():
                        tid = tab_key
                        break
                    if tid.lower() in tab.page.url.lower():
                        tid = tab_key
                        break
                    if tid.lower() in ("youtube", "yt") and "youtube.com" in tab.page.url.lower():
                        tid = tab_key
                        break

        effective_tid = tid or self._active_tab_id

        if effective_tid and effective_tid in self._tabs:
            page = self._tabs[effective_tid].page
            if not page.is_closed():
                await page.close()
            self._tabs.pop(effective_tid, None)
            final_tid = effective_tid
        else:
            try:
                page = await self.get_page(prof, effective_tid)
                final_tid = effective_tid or self._active_tab_id or "unknown"
                if not page.is_closed():
                    await page.close()
                self._tabs.pop(final_tid, None)
            except Exception:
                final_tid = effective_tid or "unknown"

        # 4. Re-target active tab to another available open tab
        if self._active_tab_id == final_tid:
            self._active_tab_id = next(
                (k for k, t in self._tabs.items() if not t.page.is_closed()), None
            )

        return {"ok": True, "targetId": final_tid, "status": "closed"}

    async def focus_tab(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Bring a tab to the front."""
        if isinstance(profile, str) and target_id is None and profile not in self.resolved.profiles:
            target_id = profile
            prof = self.default_profile
        else:
            prof = self._resolve_profile(profile)

        page = await self.get_page(prof, target_id)
        tid = target_id or self._active_tab_id or ""
        await page.bring_to_front()
        self._active_tab_id = tid
        return {
            "ok": True,
            "targetId": tid,
            "url": page.url,
            "title": await page.title(),
        }

    async def navigate(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        url: Optional[str] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Navigate tab to a target URL."""
        if isinstance(profile, str) and (
            url is None
            or profile.startswith(
                ("http://", "https://", "about:", "data:", "chrome:", "edge:", "file:")
            )
        ):
            url = profile
            prof = self.default_profile
        else:
            prof = self._resolve_profile(profile)

        if url and not url.startswith(
            ("http://", "https://", "about:", "data:", "chrome:", "edge:", "file:")
        ):
            if url.lower().startswith("www.") or "." in url:
                url = f"https://{url}"
            elif url.lower() in (
                "youtube",
                "google",
                "github",
                "twitter",
                "x",
                "reddit",
                "spotify",
            ):
                url = f"https://www.{url.lower()}.com"

        # Domain-aware tab reuse: if navigating without an explicit target_id,
        # reuse and focus any existing tab already on that domain (e.g. YouTube)
        if url and not target_id:
            try:
                from urllib.parse import urlparse

                target_parsed = urlparse(url)
                target_host = target_parsed.netloc.lower().removeprefix("www.")
                if target_host:
                    # Sync any unrecorded pages into self._tabs first
                    context = await self.get_or_create_context(prof)
                    for p in getattr(context, "pages", []):
                        if not getattr(p, "is_closed", lambda: False)():
                            self._register_page(p)

                    for tid, tab in list(self._tabs.items()):
                        if not tab.page.is_closed():
                            tab_parsed = urlparse(tab.page.url)
                            tab_host = tab_parsed.netloc.lower().removeprefix("www.")
                            if tab_host and (
                                tab_host == target_host
                                or target_host in tab_host
                                or tab_host in target_host
                            ):
                                self._active_tab_id = tid
                                await tab.page.bring_to_front()
                                # Do not destructive reload if target is root URL and tab is already on that site
                                if tab.page.url != url:
                                    if target_parsed.path in ("", "/") and tab_parsed.path != "":
                                        pass  # Keep active search or watch page
                                    else:
                                        await _goto_domcontentloaded_best_effort(
                                            tab.page,
                                            url,
                                            timeout_ms=self.resolved.actionTimeoutMs,
                                        )
                                await _wait_for_page_ready(tab.page)
                                return {
                                    "ok": True,
                                    "targetId": tid,
                                    "url": tab.page.url,
                                    "title": await tab.page.title(),
                                    "reused": True,
                                }
            except Exception:
                pass

        effective_target_id = target_id or self._active_tab_id
        page = await self.get_page(prof, effective_target_id)
        navigation_warning = await _goto_domcontentloaded_best_effort(
            page,
            url,
            timeout_ms=self.resolved.actionTimeoutMs,
        )
        await _wait_for_page_ready(page)
        return {
            "ok": True,
            "targetId": self._active_tab_id,
            "url": page.url,
            "title": await page.title(),
            **({"warning": navigation_warning} if navigation_warning else {}),
        }

    async def youtube_play(
        self,
        query: str,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
        auto_skip_ad: bool = True,
    ) -> dict[str, Any]:
        """Search and play a video on YouTube in the active or reused YouTube tab.

        Follows OpenClaw active browser targeting:
        1. Targets existing YouTube tab if open, otherwise navigates current tab or opens single tab.
        2. Waits for page load completion and dismisses cookie consent dialogs.
        3. Navigates to search results and clicks first playable video.
        4. Auto-skips pre-roll ads if present.
        """
        import urllib.parse

        prof = self._resolve_profile(profile)
        # 1. Reuse existing YouTube tab if available across active tabs
        page = None
        active_tid = None
        for tid, tab in list(self._tabs.items()):
            if not tab.page.is_closed() and "youtube.com" in tab.page.url.lower():
                page = tab.page
                active_tid = tid
                self._active_tab_id = tid
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
                break

        if page is None:
            # Check if active tab is blank/new, reuse it
            if self._active_tab_id and self._active_tab_id in self._tabs:
                curr_tab = self._tabs[self._active_tab_id]
                if not curr_tab.page.is_closed() and curr_tab.page.url in (
                    "about:blank",
                    "",
                    "data:,",
                ):
                    page = curr_tab.page
                    active_tid = self._active_tab_id

        if page is None:
            res = await self.open_tab(profile=prof, url="https://www.youtube.com", label="youtube")
            active_tid = res.get("targetId")
            page = await self.get_page(prof, active_tid)

        clean_query = (query or "").strip()
        search_url = (
            f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(clean_query)}"
        )

        # 2. Navigate to search query and wait for load
        await _goto_domcontentloaded_best_effort(
            page, search_url, timeout_ms=self.resolved.actionTimeoutMs
        )
        await _wait_for_page_ready(page, max_wait_ms=1200)
        await _dismiss_overlays_if_present(page)

        # 3. Locate the first video in the search results
        loc = page.locator(
            "ytd-video-renderer a#video-title, ytd-video-renderer #video-title, a#video-title, ytd-rich-item-renderer #video-title"
        ).first
        try:
            await loc.wait_for(state="visible", timeout=3000)
        except Exception:
            try:
                await loc.wait_for(state="attached", timeout=1500)
            except Exception:
                pass

        video_title = clean_query
        try:
            txt = await loc.text_content()
            if txt and txt.strip():
                video_title = txt.strip()
        except Exception:
            pass

        # 4. Click video to start playback
        clicked = False
        try:
            await loc.click(timeout=3500)
            clicked = True
        except Exception:
            try:
                href = await loc.get_attribute("href")
                if href:
                    target_v = f"https://www.youtube.com{href}" if href.startswith("/") else href
                    await page.goto(target_v, wait_until="domcontentloaded", timeout=8000)
                    clicked = True
            except Exception:
                pass

        if not clicked:
            try:
                await loc.click(force=True, timeout=2000)
            except Exception:
                pass

        # 5. Wait for video page to settle and start video playback
        await _wait_for_page_ready(page, max_wait_ms=4000)
        await _dismiss_overlays_if_present(page)

        # Unmute & trigger play on HTML5 video element if paused
        try:
            await page.evaluate("""() => {
                const v = document.querySelector('video');
                if (v) {
                    v.muted = false;
                    v.play().catch(() => {});
                }
            }""")
        except Exception:
            pass

        # 6. Auto-skip pre-roll ad if enabled
        ad_skipped = False
        if auto_skip_ad:
            await asyncio.sleep(0.5)
            ad_skipped = await self._try_skip_youtube_ad(page)

        return {
            "ok": True,
            "action": "youtube_play",
            "status": "playing",
            "playing_title": video_title,
            "query": clean_query,
            "url": page.url,
            "targetId": active_tid,
            "ad_skipped": ad_skipped,
        }

    async def _try_skip_youtube_ad(self, page: Any) -> bool:
        """Internal helper to click skip ad buttons or fast-forward active ads."""
        try:
            skip_selectors = [
                ".ytp-ad-skip-button",
                ".ytp-ad-skip-button-modern",
                "button.ytp-skip-ad-button",
                ".ytp-skip-ad-button",
                "button.ytp-ad-skip-button-icon",
                "[class*='ytp-ad-skip-button']",
            ]
            for sel in skip_selectors:
                btn = page.locator(sel).first
                if await btn.is_visible():
                    await btn.click(timeout=1000)
                    return True

            # If inside ad container, seek video to end
            skipped = await page.evaluate("""() => {
                const ad = document.querySelector('.ad-showing, .ad-interrupting, .video-ads');
                const v = document.querySelector('video');
                if (ad && v && !isNaN(v.duration) && v.duration > 0) {
                    v.currentTime = v.duration;
                    return true;
                }
                return false;
            }""")
            return bool(skipped)
        except Exception:
            return False

    async def youtube_skip_ad(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Skip currently playing advertisement on YouTube."""
        prof = self._resolve_profile(profile)
        page = await self.get_page(prof, target_id)
        skipped = await self._try_skip_youtube_ad(page)
        return {
            "ok": True,
            "action": "skip_ad",
            "status": "ad_skipped" if skipped else "no_active_ad",
            "url": page.url,
        }

    async def google_search(
        self,
        query: str,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search Google in active or reused Google tab."""
        import urllib.parse

        prof = self._resolve_profile(profile)
        page = None
        for tid, tab in list(self._tabs.items()):
            if not tab.page.is_closed() and "google.com" in tab.page.url.lower():
                page = tab.page
                self._active_tab_id = tid
                try:
                    await page.bring_to_front()
                except Exception:
                    pass
                break

        if page is None:
            res = await self.open_tab(profile=prof, url="https://www.google.com", label="google")
            page = await self.get_page(prof, res.get("targetId"))

        clean_query = (query or "").strip()
        search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean_query)}"
        await _goto_domcontentloaded_best_effort(
            page, search_url, timeout_ms=self.resolved.actionTimeoutMs
        )
        await _wait_for_page_ready(page, max_wait_ms=4000)
        await _dismiss_overlays_if_present(page)

        snap = await self.snapshot(profile=prof, target_id=self._active_tab_id, max_chars=2000)
        return {
            "ok": True,
            "action": "google_search",
            "query": clean_query,
            "url": page.url,
            "title": await page.title(),
            "summary": snap.get("snapshot") or snap.get("text") or "",
        }

    async def snapshot(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
        snapshot_format: str = "aria",
        max_chars: Optional[int] = None,
    ) -> dict[str, Any]:
        """Capture an ARIA or text DOM snapshot of the tab."""
        prof = self._resolve_profile(profile)
        page = await self.get_page(prof, target_id)
        await _wait_for_page_ready(page)

        # Extract Set-of-Mark interactive element map
        elements: list[dict[str, Any]] = []
        try:
            elements = await inject_set_of_marks(page, annotate=False)
        except Exception:
            pass

        page_title = ""
        try:
            page_title = await page.title()
        except Exception:
            pass

        som_summary = ""
        if elements:
            som_summary = format_som_elements_summary(elements, title=page_title, url=page.url)

        snapshot_content = ""
        try:
            # Modern Playwright ARIA snapshot (mirrors OpenClaw's ARIA tree)
            snapshot_content = await page.locator("body").aria_snapshot()
            if "youtube.com" in page.url.lower():
                try:
                    await page.evaluate("""() => {
                        const titles = document.querySelectorAll(
                            'ytd-video-renderer #video-title, ytd-rich-item-renderer #video-title, ytd-compact-video-renderer #video-title, #video-title'
                        );
                        titles.forEach((el, i) => {
                            const ref = 'e' + (i + 1);
                            el.setAttribute('data-ref', ref);
                            const card = el.closest('ytd-video-renderer, ytd-rich-item-renderer, ytd-compact-video-renderer');
                            if (card) {
                                card.setAttribute('data-ref', ref);
                                const thumb = card.querySelector('a#thumbnail');
                                if (thumb) thumb.setAttribute('data-ref', ref);
                            }
                        });
                    }""")
                    titles = await page.locator(
                        "ytd-video-renderer #video-title, ytd-rich-item-renderer #video-title, #video-title"
                    ).all_inner_texts()
                    if titles:
                        ref_lines = [
                            f'[e{i + 1}] Video: "{t.strip()}"'
                            for i, t in enumerate(titles[:10])
                            if t.strip()
                        ]
                        if ref_lines:
                            snapshot_content = "\n".join(ref_lines) + "\n\n" + snapshot_content
                except Exception:
                    pass
        except Exception:
            try:
                snapshot_content = await page.content()
            except Exception as e:
                snapshot_content = f"Error extracting snapshot: {e}"

        if som_summary:
            snapshot_content = f"{som_summary}\n\n[ARIA Accessibility Tree]:\n{snapshot_content}"

        if max_chars and len(snapshot_content) > max_chars:
            snapshot_content = snapshot_content[:max_chars] + "\n... [truncated]"

        lines = snapshot_content.count("\n") + 1
        chars = len(snapshot_content)

        return {
            "ok": True,
            "targetId": self._active_tab_id,
            "url": page.url,
            "title": page_title,
            "format": snapshot_format,
            "snapshot": snapshot_content,
            "elements": elements,
            "stats": {
                "lines": lines,
                "chars": chars,
                "refs": len(elements),
                "interactive": len(elements),
            },
        }

    async def screenshot(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
        full_page: bool = False,
        element: Optional[str] = None,
        path: Optional[str] = None,
        image_type: str = "png",
        selector: Optional[str] = None,
        annotate: bool = False,
    ) -> dict[str, Any]:
        """Capture a screenshot of the tab or specific element."""
        prof = self._resolve_profile(profile)
        page = await self.get_page(prof, target_id)

        if annotate:
            try:
                await inject_set_of_marks(page, annotate=True)
            except Exception:
                pass

        try:
            shot_type = "jpeg" if image_type.lower() in ("jpeg", "jpg") else "png"
            kwargs: dict[str, Any] = {"type": shot_type}
            if path:
                kwargs["path"] = path

            target_selector = element or selector
            if target_selector:
                locator = page.locator(target_selector)
                raw_bytes = await locator.screenshot(**kwargs)
            else:
                kwargs["full_page"] = full_page
                raw_bytes = await page.screenshot(**kwargs)

            b64 = base64.b64encode(raw_bytes).decode("ascii")
            return {
                "ok": True,
                "targetId": self._active_tab_id,
                "url": page.url,
                "format": f"image/{shot_type}",
                "path": path,
                "base64": b64,
                "annotated": annotate,
            }
        finally:
            if annotate:
                try:
                    await cleanup_set_of_marks(page)
                except Exception:
                    pass

    async def download(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
        selector: Optional[str] = None,
        ref: Optional[str] = None,
        path: Optional[str] = None,
        download_dir: Optional[str] = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """Click a visible download control and save the resulting browser download."""
        prof = self._resolve_profile(profile)
        page = await self.get_page(prof, target_id)
        locator = self._resolve_element_locator(page, selector=selector, ref=ref)
        if locator is None:
            raise ValueError("download requires a visible selector or snapshot ref")

        async with page.expect_download(timeout=timeout_ms) as download_info:
            await getattr(locator, "first", locator).click(timeout=timeout_ms)
        download = await download_info.value

        from pathlib import Path

        suggested_name = Path(download.suggested_filename or "download").name or "download"
        if path:
            destination = Path(path).expanduser()
            if destination.exists() and destination.is_dir():
                destination = destination / suggested_name
        else:
            destination = (
                Path(download_dir).expanduser() if download_dir else Path.home() / "Downloads"
            )
            destination.mkdir(parents=True, exist_ok=True)
            destination = destination / suggested_name

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            stem = destination.stem
            suffix = destination.suffix
            counter = 1
            while destination.exists():
                destination = destination.with_name(f"{stem} ({counter}){suffix}")
                counter += 1

        await download.save_as(str(destination))
        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError(f"Browser download did not produce a non-empty file: {destination}")

        return {
            "ok": True,
            "status": "downloaded",
            "targetId": target_id or self._active_tab_id,
            "url": page.url,
            "path": str(destination),
            "filename": destination.name,
            "sizeBytes": destination.stat().st_size,
        }

    async def extract_text(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Extract innerText of the page body."""
        prof = self._resolve_profile(profile)
        page = await self.get_page(prof, target_id)
        text = await page.evaluate("() => document.body ? document.body.innerText : ''")
        return {
            "ok": True,
            "targetId": self._active_tab_id,
            "url": page.url,
            "text": text,
        }

    async def get_console(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get console messages logged by the page."""
        prof = self._resolve_profile(profile)
        await self.get_page(prof, target_id)
        tid = target_id or self._active_tab_id or ""
        messages = self._console_logs.get(tid, [])
        return {"ok": True, "targetId": tid, "messages": messages}

    async def get_errors(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get uncaught exceptions logged by the page."""
        prof = self._resolve_profile(profile)
        await self.get_page(prof, target_id)
        tid = target_id or self._active_tab_id or ""
        errors = self._page_errors.get(tid, [])
        return {"ok": True, "targetId": tid, "errors": errors}

    def _resolve_element_locator(
        self, page: Any, selector: Optional[str] = None, ref: Optional[str] = None
    ) -> Optional[Any]:
        """Resolve a selector or OpenClaw ref into a Playwright Locator with smart fallbacks."""
        return _resolve_element_locator(page, selector=selector, ref=ref)

    async def act(
        self,
        profile: Optional[Union[ResolvedBrowserProfile, str]] = None,
        target_id: Optional[str] = None,
        kind: Optional[str] = None,
        action: Optional[str] = None,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        key: Optional[str] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        time_ms: Optional[int] = None,
        fn: Optional[str] = None,
        values: Optional[List[str]] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Perform a user interaction on the tab."""
        prof = self._resolve_profile(profile)
        page = await self.get_page(prof, target_id)
        act_kind_raw = kind or action or "click"
        act_kind = str(act_kind_raw).strip()
        act_kind_key = act_kind.lower()
        timeout_ms = int(
            kwargs.get("timeout_ms") or kwargs.get("timeoutMs") or kwargs.get("timeout") or 8000
        )

        locator = self._resolve_element_locator(page, selector=selector, ref=ref)

        # Keep Playwright actionability and strict resolution: recovery must observe
        # a failed action before retrying, never click a different or covered target.
        if act_kind_key == "click":
            await _wait_for_page_ready(page)
            await _dismiss_overlays_if_present(page)
            if locator:
                target_loc = getattr(locator, "first", locator)
                clicked = False
                last_err = None

                # Tier 1: Standard Playwright click
                try:
                    box = await target_loc.bounding_box()
                    if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                        try:
                            await page.mouse.move(
                                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=3
                            )
                        except Exception:
                            pass
                    await target_loc.click(timeout=min(timeout_ms, 2500))
                    clicked = True
                except Exception as err:
                    last_err = err

                # Tier 2: Force click
                if not clicked:
                    try:
                        await target_loc.click(timeout=min(timeout_ms, 1500), force=True)
                        clicked = True
                    except Exception as err:
                        last_err = err

                # Tier 3: JS DOM evaluation click
                if not clicked:
                    try:
                        await target_loc.evaluate(
                            "el => (el.closest('a') || el.closest('button') || el).click()"
                        )
                        clicked = True
                    except Exception as err:
                        last_err = err

                # Tier 4: Center bounding box mouse click
                if not clicked:
                    try:
                        box = await target_loc.bounding_box()
                        if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                            await page.mouse.click(
                                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
                            )
                            clicked = True
                    except Exception as err:
                        last_err = err

                # Tier 5: Direct querySelector click if selector was given
                if not clicked and selector:
                    try:
                        js_click = f"document.querySelector({json.dumps(selector)})?.click()"
                        if await page.evaluate(js_click):
                            clicked = True
                    except Exception as err:
                        last_err = err

                if not clicked:
                    if last_err:
                        raise last_err
                    raise RuntimeError(f"Could not click target: {selector or ref}")
            elif x is not None and y is not None:
                await page.mouse.click(x, y)
            else:
                raise ValueError("click requires selector, ref, or coordinates (x, y)")

            # Wait for navigation / settling after click
            await _wait_for_page_ready(page, max_wait_ms=3000)

        elif act_kind_key == "clickcoords":
            if x is None or y is None:
                raise ValueError("clickCoords requires x and y coordinates")
            await page.mouse.click(x, y)

        elif act_kind_key in ("type", "fill"):
            await _wait_for_page_ready(page)
            type_text = text or str(kwargs.get("value") or "")
            slowly = bool(kwargs.get("slowly", False))
            submit = bool(kwargs.get("submit", False))

            await _dismiss_overlays_if_present(page)

            # Build list of locator candidates
            loc_candidates = []
            if locator is not None:
                loc_candidates.append(getattr(locator, "first", locator))

            # Smart candidate fallback for search boxes (e.g. YouTube input#search)
            if selector and any(s in selector.lower() for s in ("search", "query", "input")):
                for cand in (
                    "input[name='search_query']",
                    "input#search",
                    "#search-input input",
                    "ytd-searchbox input",
                    "input.yt-searchbox-input",
                    "input[type='text']",
                ):
                    try:
                        loc_candidates.append(page.locator(cand).first)
                    except Exception:
                        pass

            success = False
            last_err = None
            for loc in loc_candidates:
                try:
                    if slowly:
                        await loc.click(timeout=min(timeout_ms, 2000))
                        try:
                            await loc.press_sequentially(type_text, timeout=timeout_ms, delay=75)
                        except AttributeError:
                            await loc.type(type_text, timeout=timeout_ms, delay=75)
                    else:
                        await loc.fill(type_text, timeout=min(timeout_ms, 2000))
                    success = True
                    break
                except Exception as ex:
                    last_err = ex
                    try:
                        await loc.click(timeout=1500, force=True)
                        await page.keyboard.type(type_text)
                        success = True
                        break
                    except Exception:
                        continue

            if not success:
                if selector:
                    try:
                        escaped = json.dumps(type_text)
                        js = f"""(() => {{
                            const el = document.querySelector({json.dumps(selector)});
                            if (el) {{
                                el.focus();
                                el.value = {escaped};
                                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }})()"""
                        if await page.evaluate(js):
                            success = True
                    except Exception:
                        pass

                if not success:
                    try:
                        await page.keyboard.type(type_text)
                        success = True
                    except Exception:
                        if last_err:
                            raise last_err
                        raise

            if submit:
                try:
                    if locator:
                        await getattr(locator, "first", locator).press("Enter", timeout=2000)
                    else:
                        await page.keyboard.press("Enter")
                except Exception:
                    await page.keyboard.press("Enter")

        elif act_kind_key == "press":
            await _wait_for_page_ready(page)
            raw_key = str(key or text or "Enter").strip()
            # Intelligent key mappings for YouTube media controls and navigation
            key_map = {
                "play": "k",
                "pause": "k",
                "playpause": "k",
                "play_pause": "k",
                "mute": "m",
                "unmute": "m",
                "fullscreen": "f",
                "full_screen": "f",
                "theater": "t",
                "captions": "c",
                "subtitles": "c",
                "rewind": "j",
                "forward": "l",
            }
            press_key = key_map.get(raw_key.lower(), raw_key)
            if locator:
                try:
                    await locator.press(press_key, timeout=min(timeout_ms, 3000))
                except Exception:
                    await page.keyboard.press(press_key)
            else:
                await page.keyboard.press(press_key)
            await _wait_for_page_ready(page, max_wait_ms=3000)

        elif act_kind_key in ("play", "pause", "playpause", "play_pause"):
            await _wait_for_page_ready(page)
            try:
                video_loc = page.locator("video").first
                if await video_loc.count() > 0:
                    await video_loc.click(timeout=1500)
                else:
                    await page.keyboard.press("k")
            except Exception:
                await page.keyboard.press("k")
            await asyncio.sleep(0.05)

        elif act_kind_key in ("mute", "unmute"):
            await _wait_for_page_ready(page)
            await page.keyboard.press("m")
            await asyncio.sleep(0.05)

        elif act_kind_key in ("fullscreen", "full_screen"):
            await _wait_for_page_ready(page)
            await page.keyboard.press("f")
            await asyncio.sleep(0.05)

        elif act_kind_key in (
            "scroll",
            "wheel",
            "scrolldown",
            "scrollup",
            "scroll_down",
            "scroll_up",
        ):
            await _wait_for_page_ready(page)
            raw_y = (
                kwargs.get("delta_y")
                or kwargs.get("deltaY")
                or kwargs.get("distance")
                or kwargs.get("amount")
                or y
                or 600
            )
            try:
                dy = float(raw_y)
            except Exception:
                dy = 600.0

            if act_kind_key in ("scrollup", "scroll_up") or str(
                kwargs.get("direction", "")
            ).lower() in ("up", "top", "backward"):
                dy = -abs(dy)
            elif act_kind_key in ("scrolldown", "scroll_down") or str(
                kwargs.get("direction", "")
            ).lower() in ("down", "bottom", "forward"):
                dy = abs(dy)

            raw_x = kwargs.get("delta_x") or kwargs.get("deltaX") or x or 0
            try:
                dx = float(raw_x)
            except Exception:
                dx = 0.0

            try:
                await page.mouse.wheel(dx, dy)
            except Exception:
                pass
            try:
                await page.evaluate(f"window.scrollBy({dx}, {dy})")
            except Exception:
                pass
            await asyncio.sleep(0.05)

        elif act_kind_key == "hover":
            if not locator:
                raise ValueError("hover requires selector or ref")
            await locator.hover(timeout=timeout_ms)

        elif act_kind_key == "scrollintoview":
            if not locator:
                raise ValueError("scrollIntoView requires selector or ref")
            await locator.scroll_into_view_if_needed(timeout=timeout_ms)

        elif act_kind_key == "select":
            if not locator:
                raise ValueError("select requires selector or ref")
            select_vals = values or ([text] if text else [])
            await locator.select_option(select_vals, timeout=timeout_ms)

        elif act_kind_key == "resize":
            w = width or 1280
            h = height or 800
            await page.set_viewport_size({"width": w, "height": h})

        elif act_kind_key == "wait":
            if locator is not None:
                await locator.wait_for(state="visible", timeout=timeout_ms)
            elif time_ms is not None:
                await asyncio.sleep(max(0, time_ms) / 1000.0)
            else:
                await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

        elif act_kind_key == "evaluate":
            if not fn:
                raise ValueError("evaluate requires fn parameter")
            eval_result = await page.evaluate(fn)
            return {
                "ok": True,
                "kind": act_kind,
                "targetId": self._active_tab_id,
                "result": eval_result,
            }

        elif act_kind_key in ("new_tab", "newtab", "open_tab"):
            new_tab_url = kwargs.get("url") or text
            res = await self.open_tab(prof, url=new_tab_url)
            return res

        elif act_kind_key in ("switch_tab", "switchtab", "focus_tab"):
            tid = kwargs.get("target_id") or kwargs.get("targetId") or ref or text
            res = await self.focus_tab(prof, target_id=tid)
            return res

        elif act_kind_key in ("close_tab", "closetab"):
            tid = kwargs.get("target_id") or kwargs.get("targetId") or ref or text
            res = await self.close_tab(prof, target_id=tid)
            return res

        elif act_kind_key in ("go_back", "goback", "back"):
            await page.go_back()
            await _wait_for_page_ready(page)
            return {
                "ok": True,
                "kind": act_kind_key,
                "targetId": self._active_tab_id,
                "url": page.url,
                "title": await page.title(),
            }

        elif act_kind_key in ("go_forward", "goforward", "forward"):
            await page.go_forward()
            await _wait_for_page_ready(page)
            return {
                "ok": True,
                "kind": act_kind_key,
                "targetId": self._active_tab_id,
                "url": page.url,
                "title": await page.title(),
            }

        elif act_kind_key in ("reload", "refresh"):
            await page.reload()
            await _wait_for_page_ready(page)
            return {
                "ok": True,
                "kind": act_kind_key,
                "targetId": self._active_tab_id,
                "url": page.url,
                "title": await page.title(),
            }

        elif act_kind_key == "close":
            await page.close()
            return {
                "ok": True,
                "kind": act_kind_key,
                "targetId": self._active_tab_id,
                "status": "closed",
            }

        else:
            raise ValueError(f"Unsupported act kind: {act_kind}")

        page_title = ""
        try:
            res_title = page.title()
            if asyncio.iscoroutine(res_title) or hasattr(res_title, "__await__"):
                page_title = await res_title
            else:
                page_title = str(res_title)
        except Exception:
            pass

        return {
            "ok": True,
            "kind": act_kind_key,
            "targetId": self._active_tab_id,
            "url": getattr(page, "url", ""),
            "title": page_title,
        }

    async def stop(self) -> None:
        """Stop the browser runtime and close Playwright."""
        async with self._get_lock():
            for ctx in list(self.contexts.values()):
                try:
                    await ctx.close()
                except Exception:
                    pass
            self.contexts.clear()

            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
                self.browser = None

            if self.playwright:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass
                self.playwright = None

            self._tabs.clear()
            self._console_logs.clear()
            self._page_errors.clear()
            self._active_tab_id = None

    async def close(self) -> None:
        """Alias for stop()."""
        await self.stop()


_runtime: Optional[BrowserRuntime] = None


async def get_browser_runtime(
    resolved: Optional[ResolvedBrowserConfig] = None,
) -> BrowserRuntime:
    """Retrieve or create the process-singleton BrowserRuntime instance."""
    global _runtime
    current_loop = asyncio.get_running_loop()
    if _runtime is not None and (
        _runtime._loop is None or _runtime._loop.is_closed() or _runtime._loop is not current_loop
    ):
        _runtime = None

    if not _runtime:
        if resolved is None:
            resolved = resolve_browser_config({})
        _runtime = BrowserRuntime(resolved)
        await _runtime.start()
    return _runtime
