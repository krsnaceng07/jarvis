import json
import os
import tempfile
from pathlib import Path

class PersistentProfileMap(dict):
    def __init__(self, values=None, *, parent=None):
        super().__init__()
        self._parent = parent
        if isinstance(values, dict):
            super().update(values)

    def _save(self):
        if self._parent is not None:
            self._parent._save()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._save()

class PersistentAuthProfileStore(dict):
    def __init__(self, value=None, *, agent_dir=None):
        super().__init__()
        self._agent_dir = agent_dir if isinstance(agent_dir, str) else None
        initial = {"version": 1, "profiles": {}}
        profiles = PersistentProfileMap(initial.get("profiles", {}), parent=self)
        super().update({"version": initial.get("version", 1), "profiles": profiles})
        self._save()

    def _save(self):
        path = os.path.join(self._agent_dir, "auth-profiles.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(self), handle, indent=2, sort_keys=True)

with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "agent"
    p.mkdir()
    s = PersistentAuthProfileStore(agent_dir=str(p))
    print("before", (p / "auth-profiles.json").read_text())
    s["profiles"]["p1"] = {"provider": "openai", "label": "primary", "active": True}
    print("after", (p / "auth-profiles.json").read_text())
