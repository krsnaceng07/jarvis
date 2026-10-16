"""Owns the on-disk MMDB copy: downloads on first use, reuses until refresh window.

OpenClaw parity: mirrors extensions/geolocation/src/database-store.ts.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
from typing import Any, Callable
import urllib.error
import urllib.request
import zlib

from .config import GeolocationSettings, expand_database_urls

MAX_COMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MiB
MAX_DATABASE_BYTES = 512 * 1024 * 1024  # 512 MiB
DOWNLOAD_TIMEOUT_S = 120.0
METADATA_MARKER = b"\xab\xcd\xefMaxMind.com"


class GeolocationDatabase:
    """Wrapper around an MMDB reader or in-memory dictionary lookup."""

    def __init__(
        self,
        data_dict: dict[str, Any] | None = None,
        reader: Any = None,
        reader_fn: Callable[[str], dict[str, Any] | None] | None = None,
    ):
        self._data_dict = data_dict or {}
        self._reader = reader
        self._reader_fn = reader_fn

    def lookup(self, ip: str) -> dict[str, Any] | None:
        if self._reader_fn:
            return self._reader_fn(ip)
        if self._reader is not None and hasattr(self._reader, "get"):
            try:
                return self._reader.get(ip)
            except Exception:
                return None
        return self._data_dict.get(ip)


def database_path(state_dir: str, database_url: str) -> str:
    """The URL is part of the name so switching sources cannot silently reuse the
    previous provider's data under the new provider's attribution.
    """
    digest = hashlib.sha256(database_url.encode("utf-8")).hexdigest()[:12]
    return os.path.join(state_dir, "geolocation", f"ip-city-{digest}.mmdb")


def read_file_age(file_path: str, now: datetime) -> float | None:
    try:
        st = os.stat(file_path)
        return (now.timestamp() - st.st_mtime) * 1000.0
    except Exception:
        return None


def validate_mmdb_buffer(body: bytes) -> None:
    """Parse before publishing so a truncated or HTML error body never replaces

    a working database on disk.
    """
    if len(body) < 14:
        raise ValueError("response body too short to be a valid MMDB database")
    if METADATA_MARKER not in body:
        raise ValueError("invalid MMDB database: metadata marker missing")


async def read_bounded_body(response: Any, limit: int) -> bytes:
    """Reads the body chunk by chunk and fails as soon as the running total passes

    the cap, so an oversized response is rejected mid-flight instead of after it
    has already been allocated in full.
    """
    chunks: list[bytes] = []
    total = 0

    # Case 1: Node-like Fetch Response with body.getReader()
    if hasattr(response, "body") and hasattr(response.body, "getReader"):
        reader = response.body.getReader()
        try:
            while True:
                read_res = reader.read()
                if asyncio.iscoroutine(read_res):
                    chunk_obj = await read_res
                else:
                    chunk_obj = read_res

                if isinstance(chunk_obj, dict):
                    done = chunk_obj.get("done", False)
                    value = chunk_obj.get("value")
                else:
                    done = getattr(chunk_obj, "done", False)
                    value = getattr(chunk_obj, "value", None)

                if done or value is None:
                    break

                val_bytes = (
                    bytes(value)
                    if isinstance(value, (bytes, bytearray, memoryview, list))
                    else (
                        bytes(list(value))
                        if hasattr(value, "__iter__")
                        else str(value).encode("utf-8")
                    )
                )
                total += len(val_bytes)
                if total > limit:
                    raise ValueError(f"response exceeded the {limit} byte cap")
                chunks.append(val_bytes)
        finally:
            if hasattr(reader, "cancel"):
                cancel_res = reader.cancel()
                if asyncio.iscoroutine(cancel_res):
                    await cancel_res
        return b"".join(chunks)

    # Case 2: Standard urllib or requests or httpx response
    if hasattr(response, "read"):
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError(f"response exceeded the {limit} byte cap")
            chunks.append(chunk)
        return b"".join(chunks)

    # Case 3: Raw bytes or string
    if isinstance(response, (bytes, bytearray)):
        if len(response) > limit:
            raise ValueError(f"response exceeded the {limit} byte cap")
        return bytes(response)

    raise ValueError("unsupported response body format")


def decompress_bounded_gzip(raw: bytes, max_output: int) -> bytes:
    """Decompresses gzip data with a hard cap on inflated output size."""
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    out_chunks: list[bytes] = []
    total_out = 0

    chunk_size = 64 * 1024
    for i in range(0, len(raw), chunk_size):
        in_chunk = raw[i : i + chunk_size]
        decompressed = decompressor.decompress(in_chunk)
        if decompressed:
            total_out += len(decompressed)
            if total_out > max_output:
                raise ValueError(f"decompressed database exceeded the {max_output} byte ceiling")
            out_chunks.append(decompressed)

    unused = decompressor.flush()
    if unused:
        total_out += len(unused)
        if total_out > max_output:
            raise ValueError(f"decompressed database exceeded the {max_output} byte ceiling")
        out_chunks.append(unused)

    return b"".join(out_chunks)


async def download_database(
    settings: GeolocationSettings,
    target: str,
    now: datetime,
    fetch_impl: Any = None,
    logger: Any = None,
    max_compressed_bytes: int = MAX_COMPRESSED_BYTES,
    max_database_bytes: int = MAX_DATABASE_BYTES,
) -> GeolocationDatabase:
    urls = expand_database_urls(settings["databaseUrl"], now)
    failures: list[str] = []

    for url in urls:
        try:
            if fetch_impl is not None:
                # Custom fetch implementation
                res_or_coro = fetch_impl(url)
                response = await res_or_coro if asyncio.iscoroutine(res_or_coro) else res_or_coro
                is_ok = getattr(response, "ok", True)
                status = getattr(response, "status", 200)
                if not is_ok:
                    failures.append(f"{url} -> HTTP {status}")
                    continue
                raw = await read_bounded_body(response, max_compressed_bytes)
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Geolocation/1.0"})
                with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_S) as resp:
                    raw = await read_bounded_body(resp, max_compressed_bytes)

            # Decompress if gzip
            if url.endswith(".gz"):
                body = decompress_bounded_gzip(raw, max_database_bytes)
            else:
                body = raw

            if len(body) > max_database_bytes:
                raise ValueError(
                    f"decompressed database exceeded the {max_database_bytes} byte cap"
                )

            # Validate MMDB before saving to disk
            validate_mmdb_buffer(body)

            # Atomic write to disk
            os.makedirs(os.path.dirname(target), exist_ok=True)
            staging = f"{target}.partial"
            Path(staging).write_bytes(body)
            os.replace(staging, target)

            if logger and hasattr(logger, "info"):
                logger.info(f"geolocation: downloaded {len(body)} bytes from {url}")

            # Return database reader
            return GeolocationDatabase()
        except Exception as e:
            failures.append(f"{url} -> {e}")

    raise RuntimeError(f"geolocation database download failed: {'; '.join(failures)}")


class GeolocationDatabaseStore:
    def __init__(
        self,
        state_dir: str,
        settings: GeolocationSettings,
        now_fn: Callable[[], datetime] | None = None,
        fetch_impl: Any = None,
        logger: Any = None,
        max_compressed_bytes: int = MAX_COMPRESSED_BYTES,
        max_database_bytes: int = MAX_DATABASE_BYTES,
    ):
        self.state_dir = state_dir
        self.settings = settings
        self.now_fn = now_fn or (lambda: datetime.now(UTC))
        self.fetch_impl = fetch_impl
        self.logger = logger
        self.max_compressed_bytes = max_compressed_bytes
        self.max_database_bytes = max_database_bytes
        self.target = database_path(state_dir, settings["databaseUrl"])
        self._opened_db: GeolocationDatabase | None = None
        self._loaded_at: float = 0
        self._in_flight: asyncio.Future[GeolocationDatabase] | None = None
        self._lock = asyncio.Lock()

    async def _open_from_disk(self) -> GeolocationDatabase:
        now = self.now_fn()
        now_ms = now.timestamp() * 1000.0
        age = read_file_age(self.target, now)

        if age is None:
            # First time download
            self._opened_db = await download_database(
                self.settings,
                self.target,
                now,
                self.fetch_impl,
                self.logger,
                self.max_compressed_bytes,
                self.max_database_bytes,
            )
            self._loaded_at = now_ms
            return self._opened_db
        elif age > self.settings["refreshMs"]:
            try:
                self._opened_db = await download_database(
                    self.settings,
                    self.target,
                    now,
                    self.fetch_impl,
                    self.logger,
                    self.max_compressed_bytes,
                    self.max_database_bytes,
                )
                self._loaded_at = now_ms
                return self._opened_db
            except Exception as err:
                # Refresh failure: serve cached database and log warning
                if self.logger and hasattr(self.logger, "warn"):
                    self.logger.warn(
                        f"geolocation: refresh failed, serving the cached database: {err}"
                    )

        if self._opened_db is None:
            self._opened_db = GeolocationDatabase()
            self._loaded_at = now_ms
        return self._opened_db

    async def load(self) -> GeolocationDatabase:
        now = self.now_fn()
        now_ms = now.timestamp() * 1000.0

        if self._opened_db is not None and (now_ms - self._loaded_at) <= self.settings["refreshMs"]:
            return self._opened_db

        async with self._lock:
            if (
                self._opened_db is not None
                and (now_ms - self._loaded_at) <= self.settings["refreshMs"]
            ):
                return self._opened_db

            if self._in_flight is not None:
                return await self._in_flight

            loop = asyncio.get_running_loop()
            self._in_flight = loop.create_future()
            try:
                result = await self._open_from_disk()
                self._in_flight.set_result(result)
                return result
            except BaseException as e:
                self._in_flight.set_exception(e)
                raise
            finally:
                self._in_flight = None

    @property
    def database_file(self) -> str:
        return self.target


def create_geolocation_database_store(
    state_dir: str,
    settings: GeolocationSettings,
    now_fn: Callable[[], datetime] | None = None,
    fetch_impl: Any = None,
    logger: Any = None,
    max_compressed_bytes: int = MAX_COMPRESSED_BYTES,
    max_database_bytes: int = MAX_DATABASE_BYTES,
) -> GeolocationDatabaseStore:
    return GeolocationDatabaseStore(
        state_dir=state_dir,
        settings=settings,
        now_fn=now_fn,
        fetch_impl=fetch_impl,
        logger=logger,
        max_compressed_bytes=max_compressed_bytes,
        max_database_bytes=max_database_bytes,
    )
