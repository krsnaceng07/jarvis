"""iMessage extension entry point for JARVIS."""

from .src.jarvis_imessage.plugin import IMessagePlugin, plugin

entry = plugin

__all__ = ["IMessagePlugin", "plugin", "entry"]
