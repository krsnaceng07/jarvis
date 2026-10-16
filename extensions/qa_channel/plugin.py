"""Compatibility shim for ``extensions.qa_channel.plugin``."""

from __future__ import annotations

from importlib import import_module

_module = import_module("extensions.qa-channel.plugin")

QAChannelPlugin = _module.QAChannelPlugin
qa_channel_plugin = _module.qa_channel_plugin
entry = _module.entry

__all__ = ["QAChannelPlugin", "qa_channel_plugin", "entry"]
