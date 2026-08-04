"""jarvis.config.types_installs — install record config type definitions.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.installs.ts``.
"""
from __future__ import annotations

from typing import Literal, TypedDict

#: Install source kind.
InstallSource = Literal["npm", "archive", "path", "clawhub", "git"]
#: clawhub family.
ClawhubFamily = Literal["code-plugin", "bundle-plugin"]
#: clawhub channel.
ClawhubChannel = Literal["official", "community", "private"]
#: clawhub trust disposition.
ClawhubTrustDisposition = Literal["clean", "review-recommended", "review-required", "blocked"]
#: Artifact kind.
ArtifactKind = Literal["legacy-zip", "npm-pack"]
#: Artifact format.
ArtifactFormat = Literal["zip", "tgz"]


class InstallRecordBase(TypedDict, total=False):
    """Base persisted install record shared by plugin and skill tracking."""

    source: str
    spec: str
    sourcePath: str
    installPath: str
    version: str
    resolvedName: str
    resolvedVersion: str
    resolvedSpec: str
    integrity: str
    shasum: str
    resolvedAt: str
    installedAt: str
    clawhubUrl: str
    clawhubPackage: str
    clawhubFamily: str
    clawhubChannel: str
    clawhubTrustDisposition: str
    clawhubTrustScanStatus: str
    clawhubTrustModerationState: str
    clawhubTrustReasons: list
    clawhubTrustPending: bool
    clawhubTrustStale: bool
    clawhubTrustCheckedAt: str
    clawhubTrustAcknowledgedAt: str
    artifactKind: str
    artifactFormat: str
    npmIntegrity: str
    npmShasum: str
    npmTarballName: str
    clawpackSha256: str
    clawpackSpecVersion: int
    clawpackManifestSha256: str
    clawpackSize: int
    gitUrl: str
    gitRef: str
    gitCommit: str


__all__ = [
    "InstallSource",
    "ClawhubFamily",
    "ClawhubChannel",
    "ClawhubTrustDisposition",
    "ArtifactKind",
    "ArtifactFormat",
    "InstallRecordBase",
]
