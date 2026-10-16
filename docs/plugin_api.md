# JARVIS Plugin API Reference

This guide explains how to author code plugins for JARVIS.

---

## 1. Plugin Entrypoint (`define_plugin_entry`)

```python
from jarvis_sdk.plugin_entry import define_plugin_entry

def register(api):
    # Register tools
    api.register_tool(
        factory=create_my_tool,
        names=["my_tool"],
    )
    
    # Register lifecycle hooks
    api.on("before_prompt_build", on_before_prompt)
    
    # Register slash commands
    api.register_command(
        name="status",
        description="Show system status",
        handler=handle_status,
    )

entry = define_plugin_entry(
    id="my-plugin",
    name="My Plugin",
    description="Plugin description",
    kind="tool",
    register=register,
)
```

---

## 2. Registering Tools

Tools receive a `PluginContext` providing turn details:

```python
def create_my_tool(ctx):
    return {
        "name": "weather",
        "description": "Fetch weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string"}
            },
            "required": ["city"]
        },
        "execute": lambda tool_call_id, args, signal=None, on_update=None: {
            "temperature": 22,
            "condition": "Sunny in " + args["city"]
        }
    }
```
