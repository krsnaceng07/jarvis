from __future__ import annotations

from src.plugins.registry import create_plugin_registry


def make_registry_with_entries():
    params = {}
    reg = create_plugin_registry(params)
    r = reg["registry"]
    # seed various registries with entries owned by plugin.foo and others
    r.setdefault("tools", []).extend([
        {"ownerPluginId": "plugin.foo", "names": ["foo-tool"]},
        {"ownerPluginId": "plugin.bar", "names": ["bar-tool"]},
    ])
    r.setdefault("hooks", []).extend([
        {"ownerPluginId": "plugin.foo", "hook": lambda: None},
        {"ownerPluginId": "plugin.bar", "hook": lambda: None},
    ])
    r.setdefault("typedHooks", []).extend([
        {"ownerPluginId": "plugin.foo", "hookName": "onX"},
    ])
    r.setdefault("httpRoutes", []).extend([
        {"_owner_id": "plugin.foo", "path": "/foo"},
        {"_owner_id": "plugin.bar", "path": "/bar"},
    ])
    r.setdefault("channels", []).extend([
        {"pluginId": "plugin.foo", "name": "foo-ch"},
        {"pluginId": "plugin.bar", "name": "bar-ch"},
    ])
    r.setdefault("providers", []).extend([
        {"id": "p1", "ownerPluginId": "plugin.foo"},
        {"id": "p2", "ownerPluginId": "plugin.bar"},
    ])
    r.setdefault("workerProviders", {})["w1"] = {"ownerPluginId": "plugin.foo", "provider": {}}

    return reg


def test_rollback_clears_plugin_entries():
    outer = make_registry_with_entries()
    reg = outer["registry"]
    # Sanity: plugin.foo entries exist
    assert any(isinstance(t, dict) and t.get("ownerPluginId") == "plugin.foo" for t in reg.get("tools", [])) is True

    # Call rollback using the same registry object
    rb = outer.get("rollbackPluginGlobalSideEffects")
    assert callable(rb)
    rb("plugin.foo")

    # Now assert plugin.foo entries removed
    assert all(not (isinstance(t, dict) and t.get("ownerPluginId") == "plugin.foo") for t in reg.get("tools", []))
    assert all(not (isinstance(h, dict) and h.get("ownerPluginId") == "plugin.foo") for h in reg.get("hooks", []))
    assert all(not (isinstance(th, dict) and th.get("ownerPluginId") == "plugin.foo") for th in reg.get("typedHooks", []))
    assert all(not (isinstance(r2, dict) and (r2.get("_owner_id") == "plugin.foo" or r2.get("ownerPluginId") == "plugin.foo")) for r2 in reg.get("httpRoutes", []))
    assert all(not (isinstance(c, dict) and (c.get("pluginId") == "plugin.foo" or c.get("ownerPluginId") == "plugin.foo")) for c in reg.get("channels", []))
    assert all(not (isinstance(p, dict) and p.get("ownerPluginId") == "plugin.foo") for p in reg.get("providers", []))
    assert all(not (isinstance(v, dict) and v.get("ownerPluginId") == "plugin.foo") for v in reg.get("workerProviders", {}).values())
