"""Unit tests for the Beam snapshot receiver, storage, and mirror."""

import pytest

from extensions.beam.src.http import create_beam_request_handler
from extensions.beam.src.mirror import parse_beam_mirror_config
from extensions.beam.src.store import create_beam_store
from extensions.beam.src.types import (
    BEAM_MAX_ITEM_CHARS,
    BEAM_MAX_ITEMS,
    build_beam_url,
    parse_beam_upload,
    slugify_title,
)


def test_slugify_and_build_url():
    slug = slugify_title("Fix the upload flow")
    assert slug == "fix-the-upload-flow"

    url = build_beam_url("Fix the upload flow", "0123456789abcdef0123456789abcdef")
    assert url == "/beam/fix-the-upload-flow-0123456789ab"

    url_base = build_beam_url(
        "Fix the upload flow",
        "0123456789abcdef0123456789abcdef",
        base_path="/openclaw",
    )
    assert url_base == "/openclaw/beam/fix-the-upload-flow-0123456789ab"

    # Empty slug fallback
    url_noslug = build_beam_url("", "0123456789abcdef0123456789abcdef")
    assert url_noslug == "/beam/0123456789ab"


def test_parse_beam_upload_valid():
    raw = {
        "version": 1,
        "beamId": "0123456789abcdef0123456789abcdef",
        "source": "claude",
        "title": "Fix the upload flow",
        "updatedAt": "2026-07-20T12:00:00.000Z",
        "completed": False,
        "items": [
            {"type": "userMessage", "text": "Fix the upload flow."},
            {"type": "agentMessage", "text": "Implemented and tested."},
            {
                "type": "other",
                "text": "3 read, 2 write, 1 execute; raw tool outputs dropped: 4",
            },
        ],
    }
    ok, upload, err = parse_beam_upload(raw)
    assert ok is True
    assert err is None
    assert upload is not None
    assert upload["beamId"] == "0123456789abcdef0123456789abcdef"
    assert len(upload["items"]) == 3


def test_parse_beam_upload_rejects_empty_text():
    raw = {
        "version": 1,
        "beamId": "0123456789abcdef0123456789abcdef",
        "source": "claude",
        "title": "Test",
        "updatedAt": "2026-07-20T12:00:00.000Z",
        "completed": False,
        "items": [{"type": "userMessage", "text": ""}],
    }
    ok, upload, err = parse_beam_upload(raw)
    assert ok is False
    assert "non-empty" in err


def test_parse_beam_upload_rejects_too_many_items():
    raw = {
        "version": 1,
        "beamId": "0123456789abcdef0123456789abcdef",
        "source": "claude",
        "title": "Test",
        "updatedAt": "2026-07-20T12:00:00.000Z",
        "completed": False,
        "items": [{"type": "userMessage", "text": f"Msg {i}"} for i in range(BEAM_MAX_ITEMS + 1)],
    }
    ok, upload, err = parse_beam_upload(raw)
    assert ok is False
    assert "at most 200 entries" in err


def test_parse_beam_upload_rejects_oversized_item_text():
    raw = {
        "version": 1,
        "beamId": "0123456789abcdef0123456789abcdef",
        "source": "claude",
        "title": "Test",
        "updatedAt": "2026-07-20T12:00:00.000Z",
        "completed": False,
        "items": [{"type": "userMessage", "text": "a" * (BEAM_MAX_ITEM_CHARS + 1)}],
    }
    ok, upload, err = parse_beam_upload(raw)
    assert ok is False
    assert "6000 characters" in err


