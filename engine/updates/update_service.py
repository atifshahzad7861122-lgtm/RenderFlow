"""
engine/updates/update_service.py — Production-Grade Update Orchestrator
======================================================================
Coordinates release discovery, cryptographic verification, streaming download,
installer execution, atomic patch application, backup/rollback, and post-restart
verification within a thread-safe bounded state machine.
"""

import os
import sys
import time
import shutil
import zipfile
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List, Union

from engine.version import __version__ as CURRENT_APP_VERSION, GITHUB_RELEASES_PAGE
from engine.updates.models import (
    UpdateState,
    UpdateStatus,
    ReleaseInfo,
    InstallerAsset,
    PatchAsset,
    PackageType,
    DownloadProgress,
)
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

        self.staging_dir = self.cache_dir / "staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)

        self.backups_dir = self.cache_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)

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
        self._selected_asset: Optional[Union[InstallerAsset, PatchAsset]] = None
        self._downloaded_package_path: Optional[Path] = None
        self._download_thread: Optional[threading.Thread] = None

    def get_status(self) -> Dict[str, Any]:
        """Returns instantaneous snapshot of updater status dictionary."""
        with self.lock:
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
        Selects between incremental patch and full installer deterministically.
        """
        with self.lock:
            now = time.time()
            if not force and not custom_manifest_url and self._cached_release:
                if (now - self.status.last_checked_timestamp) < self.check_ttl:
                    logger.info("Returning cached update status (age: %.1fs)", now - self.status.last_checked_timestamp)
                    return self.status.to_dict()

            if self.status.state in (UpdateState.DOWNLOADING, UpdateState.VERIFYING, UpdateState.INSTALLING):
                logger.warning("Update check rejected: operation in progress (%s)", self.status.state)
                return self.status.to_dict()

            self.status.state = UpdateState.CHECKING
            self.status.error_message = None
            self.status.error_details = None
            self.status.is_verified = False
            self.status.latest_version = None
            self.status.update_available = False
            self.status.package_type = "none"
            self.status.can_patch = False
            self.status.can_install_full = False
            self._cached_release = None
            self._selected_asset = None
            self._downloaded_package_path = None
            self.status.installer_path = None
            self.status.patch_path = None
            self.recovery.log_event("CHECK_INITIATED", "Checking for updates...")

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

            # Semantic version comparison
            current_sem = SemVer(self.status.current_version)
            latest_sem = SemVer(release_info.version)

            if latest_sem <= current_sem:
                self.status.update_available = False
                self.status.state = UpdateState.UP_TO_DATE
                self.recovery.log_event("UP_TO_DATE", f"RenderFlow is up to date (v{self.status.current_version})")
                return self.status.to_dict()

            # Version is newer -> Determine package eligibility
            can_patch = False
            if release_info.patch:
                # If from_version is specified, verify compatibility
                if release_info.patch.from_version:
                    from_clean = release_info.patch.from_version.lstrip("vV")
                    curr_clean = self.status.current_version.lstrip("vV")
                    if from_clean == curr_clean or SemVer(curr_clean) >= SemVer(from_clean):
                        can_patch = True
                else:
                    can_patch = True

            can_install_full = bool(release_info.installer)

            self.status.can_patch = can_patch
            self.status.can_install_full = can_install_full

            # Deterministic package selection policy:
            # 1. Prefer compatible incremental patch (network-efficient & non-destructive)
            # 2. Fall back to full installer if patch is unavailable or incompatible
            if can_patch and release_info.patch:
                self._selected_asset = release_info.patch
                release_info.selected_package_type = PackageType.PATCH
                self.status.package_type = "patch"
                self.status.package_size_bytes = release_info.patch.size_bytes
            elif can_install_full and release_info.installer:
                self._selected_asset = release_info.installer
                release_info.selected_package_type = PackageType.FULL
                self.status.package_type = "full"
                self.status.package_size_bytes = release_info.installer.size_bytes
            else:
                self.status.state = UpdateState.CHECK_FAILED
                self.status.update_available = False
                self.status.error_message = (
                    f"Release v{release_info.version} does not provide a package compatible with "
                    f"installed v{self.status.current_version}."
                )
                self.status.error_details = self.recovery.get_recovery_guidance("CHECK_FAILED", self.status.error_message)
                self.recovery.log_event("CHECK_FAILED", self.status.error_message)
                return self.status.to_dict()

            self.status.update_available = True
            self.status.state = UpdateState.UPDATE_AVAILABLE
            self.recovery.log_event("UPDATE_AVAILABLE", f"New version available: v{release_info.version} (package: {self.status.package_type})")
            return self.status.to_dict()

    def start_download(self) -> Dict[str, Any]:
        """
        Initiates asynchronous background download of the selected package asset.
        """
        with self.lock:
            if self.status.state == UpdateState.DOWNLOADING:
                return self.status.to_dict()

            if not self._selected_asset:
                self.status.state = UpdateState.DOWNLOAD_FAILED
                self.status.error_message = "No approved package available to download. Please check for updates first."
                return self.status.to_dict()

            asset = self._selected_asset
            self.status.state = UpdateState.DOWNLOADING
            self.status.error_message = None
            self.status.error_details = None
            self.recovery.log_event("DOWNLOAD_STARTED", f"Starting download of {asset.name}")

            self._download_thread = threading.Thread(
                target=self._run_download_pipeline,
                args=(asset,),
                name="package_downloader_thread",
                daemon=True
            )
            self._download_thread.start()
            return self.status.to_dict()

    def _run_download_pipeline(self, asset: Union[InstallerAsset, PatchAsset]):
        """Worker thread executing streaming download and checksum validation."""
        def _on_progress(prog: DownloadProgress):
            with self.lock:
                self.status.download_progress = prog

        downloaded_path, dl_err = self.downloader.download_package(
            asset=asset,
            progress_callback=_on_progress
        )

        with self.lock:
            if dl_err or not downloaded_path:
                self.status.state = UpdateState.DOWNLOAD_FAILED
                self.status.error_message = dl_err or "Download failed."
                self.status.error_details = self.recovery.get_recovery_guidance("DOWNLOAD_FAILED", self.status.error_message)
                self.recovery.log_event("DOWNLOAD_FAILED", self.status.error_message)
                return

            self.status.state = UpdateState.VERIFYING
            self.recovery.log_event("VERIFICATION_STARTED", f"Verifying {downloaded_path.name}")

        is_verified = True
        verify_error = None

        if asset.sha256:
            ok, v_err = self.verifier.verify_file_integrity(
                filepath=downloaded_path,
                expected_sha256=asset.sha256,
                expected_size=asset.size_bytes
            )
            if not ok:
                is_verified = False
                verify_error = v_err

        with self.lock:
            if not is_verified:
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

            self._downloaded_package_path = downloaded_path
            self.status.is_verified = True
            self.status.state = UpdateState.READY_TO_INSTALL

            if isinstance(asset, PatchAsset) or self.status.package_type == "patch":
                self.status.patch_path = str(downloaded_path)
            else:
                self.status.installer_path = str(downloaded_path)

            self.recovery.log_event("READY_TO_INSTALL", f"Verified package ready: {downloaded_path.name}")

    def cancel_download(self) -> Dict[str, Any]:
        """Cancels active download and restores state."""
        with self.lock:
            self.downloader.cancel()
            self.status.state = UpdateState.UPDATE_AVAILABLE if self.status.update_available else UpdateState.IDLE
            self.status.download_progress.is_active = False
            self.recovery.log_event("DOWNLOAD_CANCELLED", "User cancelled download.")
            return self.status.to_dict()

    def launch_installer(self, silent: bool = False) -> Dict[str, Any]:
        """
        Executes the verified full installer executable and initiates application shutdown.
        """
        with self.lock:
            if not self.status.installer_ready or not self._downloaded_package_path:
                self.status.state = UpdateState.INSTALL_FAILED
                self.status.error_message = "Installer is not downloaded or verified."
                return self.status.to_dict()

            installer_file = self._downloaded_package_path
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

    def apply_patch(self) -> Dict[str, Any]:
        """
        Safely unpacks, backs up, and installs a verified incremental patch archive (.zip).
        Implements path traversal protection, backup creation, and atomic rollback on failure.
        """
        with self.lock:
            if not self.status.patch_ready or not self._downloaded_package_path:
                self.status.state = UpdateState.INSTALL_FAILED
                self.status.error_message = "Patch package is not downloaded or verified."
                return self.status.to_dict()

            zip_path = self._downloaded_package_path
            self.status.state = UpdateState.INSTALLING
            self.recovery.log_event("PATCH_APPLY_INITIATED", f"Applying patch: {zip_path.name}")

        target_version = self.status.latest_version or "latest"
        current_version = self.status.current_version
        ts = int(time.time())
        staging_dir = self.staging_dir / f"patch_v{target_version}_{ts}"
        backup_dir = self.backups_dir / f"backup_v{current_version}_{ts}"

        try:
            # 1. Clean previous staging sandbox
            shutil.rmtree(staging_dir, ignore_errors=True)
            staging_dir.mkdir(parents=True, exist_ok=True)

            # 2. Extract into isolated staging sandbox with strict path traversal guards
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    norm_path = os.path.normpath(member.filename).lstrip(r"\/")
                    # Security checks: prevent path traversal and protected directories
                    if norm_path.startswith("..") or os.path.isabs(norm_path) or ":" in norm_path:
                        continue
                    parts = [p.lower() for p in Path(norm_path).parts]
                    if any(p in ("projects", ".env", "credentials.json", ".git") for p in parts):
                        continue

                    dest_staged = staging_dir / norm_path
                    try:
                        if hasattr(dest_staged, "is_relative_to"):
                            if not dest_staged.is_relative_to(staging_dir):
                                continue
                        else:
                            if os.path.commonpath([str(staging_dir), str(dest_staged)]) != str(staging_dir):
                                continue
                    except ValueError:
                        continue

                    dest_staged.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest_staged, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # 3. Create backup of current files that will be overwritten
            backup_dir.mkdir(parents=True, exist_ok=True)
            staged_files: List[Tuple[Path, Path, Path]] = []

            for root, _, files in os.walk(staging_dir):
                for f in files:
                    s_file = Path(root) / f
                    rel_p = s_file.relative_to(staging_dir)
                    dest_file = self.app_root / rel_p
                    backup_file = backup_dir / rel_p
                    staged_files.append((s_file, dest_file, backup_file))

            # Backup existing files
            for _, dest_file, backup_file in staged_files:
                if dest_file.exists():
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest_file, backup_file)

            # 4. Copy staged files into app_root
            for s_file, dest_file, _ in staged_files:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s_file, dest_file)

            # Cleanup staging
            shutil.rmtree(staging_dir, ignore_errors=True)

            with self.lock:
                self.status.state = UpdateState.READY_TO_RESTART
                self.recovery.log_event("PATCH_APPLIED", f"Patch v{target_version} applied successfully. Backup at {backup_dir.name}")
                return {
                    "ok": True,
                    "success": True,
                    "state": UpdateState.READY_TO_RESTART.value,
                    "message": f"Patch v{target_version} applied successfully. Restart required.",
                    "status": self.status.to_dict()
                }

        except Exception as e:
            logger.error("Failed to apply patch: %s. Initiating rollback...", e)
            self.recovery.log_event("PATCH_APPLY_FAILED", f"Error: {e}. Rolling back...")
            # Rollback
            try:
                for _, dest_file, backup_file in staged_files:
                    if backup_file.exists():
                        shutil.copy2(backup_file, dest_file)
            except Exception as rb_err:
                logger.error("Rollback error: %s", rb_err)

            shutil.rmtree(staging_dir, ignore_errors=True)

            with self.lock:
                self.status.state = UpdateState.INSTALL_FAILED
                self.status.error_message = f"Failed to apply patch: {e}"
                self.status.error_details = self.recovery.get_recovery_guidance("INSTALL_FAILED", self.status.error_message)
                return {
                    "ok": False,
                    "success": False,
                    "state": UpdateState.INSTALL_FAILED.value,
                    "message": self.status.error_message,
                    "status": self.status.to_dict()
                }

    def restart_app(self) -> bool:
        """
        Launches a detached helper script to cleanly restart the application after update.
        """
        try:
            exe_names = ["RenderingStudio.exe", "RenderFlow.exe"]
            target_exe = None
            target_args = ""
            for name in exe_names:
                p = self.app_root / name
                if p.exists() and p.is_file():
                    target_exe = str(p.resolve())
                    target_args = ""
                    break

            if not target_exe:
                bat_names = ["RenderingStudio.bat", "run_localhost.bat"]
                for name in bat_names:
                    p = self.app_root / name
                    if p.exists() and p.is_file():
                        target_exe = "cmd.exe"
                        target_args = f'/c "{str(p.resolve())}"'
                        break

            if not target_exe:
                target_exe = sys.executable
                server_p = (self.app_root / "web" / "server.py").resolve()
                launcher_p = (self.app_root / "installer" / "launcher_entry.py").resolve()
                if launcher_p.exists() and launcher_p.is_file():
                    target_args = f'"{launcher_p}"'
                elif server_p.exists() and server_p.is_file():
                    target_args = f'"{server_p}"'
                else:
                    target_args = "web\\server.py"

            pid = os.getpid()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            restart_ps1 = self.cache_dir / "restart_helper.ps1"
            log_file = (self.cache_dir / "restart_helper.log").resolve()

            safe_app_root = str(self.app_root.resolve()).replace("'", "''")
            safe_target_exe = target_exe.replace("'", "''")
            safe_log_file = str(log_file).replace("'", "''")

            script_content = f"""# RenderFlow Auto-Restart Helper
