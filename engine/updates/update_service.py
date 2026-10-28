"""
engine/updates/update_service.py — Production-Grade Update Orchestrator
======================================================================
Coordinates release discovery, cryptographic verification, streaming download,
installer execution, and post-restart verification within a bounded state machine.
"""

import os
import sys
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from engine.version import __version__ as CURRENT_APP_VERSION, GITHUB_RELEASES_PAGE
from engine.updates.models import UpdateState, UpdateStatus, ReleaseInfo, DownloadProgress
from engine.updates.semver import SemVer
from engine.updates.artifact_verifier import ArtifactVerifier
from engine.updates.manifest_validator import ReleaseManifestValidator
from engine.updates.download_service import SecureDownloadService
from engine.updates.installer_launcher import InstallerLauncher
from engine.updates.post_update_verifier import PostUpdateVerifier
from engine.updates.recovery_service import UpdateRecoveryService

logger = logging.getLogger("renderflow.updates.service")


class UpdateService:
    """Thread-safe central update coordinator and state machine."""

    def __init__(
        self,
        app_root: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        check_cache_ttl_seconds: float = 300.0
    ):
        if app_root is None:
            if getattr(sys, "frozen", False):
                app_root = Path(sys.executable).resolve().parent
            else:
                app_root = Path(__file__).resolve().parent.parent.parent
        self.app_root = Path(app_root).resolve()

        if cache_dir is None:
            cache_dir = self.app_root / ".cache" / "updates"
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.downloads_dir = self.cache_dir / "downloads"
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        self.check_ttl = check_cache_ttl_seconds
        self.lock = threading.RLock()

        # Subsystems
        self.verifier = ArtifactVerifier()
        self.validator = ReleaseManifestValidator(verifier=self.verifier)
        self.downloader = SecureDownloadService(download_dir=self.downloads_dir)
        self.launcher = InstallerLauncher(app_root=self.app_root, cache_dir=self.cache_dir)
        self.post_verifier = PostUpdateVerifier()
        self.recovery = UpdateRecoveryService(cache_dir=self.cache_dir)

        # Internal state
        self.status = UpdateStatus(
            state=UpdateState.IDLE,
            current_version=CURRENT_APP_VERSION,
            diagnostics_log_path=str(self.recovery.diagnostics_file)
        )
        self._cached_release: Optional[ReleaseInfo] = None
        self._downloaded_installer_path: Optional[Path] = None
        self._download_thread: Optional[threading.Thread] = None

    def get_status(self) -> Dict[str, Any]:
        """Returns instantaneous snapshot of updater status dictionary."""
        with self.lock:
            # Sync download progress if active
            if self.downloader.progress.is_active:
                self.status.download_progress = self.downloader.progress
            return self.status.to_dict()

    def check_for_updates(
        self,
        force: bool = False,
        custom_manifest_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Queries release metadata and evaluates whether an upgrade is available.
        """
        with self.lock:
            now = time.time()
            # If recent cached check exists and not forced, return cached result
            if not force and not custom_manifest_url and self._cached_release:
                if (now - self.status.last_checked_timestamp) < self.check_ttl:
                    logger.info("Returning cached update status (age: %.1fs)", now - self.status.last_checked_timestamp)
                    return self.status.to_dict()

            # Prevent checking if active download in progress
            if self.status.state in (UpdateState.DOWNLOADING, UpdateState.VERIFYING, UpdateState.INSTALLING):
                logger.warning("Update check rejected: operation in progress (%s)", self.status.state)
                return self.status.to_dict()

            self.status.state = UpdateState.CHECKING
            self.status.error_message = None
            self.status.error_details = None
            self.status.is_verified = False
            self.status.latest_version = None
            self.status.update_available = False
            self._cached_release = None
            self.recovery.log_event("CHECK_INITIATED", "Checking for updates...")

        # Perform network check outside the lock to avoid blocking callers
        release_info, err = self.validator.fetch_latest_release(custom_manifest_url=custom_manifest_url)

        with self.lock:
            self.status.last_checked_timestamp = time.time()

            if err or not release_info:
                self.status.state = UpdateState.CHECK_FAILED
                self.status.is_verified = False
                self.status.latest_version = None
                self.status.update_available = False
                self._cached_release = None
                self.status.error_message = err or "Failed to retrieve update metadata."
                self.status.error_details = self.recovery.get_recovery_guidance("CHECK_FAILED", self.status.error_message)
                self.recovery.log_event("CHECK_FAILED", self.status.error_message)
                return self.status.to_dict()

            self._cached_release = release_info
            self.status.is_verified = True
            self.status.latest_version = release_info.version
            self.status.release_title = release_info.release_title
            self.status.release_notes = release_info.release_notes
            self.status.release_url = release_info.release_url
            self.status.package_size_bytes = release_info.installer.size_bytes if release_info.installer else 0

            # Semantic version comparison
            current_sem = SemVer(self.status.current_version)
            latest_sem = SemVer(release_info.version)

            if latest_sem > current_sem:
                self.status.update_available = True
                self.status.state = UpdateState.UPDATE_AVAILABLE
                self.recovery.log_event("UPDATE_AVAILABLE", f"New version available: v{release_info.version}")
            else:
                self.status.update_available = False
                self.status.state = UpdateState.UP_TO_DATE
                self.recovery.log_event("UP_TO_DATE", f"RenderFlow is up to date (v{self.status.current_version})")

            return self.status.to_dict()

    def start_download(self) -> Dict[str, Any]:
        """
        Initiates asynchronous background download of the approved installer.
        """
        with self.lock:
            if self.status.state == UpdateState.DOWNLOADING:
                return self.status.to_dict()

            if not self._cached_release or not self._cached_release.installer:
                self.status.state = UpdateState.DOWNLOAD_FAILED
                self.status.error_message = "No approved installer package available to download."
                return self.status.to_dict()

            installer_asset = self._cached_release.installer
            self.status.state = UpdateState.DOWNLOADING
            self.status.error_message = None
            self.status.error_details = None
            self.recovery.log_event("DOWNLOAD_STARTED", f"Starting download of {installer_asset.name}")

            # Spawn background download thread
            self._download_thread = threading.Thread(
                target=self._run_download_pipeline,
                args=(installer_asset,),
                name="installer_downloader_thread",
                daemon=True
            )
            self._download_thread.start()
            return self.status.to_dict()

    def _run_download_pipeline(self, installer_asset):
        """Worker thread executing streaming download, hashing, and signature validation."""
        def _on_progress(prog: DownloadProgress):
            with self.lock:
                self.status.download_progress = prog

        downloaded_path, dl_err = self.downloader.download_installer(
            installer=installer_asset,
            progress_callback=_on_progress
        )

        with self.lock:
            if dl_err or not downloaded_path:
                self.status.state = UpdateState.DOWNLOAD_FAILED
                self.status.error_message = dl_err or "Download failed."
                self.status.error_details = self.recovery.get_recovery_guidance("DOWNLOAD_FAILED", self.status.error_message)
                self.recovery.log_event("DOWNLOAD_FAILED", self.status.error_message)
                return

            # Transition to VERIFYING state
            self.status.state = UpdateState.VERIFYING
            self.recovery.log_event("VERIFICATION_STARTED", f"Verifying {downloaded_path.name}")

        # Perform checksum and signature verification
        is_verified = True
        verify_error = None

        if installer_asset.sha256:
            ok, v_err = self.verifier.verify_file_integrity(
                filepath=downloaded_path,
                expected_sha256=installer_asset.sha256,
                expected_size=installer_asset.size_bytes
            )
            if not ok:
                is_verified = False
                verify_error = v_err

        with self.lock:
            if not is_verified:
                # Quarantine/delete corrupt binary
                try:
                    if downloaded_path.exists():
                        downloaded_path.unlink()
                except Exception:
                    pass
                self.status.state = UpdateState.VERIFICATION_FAILED
                self.status.error_message = verify_error or "Checksum verification failed."
                self.status.error_details = self.recovery.get_recovery_guidance("VERIFICATION_FAILED", self.status.error_message)
                self.recovery.log_event("VERIFICATION_FAILED", self.status.error_message)
                return

            self._downloaded_installer_path = downloaded_path
            self.status.installer_path = str(downloaded_path)
            self.status.is_verified = True
            self.status.state = UpdateState.READY_TO_INSTALL
            self.recovery.log_event("READY_TO_INSTALL", f"Verified installer ready at {downloaded_path}")

    def cancel_download(self) -> Dict[str, Any]:
        """Cancels any active download and restores state."""
        with self.lock:
            self.downloader.cancel()
            self.status.state = UpdateState.UPDATE_AVAILABLE if self.status.update_available else UpdateState.IDLE
            self.status.download_progress.is_active = False
            self.recovery.log_event("DOWNLOAD_CANCELLED", "User cancelled installer download.")
            return self.status.to_dict()

    def launch_installer(self, silent: bool = False) -> Dict[str, Any]:
        """
        Executes the verified installer and initiates graceful application handover.
        """
        with self.lock:
            if self.status.state != UpdateState.READY_TO_INSTALL or not self._downloaded_installer_path:
                self.status.state = UpdateState.INSTALL_FAILED
                self.status.error_message = "Installer is not downloaded or verified."
                return self.status.to_dict()

            installer_file = self._downloaded_installer_path
            self.status.state = UpdateState.INSTALLING
            self.recovery.log_event("LAUNCH_INITIATED", f"Launching installer: {installer_file.name}")

        success, err = self.launcher.launch_installer(
            installer_path=installer_file,
            silent=silent,
            schedule_exit=True
        )

        with self.lock:
            if not success:
                self.status.state = UpdateState.INSTALL_FAILED
                self.status.error_message = err or "Failed to start installer process."
                self.status.error_details = self.recovery.get_recovery_guidance("INSTALL_FAILED", self.status.error_message)
                self.recovery.log_event("LAUNCH_FAILED", self.status.error_message)
            else:
                self.recovery.log_event("LAUNCH_SUCCESS", "Installer launched. Server shutdown scheduled.")

            return self.status.to_dict()

    def verify_post_install(self, target_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Polls restarted application backend to confirm running version matches target.
        """
        with self.lock:
            ver = target_version or (self._cached_release.version if self._cached_release else None)
            if not ver:
                return {"ok": False, "message": "No target version specified for verification."}
            self.status.state = UpdateState.VERIFYING_INSTALL

        ok, err, details = self.post_verifier.verify_running_application(target_version=ver)

        with self.lock:
            if ok:
                self.status.state = UpdateState.SUCCESS
                self.status.current_version = ver
                self.status.update_available = False
                self.recovery.log_event("VERIFY_SUCCESS", f"Successfully upgraded and verified v{ver}")
                return {"ok": True, "message": f"Successfully updated to v{ver}!", "status": self.status.to_dict()}
            else:
                self.status.state = UpdateState.VERIFY_FAILED
                self.status.error_message = err or "Post-install verification failed."
                self.status.error_details = self.recovery.get_recovery_guidance("VERIFY_FAILED", self.status.error_message)
                self.recovery.log_event("VERIFY_FAILED", self.status.error_message)
                return {"ok": False, "message": self.status.error_message, "status": self.status.to_dict()}

    def clear_error(self) -> Dict[str, Any]:
        """Resets error state to IDLE or UPDATE_AVAILABLE."""
        with self.lock:
            if self.status.update_available:
                self.status.state = UpdateState.UPDATE_AVAILABLE
            else:
                self.status.state = UpdateState.IDLE
            self.status.error_message = None
            self.status.error_details = None
            return self.status.to_dict()
