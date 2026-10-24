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


def test_deadline_expired_error_classification() -> None:
    ui = cast(JarvisUI, DummyUI())
    j = JarvisLive(ui)

    # 1011 deadline expired error
    err_deadline = APIError(1011, "None. Deadline expired before operation could complete.", None)
    assert j._is_deadline_expired_error(err_deadline) is True
    # Deadline expiration must NOT be treated as a fatal server internal error
    assert j._is_server_internal_error(err_deadline) is False
    # It must be treated as a connection closed error
    assert j._is_connection_closed_error(err_deadline) is True

    # ExceptionGroup wrapping deadline expired
    eg_deadline = ExceptionGroup("TaskGroup error", [err_deadline])
    assert j._is_deadline_expired_error(eg_deadline) is True
    assert j._is_server_internal_error(eg_deadline) is False


def test_session_resumption_config_initial_and_updated() -> None:
    ui = cast(JarvisUI, DummyUI())
    j = JarvisLive(ui)

    # Initial session configuration must include SessionResumptionConfig even when handle is None
    cfg_initial = j._build_config()
    assert cfg_initial.session_resumption is not None
    assert cfg_initial.session_resumption.handle is None

    # When handle is captured from server update, it must flow into next config
    j._session_resumption_handle = "test-resumption-token-12345"
    cfg_resumed = j._build_config()
    assert cfg_resumed.session_resumption is not None
    assert cfg_resumed.session_resumption.handle == "test-resumption-token-12345"


def test_invalid_argument_1007_classification() -> None:
    ui = cast(JarvisUI, DummyUI())
    j = JarvisLive(ui)

    # 1007 APIError
    err1007 = APIError(1007, "None. Request contains an invalid argument.", None)
    assert j._is_invalid_argument_or_handle_error(err1007) is True
    assert j._is_connection_closed_error(err1007) is True

    # Raw WebSocket 1007 frame error
    err_ws1007 = Exception(
        "ConnectionClosedError: received 1007 (invalid frame payload data) Request contains an invalid argument."
    )
    assert j._is_invalid_argument_or_handle_error(err_ws1007) is True
    assert j._is_connection_closed_error(err_ws1007) is True

    # ExceptionGroup wrapping 1007
    eg1007 = ExceptionGroup("TaskGroup error", [err1007])
    assert j._is_invalid_argument_or_handle_error(eg1007) is True

    # 1008 / 1011 deadline are NOT invalid argument errors
    err1008 = APIError(1008, "Requested entity was not found.", None)
    err1011 = APIError(1011, "Deadline expired before operation could complete.", None)
    assert j._is_invalid_argument_or_handle_error(err1008) is False
    assert j._is_invalid_argument_or_handle_error(err1011) is False
