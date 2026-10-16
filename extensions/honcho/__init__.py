from .plugin import HonchoPlugin, honcho_plugin, entry
from .cli import register_honcho_cli

plugin = honcho_plugin

__all__ = ["HonchoPlugin", "honcho_plugin", "plugin", "entry", "register_honcho_cli"]
