"""jarvis.config.zod_schema_installs — install-related Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.installs.ts``.
"""
from __future__ import annotations



#: Generic install record shape (zod schema fields).
InstallRecordShape: dict = {
    "source": None,  # InstallSourceSchema (union of npm|archive|path|clawhub|git)
    "spec": None,
    "sourcePath": None,
    "installPath": None,
    "version": None,
    "resolvedName": None,
    "resolvedVersion": None,
    "resolvedSpec": None,
    "integrity": None,
    "shasum": None,
    "resolvedAt": None,
    "installedAt": None,
    "clawhubUrl": None,
    "clawhubPackage": None,
    "clawhubFamily": None,  # "code-plugin" | "bundle-plugin"
    "clawhubChannel": None,  # "official" | "community" | "private"
    "clawhubTrustDisposition": None,
    "clawhubTrustScanStatus": None,
    "clawhubTrustModerationState": None,
    "clawhubTrustReasons": None,
    "clawhubTrustPending": None,
    "clawhubTrustStale": None,
    "clawhubTrustCheckedAt": None,
    "clawhubTrustAcknowledgedAt": None,
    "artifactKind": None,  # "legacy-zip" | "npm-pack"
    "artifactFormat": None,  # "zip" | "tgz"
    "npmIntegrity": None,
    "npmShasum": None,
    "npmTarballName": None,
    "clawpackSha256": None,
    "clawpackSpecVersion": None,
    "clawpackManifestSha256": None,
    "clawpackSize": None,
    "gitUrl": None,
    "gitRef": None,
    "gitCommit": None,
}


#: Plugin install record shape (extends InstallRecordShape with marketplace).
PluginInstallRecordShape: dict = {
    **InstallRecordShape,
    "source": None,  # PluginInstallSourceSchema (union incl. "marketplace")
    "marketplaceName": None,
    "marketplaceSource": None,
    "marketplacePlugin": None,
}


#: Install source kinds.
InstallSourceKind: list = ["npm", "archive", "path", "clawhub", "git"]


#: Plugin install source kinds.
PluginInstallSourceKind: list = ["npm", "archive", "path", "clawhub", "git", "marketplace"]


__all__ = [
    "InstallRecordShape",
    "PluginInstallRecordShape",
    "InstallSourceKind",
    "PluginInstallSourceKind",
]
