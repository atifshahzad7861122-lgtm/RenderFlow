"""
engine/updates/models.py — Data Models & State Enums for Complete-Installer and Incremental Update System
========================================================================================================
Authoritative type definitions, enumerations, and immutable data classes.
Supports full installer executables, incremental ZIP patches, and dual-package releases.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List


class UpdateState(str, Enum):
    IDLE = "idle"
    CHECKING = "checking"
    UPDATE_AVAILABLE = "update_available"
    UP_TO_DATE = "up_to_date"
    CHECK_FAILED = "check_failed"

    DOWNLOADING = "downloading"
    DOWNLOAD_FAILED = "download_failed"

    VERIFYING = "verifying"
    VERIFICATION_FAILED = "verification_failed"

    READY_TO_INSTALL = "ready_to_install"
    INSTALLING = "installing"
    INSTALL_FAILED = "install_failed"

    READY_TO_RESTART = "ready_to_restart"
    ROLLBACK_COMPLETED = "rollback_completed"

    VERIFYING_INSTALL = "verifying_install"
    VERIFY_FAILED = "verify_failed"
    SUCCESS = "success"

    # Compatibility aliases
    AVAILABLE = "update_available"
    ERROR = "check_failed"
    DOWNLOADED = "ready_to_install"


class PackageType(str, Enum):
    FULL = "full"
    PATCH = "patch"
    DUAL = "dual"
    NONE = "none"


@dataclass
class InstallerAsset:
    name: str
    url: str
    size_bytes: int
    sha256: str
    platform: str = "windows-x64"
    browser_download_url: Optional[str] = None


@dataclass
class PatchAsset:
    name: str
    url: str
    size_bytes: int
    sha256: str
    from_version: Optional[str] = None
    to_version: Optional[str] = None
    platform: str = "windows-x64"
    browser_download_url: Optional[str] = None


@dataclass
class ReleaseInfo:
    version: str
    release_title: str
    release_notes: str
    published_at: str
    release_url: str
    installer: Optional[InstallerAsset] = None
    patch: Optional[PatchAsset] = None
    package_type: PackageType = PackageType.NONE
    selected_package_type: Optional[PackageType] = None
    signature_ed25519: Optional[str] = None
    public_key: Optional[str] = None
    is_prerelease: bool = False
    is_draft: bool = False
    raw_manifest: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadProgress:
    total_bytes: int = 0
    downloaded_bytes: int = 0
    percent: float = 0.0
    speed_bytes_per_sec: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    is_active: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_bytes": self.total_bytes,
            "downloaded_bytes": self.downloaded_bytes,
            "percent": round(self.percent, 1),
            "speed_bytes_per_sec": round(self.speed_bytes_per_sec, 1),
            "speed_formatted": self.format_speed(),
            "bytes_formatted": f"{self.format_bytes(self.downloaded_bytes)} / {self.format_bytes(self.total_bytes)}",
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "eta_seconds": round(self.eta_seconds, 1),
            "is_active": self.is_active,
        }

    @staticmethod
    def format_bytes(b: int) -> str:
        if b <= 0:
            return "0 B"
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024.0 or unit == "GB":
                return f"{b:.1f} {unit}" if unit != "B" else f"{int(b)} B"
            b /= 1024.0
        return f"{b:.1f} GB"

    def format_speed(self) -> str:
        if self.speed_bytes_per_sec <= 0:
            return "0 KB/s"
        return f"{self.format_bytes(int(self.speed_bytes_per_sec))}/s"


@dataclass
class UpdateStatus:
    state: UpdateState = UpdateState.IDLE
    current_version: str = "0.0.0"
    latest_version: Optional[str] = None
    update_available: bool = False
    package_type: str = "none"  # "patch", "full", or "dual"
    can_patch: bool = False
    can_install_full: bool = False
    error_message: Optional[str] = None
    error_details: Optional[str] = None
    last_checked_timestamp: float = 0.0
    release_title: Optional[str] = None
    release_notes: Optional[str] = None
    release_url: Optional[str] = None
    package_size_bytes: int = 0
    download_progress: DownloadProgress = field(default_factory=DownloadProgress)
    installer_path: Optional[str] = None
    patch_path: Optional[str] = None
    is_verified: bool = False
    diagnostics_log_path: Optional[str] = None
    recovery_guidance: Optional[str] = None

    @property
    def check_status(self) -> str:
        if self.state == UpdateState.CHECK_FAILED:
            return "check_failed"
        if self.state == UpdateState.CHECKING:
            return "checking"
        if self.is_verified:
            return "update_available" if self.update_available else "verified_latest"
        return "idle"

    @property
    def installer_ready(self) -> bool:
        return self.state in (UpdateState.READY_TO_INSTALL, UpdateState.READY_TO_RESTART) and bool(self.installer_path)

    @property
    def patch_ready(self) -> bool:
        return self.state in (UpdateState.READY_TO_INSTALL, UpdateState.READY_TO_RESTART) and bool(self.patch_path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.state not in (
                UpdateState.CHECK_FAILED,
                UpdateState.DOWNLOAD_FAILED,
                UpdateState.VERIFICATION_FAILED,
                UpdateState.INSTALL_FAILED,
                UpdateState.VERIFY_FAILED,
            ),
            "state": self.state.value if isinstance(self.state, UpdateState) else str(self.state),
            "check_status": self.check_status,
            "current_version": self.current_version,
            "latest_version": self.latest_version if (self.is_verified and self.latest_version) else None,
            "update_available": self.update_available,
            "package_type": self.package_type,
            "can_patch": self.can_patch,
            "can_install_full": self.can_install_full,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "last_checked": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_checked_timestamp)) if self.last_checked_timestamp > 0 else "Never",
            "last_checked_timestamp": self.last_checked_timestamp,
            "release_title": self.release_title,
            "release_notes": self.release_notes,
            "release_url": self.release_url,
            "package_size_bytes": self.package_size_bytes,
            "package_size": DownloadProgress.format_bytes(self.package_size_bytes),
            "download_progress": self.download_progress.to_dict(),
            "installer_ready": self.installer_ready,
            "patch_ready": self.patch_ready,
            "installer_path": self.installer_path,
            "patch_path": self.patch_path,
            "is_verified": self.is_verified,
            "diagnostics_log_path": self.diagnostics_log_path,
            "recovery_guidance": self.recovery_guidance,
        }
