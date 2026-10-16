"""jarvis.application_automation.applications.youtube.locators — 4-tier resilient YouTube locators.

Cascade:
1. ARIA Accessibility selectors (role, aria-label)
2. Semantic custom element & data-attribute selectors
3. Reliable CSS / DOM selectors
4. Direct JavaScript evaluation fallback
"""

from __future__ import annotations

from typing import List

# ── Search Locators ──
SEARCH_INPUT_SELECTORS: List[str] = [
    'input[name="search_query"]',
    'input#search',
    'input[aria-label="Search"]',
    'input.ytSearchboxComponentInput',
    'input[placeholder="Search"]',
    '#search-input input',
]

SEARCH_BUTTON_SELECTORS: List[str] = [
    'button#search-icon-legacy',
    'button[aria-label="Search"]',
    'button.ytSearchboxComponentSearchButton',
    '#search-icon-legacy',
    'ytd-searchbox button#search-icon-legacy',
]

# ── Video Search Results ──
VIDEO_RESULT_TITLE_SELECTORS: List[str] = [
    'ytd-video-renderer a#video-title',
    'a#video-title',
    'ytd-item-section-renderer ytd-video-renderer a#video-title',
    'ytd-rich-item-renderer a#video-title-link',
]

# ── Player Controls ──
PLAY_PAUSE_BUTTON_SELECTORS: List[str] = [
    'button.ytp-play-button',
    'button[aria-label^="Play"]',
    'button[aria-label^="Pause"]',
    '.ytp-play-button.ytp-button',
]

MUTE_BUTTON_SELECTORS: List[str] = [
    'button.ytp-mute-button',
    'button[aria-label^="Mute"]',
    'button[aria-label^="Unmute"]',
]

# ── Video Elements ──
VIDEO_ELEMENT_SELECTORS: List[str] = [
    'video.html5-main-video',
    'video',
    '#movie_player video',
]

# ── Interstitials: Ads ──
SKIP_AD_SELECTORS: List[str] = [
    'button.ytp-skip-ad-button',
    'button.ytp-ad-skip-button-modern',
    '.ytp-ad-skip-button',
    '.ytp-ad-skip-button-modern',
    'button[id*="skip-button"]',
]

AD_OVERLAY_SELECTORS: List[str] = [
    '.ytp-ad-player-overlay',
    '.ytp-ad-module .ytp-ad-player-overlay',
    '.video-ads.ytp-ad-module',
    '.ytp-ad-text',
]

# ── Interstitials: Popups & Cookie Consent ──
COOKIE_CONSENT_SELECTORS: List[str] = [
    'form[action*="consent.youtube.com"] button',
    'form[action*="consent.google.com"] button',
    'button[aria-label*="Accept all"]',
    'button[aria-label*="Reject all"]',
    'button:has-text("Accept all")',
    'button:has-text("I agree")',
    'ytd-button-renderer:has-text("Accept")',
]

PREMIUM_PROMO_DISMISS_SELECTORS: List[str] = [
    'yt-button-renderer:has-text("No thanks")',
    '#dismiss-button',
    'button[aria-label="Dismiss"]',
    'button[aria-label="Close"]',
    'ytd-popup-container button#dismiss-button',
]

# ── Channel Metadata Locators ──
CHANNEL_TITLE_SELECTORS: List[str] = [
    '#channel-header-container #channel-name yt-formatted-string',
    '#channel-header #channel-name',
    'ytd-channel-name a',
    '#upload-info ytd-channel-name a',
    '#owner-sub-count',
    'ytd-video-owner-renderer ytd-channel-name',
    'ytd-channel-renderer #channel-title',
    'h1.dynamic-text-view-model-wiz__h1',
    '#page-header ytd-dynamic-text-view-model',
]

# ── Subscription Controls ──
SUBSCRIBE_BUTTON_SELECTORS: List[str] = [
    'ytd-subscribe-button-renderer button:not([aria-label*="Subscribed" i]):not([aria-label*="Unsubscribe" i])',
    'yt-subscribe-button-view-model button:not([aria-label*="Subscribed" i]):not([aria-label*="Unsubscribe" i])',
    '#subscribe-button button:not([aria-label*="Subscribed" i]):not([aria-label*="Unsubscribe" i])',
    'ytd-channel-renderer #subscribe-button button',
    'ytd-channel-renderer yt-subscribe-button-view-model button',
    'button[aria-label^="Subscribe to" i]',
    'button[aria-label="Subscribe" i]',
    'ytd-subscribe-button-renderer yt-button-shape button',
    '#subscribe-button-shape button',
    'yt-subscribe-button-view-model button',
    'ytd-subscribe-button-renderer button',
    '#subscribe-button button',
]

SUBSCRIBED_INDICATOR_SELECTORS: List[str] = [
    'ytd-subscribe-button-renderer button[aria-label*="Subscribed" i]',
    'ytd-subscribe-button-renderer button[aria-label*="Unsubscribe" i]',
    'yt-subscribe-button-view-model button[aria-label*="Subscribed" i]',
    'yt-subscribe-button-view-model button[aria-label*="Unsubscribe" i]',
    'ytd-channel-renderer #subscribe-button button[aria-label*="Subscribed" i]',
    'button[aria-label*="Current notification state" i]',
    'button[aria-label*="Subscribed" i]',
    'button[aria-label*="Unsubscribe" i]',
    '#subscribe-button button:has-text("Subscribed")',
]

UNSUBSCRIBE_MENU_ITEM_SELECTORS: List[str] = [
    'ytd-menu-popup-renderer ytd-menu-service-item-renderer:has-text("Unsubscribe")',
    'ytd-menu-popup-renderer tp-yt-paper-item:has-text("Unsubscribe")',
    'tp-yt-paper-listbox tp-yt-paper-item:has-text("Unsubscribe")',
    'ytd-popup-container ytd-menu-service-item-renderer:has-text("Unsubscribe")',
    'tp-yt-iron-dropdown [role="menuitem"]:has-text("Unsubscribe")',
]

UNSUBSCRIBE_CONFIRM_SELECTORS: List[str] = [
    'yt-confirm-dialog-renderer #confirm-button button',
    'yt-confirm-dialog-renderer button[aria-label*="Unsubscribe" i]',
    'yt-confirm-dialog-renderer button:has-text("Unsubscribe")',
    'tp-yt-paper-dialog #confirm-button button',
    '#confirm-button button',
    'button[aria-label*="Unsubscribe" i]',
]

MODAL_BACKDROP_SELECTORS: List[str] = [
    'tp-yt-iron-overlay-backdrop',
    'ytd-popup-container tp-yt-iron-overlay-backdrop',
    '.opened[aria-hidden="true"]',
]

