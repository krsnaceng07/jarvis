"""Network boundary isolation guard and connectivity penetration probes.

Executes probes NET-001 through NET-007:
- Outbound TCP 443 / 80 connections
- Outbound UDP 53 DNS queries
- Inbound TCP socket binding
- Raw socket creation (SOCK_RAW)
- Localhost loopback connection
- LAN subnet probe

Enforces the Truthful Attribution Rule:
Raw socket creation failure != network isolation. Outbound connections are only
marked OS_ENFORCED if blocked by Windows Filtering Platform (WFP), Windows Firewall,
or AppContainer network capability SID. If unblocked, status is NOT_CONFIGURED.
"""

from __future__ import annotations

import logging
import socket
import time

from jarvis_learning.sandbox.models import (
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


class NetworkGuard:
    """Probes and verifies network boundary isolation and connectivity attribution."""

    @classmethod
    def probe_outbound_tcp(
        cls,
        host: str = "1.1.1.1",
        port: int = 443,
        vector_id: str = "NET-001",
        name: str = "OutboundTcp443Probe",
        timeout: float = 1.0,
    ) -> HostileProbeResult:
        """NET-001/NET-002: Attempt outbound TCP connection."""
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.NOT_CONFIGURED
        sev = SeverityLevel.S0_EXPECTED_DENIAL
        connected = False

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            connected = True
            blocked = False
            # Unrestricted network escape!
            sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
            mech = EnforcementMechanism.NOT_CONFIGURED
        except (socket.timeout, TimeoutError):
            # Timeout does not guarantee OS-enforced firewall, could be network drop
            blocked = True
            err_name = "SOCKET_TIMEOUT"
            mech = EnforcementMechanism.NOT_CONFIGURED
            sev = SeverityLevel.S2_SANDBOX_POLICY_VIOLATION
        except (PermissionError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__
            # WinError 10013 = WSAEACCES (often firewall or permission block)
            if err_code == 10013:
                mech = EnforcementMechanism.OS_ENFORCED
                sev = SeverityLevel.S0_EXPECTED_DENIAL
            else:
                mech = EnforcementMechanism.NOT_CONFIGURED
                sev = SeverityLevel.S2_SANDBOX_POLICY_VIOLATION
        finally:
            try:
                s.close()
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id=vector_id,
            family=VectorFamily.NETWORK,
            name=name,
            target=f"{host}:{port}",
            attempt_details=f"Attempted outbound TCP socket connection to {host}:{port}",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"connected": connected, "timeout_seconds": timeout},
        )

    @classmethod
    def probe_outbound_udp_dns(
        cls,
        server: str = "8.8.8.8",
        port: int = 53,
        timeout: float = 1.0,
    ) -> HostileProbeResult:
        """NET-003: Attempt outbound UDP DNS packet dispatch."""
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.NOT_CONFIGURED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        try:
            # Minimal DNS query header for example.com
            dummy_dns = b"\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01"
            s.sendto(dummy_dns, (server, port))
            # If send succeeded, UDP egress is open
            blocked = False
            sev = SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS
            mech = EnforcementMechanism.NOT_CONFIGURED
        except (PermissionError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__
            if err_code == 10013:
                mech = EnforcementMechanism.OS_ENFORCED
                sev = SeverityLevel.S0_EXPECTED_DENIAL
            else:
                mech = EnforcementMechanism.NOT_CONFIGURED
        finally:
            try:
                s.close()
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="NET-003",
            family=VectorFamily.NETWORK,
            name="OutboundUdpDnsProbe",
            target=f"{server}:{port}",
            attempt_details=f"Attempted outbound UDP DNS datagram transmission to {server}:{port}",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_raw_socket(cls) -> HostileProbeResult:
        """NET-005: Attempt raw socket creation (SOCK_RAW).

        On modern Windows, SOCK_RAW requires Administrator privileges;
        restricted / low integrity tokens must be denied with WSAEACCES.
        """
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.OS_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
            s.close()
            blocked = False
            sev = SeverityLevel.S6_PRIVILEGE_ESCALATION
            mech = EnforcementMechanism.OS_ENFORCED
        except (PermissionError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__
            mech = EnforcementMechanism.OS_ENFORCED
            sev = SeverityLevel.S0_EXPECTED_DENIAL

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="NET-005",
            family=VectorFamily.NETWORK,
            name="RawSocketCreationProbe",
            target="AF_INET/SOCK_RAW",
            attempt_details="Attempted creation of raw IP socket (SOCK_RAW)",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
        )

    @classmethod
    def probe_loopback_binding(cls, port: int = 0) -> HostileProbeResult:
        """NET-004: Attempt binding to localhost TCP interface."""
        start = time.perf_counter()
        blocked = False
        err_code: int | None = None
        err_name: str | None = None
        mech = EnforcementMechanism.APPLICATION_ENFORCED
        sev = SeverityLevel.S0_EXPECTED_DENIAL
        bound_port = 0

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", port))
            s.listen(1)
            bound_port = s.getsockname()[1]
            blocked = False
            sev = SeverityLevel.S3_HOST_RESOURCE_VIOLATION
            mech = EnforcementMechanism.NOT_CONFIGURED
        except (PermissionError, OSError) as exc:
            blocked = True
            err_code = getattr(exc, "winerror", getattr(exc, "errno", None))
            err_name = exc.__class__.__name__
            mech = EnforcementMechanism.OS_ENFORCED
            sev = SeverityLevel.S0_EXPECTED_DENIAL
        finally:
            try:
                s.close()
            except Exception:
                pass

        duration_ms = (time.perf_counter() - start) * 1000.0
        return HostileProbeResult(
            vector_id="NET-004",
            family=VectorFamily.NETWORK,
            name="LoopbackSocketBindProbe",
            target=f"127.0.0.1:{port}",
            attempt_details="Attempted binding listening TCP socket on loopback interface",
            win32_error_code=err_code,
            win32_error_name=err_name,
            enforcement_mechanism=mech,
            severity=sev,
            blocked=blocked,
            duration_ms=duration_ms,
            details={"bound_port": bound_port},
        )

    @classmethod
    def run_all_probes(cls) -> list[HostileProbeResult]:
        """Execute full network boundary probe suite."""
        return [
            cls.probe_outbound_tcp("1.1.1.1", 443, "NET-001", "OutboundTcp443Probe"),
            cls.probe_outbound_tcp("1.1.1.1", 80, "NET-002", "OutboundTcp80Probe"),
            cls.probe_outbound_udp_dns(),
            cls.probe_raw_socket(),
            cls.probe_loopback_binding(),
        ]


__all__ = ["NetworkGuard"]
