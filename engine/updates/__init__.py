"""
engine/updates — Complete-Installer Update Subsystem for RenderFlow
==================================================================
Public API exports for modular, secure, complete-installer updates.
"""

from engine.updates.models import (
    UpdateState,
    UpdateStatus,
    ReleaseInfo,
    InstallerAsset,
    DownloadProgress,
)
from engine.updates.semver import SemVer
from engine.updates.artifact_verifier import ArtifactVerifier, canonicalize_manifest
from engine.updates.manifest_validator import ReleaseManifestValidator
from engine.updates.download_service import SecureDownloadService
from engine.updates.installer_launcher import InstallerLauncher
from engine.updates.post_update_verifier import PostUpdateVerifier
from engine.updates.recovery_service import UpdateRecoveryService
from engine.updates.update_service import UpdateService

# Authoritative singleton instance
update_service = UpdateService()

__all__ = [
    "UpdateState",
    "UpdateStatus",
    "ReleaseInfo",
    "InstallerAsset",
    "DownloadProgress",
    "SemVer",
    "ArtifactVerifier",
    "canonicalize_manifest",
    "ReleaseManifestValidator",
    "SecureDownloadService",
    "InstallerLauncher",
    "PostUpdateVerifier",
    "UpdateRecoveryService",
    "UpdateService",
    "update_service",
]
