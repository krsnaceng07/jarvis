"""Browser plugin configuration contracts and resolution."""

from dataclasses import dataclass
from typing import Literal, TypedDict, Dict, List, Optional, Union


class BrowserTabCleanupConfig(TypedDict, total=False):
    enabled: bool
    maxStaleAgeMs: int


class BrowserSsrFPolicy(TypedDict, total=False):
    allowLoopback: bool
    allowedHostnames: List[str]
    allowedCidrRanges: List[str]


class BrowserProfileConfig(TypedDict, total=False):
    cdpUrl: str
    cdpPort: int
    driver: Literal["openclaw", "existing-session", "extension"]
    headless: Union[bool, Literal["new"]]
    executablePath: str
    color: str
    userDataDir: str
    mcpCommand: str
    mcpArgs: List[str]
    attachOnly: bool


class BrowserConfig(TypedDict, total=False):
    enabled: bool
    evaluateEnabled: bool
    controlPort: int
    cdpPortRangeStart: int
    cdpPortRangeEnd: int
    cdpProtocol: str
    remoteCdpTimeoutMs: int
    remoteCdpHandshakeTimeoutMs: int
    localLaunchTimeoutMs: int
    localCdpReadyTimeoutMs: int
    actionTimeoutMs: int
    color: str
    executablePath: str
    headless: Union[bool, Literal["new"]]
    headlessSource: str
    noSandbox: bool
    attachOnly: bool
    defaultProfile: str
    profiles: Dict[str, BrowserProfileConfig]
    tabCleanup: BrowserTabCleanupConfig
    ssrfPolicy: BrowserSsrFPolicy
    extraArgs: List[str]
    extensionRelayToken: str


@dataclass(frozen=True)
class ResolvedBrowserProfile:
    name: str
    cdpPort: int
    cdpUrl: str
    cdpHost: str
    cdpIsLoopback: bool
    color: Optional[str]
    driver: Literal["openclaw", "existing-session", "extension"]
    executablePath: Optional[str]
    headless: Union[bool, Literal["new"]]
    headlessSource: str
    attachOnly: bool
    userDataDir: Optional[str] = None
    mcpCommand: Optional[str] = None
    mcpArgs: Optional[List[str]] = None


@dataclass(frozen=True)
class ResolvedBrowserConfig:
    enabled: bool
    evaluateEnabled: bool
    controlPort: int
    cdpPortRangeStart: int
    cdpPortRangeEnd: int
    cdpProtocol: str
    cdpHost: str
    cdpIsLoopback: bool
    remoteCdpTimeoutMs: int
    remoteCdpHandshakeTimeoutMs: int
    localLaunchTimeoutMs: int
    localCdpReadyTimeoutMs: int
    actionTimeoutMs: int
    color: str
    executablePath: Optional[str]
    headless: Union[bool, Literal["new"]]
    headlessSource: str
    noSandbox: bool
    attachOnly: bool
    defaultProfile: str
    profiles: Dict[str, ResolvedBrowserProfile]
    tabCleanup: BrowserTabCleanupConfig
    ssrfPolicy: BrowserSsrFPolicy
    extraArgs: List[str]
    extensionRelayDefaultPort: int
    extensionRelayPorts: Dict[str, int]
    extensionRelayToken: Optional[str] = None
