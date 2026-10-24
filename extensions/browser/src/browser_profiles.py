"""Browser profiles configuration and defaults."""

import os
from typing import Dict, Any, Optional
from .config import (
    BrowserConfig,
    BrowserProfileConfig,
    ResolvedBrowserConfig,
    ResolvedBrowserProfile,
    BrowserTabCleanupConfig,
    BrowserSsrFPolicy,
)

DEFAULT_BROWSER_CONTROL_PORT = 18791
DEFAULT_BROWSER_CDP_PORT_RANGE_START = 18800
DEFAULT_BROWSER_CDP_PORT_RANGE_END = 18899
DEFAULT_BROWSER_CDP_PORT_RANGE_SPAN = (
    DEFAULT_BROWSER_CDP_PORT_RANGE_END - DEFAULT_BROWSER_CDP_PORT_RANGE_START
)

DEFAULT_OPENCLAW_BROWSER_ENABLED = True
DEFAULT_BROWSER_EVALUATE_ENABLED = True
DEFAULT_OPENCLAW_BROWSER_PROFILE_NAME = "jarvis"
DEFAULT_BROWSER_DEFAULT_PROFILE_NAME = "jarvis"
DEFAULT_OPENCLAW_BROWSER_COLOR = "#00E5FF"
DEFAULT_BROWSER_LOCAL_LAUNCH_TIMEOUT_MS = 30000
DEFAULT_BROWSER_LOCAL_CDP_READY_TIMEOUT_MS = 30000
DEFAULT_BROWSER_ACTION_TIMEOUT_MS = 30000
DEFAULT_BROWSER_HEADLESS = False


