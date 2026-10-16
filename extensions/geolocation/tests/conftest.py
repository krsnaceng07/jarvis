"""Pytest fixtures for geolocation tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_settings():
    return {
        "databaseUrl": "https://example.com/geo-{yyyy}-{mm}.mmdb.gz",
        "attribution": {
            "text": "Custom Geo Credit",
            "url": "https://example.com",
        },
        "refreshMs": 7 * 24 * 60 * 60 * 1000,
    }