@pytest.mark.asyncio
async def test_store_monotonic_updates_and_completion():
    store = create_beam_store()
    bid = "0123456789abcdef0123456789abcdef"

    # First upload
    up1 = {
        "version": 1,
        "beamId": bid,
        "source": "claude",
        "title": "Upload 1",
        "updatedAt": "2026-07-20T12:00:00.000Z",
        "completed": False,
        "items": [{"type": "userMessage", "text": "Msg 1"}],
    }
    s1 = await store.put(up1, uploader_profile_id="user-1")
    assert s1["title"] == "Upload 1"
    assert s1["uploaderProfileId"] == "user-1"

    # Older upload ignored
    up_older = {
        "version": 1,
        "beamId": bid,
        "source": "claude",
        "title": "Older Upload",
        "updatedAt": "2026-07-20T11:00:00.000Z",
        "completed": False,
        "items": [{"type": "userMessage", "text": "Msg 0"}],
    }
    s_ignored = await store.put(up_older, uploader_profile_id="user-2")
    assert s_ignored["title"] == "Upload 1"  # Retained

    # Newer upload accepted
    up2 = {
        "version": 1,
        "beamId": bid,
        "source": "claude",
        "title": "Upload 2 (Done)",
        "updatedAt": "2026-07-20T13:00:00.000Z",
        "completed": True,
        "items": [{"type": "userMessage", "text": "Msg 2"}],
    }
    s2 = await store.put(up2, uploader_profile_id="user-2")
    assert s2["title"] == "Upload 2 (Done)"
    assert s2["completed"] is True
    assert s2["uploaderProfileId"] == "user-2"

    # Equal-timestamp completion regression ignored
    up_regress = {
        "version": 1,
        "beamId": bid,
        "source": "claude",
        "title": "Regress to Live",
        "updatedAt": "2026-07-20T13:00:00.000Z",
        "completed": False,
        "items": [{"type": "userMessage", "text": "Msg 2"}],
    }
    s_regress = await store.put(up_regress)
    assert s_regress["completed"] is True  # Did not regress


@pytest.mark.asyncio
async def test_store_delete():
    store = create_beam_store()
    bid = "0123456789abcdef0123456789abcdef"
    up = {
        "version": 1,
        "beamId": bid,
        "source": "claude",
        "title": "Delete Me",
        "updatedAt": "2026-07-20T12:00:00.000Z",
        "completed": True,
        "items": [{"type": "userMessage", "text": "Hi"}],
    }
    await store.put(up)
    assert await store.get(bid) is not None

    deleted = await store.delete(bid)
    assert deleted is True
    assert await store.get(bid) is None

    deleted_again = await store.delete(bid)
    assert deleted_again is False


@pytest.mark.asyncio
async def test_http_request_handler_flow():
    store = create_beam_store()
    handler = create_beam_request_handler(store)

    import json

    body = json.dumps(
        {
            "version": 1,
            "beamId": "0123456789abcdef0123456789abcdef",
            "source": "claude",
            "title": "Fix the upload flow",
            "updatedAt": "2026-07-20T12:00:00.000Z",
            "completed": False,
            "items": [{"type": "userMessage", "text": "Fix the upload flow."}],
        }
    ).encode("utf-8")

    # Missing write scope -> 403
    status, res = await handler.handle_request("POST", body, client_scopes=["operator.read"])
    assert status == 403
    assert res["ok"] is False

    # GET -> 405
    status, res = await handler.handle_request("GET", body, client_scopes=["operator.write"])
    assert status == 405

    # Valid POST with operator.write -> 200
    status, res = await handler.handle_request(
        "POST", body, client_scopes=["operator.write"], uploader_profile_id="u1"
    )
    assert status == 200
    assert res["ok"] is True
    assert res["beamId"] == "0123456789abcdef0123456789abcdef"
    assert res["url"] == "/beam/fix-the-upload-flow-0123456789ab"


def test_mirror_config_validation():
    # Valid remote HTTPS config
    cfg_valid = {
        "plugins": {
            "entries": {
                "beam": {
                    "config": {
                        "mirror": {
                            "endpoint": "https://team.example.com/api/v1/beam/sessions",
                            "token": "secret-token",
                            "catalogs": ["claude", "codex", "beam"],
                        }
                    }
                }
            }
        }
    }
    parsed = parse_beam_mirror_config(cfg_valid)
    assert isinstance(parsed, dict)
    assert parsed["endpoint"] == "https://team.example.com/api/v1/beam/sessions"
    assert parsed["catalogs"] == ["claude", "codex"]  # beam excluded!
    assert parsed["pollSeconds"] == 30

    # Insecure plaintext HTTP for remote host -> error
    cfg_insecure = {
        "plugins": {
            "entries": {
                "beam": {
                    "config": {
                        "mirror": {
                            "endpoint": "http://remote.example.com/api/v1/beam/sessions",
                            "catalogs": ["claude"],
                        }
                    }
                }
            }
        }
    }
    err = parse_beam_mirror_config(cfg_insecure)
    assert isinstance(err, str)
    assert "HTTPS" in err

    # Plaintext HTTP allowed for localhost
    cfg_local = {
        "plugins": {
            "entries": {
                "beam": {
                    "config": {
                        "mirror": {
                            "endpoint": "http://localhost:7433/api/v1/beam/sessions",
                            "catalogs": ["claude"],
                        }
                    }
                }
            }
        }
    }
    parsed_local = parse_beam_mirror_config(cfg_local)
    assert isinstance(parsed_local, dict)
