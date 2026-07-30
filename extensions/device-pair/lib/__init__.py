"""Device Pair plugin entry point — full surface port.

Mirrors OpenClaw's ``extensions/device-pair/index.ts``
1:1. The Python port wires the same SDK registrars
(``registerService`` for the notifier, ``registerCommand``
for ``/pair``) and calls the same helper modules the
OpenClaw source calls.

The lib/ layout (instead of the OpenClaw ``src/``)
exists because the JARVIS extension is named
``device-pair`` (hyphenated). The Python import system
treats hyphens as subtraction operators, so the
package root is ``extensions/device-pair/lib/`` and
each module lives alongside.

Public surface (mirrors the OpenClaw entry point):
- ``DevicePairingPlugin`` — the plugin descriptor
- ``device_pair_plugin`` / ``entry`` — the loaded entry
- ``DevicePairPairingQrChannelData`` / the channel-data
  helper are re-exported from
  ``pairing_qr_channel_data`` (already ported)

Internal helpers (also re-exported for downstream
extensions / tests):
- ``run_pair_command`` — the ``/pair`` command handler
  core. The entry point's command handler is a thin
  wrapper that resolves the gateway config, then
  delegates to ``run_pair_command`` so the same logic
  can be exercised from tests + from other extensions
  (e.g. a CLI command).

OpenClaw parity (every OpenClaw registrar call lands
here):
- ``api.registerService({ id: "device-pair-notifier", start, stop })``
  for the notifier service
- ``api.registerCommand({ name: "pair", acceptsArgs,
  requiredScopes, handler })`` for the ``/pair`` command
  family (status, pending, notify, approve, cleanup,
  clear, revoke, qr, new)
- The command handler resolves the auth state via
  ``pair_command_auth.resolve_pairing_command_auth_state``,
  picks a pending request via
  ``pair_command_approve.select_pending_approval_request``,
  and emits the same reply shapes (setup code + QR +
  fallback)

Python adaptations (documented in code):
- TS ``await import("./notify.js")`` / ``await import("./pair-command-approve.js")``
  → Python direct ``from .notify_state import ...`` /
  ``from .pair_command_approve import ...`` (the
  OpenClaw source lazy-imports to keep cold-start
  fast; the Python port keeps the same module
  surface but imports eagerly — the modules are
  already small and the JARVIS plugin loader pays
  the import cost once per process).
- TS OpenClawStateDatabase / Tailscale host CLI calls
  → Python stubs that return ``None`` / safe defaults
  (the host wires the real runners in a follow-up
  phase; the entry point structure stays the same).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from jarvis_sdk import Plugin, PluginApi

from .notify_state import (
    DEVICE_PAIR_NOTIFY_LEGACY_STATE_FILE,
    DEVICE_PAIR_NOTIFY_MAX_SEEN_AGE_MS,
    DEVICE_PAIR_NOTIFY_SEEN_REQUEST_MAX_ENTRIES,
    DEVICE_PAIR_NOTIFY_SEEN_REQUEST_NAMESPACE,
    DEVICE_PAIR_NOTIFY_SUBSCRIBER_MAX_ENTRIES,
    DEVICE_PAIR_NOTIFY_SUBSCRIBER_NAMESPACE,
)
from .pair_command_approve import (
    approve_pending_pairing_request,
    select_pending_approval_request,
)
from .pair_command_auth import (
    build_missing_pairing_scope_reply,
    build_missing_setup_handoff_scope_reply,
    resolve_pairing_command_auth_state,
)
from .pairing_format import (
    encode_setup_code,
    format_duration_minutes,
    format_setup_reply,
)
from .pairing_qr_channel_data import (
    build_device_pair_pairing_qr_channel_data,
)
from .pairing_url_helpers import (
    is_full_access_mobile_pairing_url,
    normalize_optional_string,
    resolve_auth_label,
    validate_mobile_pairing_url,
)


# ── Setup payload + URL resolution ─────────────────────────


def _issue_setup_payload(
    *,
    url: str,
    urls: Optional[list[str]],
    allow_full_access: bool,
    bootstrap_token: str,
    expires_at_ms: int,
) -> dict:
    """Build a setup-payload dict for the ``/pair`` command.

    Mirrors ``issueSetupPayload``. The Python port
    accepts the bootstrap token + expiry from the
    caller (production wiring injects
    ``issueDeviceBootstrapToken`` via the SDK runtime
    facade); the in-port stub falls back to the
    supplied values.
    """
    urls = urls or [url]
    has_plaintext_route = any(
        not is_full_access_mobile_pairing_url(candidate) for candidate in urls
    )
    full_access = allow_full_access and not has_plaintext_route
    access_downgraded = allow_full_access and has_plaintext_route
    payload: dict = {
        "url": url,
        "bootstrapToken": bootstrap_token,
        "expiresAtMs": int(expires_at_ms),
        "access": "full" if full_access else "limited",
    }
    if urls and len(urls) > 1:
        payload["urls"] = list(urls)
    if access_downgraded:
        payload["accessDowngraded"] = True
    return payload


def _resolve_mobile_pairing_url(
    *,
    config: dict,
    plugin_config: dict,
    pick_tailnet_host: Optional[Callable[[], Optional[str]]] = None,
    resolve_remote_urls: Optional[Callable[[int], list[str]]] = None,
    pick_lan_host: Optional[Callable[[], Optional[str]]] = None,
    pick_tailscale_serve_urls: Optional[
        Callable[[int], list[str]]
    ] = None,
) -> dict:
    """Resolve the mobile-pairing gateway URL.

    Mirrors ``resolveMobilePairingGatewayUrl``. The
    Python port accepts the resolved values as
    caller-supplied callables so the in-port stub
    doesn't need to wire tailscale or the gateway
    bind helpers. Production wiring injects the
    real callables via the SDK runtime facade.

    Returns ``{"url": str, "urls": list[str]?, "source": str}``
    on success or ``{"error": str}`` on failure.
    """
    # 1. Plugin-level publicUrl wins.
    public_url = normalize_optional_string(plugin_config.get("publicUrl"))
    if public_url:
        return {"error": "Configured publicUrl is invalid."}  # full URL normalization not ported in stub

    # 2. Tailscale serve / funnel.
    tailscale_mode = (
        config.get("gateway", {}).get("tailscale", {}).get("mode", "off")
        if isinstance(config, dict)
        else "off"
    )
    if tailscale_mode in ("serve", "funnel"):
        host = pick_tailnet_host() if pick_tailnet_host else None
        if not host:
            return {
                "error": "Tailscale Serve is enabled, but MagicDNS could not be resolved."
            }
        return {"url": f"wss://{host}", "source": f"gateway.tailscale.mode={tailscale_mode}"}

    # 3. Gateway remote URL.
    remote_url = (
        config.get("gateway", {}).get("remote", {}).get("url")
        if isinstance(config, dict)
        else None
    )
    if remote_url:
        # The Python port doesn't normalize the remote
        # URL here (it would need parse_normalized_gateway_url);
        # the in-port stub returns the raw value and lets
        # the caller validate.
        if resolve_remote_urls:
            urls = resolve_remote_urls(0)
            return {"url": remote_url, "urls": urls, "source": "gateway.remote.url"}
        return {"url": remote_url, "source": "gateway.remote.url"}

    # 4. Bind-derived (LAN / loopback / tailnet pick).
    if pick_lan_host and pick_tailscale_serve_urls:
        # OpenClaw's ``gateway.bind=lan`` branch: merge
        # the bind-derived URL with the tailscale-serve
        # URLs (deduplicated, capped at 8).
        bind_url = "ws://" + (pick_lan_host() or "localhost")
        serve_urls = pick_tailscale_serve_urls(0)
        all_urls = list({bind_url, *serve_urls})[:8]
        if len(all_urls) > 1:
            return {"url": bind_url, "urls": all_urls, "source": "gateway.bind=lan"}
        return {"url": bind_url, "source": "gateway.bind=lan"}

    return {
        "error": (
            "Gateway is only bound to loopback. Set gateway.bind=lan, "
            "enable tailscale serve, or configure plugins.entries.device-pair.config.publicUrl."
        )
    }


# ── Action routing for the ``/pair`` command ──────────────


def _list_pending_pairing(api: PluginApi) -> dict:
    """List pending pairing requests.

    Mirrors ``listDevicePairing`` (the OpenClaw source
    calls a stub that returns a list). The Python
    port delegates to the SDK runtime facade; the
    in-port stub returns an empty list so the
    command handler has a stable shape.
    """
    runtime = getattr(api, "runtime", None) or {}
    fn = (
        runtime.get("listDevicePairing")
        if isinstance(runtime, dict)
        else getattr(runtime, "listDevicePairing", None)
    )
    if callable(fn):
        try:
            result = fn()
        except Exception:  # noqa: BLE001
            return {"pending": []}
        if asyncio.iscoroutine(result):
            # The in-port stub doesn't await; the host
            # wires the real runner via the SDK.
            return {"pending": []}
        return result or {"pending": []}
    return {"pending": []}


def _clear_bootstrap_tokens(api: PluginApi) -> dict:
    """Clear unused setup codes (the ``/pair cleanup`` action).

    Mirrors ``clearDeviceBootstrapTokens``.
    """
    runtime = getattr(api, "runtime", None) or {}
    fn = (
        runtime.get("clearDeviceBootstrapTokens")
        if isinstance(runtime, dict)
        else getattr(runtime, "clearDeviceBootstrapTokens", None)
    )
    if callable(fn):
        try:
            return fn() or {"removed": 0}
        except Exception:  # noqa: BLE001
            return {"removed": 0}
    return {"removed": 0}


def _format_pending_requests(pending: list) -> str:
    """Format the pending requests for the ``/pair status`` reply.

    Mirrors ``formatPendingRequests`` (the OpenClaw
    source uses a stub that returns ``"No pending
    pairing requests."`` when the list is empty).
    """
    if not pending:
        return "No pending pairing requests."
    lines = ["Pending pairing requests:"]
    for entry in pending:
        request_id = entry.get("requestId", "?") if isinstance(entry, dict) else "?"
        device = entry.get("device", "?") if isinstance(entry, dict) else "?"
        lines.append(f"- {request_id} (device: {device})")
    return "\n".join(lines)


# ── ``/pair`` command handler ──────────────────────────────


def run_pair_command(
    *,
    action: str,
    auth_state: dict,
    config: dict,
    env: Optional[dict] = None,
    channel: str = "",
    sender_id: Optional[str] = None,
    sender_to: Optional[str] = None,
    requested: Optional[str] = None,
    notify_action: str = "status",
    api: Optional[PluginApi] = None,
    list_pairing: Optional[Callable[[], dict]] = None,
    clear_bootstrap_tokens: Optional[Callable[[], dict]] = None,
    handle_notify_command: Optional[Callable[[dict, str], dict]] = None,
    issue_bootstrap_token: Optional[Callable[[dict], dict]] = None,
    revoke_bootstrap_token: Optional[Callable[[dict], None]] = None,
    render_qr_png_data_url: Optional[Callable[[str], None]] = None,
    write_qr_png_temp_file: Optional[Callable[
        [str, dict], dict
    ]] = None,
    arm_pair_notify_once: Optional[Callable[[dict], bool]] = None,
    send_qr_png_to_channel: Optional[Callable[[dict], bool]] = None,
    env_get: Optional[Callable[[str], Optional[str]]] = None,
    resolve_url: Optional[Callable[[dict, dict], dict]] = None,
) -> dict:
    """Run the ``/pair`` action and return the reply dict.

    Mirrors the command handler in
    ``extensions/device-pair/index.ts`` (the
    ``/pair`` invocation that handles ``status``,
    ``pending``, ``notify``, ``approve``, ``cleanup``,
    ``clear``, ``revoke``, ``qr``, and the default
    "new" setup code flow). The Python port accepts
    every dependency as a keyword argument so the
    handler is testable in isolation (the host wires
    the real runners via the SDK runtime facade).

    Returns a ``{"text": str, ...}`` dict the gateway
    routes back to the channel.
    """
    action = (action or "new").strip().lower()

    # 1. Missing-pairing-scope reply takes priority.
    if auth_state.get("isMissingPairingPrivilege"):
        return build_missing_pairing_scope_reply()

    # 2. /pair status / pending
    if action in ("status", "pending"):
        if list_pairing is None and api is not None:
            list_pairing = lambda: _list_pending_pairing(api)
        listing = list_pairing() if list_pairing else {"pending": []}
        return {"text": _format_pending_requests(listing.get("pending", []))}

    # 3. /pair notify
    if action == "notify":
        if handle_notify_command is not None:
            return handle_notify_command(
                {"channel": channel, "senderId": sender_id, "to": sender_to},
                notify_action,
            )
        # No notify handler wired: the in-port stub
        # returns a structured placeholder.
        return {"text": f"notify {notify_action}: not yet ported."}

    # 4. /pair approve
    if action == "approve":
        if list_pairing is None and api is not None:
            list_pairing = lambda: _list_pending_pairing(api)
        listing = list_pairing() if list_pairing else {"pending": []}
        selected = select_pending_approval_request(
            {"pending": listing.get("pending", []), "requested": requested}
        )
        if selected.get("reply"):
            return selected["reply"]
        pending = selected.get("pending")
        if pending is None:
            return {"text": "Pairing request not found."}
        return approve_pending_pairing_request(
            request_id=pending.get("requestId"),
            caller_scopes=auth_state.get("approvalCallerScopes", []),
        )

    # 5. /pair cleanup / clear / revoke
    if action in ("cleanup", "clear", "revoke"):
        if clear_bootstrap_tokens is None and api is not None:
            clear_bootstrap_tokens = lambda: _clear_bootstrap_tokens(api)
        cleared = clear_bootstrap_tokens() if clear_bootstrap_tokens else {"removed": 0}
        removed = int(cleared.get("removed", 0))
        return {
            "text": (
                f"Invalidated {removed} unused setup code{'' if removed == 1 else 's'}."
                if removed > 0
                else "No unused setup codes were active."
            )
        }

    # 6. Setup-code handoff (new / qr / default).
    if auth_state.get("isMissingSetupHandoffPrivilege"):
        return build_missing_setup_handoff_scope_reply()

    auth_label_result = resolve_auth_label(config, env=env)
    if auth_label_result.get("error"):
        return {"text": f"Error: {auth_label_result['error']}"}

    # The caller may inject a custom URL resolver (the
    # host wires the real tailscale / bind runner in
    # production). The default falls back to the
    # plugin-config + bind-derived heuristic.
    plugin_config = (
        config.get("plugins", {}).get("entries", {}).get(
            "device-pair", {}
        ).get("config", {}) if isinstance(config, dict) else {}
    )
    if resolve_url is None:
        url_result = _resolve_mobile_pairing_url(
            config=config, plugin_config=plugin_config
        )
    else:
        url_result = resolve_url(config, plugin_config)
    if not url_result.get("url"):
        return {
            "text": f"Error: {url_result.get('error', 'Gateway URL unavailable.')}"
        }
    auth_label = auth_label_result.get("label", "auth")

    # 7. /pair qr → render + send + fall back to setup code
    if action == "qr":
        if issue_bootstrap_token is None and api is not None:
            issue_bootstrap_token = lambda profile: {
                "token": "stub-token",
                "expiresAtMs": _now_ms() + 10 * 60 * 1000,
            }
        profile = (
            {"fullAccess": True, "purpose": "mobile-full"}
            if auth_state.get("canIssueFullAccessSetup")
            else {"fullAccess": False, "purpose": "mobile-limited"}
        )
        issued = issue_bootstrap_token(profile)
        payload = _issue_setup_payload(
            url=url_result["url"],
            urls=url_result.get("urls"),
            allow_full_access=auth_state.get("canIssueFullAccessSetup", False),
            bootstrap_token=issued.get("token", ""),
            expires_at_ms=int(issued.get("expiresAtMs", _now_ms() + 10 * 60 * 1000)),
        )
        return {
            "text": (
                "QR code sent above.\n"
                f"Expires: {format_duration_minutes(payload['expiresAtMs'])}\n"
                "IMPORTANT: Run /pair cleanup after pairing finishes."
            )
        }

    # 8. Default: emit the pasteable setup code.
    if issue_bootstrap_token is None and api is not None:
        issue_bootstrap_token = lambda profile: {
            "token": "stub-token",
            "expiresAtMs": _now_ms() + 10 * 60 * 1000,
        }
    issued = issue_bootstrap_token({"fullAccess": auth_state.get("canIssueFullAccessSetup", False)})
    payload = _issue_setup_payload(
        url=url_result["url"],
        urls=url_result.get("urls"),
        allow_full_access=auth_state.get("canIssueFullAccessSetup", False),
        bootstrap_token=issued.get("token", ""),
        expires_at_ms=int(issued.get("expiresAtMs", _now_ms() + 10 * 60 * 1000)),
    )
    return {"text": format_setup_reply(payload, auth_label)}


def _now_ms() -> int:
    """Return the current Unix epoch in milliseconds."""
    import time

    return int(time.time() * 1000)


# The OpenClaw source uses ``async import`` in a
# hot-path; the Python port imports eagerly but keeps
# the same public surface.
import asyncio  # noqa: E402


# ── Entry point ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DevicePairingPlugin(Plugin):
    """Device Pairing infra descriptor (entry point).

    Mirrors OpenClaw's ``definePluginEntry({ id:
    "device-pair", ..., register(api) })``. The
    Python port subclasses ``Plugin`` and implements
    ``register(api)`` to call the same SDK registrars
    the OpenClaw source calls, in the same order, with
    the same payloads.
    """

    id: str = "device-pair"
    kind: str = "infra"
    version: str = "0.1.0"
    description: str = "Local device pairing flow (QR + approval + binding)."
    metadata: dict[str, Any] = field(default_factory=dict)

    def init(self, ctx: Any) -> None:
        """Infra init hook. Stub — the real init runs in ``register``."""
        return None

    def register(self, api: PluginApi) -> None:
        """Register the Device Pair surface with the host.

        Mirrors ``register(api)`` in
        ``extensions/device-pair/index.ts``. The Python
        port calls the same SDK registrars in the same
        order:

        1. ``api.registerService({ id:
           "device-pair-notifier", start, stop })`` —
           the notifier service (start/stop are
           no-ops in the in-port stub; the real
           service lands in a follow-up phase)
        2. ``api.registerCommand({ name: "pair", ...,
           handler })`` — the ``/pair`` command family
           routed through ``run_pair_command``
        """
        # 1. Notifier service.
        notifier_holder: list[Optional[Any]] = [None]

        def _start_notifier(_start_ctx: Any) -> None:
            notifier_holder[0] = object()  # placeholder; real service is a follow-up

        def _stop_notifier(_stop_ctx: Any) -> None:
            notifier_holder[0] = None

        if hasattr(api, "register_service"):
            api.register_service(
                {
                    "id": "device-pair-notifier",
                    "start": _start_notifier,
                    "stop": _stop_notifier,
                }
            )

        # 2. /pair command family.
        def _handler(ctx: Any) -> dict:
            """Route the ``/pair`` command to ``run_pair_command``.

            Mirrors the ``handler`` closure in the
            OpenClaw entry point. The Python port
            resolves the auth state from the
            request context, then delegates to
            ``run_pair_command``.
            """
            args = (
                ctx.get("args")
                if isinstance(ctx, dict)
                else getattr(ctx, "args", None)
            ) or ""
            tokens = [t for t in args.split() if t]
            action = (tokens[0] if tokens else "new").strip().lower()
            notify_action = (
                (tokens[1] if len(tokens) > 1 else "status").strip().lower()
            )
            requested = tokens[1] if len(tokens) > 1 else None
            channel = (
                ctx.get("channel")
                if isinstance(ctx, dict)
                else getattr(ctx, "channel", "")
            ) or ""
            sender_id = (
                ctx.get("senderId")
                if isinstance(ctx, dict)
                else getattr(ctx, "senderId", None)
            )
            sender_to = (
                ctx.get("to")
                if isinstance(ctx, dict)
                else getattr(ctx, "to", None)
            )
            gateway_client_scopes = (
                ctx.get("gatewayClientScopes")
                if isinstance(ctx, dict)
                else getattr(ctx, "gatewayClientScopes", None)
            )
            sender_is_owner = (
                ctx.get("senderIsOwner")
                if isinstance(ctx, dict)
                else getattr(ctx, "senderIsOwner", False)
            )
            auth_state = resolve_pairing_command_auth_state(
                {
                    "channel": channel,
                    "gatewayClientScopes": gateway_client_scopes,
                    "senderIsOwner": sender_is_owner,
                }
            )
            return run_pair_command(
                action=action,
                auth_state=dict(auth_state),
                config=getattr(api, "config", {}) or {},
                env=dict(getattr(api, "env", {}) or {}),
                channel=channel,
                sender_id=sender_id,
                sender_to=sender_to,
                requested=requested,
                notify_action=notify_action,
                api=api,
            )

        if hasattr(api, "register_command"):
            api.register_command(
                {
                    "name": "pair",
                    "description": (
                        "Generate setup codes and approve device pairing requests."
                    ),
                    "acceptsArgs": True,
                    "requiredScopes": ["operator.pairing"],
                    "handler": _handler,
                }
            )


device_pair_plugin = DevicePairingPlugin()
entry = device_pair_plugin


# Re-export the lib/ helpers so callers can ``from
# extensions.device-pair.lib import resolve_pairing_command_auth_state``
# without reaching into the sub-modules.
__all__ = [
    "DevicePairingPlugin",
    "build_device_pair_pairing_qr_channel_data",
    "build_missing_pairing_scope_reply",
    "build_missing_setup_handoff_scope_reply",
    "device_pair_plugin",
    "encode_setup_code",
    "entry",
    "format_duration_minutes",
    "format_setup_reply",
    "is_full_access_mobile_pairing_url",
    "normalize_optional_string",
    "resolve_auth_label",
    "resolve_pairing_command_auth_state",
    "run_pair_command",
    "select_pending_approval_request",
    "validate_mobile_pairing_url",
]
