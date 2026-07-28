"""Bonjour mDNS advertiser for the JARVIS gateway.

Mirrors OpenClaw's ``extensions/bonjour/src/advertiser.ts``
which uses ``@homebridge/ciao``. The Python port uses the
``zeroconf`` package (the canonical Python mDNS implementation).

The advertiser publishes gateway/canvas/SSH records via a
single ``Zeroconf`` instance lifecycle. The function returns
an object with a ``stop()`` method that tears down the
advertisements and shuts the responder down.

Key differences from the TS port:
- ``ciao.getResponder()`` → ``Zeroconf()`` constructor
- ``responder.createService({...})`` → ``ServiceInfo(...)`` class
- ``svc.advertise()`` → ``zeroconf.register_service(info)``
- ``svc.destroy()`` → ``zeroconf.unregister_service(info)``
- ``responder.shutdown()`` → ``zeroconf.close()``
- ciao's ``serviceState`` → ``zeroconf`` has no equivalent;
  the service summary just logs the registration state
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from zeroconf import ServiceInfo, Zeroconf

from .ciao import classify_ciao_process_error
from .env_helpers import (
    is_disabled_by_env,
    prettify_instance_name,
    resolve_system_mdns_hostname,
    safe_service_name,
    truncate_to_dns_label,
)
from .errors import format_bonjour_error

LOGGER = logging.getLogger(__name__)

# Default Bonjour service type for the OpenClaw gateway.
# The OpenClaw TS source uses the bare ``"openclaw-gw"`` type
# (ciao prepends ``_`` and appends ``._tcp.local.`` automatically).
# Python's ``zeroconf`` requires the fully-qualified form, so we
# use ``"_openclaw-gw._tcp.local."`` here. The TXT keys + the
# gateway-port contract are unchanged.
DEFAULT_SERVICE_TYPE = "_openclaw-gw._tcp.local."
DEFAULT_DOMAIN = "local."

# Maximum TXT record byte size per record (DNS limit).
# The TS source doesn't enforce this — ciao handles it.
MAX_TXT_BYTES = 65535


@dataclass(frozen=True, slots=True)
class GatewayBonjourAdvertiseOpts:
    """Input data used to publish JARVIS gateway Bonjour records.

    Mirrors the TS ``GatewayBonjourAdvertiseOpts`` in
    ``extensions/bonjour/src/advertiser.ts``.
    """

    instance_name: Optional[str] = None
    gateway_port: int = 0
    ssh_port: Optional[int] = None
    gateway_tls_enabled: bool = False
    gateway_tls_fingerprint_sha256: Optional[str] = None
    gateway_direct_reachable: bool = False
    canvas_port: Optional[int] = None
    tailnet_dns: Optional[str] = None
    cli_path: Optional[str] = None
    minimal: bool = False
    service_type: str = DEFAULT_SERVICE_TYPE
    domain: str = DEFAULT_DOMAIN


@dataclass(slots=True)
class GatewayBonjourAdvertiser:
    """Active advertiser handle.

    Mirrors the TS ``GatewayBonjourAdvertiser`` type:
    exposes a ``stop()`` async function that tears down
    the registered service(s) and shuts the responder.

    Not frozen: the ``_stopped`` flag mutates on the first
    ``stop()`` call to keep teardown idempotent.
    """

    _responder: Zeroconf
    _services: list[ServiceInfo]
    _stop_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _stopped: bool = False

    async def stop(self) -> None:
        """Stop the advertiser (idempotent)."""
        async with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
            for info in self._services:
                try:
                    self._responder.unregister_service(info)
                except Exception:  # noqa: BLE001 — best-effort teardown
                    pass
            try:
                self._responder.close()
            except Exception:  # noqa: BLE001 — best-effort teardown
                pass


@dataclass
class BonjourAdvertiserDeps:
    """Dependencies for ``start_gateway_bonjour_advertiser``.

    Mirrors the TS ``BonjourAdvertiserDeps`` interface in
    ``extensions/bonjour/src/advertiser.ts``.
    """

    logger: Optional[logging.Logger] = None
    on_uncaught_exception: Optional[Callable[[BaseException], bool]] = None
    on_unhandled_rejection: Optional[Callable[[Any], bool]] = None


def _build_txt_base(opts: GatewayBonjourAdvertiseOpts, hostname: str, display_name: str) -> dict[str, str]:
    """Build the base TXT record dict for the gateway service.

    Mirrors the TS source's ``txtBase`` construction.
    """
    txt: dict[str, str] = {
        "role": "gateway",
        "gatewayPort": str(opts.gateway_port),
        "lanHost": f"{hostname}.local",
        "displayName": display_name,
    }
    if opts.gateway_tls_enabled:
        txt["gatewayTls"] = "1"
        if opts.gateway_tls_fingerprint_sha256:
            txt["gatewayTlsSha256"] = opts.gateway_tls_fingerprint_sha256
    if opts.gateway_direct_reachable:
        txt["gatewayDirectReachable"] = "1"
    if isinstance(opts.canvas_port, int) and opts.canvas_port > 0:
        txt["canvasPort"] = str(opts.canvas_port)
    if not opts.minimal and opts.tailnet_dns and opts.tailnet_dns.strip():
        txt["tailnetDns"] = opts.tailnet_dns.strip()
    if not opts.minimal and opts.cli_path and opts.cli_path.strip():
        txt["cliPath"] = opts.cli_path.strip()
    return txt


def _resolve_hostname(opts: GatewayBonjourAdvertiseOpts) -> str:
    """Resolve the mDNS hostname for the advertisement.

    Honors ``OPENCLAW_MDNS_HOSTNAME`` env override, then
    falls back to the OS hostname, then to ``"openclaw"``.
    """
    override = os.environ.get("OPENCLAW_MDNS_HOSTNAME", "").strip()
    raw = override or resolve_system_mdns_hostname() or "openclaw"
    without_local = raw.removesuffix(".local").removesuffix(".LOCAL")
    # Use only the first DNS label
    dot_index = without_local.find(".")
    label_end = len(without_local) if dot_index == -1 else dot_index
    label = without_local[:label_end].strip() or "openclaw"
    return truncate_to_dns_label(label, fallback="openclaw")


def start_gateway_bonjour_advertiser(
    opts: GatewayBonjourAdvertiseOpts,
    deps: Optional[BonjourAdvertiserDeps] = None,
) -> GatewayBonjourAdvertiser:
    """Start Bonjour advertisements for the local gateway services.

    Returns an object with a ``stop()`` async function that
    tears down the registrations. When Bonjour is disabled
    by env (``NODE_ENV=test``, container default, or
    ``OPENCLAW_DISABLE_BONJOUR=1``), returns a no-op
    advertiser whose ``stop()`` is a no-op.

    Mirrors ``startGatewayBonjourAdvertiser`` in OpenClaw's
    ``extensions/bonjour/src/advertiser.ts``.
    """
    if is_disabled_by_env():
        # Disabled path — return a no-op advertiser.
        # Build an unopened Zeroconf stub; .close() on a
        # never-opened instance is safe.
        return GatewayBonjourAdvertiser(
            _responder=Zeroconf(),
            _services=[],
        )

    deps = deps or BonjourAdvertiserDeps()
    log = deps.logger or LOGGER

    hostname = _resolve_hostname(opts)
    instance_name_raw = (
        opts.instance_name.strip()
        if isinstance(opts.instance_name, str) and opts.instance_name.strip()
        else f"{hostname} (OpenClaw)"
    )
    display_name = prettify_instance_name(instance_name_raw)

    txt_base = _build_txt_base(opts, hostname, display_name)
    gateway_txt: dict[str, str] = {**txt_base, "transport": "gateway"}
    if not opts.minimal:
        ssh_port_str = str(opts.ssh_port if opts.ssh_port is not None else 22)
        gateway_txt["sshPort"] = ssh_port_str

    # Encode TXT values as bytes (zeroconf's ServiceInfo expects
    # dict[str, bytes | None | str]).
    txt_bytes: dict[str, bytes] = {k: v.encode("utf-8") for k, v in gateway_txt.items()}

    log.debug(
        "bonjour: starting (hostname=%s, instance=%s, gatewayPort=%d%s)",
        hostname,
        repr(safe_service_name(instance_name_raw)),
        opts.gateway_port,
        ", minimal=true" if opts.minimal else f", sshPort={opts.ssh_port if opts.ssh_port is not None else 22}",
    )

    # Build the service registration. The ServiceInfo constructor
    # requires a server name; we use the local hostname.
    safe_instance = safe_service_name(instance_name_raw)
    # The fully-qualified service type already ends in ``.local.``,
    # so we don't append the domain again — just ``<name>.<type>``.
    service_name = f"{safe_instance}.{opts.service_type}"

    info = ServiceInfo(
        type_=opts.service_type,
        name=service_name,
        port=opts.gateway_port,
        server=f"{hostname}.local",
        properties=txt_bytes,
    )

    responder = Zeroconf()
    try:
        responder.register_service(info)
        log.info(
            "bonjour: advertised gateway fqdn=%s host=%s port=%d",
            service_name,
            f"{hostname}.local",
            opts.gateway_port,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort registration
        classification = classify_ciao_process_error(exc)
        if classification is not None:
            log.warning(
                "bonjour: advertise failed with ciao %s: %s",
                classification.kind,
                classification.formatted,
            )
        else:
            log.warning("bonjour: advertise failed: %s", format_bonjour_error(exc))
        # Still return a handle so the caller can attempt to stop.
        # The unregister call in stop() is a no-op on an un-registered service.
    finally:
        pass  # ciao's startAdvertising is fire-and-forget; we mirror that.

    return GatewayBonjourAdvertiser(
        _responder=responder,
        _services=[info],
    )


def format_bonjour_instance_name(display_name: str) -> str:
    """Format a human-readable Bonjour instance name.

    Mirrors the TS ``formatBonjourInstanceName`` in
    ``extensions/bonjour/index.ts``:
    - empty → ``"openclaw"``
    - contains ``openclaw`` (case-insensitive) → unchanged
    - otherwise → ``"{name} (openclaw)"``
    """
    trimmed = (display_name or "").strip()
    if not trimmed:
        return "openclaw"
    if "openclaw" in trimmed.lower():
        return trimmed
    return f"{trimmed} (openclaw)"
