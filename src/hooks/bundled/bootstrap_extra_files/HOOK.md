---
name: bootstrap-extra-files
description: "Injects additional bootstrap files from glob patterns"
events: ["agent:bootstrap"]
---

# Bootstrap Extra Files Hook

This hook intercepts the `agent:bootstrap` event and allows extending the default bootstrap files injected into the LLM context.
