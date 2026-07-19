# JARVIS Plugin SDK

The contract that all JARVIS extensions import from.

Mirrors OpenClaw's `src/plugin-sdk/` pattern. Plugins:

```python
from jarvis_sdk import (
    define_plugin_entry, ToolDecl, Result, Ok, Err,
)

def register(api):
    api.register_tool(
        MyTool(),
        names=["my_tool"],
    )

entry = define_plugin_entry(
    id="my_tool",
    kind="tool",
    name="My Tool",
    description="...",
    register=register,
)
```

## Rules (enforced by `tools/ci/check_imports.py`)

- ✅ `from jarvis_sdk import ...`
- ✅ `from . import sibling_module` (within same package)
- ❌ `from extensions.<other> import ...` (cross-extension)
- ❌ `from packages.<other> import ...` (except `jarvis_sdk`)
- ❌ `import main`, `import ui`, `import or_client` (legacy modules)

See `AGENTS.md` for the full SDK boundary rules.
