"""Web plugin definition and export."""

from .src.plugin import WebPlugin, entry

plugin = entry

__all__ = ["WebPlugin", "entry", "plugin"]
