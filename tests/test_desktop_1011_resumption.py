"""tests.test_desktop_1011_resumption — Verification for 1011 server error classification,
session resumption handle invalidation, and automated model fallback.
"""

from __future__ import annotations

from typing import cast
from google.genai.errors import APIError

from apps.desktop.src.jarvis_desktop.app import JarvisLive
from apps.desktop.src.jarvis_desktop.ui import JarvisUI


class DummyUI:
    muted: bool = False

    def set_state(self, s: str) -> None:
        pass

    def write_log(self, s: str) -> None:
        pass


def test_is_server_internal_error() -> None:
    ui = cast(JarvisUI, DummyUI())
    j = JarvisLive(ui)

    # 1011 APIError
    err1011 = APIError(1011, "Internal error encountered.", None)
    assert j._is_server_internal_error(err1011) is True

    # ExceptionGroup wrapping 1011
    eg = ExceptionGroup("TaskGroup error", [err1011])
    assert j._is_server_internal_error(eg) is True

    # 503 Service Unavailable
    err503 = Exception("503 Service Unavailable")
    assert j._is_server_internal_error(err503) is True

    # Normal 1008 is NOT an internal error
    err1008 = APIError(1008, "Requested entity was not found.", None)
    assert j._is_server_internal_error(err1008) is False


def test_is_connection_closed_error() -> None:
    ui = cast(JarvisUI, DummyUI())
    j = JarvisLive(ui)

    err1011 = APIError(1011, "Internal error encountered.", None)
    assert j._is_connection_closed_error(err1011) is True

    err_closed = Exception("ConnectionClosedError: received 1000 (normal closure)")
    assert j._is_connection_closed_error(err_closed) is True

    # TypeError is NOT a connection closed error
    err_type = TypeError("object NoneType has no attribute foo")
    assert j._is_connection_closed_error(err_type) is False


def test_exception_group_model_not_found_unpacking() -> None:
    ui = cast(JarvisUI, DummyUI())
    j = JarvisLive(ui)

    err1008 = APIError(1008, "Requested entity was not found.", None)
    eg = ExceptionGroup("TaskGroup error", [err1008])

    assert j._is_model_not_found_error(eg) is True
    assert j._is_server_internal_error(eg) is False
