"""tool_weather — current weather and forecasts via Google search.

**Phase 1A proof consumer.** Demonstrates the plugin pattern (manifest +
class) that Phase 1C will formalize into `packages/plugin_sdk/`.

The plugin:
- Declares its tools in `jarvis.plugin.json` (the manifest).
- Implements a `WeatherPlugin` class with `tools` and `call(name, args)`.
- The host (`apps/desktop/src/jarvis_desktop/app.py`) loads the manifest
  and instantiates the class, then dispatches tool calls.
"""

__version__ = "0.1.0"
