"""The desktop host must still expose the audio transport methods it inherited.

The audio half of ``JarvisLive`` was moved verbatim into ``live_transport``.
These tests fail if a future edit re-defines one of them on ``JarvisLive`` (two
sources of truth) or drops it from the inheritance chain.
"""

import inspect

MOVED_METHODS = (
    "_send_realtime",
    "_send_visual_stream",
    "_trigger_local_barge_in",
    "_keepalive_ping",
    "_listen_audio",
    "_receive_audio",
    "_play_audio",
)


def test_jarvis_live_resolves_transport_methods_to_live_transport() -> None:
    from jarvis_desktop.app import JarvisLive
    from jarvis_desktop.live_transport import LiveTransport

    for name in MOVED_METHODS:
        owner = inspect.getattr_static(JarvisLive, name)
        assert owner is LiveTransport.__dict__[name], name
        assert owner.__module__ == "jarvis_desktop.live_transport", name
