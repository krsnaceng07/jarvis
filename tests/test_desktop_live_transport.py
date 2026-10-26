"""Pins the seams created by the Phase 2 mechanical splits.

The audio half of ``JarvisLive`` moved verbatim into ``live_transport``, and the
plugin hook bus moved with it. These tests fail if a future edit re-defines a
moved method on ``JarvisLive`` (two sources of truth), drops it from the
inheritance chain, or hands the host a second hook-bus instance (which would
silently drop every plugin hook).
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


def test_plugin_hook_bus_is_the_same_object_in_app_and_transport() -> None:
    import jarvis_desktop.app as app
    import jarvis_desktop.live_transport as live_transport

    assert app._PLUGIN_HOOK_BUS is live_transport._PLUGIN_HOOK_BUS


def test_tool_pipeline_reexports_desktop_action_executors() -> None:
    import jarvis_desktop.desktop_actions as desktop_actions
    import jarvis_desktop.tool_pipeline as tool_pipeline

    for name in ("execute_desktop_action", "execute_auto_control"):
        assert getattr(tool_pipeline, name) is getattr(desktop_actions, name), name

