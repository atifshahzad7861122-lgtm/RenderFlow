"""
engine/updates/installer_launcher.py — Safe Installer Launcher & Process Handover
================================================================================
Gracefully closes RenderFlow, backs up mutable user configurations, and starts
the verified Inno Setup installer executable with safe process isolation.
"""

import os
import sys
import time
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

logger = logging.getLogger("renderflow.updates.launcher")


class InstallerLauncher:
    """Manages pre-install backups, process shutdown, and installer execution."""

    def __init__(self, app_root: Path, cache_dir: Optional[Path] = None):
        self.app_root = Path(app_root).resolve()
        self.cache_dir = Path(cache_dir or (self.app_root / ".cache" / "updates")).resolve()
        self.backup_dir = self.cache_dir / "backup"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_user_configurations(self) -> Tuple[bool, Optional[str]]:
        """
        Creates a timestamped snapshot of settings, credentials, and env before upgrade.
        User projects are isolated in projects/ and never touched.
        """
        ts = time.strftime("%Y%m%d_%H%M%S")
        target_backup = self.backup_dir / f"config_backup_{ts}"
        try:
            target_backup.mkdir(parents=True, exist_ok=True)

            # Files to protect
            configs_to_save = [
                self.app_root / "config" / "settings.json",
                self.app_root / "config" / "render_profiles.json",
                self.app_root / ".env",
                self.app_root / "credentials.json",
            ]

            copied_count = 0
            for src_file in configs_to_save:
                if src_file.exists() and src_file.is_file():
                    rel_name = src_file.name
                    shutil.copy2(src_file, target_backup / rel_name)
                    copied_count += 1

            logger.info("Backed up %d configuration files to %s", copied_count, target_backup)
            return True, str(target_backup)
        except Exception as e:
            logger.error("Failed to backup user configurations: %s", e)
            return False, f"Failed to backup configurations before update: {e}"

    def launch_installer(
        self,
        installer_path: Path,
        silent: bool = False,
        schedule_exit: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Launches the Inno Setup installer as an independent, detached process.
        """
        installer_path = Path(installer_path).resolve()
        if not installer_path.exists() or not installer_path.is_file():
            return False, f"Installer executable not found at: {installer_path}"

        if installer_path.suffix.lower() != ".exe":
            return False, f"Refusing to execute non-executable installer: {installer_path}"

        # 1. Back up user configurations first
        backup_ok, backup_info = self.backup_user_configurations()
        if not backup_ok:
            logger.warning("Proceeding with caution: backup warning: %s", backup_info)

        # 2. Prepare installer command line arguments
        log_file = (self.cache_dir / "installer_execution.log").resolve()
        safe_app_dir = str(self.app_root)

        cmd: List[str] = [str(installer_path)]
        cmd.append(f"/DIR={safe_app_dir}")
        cmd.append(f"/LOG={str(log_file)}")

        if silent:
            cmd.extend(["/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"])
        else:
            # Attended wizard: let Inno Setup show GUI but target the current directory
            cmd.append("/CLOSEAPPLICATIONS")

        logger.info("Launching installer: %s", " ".join(cmd))

        # 3. Spawn detached process on Windows
        try:
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = (
                    getattr(subprocess, "DETACHED_PROCESS", 0) |
                    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )

            proc = subprocess.Popen(
                cmd,
                cwd=str(installer_path.parent),
                creationflags=creation_flags,
                close_fds=True
            )
            logger.info("Installer process spawned successfully (PID: %d)", proc.pid)

            # 4. Schedule clean exit of current RenderFlow instance if requested
            if schedule_exit:
                self._schedule_graceful_shutdown()

            return True, None
        except Exception as e:
            logger.error("Failed to launch installer process: %s", e)
            return False, f"Failed to execute installer process: {e}"

    def _schedule_graceful_shutdown(self, delay_seconds: float = 1.5):
        """Asynchronously stops the server and terminates current process cleanly."""
        def _exit_task():
            time.sleep(delay_seconds)
            logger.info("Initiating graceful shutdown for installer handover...")
            # Release single-instance lock if present
            lock_file = self.app_root / ".renderflow_instance.json"
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except Exception:
                    pass
            # Force hard exit to release all ports and file handles immediately
            os._exit(0)

        t = threading.Thread(target=_exit_task, name="installer_handover_exit", daemon=True)
        t.start()
