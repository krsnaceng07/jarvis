"""Pytest fixtures for beam tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def sample_beam_upload():
    return {
        "version": 1,
        "beamId": "0123456789abcdef0123456789abcdef",
        "source": "claude-code",
        "title": "Fix memory leak in web client",
        "updatedAt": "2025-06-01T12:00:00Z",
        "completed": True,
        "items": [
            {"type": "userMessage", "text": "Can you check this bug?"},
            {"type": "agentMessage", "text": "Fixed in patch."},
        ],
    }
