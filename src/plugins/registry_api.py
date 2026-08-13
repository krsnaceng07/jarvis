"""Scaffold for porting OpenClaw's `registry-api.ts` factory.

This module will house the richer `create_api_factory(state, registrars)`
implementation that wires lifecycle scoping, owner injection, and full
registrar implementations. Phase work plan:

1. Provide `create_api_factory(state, registrars)` that returns the
   host `createApi(record, opts)` callable.
2. Implement scoped runtime + lifecycle placeholders.
3. Port registrar domain logic in small batches (tools, hooks, providers).
4. Expose useful hooks for tests and the loader to validate behaviour.

This file implements `create_api_factory(state, registrars)` for the
host-side `createApi(record, opts)` lifecycle. The returned factory
builds a live `PluginApi` instance while preserving the legacy
CamelCase registrar view for host consumers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def _noop_registrar(*_args: Any, **_kwargs: Any) -> None:
    return None


def _normalize_path(value: Any, fallback: Path) -> Path:
    if isinstance(value, (str, Path)):
        return Path(value)
    return fallback


def create_api_factory(
    state: dict[str, Any],
    registrars: dict[str, Callable[..., Any]],
) -> Callable[[dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]:
    """Return a `createApi(record, opts)` callable.

    The returned factory builds a lightweight plugin API object for the
    host and exposes the legacy OpenClaw registrar names through a plain
    dict view. Each registrar wrapper updates the host registry state and
    also forwards to the SDK-style `PluginApi` method when available.
    """

    def _camel_to_snake(name: str) -> str:
        s = name[0].lower() if name else ""
        for ch in name[1:]:
            if ch.isupper():
                s += "_" + ch.lower()
            else:
                s += ch
        return s

    def _create_api(record: dict[str, Any] | None = None, opts: dict[str, Any] | None = None) -> dict[str, Any]:
        from .registry import PluginApi, PluginContext

        record = record or {}
        opts = opts or {}

        plugin_id = record.get("id", "") or ""
        plugin_kind = record.get("kind", "plugin") or "plugin"
        ctx = PluginContext(
            plugin_id=plugin_id,
            plugin_kind=plugin_kind,
            config=opts.get("config"),
            logger=opts.get("logger"),
            data_dir=_normalize_path(opts.get("dataDir"), Path.cwd()),
            workspace=_normalize_path(opts.get("workspaceDir"), Path.cwd()),
        )
        ctx.secrets = opts.get("secrets")
        api_obj = PluginApi(ctx, registrars, record)

        manifest: Any = record.get("manifest") or record.get("package") or {}
        try:
            api_obj.set_manifest(manifest)
        except Exception:
            pass

        try:
            api_obj.set_config(opts.get("config"))
        except Exception:
            pass

        out: dict[str, Any] = {
            # Legacy host stub returns an empty id/name in the plain dict view.
            # Advanced consumers must use ``pluginApi`` for the live plugin identity.
            "id": "",
            "name": "",
            "config": api_obj._plugin_config or {},
            "logger": api_obj.logger,
            "runtime": api_obj.runtime,
            "pluginApi": api_obj,
        }

        def _make_host_only_wrapper(
            registrar_fn: Callable[..., Any],
            rec: dict[str, Any],
        ) -> Callable[..., Any]:
            def _wrapper(*a: Any, **k: Any) -> Any:
                try:
                    return registrar_fn(rec, *a, **k)
                except TypeError:
                    return registrar_fn(rec)

            return _wrapper

        for name, fn in registrars.items():
            sdk_name = _camel_to_snake(name)
            api_method = getattr(api_obj, sdk_name, None)
            if callable(api_method):
                out[name] = api_method
            else:
                out[name] = _make_host_only_wrapper(fn, record)

        out.setdefault("registerCli", out.get("registerCli", _noop_registrar))
        out.setdefault("registerChannel", out.get("registerChannel", _noop_registrar))

        return out

    return _create_api
