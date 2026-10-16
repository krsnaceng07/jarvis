"""Compatibility shim for ``extensions.qa_channel.runtime``."""

from __future__ import annotations

from importlib import import_module

_module = import_module("extensions.qa-channel.runtime")

QAChannelMessage = _module.QAChannelMessage
QAChannelRuntime = _module.QAChannelRuntime
clear_qa_channel_messages = _module.clear_qa_channel_messages
enqueue_qa_channel_message = _module.enqueue_qa_channel_message
get_qa_channel_runtime = _module.get_qa_channel_runtime
read_qa_channel_messages = _module.read_qa_channel_messages
reset_qa_channel_runtime = _module.reset_qa_channel_runtime
set_qa_channel_runtime = _module.set_qa_channel_runtime

__all__ = [
    "QAChannelMessage",
    "QAChannelRuntime",
    "clear_qa_channel_messages",
    "enqueue_qa_channel_message",
    "get_qa_channel_runtime",
    "read_qa_channel_messages",
    "reset_qa_channel_runtime",
    "set_qa_channel_runtime",
]
