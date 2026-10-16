"""jarvis.config.sandbox_config — OpenClaw-parity sandbox configuration contracts.

Mirrors OpenClaw's sandbox configuration schema from ``src/config/types.openclaw.ts``
and ``docs/gateway/sandboxing.md``:
- SandboxMode: "off" | "non-main" | "all"
- SandboxScope: "agent" | "session" | "shared"
- SandboxBackend: "docker" | "podman" | "ssh" | "process" | "openshell"
- SandboxWorkspaceAccess: "none" | "ro" | "rw"
- DockerSandboxConfig: container options (image, network, readOnlyRoot, tmpfs, capDrop, binds)
- BrowserSandboxConfig: browser sidecar container settings
- SandboxConfig: top-level sandbox configuration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SandboxMode = Literal["off", "non-main", "all"]
SandboxScope = Literal["agent", "session", "shared"]
SandboxBackend = Literal["docker", "podman", "ssh", "process", "openshell"]
SandboxWorkspaceAccess = Literal["none", "ro", "rw"]

DEFAULT_SANDBOX_IMAGE = "openclaw-sandbox:bookworm-slim"
DEFAULT_SANDBOX_BROWSER_IMAGE = "openclaw-sandbox-browser:bookworm-slim"
DEFAULT_SANDBOX_NETWORK = "none"
DEFAULT_BROWSER_NETWORK = "openclaw-sandbox-browser"


@dataclass(slots=True)
class DockerSandboxConfig:
    """Docker/Podman container engine configuration.

    Mirrors OpenClaw's ``agents.defaults.sandbox.docker`` schema.
    """

    image: str = DEFAULT_SANDBOX_IMAGE
    network: str = DEFAULT_SANDBOX_NETWORK
    read_only_root: bool = True
    tmpfs: list[str] = field(default_factory=lambda: ["/tmp", "/var/tmp", "/run"])
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])
    binds: list[str] = field(default_factory=list)
    user: str | None = None
    gpus: str | None = None
    extra_args: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DockerSandboxConfig:
        if not data:
            return cls()
        return cls(
            image=str(data.get("image") or DEFAULT_SANDBOX_IMAGE),
            network=str(data.get("network") or DEFAULT_SANDBOX_NETWORK),
            read_only_root=bool(data.get("readOnlyRoot", data.get("read_only_root", True))),
            tmpfs=list(data.get("tmpfs") or ["/tmp", "/var/tmp", "/run"]),
            cap_drop=list(data.get("capDrop", data.get("cap_drop", ["ALL"]))),
            binds=list(data.get("binds") or []),
            user=str(data["user"]) if data.get("user") is not None else None,
            gpus=str(data["gpus"]) if data.get("gpus") is not None else None,
            extra_args=list(data.get("extraArgs", data.get("extra_args", []))),
        )


@dataclass(slots=True)
class BrowserSandboxConfig:
    """Browser sidecar container configuration.

    Mirrors OpenClaw's ``agents.defaults.sandbox.browser`` schema.
    """

    auto_start: bool = True
    auto_start_timeout_ms: int = 12000
    network: str = DEFAULT_BROWSER_NETWORK
    cdp_source_range: str | None = None
    allow_host_control: bool = False
    allowed_control_urls: list[str] = field(default_factory=list)
    allowed_control_hosts: list[str] = field(default_factory=list)
    allowed_control_ports: list[int] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BrowserSandboxConfig:
        if not data:
            return cls()
        return cls(
            auto_start=bool(data.get("autoStart", data.get("auto_start", True))),
            auto_start_timeout_ms=int(
                data.get("autoStartTimeoutMs", data.get("auto_start_timeout_ms", 12000))
            ),
            network=str(data.get("network") or DEFAULT_BROWSER_NETWORK),
            cdp_source_range=str(data["cdpSourceRange"]) if data.get("cdpSourceRange") else None,
            allow_host_control=bool(
                data.get("allowHostControl", data.get("allow_host_control", False))
            ),
            allowed_control_urls=list(
                data.get("allowedControlUrls", data.get("allowed_control_urls", []))
            ),
            allowed_control_hosts=list(
                data.get("allowedControlHosts", data.get("allowed_control_hosts", []))
            ),
            allowed_control_ports=[
                int(p)
                for p in data.get("allowedControlPorts", data.get("allowed_control_ports", []))
            ],
        )


@dataclass(slots=True)
class SandboxConfig:
    """Top-level sandbox configuration.

    Mirrors OpenClaw's ``agents.defaults.sandbox`` schema.
    """

    mode: SandboxMode = "off"
    scope: SandboxScope = "agent"
    backend: SandboxBackend = "docker"
    workspace_access: SandboxWorkspaceAccess = "rw"
    docker: DockerSandboxConfig = field(default_factory=DockerSandboxConfig)
    browser: BrowserSandboxConfig = field(default_factory=BrowserSandboxConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SandboxConfig:
        if not data:
            return cls()
        mode_val = str(data.get("mode") or "off").lower()
        if mode_val not in ("off", "non-main", "all"):
            mode_val = "off"
        scope_val = str(data.get("scope") or "agent").lower()
        if scope_val not in ("agent", "session", "shared"):
            scope_val = "agent"
        backend_val = str(data.get("backend") or "docker").lower()
        if backend_val not in ("docker", "podman", "ssh", "process", "openshell"):
            backend_val = "docker"
        ws_val = str(data.get("workspaceAccess", data.get("workspace_access", "rw"))).lower()
        if ws_val not in ("none", "ro", "rw"):
            ws_val = "rw"

        return cls(
            mode=mode_val,  # type: ignore[arg-type]
            scope=scope_val,  # type: ignore[arg-type]
            backend=backend_val,  # type: ignore[arg-type]
            workspace_access=ws_val,  # type: ignore[arg-type]
            docker=DockerSandboxConfig.from_dict(data.get("docker")),
            browser=BrowserSandboxConfig.from_dict(data.get("browser")),
        )


def resolve_sandbox_config(raw_config: dict[str, Any] | None = None) -> SandboxConfig:
    """Resolve raw config dictionary into a validated SandboxConfig."""
    if not raw_config:
        return SandboxConfig()

    sandbox_dict: dict[str, Any] | None = None
    if "agents" in raw_config and isinstance(raw_config["agents"], dict):
        defaults = raw_config["agents"].get("defaults", {})
        if isinstance(defaults, dict):
            sandbox_dict = defaults.get("sandbox")

    if sandbox_dict is None:
        if "sandbox" in raw_config and isinstance(raw_config["sandbox"], dict):
            sandbox_dict = raw_config["sandbox"]
        else:
            sandbox_dict = raw_config

    return SandboxConfig.from_dict(sandbox_dict if isinstance(sandbox_dict, dict) else None)
