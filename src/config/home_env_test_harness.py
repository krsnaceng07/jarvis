"""jarvis.config.home_env_test_harness — temp-home test harness for config tests.

OpenClaw parity: mirrors
``openclaw-main/src/config/home-env.test-harness.ts``.

Focused minimal port: provides a ``with_temp_home`` async helper that
sets ``HOME``/``USERPROFILE`` to a temp directory for the duration of
``fn`` and restores them afterward.
"""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from typing import Iterator, TypeVar

T = TypeVar("T")


@contextmanager
def with_temp_home(prefix: str) -> Iterator[str]:
    """Run code with a temporary home directory.

    The Python port uses a synchronous context manager that creates a
    temp directory, sets ``HOME``/``USERPROFILE`` to it, and restores
    the originals on exit. Async-friendly callers can wrap in
    ``asyncio.to_thread``.
    """
    tmp = tempfile.mkdtemp(prefix=prefix)
    saved_home = os.environ.get("HOME")
    saved_userprofile = os.environ.get("USERPROFILE")
    os.environ["HOME"] = tmp
    if "USERPROFILE" in os.environ or hasattr(os, "getenv"):
        os.environ["USERPROFILE"] = tmp
    try:
        yield tmp
    finally:
        if saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved_home
        if saved_userprofile is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = saved_userprofile
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except OSError:
            pass


__all__ = ["with_temp_home"]
