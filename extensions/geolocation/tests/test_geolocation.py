"""Unit tests for the bundled geolocation plugin.

OpenClaw parity: mirrors config.test.ts, database-store.test.ts, and lookup-route.test.ts.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import gzip
from pathlib import Path
import tempfile
from unittest.mock import MagicMock

import pytest

from extensions.geolocation.src.config import (
    expand_database_urls,
    resolve_geolocation_settings,
)
from extensions.geolocation.src.database_store import (
    METADATA_MARKER,
    GeolocationDatabase,
    create_geolocation_database_store,
)
from extensions.geolocation.src.lookup import project_geolocation_record
from extensions.geolocation.src.lookup_route import (
    create_geolocation_lookup_handler,
    is_private_or_loopback_ip,
    is_valid_ip,
)


class MockResponse:
    """Mock Fetch/HTTP response for testing bounded streaming."""

    def __init__(self, body: bytes | list[bytes], ok: bool = True, status: int = 200):
        self.ok = ok
        self.status = status
        self._body = body
        self.body = self

    def getReader(self):
        chunks = [self._body] if isinstance(self._body, bytes) else list(self._body)
        idx = 0

        class Reader:
            async def read(self):
                nonlocal idx
                if idx >= len(chunks):
                    return {"done": True, "value": None}
                val = chunks[idx]
                idx += 1
                return {"done": False, "value": val}

            async def cancel(self):
                pass

        return Reader()


# ===========================================================================
# 1. Config Tests (mirrors config.test.ts)
# ===========================================================================


def test_geolocation_settings_defaults():
    settings = resolve_geolocation_settings(None)
    assert "dbip-city-lite" in settings["databaseUrl"]
    assert settings["attribution"] == {
        "text": "IP Geolocation by DB-IP",
        "url": "https://db-ip.com",
    }
    assert settings["refreshMs"] == 30 * 24 * 60 * 60 * 1000


def test_geolocation_settings_custom_overrides():
    settings = resolve_geolocation_settings(
        {
            "databaseUrl": "https://example.test/db.mmdb",
            "attributionText": "Data by Example",
            "attributionUrl": "https://example.test",
            "refreshDays": 7,
        }
    )
    assert settings["databaseUrl"] == "https://example.test/db.mmdb"
    assert settings["attribution"]["text"] == "Data by Example"
    assert settings["attribution"]["url"] == "https://example.test"
    assert settings["refreshMs"] == 7 * 24 * 60 * 60 * 1000


def test_geolocation_settings_ignores_unusable_overrides():
    settings = resolve_geolocation_settings(
        {
            "databaseUrl": "   ",
            "attributionText": "",
            "refreshDays": 0,
        }
    )
    assert "dbip-city-lite" in settings["databaseUrl"]
    assert settings["attribution"]["text"] == "IP Geolocation by DB-IP"
    assert settings["refreshMs"] == 30 * 24 * 60 * 60 * 1000


def test_expand_database_urls_monthly_fallback():
    urls = expand_database_urls(
        "https://host.test/db-{yyyy}-{mm}.mmdb.gz",
        datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC),
    )
    assert urls == [
        "https://host.test/db-2026-01.mmdb.gz",
        "https://host.test/db-2025-12.mmdb.gz",
    ]


def test_expand_database_urls_no_repetition_static_template():
    urls = expand_database_urls(
        "https://host.test/db.mmdb",
        datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC),
    )
    assert urls == ["https://host.test/db.mmdb"]


# ===========================================================================
# 2. Database Store Tests (mirrors database-store.test.ts)
# ===========================================================================


@pytest.mark.asyncio
async def test_store_tries_previous_month_when_current_not_published():
    with tempfile.TemporaryDirectory() as tmpdir:
        fetch_calls = []

        async def fetch_impl(url: str):
            fetch_calls.append(url)
            return MockResponse(b"nope", ok=False, status=404)

        store = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings(
                {"databaseUrl": "https://host.test/db-{yyyy}-{mm}.mmdb"}
            ),
            now_fn=lambda: datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC),
            fetch_impl=fetch_impl,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await store.load()
        msg = str(exc_info.value)
        assert "db-2026-01" in msg
        assert "db-2025-12" in msg
        assert len(fetch_calls) == 2


@pytest.mark.asyncio
async def test_store_refuses_to_publish_unparsable_body():
    with tempfile.TemporaryDirectory() as tmpdir:

        async def fetch_impl(url: str):
            return MockResponse(b"<html>rate limited</html>", ok=True, status=200)

        store = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings({"databaseUrl": "https://host.test/db.mmdb"}),
            now_fn=lambda: datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC),
            fetch_impl=fetch_impl,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await store.load()
        assert "db.mmdb" in str(exc_info.value)

        # Ensure no database file was left behind
        geo_dir = Path(tmpdir) / "geolocation"
        assert not geo_dir.exists() or len(list(geo_dir.glob("*.mmdb"))) == 0


@pytest.mark.asyncio
async def test_store_downloads_once_on_concurrent_first_lookup():
    with tempfile.TemporaryDirectory() as tmpdir:
        call_count = 0

        async def fetch_impl(url: str):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            # Valid dummy MMDB with metadata marker
            valid_body = b"data..." + METADATA_MARKER + b"...meta"
            return MockResponse(valid_body, ok=True, status=200)

        store = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings({"databaseUrl": "https://host.test/db.mmdb"}),
            now_fn=lambda: datetime(2026, 1, 3, 0, 0, 0, tzinfo=UTC),
            fetch_impl=fetch_impl,
        )

        results = await asyncio.gather(store.load(), store.load(), store.load())
        assert len(results) == 3
        assert call_count == 1


def test_store_names_source_in_cache_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        store1 = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings({"databaseUrl": "https://a.test/db.mmdb"}),
        )
        store2 = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings({"databaseUrl": "https://b.test/db.mmdb"}),
        )
        assert store1.database_file != store2.database_file


@pytest.mark.asyncio
async def test_store_rejects_oversized_compressed_body_while_reading():
    with tempfile.TemporaryDirectory() as tmpdir:
        # 3 chunks of 100 MiB exceed the 256 MiB cap
        chunk_100mb = b"0" * (100 * 1024 * 1024)

        async def fetch_impl(url: str):
            return MockResponse([chunk_100mb, chunk_100mb, chunk_100mb], ok=True)

        store = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings({"databaseUrl": "https://host.test/db.mmdb"}),
            fetch_impl=fetch_impl,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await store.load()
        assert "byte cap" in str(exc_info.value)


@pytest.mark.asyncio
async def test_store_refuses_gzip_that_inflates_past_ceiling():
    with tempfile.TemporaryDirectory() as tmpdir:
        inflated = b"0" * (10 * 1024)
        compressed = gzip.compress(inflated)

        async def fetch_impl(url: str):
            return MockResponse(compressed, ok=True)

        store = create_geolocation_database_store(
            state_dir=tmpdir,
            settings=resolve_geolocation_settings({"databaseUrl": "https://host.test/db.mmdb.gz"}),
            fetch_impl=fetch_impl,
            max_database_bytes=1024,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await store.load()
        assert "db.mmdb.gz" in str(exc_info.value)


# ===========================================================================
# 3. Lookup Projections Tests
# ===========================================================================


def test_project_geolocation_record_none_and_empty():
    assert project_geolocation_record(None) is None
    assert project_geolocation_record({}) is None


def test_project_geolocation_record_fields():
    record = {
        "city": {"names": {"en": "Vienna", "de": "Wien"}},
        "subdivisions": [{"names": {"en": "Vienna"}}],
        "country": {"names": {"en": "Austria"}, "iso_code": "AT"},
    }
    projected = project_geolocation_record(record)
    assert projected == {
        "city": "Vienna",
        "region": "Vienna",
        "country": "Austria",
        "countryCode": "AT",
    }


# ===========================================================================
# 4. Lookup Route Tests (mirrors lookup-route.test.ts)
# ===========================================================================


@pytest.mark.asyncio
async def test_lookup_route_answers_with_placement_and_credit():
    settings = resolve_geolocation_settings(None)
    handler = create_geolocation_lookup_handler(
        settings=settings,
        load_database=lambda: GeolocationDatabase(
            reader_fn=lambda ip: {
                "city": {"names": {"en": "Vienna"}},
                "subdivisions": [{"names": {"en": "Vienna"}}],
                "country": {"iso_code": "AT", "names": {"en": "Austria"}},
            }
        ),
    )

    status, body = await handler.handle_request(
        "/plugins/geolocation/lookup", {"ip": "203.0.113.7"}
    )
    assert status == 200
    assert body["found"] is True
    assert body["city"] == "Vienna"
    assert body["country"] == "Austria"
    assert body["countryCode"] == "AT"
    assert body["attribution"] == {
        "text": "IP Geolocation by DB-IP",
        "url": "https://db-ip.com",
    }


@pytest.mark.asyncio
async def test_lookup_route_reports_database_outage_as_503():
    settings = resolve_geolocation_settings(None)
    logger = MagicMock()

    async def fail_load():
        raise RuntimeError("download failed")

    handler = create_geolocation_lookup_handler(
        settings=settings,
        load_database=fail_load,
        logger=logger,
    )

    status, body = await handler.handle_request(
        "/plugins/geolocation/lookup", {"ip": "203.0.113.7"}
    )
    assert status == 503
    assert "found" not in body
    assert body["error"] == "geolocation database unavailable"
    assert logger.warn.called


@pytest.mark.asyncio
async def test_lookup_route_distinguishes_address_not_placed():
    settings = resolve_geolocation_settings(None)
    handler = create_geolocation_lookup_handler(
        settings=settings,
        load_database=lambda: GeolocationDatabase(reader_fn=lambda ip: None),
    )

    status, body = await handler.handle_request(
        "/plugins/geolocation/lookup", {"ip": "203.0.113.7"}
    )
    assert status == 200
    assert body["found"] is False
    assert body["attribution"] == {
        "text": "IP Geolocation by DB-IP",
        "url": "https://db-ip.com",
    }


@pytest.mark.asyncio
async def test_lookup_route_rejects_non_ip():
    settings = resolve_geolocation_settings(None)
    mock_lookup = MagicMock()
    handler = create_geolocation_lookup_handler(
        settings=settings,
        load_database=lambda: GeolocationDatabase(reader_fn=mock_lookup),
    )

    status, body = await handler.handle_request("/plugins/geolocation/lookup", {"ip": "not-an-ip"})
    assert status == 400
    assert "error" in body
    assert not mock_lookup.called


@pytest.mark.asyncio
async def test_lookup_route_answers_unresolvable_ranges_without_database():
    settings = resolve_geolocation_settings(None)
    mock_load = MagicMock()
    handler = create_geolocation_lookup_handler(
        settings=settings,
        load_database=mock_load,
    )

    unresolvable_ips = [
        "100.64.1.5",  # CGNAT
        "192.168.1.20",  # Private
        "10.0.0.4",  # Private
        "127.0.0.1",  # Loopback
        "169.254.1.1",  # Link-local
    ]

    for ip in unresolvable_ips:
        status, body = await handler.handle_request("/plugins/geolocation/lookup", {"ip": ip})
        assert status == 200
        assert body["found"] is False

    assert not mock_load.called


@pytest.mark.asyncio
async def test_lookup_route_consults_database_for_routable_address():
    settings = resolve_geolocation_settings(None)
    mock_load = MagicMock(return_value=GeolocationDatabase(reader_fn=lambda ip: None))
    handler = create_geolocation_lookup_handler(
        settings=settings,
        load_database=mock_load,
    )

    status, body = await handler.handle_request("/plugins/geolocation/lookup", {"ip": "8.8.8.8"})
    assert status == 200
    assert body["found"] is False
    assert mock_load.called


def test_ip_helpers():
    assert is_valid_ip("8.8.8.8") is True
    assert is_valid_ip("2001:4860:4860::8888") is True
    assert is_valid_ip("invalid") is False

    assert is_private_or_loopback_ip("127.0.0.1") is True
    assert is_private_or_loopback_ip("10.0.0.1") is True
    assert is_private_or_loopback_ip("192.168.1.1") is True
    assert is_private_or_loopback_ip("100.64.1.5") is True  # CGNAT
    assert is_private_or_loopback_ip("::1") is True
    assert is_private_or_loopback_ip("8.8.8.8") is False
    assert is_private_or_loopback_ip("invalid") is False
