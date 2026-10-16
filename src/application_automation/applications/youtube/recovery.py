"""jarvis.application_automation.applications.youtube.recovery — Interstitial & popup recovery.

Automatically intercepts and handles:
1. Google Cookie Consent modals ("Before you continue to YouTube")
2. YouTube Premium promotional dialogs
3. Skippable pre-roll and mid-roll advertisements
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from .locators import (
    AD_OVERLAY_SELECTORS,
    COOKIE_CONSENT_SELECTORS,
    PREMIUM_PROMO_DISMISS_SELECTORS,
    SKIP_AD_SELECTORS,
)


class YouTubeRecoveryHandler:
    """Detects and resolves blocking popups, ads, and consent dialogs on YouTube."""

    @staticmethod
    async def dismiss_cookie_consent(page: Any) -> bool:
        """Find and click cookie consent accept/agree buttons."""
        for selector in COOKIE_CONSENT_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.5)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    async def dismiss_premium_dialog(page: Any) -> bool:
        """Find and click dismiss buttons on YouTube Premium promotional popups."""
        for selector in PREMIUM_PROMO_DISMISS_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    await el.click()
                    await asyncio.sleep(0.3)
                    return True
            except Exception:
                continue
        return False

    @staticmethod
    async def handle_advertisements(page: Any) -> Dict[str, Any]:
        """Detect active ad and attempt to skip it if button is available."""
        is_ad_active = False
        for selector in AD_OVERLAY_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    is_ad_active = True
                    break
            except Exception:
                continue

        if not is_ad_active:
            return {"ad_active": False}

        # Try clicking skip ad button
        for selector in SKIP_AD_SELECTORS:
            try:
                btn = await page.query_selector(selector)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.5)
                    return {"ad_active": True, "skipped": True}
            except Exception:
                continue

        return {"ad_active": True, "skipped": False, "status": "Ad is playing (skip not yet available)."}

    @classmethod
    async def handle_all_interstitials(cls, page: Any) -> bool:
        """Run all interstitial dismissers in sequence. Returns True if any was handled."""
        handled = False
        if await cls.dismiss_cookie_consent(page):
            handled = True
        if await cls.dismiss_premium_dialog(page):
            handled = True
        ad_res = await cls.handle_advertisements(page)
        if ad_res.get("skipped"):
            handled = True
        return handled