def resolve_browser_config(
    raw_config: BrowserConfig | Dict[str, Any] | None,
) -> ResolvedBrowserConfig:
    """Normalize raw browser config into a ResolvedBrowserConfig."""
    cfg = raw_config or {}
    enabled = cfg.get("enabled", DEFAULT_OPENCLAW_BROWSER_ENABLED)

    control_port = cfg.get("controlPort", DEFAULT_BROWSER_CONTROL_PORT)
    cdp_range_start = cfg.get("cdpPortRangeStart", DEFAULT_BROWSER_CDP_PORT_RANGE_START)
    cdp_range_end = cfg.get("cdpPortRangeEnd", DEFAULT_BROWSER_CDP_PORT_RANGE_END)

    # Process headless override
    headless_cfg = cfg.get("headless", DEFAULT_BROWSER_HEADLESS)
    headless_source = "default"

    import sys

    if sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            headless_cfg = True
            headless_source = "linux-no-display-fallback"

    env_headless = os.environ.get("OPENCLAW_BROWSER_HEADLESS")
    if env_headless is not None:
        headless_cfg = env_headless in ("1", "true", "True")
        headless_source = "env"

    from pathlib import Path

    jarvis_profile_dir = str(Path.home() / ".jarvis" / "browser" / "chrome_profile")
    profiles = cfg.get("profiles", {})
    if not profiles:
        profiles = {
            "jarvis": BrowserProfileConfig(
                driver="jarvis",
                color=DEFAULT_OPENCLAW_BROWSER_COLOR,
                userDataDir=jarvis_profile_dir,
                cdpPort=9222,
            ),
            "openclaw": BrowserProfileConfig(
                driver="jarvis",
                color=DEFAULT_OPENCLAW_BROWSER_COLOR,
                userDataDir=jarvis_profile_dir,
                cdpPort=9222,
            ),
            "user": BrowserProfileConfig(
                driver="existing-session",
            ),
        }

    # Python-specific default values filling
    resolved_profiles: Dict[str, ResolvedBrowserProfile] = {}
    for name, p in profiles.items():
        # Ensure we have type safe defaults for the profiles
        resolved_profiles[name] = ResolvedBrowserProfile(
            name=name,
            cdpPort=p.get(
                "cdpPort", 9222 if name in ("jarvis", "openclaw", "user") else control_port + 2000
            ),
            cdpUrl=p.get("cdpUrl", ""),
            cdpHost="127.0.0.1",
            cdpIsLoopback=True,
            color=p.get("color", DEFAULT_OPENCLAW_BROWSER_COLOR),
            driver=p.get("driver", "openclaw"),
            executablePath=p.get("executablePath"),
            headless=p.get("headless", headless_cfg),
            headlessSource=p.get("headlessSource", headless_source),
            attachOnly=p.get("attachOnly", False),
            userDataDir=p.get(
                "userDataDir", jarvis_profile_dir if name in ("jarvis", "openclaw") else None
            ),
            mcpCommand=p.get("mcpCommand"),
            mcpArgs=p.get("mcpArgs"),
        )

    return ResolvedBrowserConfig(
        enabled=enabled,
        evaluateEnabled=cfg.get("evaluateEnabled", DEFAULT_BROWSER_EVALUATE_ENABLED),
        controlPort=control_port,
        cdpPortRangeStart=cdp_range_start,
        cdpPortRangeEnd=cdp_range_end,
        cdpProtocol=cfg.get("cdpProtocol", "http"),
        cdpHost="127.0.0.1",
        cdpIsLoopback=True,
        remoteCdpTimeoutMs=cfg.get("remoteCdpTimeoutMs", 10000),
        remoteCdpHandshakeTimeoutMs=cfg.get("remoteCdpHandshakeTimeoutMs", 15000),
        localLaunchTimeoutMs=cfg.get(
            "localLaunchTimeoutMs", DEFAULT_BROWSER_LOCAL_LAUNCH_TIMEOUT_MS
        ),
        localCdpReadyTimeoutMs=cfg.get(
            "localCdpReadyTimeoutMs", DEFAULT_BROWSER_LOCAL_CDP_READY_TIMEOUT_MS
        ),
        actionTimeoutMs=cfg.get("actionTimeoutMs", DEFAULT_BROWSER_ACTION_TIMEOUT_MS),
        color=cfg.get("color", DEFAULT_OPENCLAW_BROWSER_COLOR),
        executablePath=cfg.get("executablePath"),
        headless=headless_cfg,
        headlessSource=headless_source,
        noSandbox=cfg.get("noSandbox", False),
        attachOnly=cfg.get("attachOnly", False),
        defaultProfile=cfg.get("defaultProfile", DEFAULT_BROWSER_DEFAULT_PROFILE_NAME),
        profiles=resolved_profiles,
        tabCleanup=cfg.get(
            "tabCleanup", BrowserTabCleanupConfig(enabled=True, maxStaleAgeMs=3600000)
        ),
        ssrfPolicy=cfg.get(
            "ssrfPolicy",
            BrowserSsrFPolicy(allowLoopback=False, allowedHostnames=[], allowedCidrRanges=[]),
        ),
        extraArgs=cfg.get("extraArgs", []),
        extensionRelayDefaultPort=control_port + 1000,
        extensionRelayPorts={},
        extensionRelayToken=cfg.get("extensionRelayToken"),
    )


def resolve_profile(
    config: ResolvedBrowserConfig, name: Optional[str] = None
) -> Optional[ResolvedBrowserProfile]:
    """Find a browser profile by name in the resolved config with smart alias resolution.

    Prevents 'Unknown browser profile' errors when models request 'chrome', 'default',
    'chromium', or 'personal'.
    """
    if not name:
        target_name = config.defaultProfile
    else:
        target_name = str(name).strip().lower()

    if target_name in config.profiles:
        return config.profiles[target_name]

    # Smart profile aliases (JARVIS parity)
    if target_name in (
        "jarvis",
        "openclaw",
        "chrome",
        "default",
        "chromium",
        "google-chrome",
        "google_chrome",
        "system",
    ):
        if "jarvis" in config.profiles:
            return config.profiles["jarvis"]
        if "openclaw" in config.profiles:
            return config.profiles["openclaw"]
    if target_name in ("user", "user-session", "personal", "my-chrome", "my_chrome", "existing"):
        if "user" in config.profiles:
            return config.profiles["user"]

    # Safe fallback to configured default profile
    return config.profiles.get(config.defaultProfile)