$targetPid = {pid}
$logPath = '{safe_log_file}'
$workDir = '{safe_app_root}'
$targetExe = '{safe_target_exe}'
$targetArgs = '{target_args}'

Function Write-Log($msg) {{
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $logPath -Value "[$ts] $msg" -ErrorAction SilentlyContinue
}}

Write-Log "Restart helper initiated. Target PID: $targetPid, Target Exe: $targetExe"

# Wait for old process to exit
if ($targetPid -gt 0) {{
    $waitCount = 0
    while ((Get-Process -Id $targetPid -ErrorAction SilentlyContinue) -and ($waitCount -lt 30)) {{
        Start-Sleep -Milliseconds 500
        $waitCount++
    }}
}}

Write-Log "Old process cleared or timed out. Launching updated application..."
Set-Location -Path $workDir
if ($targetArgs) {{
    Start-Process -FilePath $targetExe -ArgumentList $targetArgs -WorkingDirectory $workDir
}} else {{
    Start-Process -FilePath $targetExe -WorkingDirectory $workDir
}}
Write-Log "Updated application process launched successfully."
"""
            with open(restart_ps1, "w", encoding="utf-8") as f:
                f.write(script_content)

            cmd = [
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-NoProfile",
                "-WindowStyle", "Hidden",
                "-File", str(restart_ps1.resolve())
            ]

            subprocess.Popen(
                cmd,
                cwd=str(self.app_root),
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
            self.recovery.log_event("RESTART_TRIGGERED", "Detached restart helper launched.")
            return True
        except Exception as e:
            logger.error("Failed to launch restart helper: %s", e)
            self.recovery.log_event("RESTART_FAILED", str(e))
            return False

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
