"""
engine/updates/recovery_service.py — Diagnostics & Safe Recovery Service
=======================================================================
Maintains authoritative diagnostic event logs and provides actionable
recovery procedures when network, verification, or installation steps fail.
"""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from engine.version import GITHUB_RELEASES_PAGE

logger = logging.getLogger("renderflow.updates.recovery")


class UpdateRecoveryService:
    """Records diagnostic milestones and generates user recovery guidance."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostics_file = self.cache_dir / "update_diagnostics.log"

    def log_event(self, event_type: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Appends a timestamped structured diagnostic event to the log file."""
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] [{event_type.upper()}] {message}"
        if details:
            clean_details = " | ".join(f"{k}={v}" for k, v in details.items())
            entry += f" ({clean_details})"

        try:
            with open(self.diagnostics_file, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception as e:
            logger.error("Failed to append to update diagnostics log: %s", e)

    def get_recovery_guidance(self, failure_state: str, error_message: Optional[str] = None) -> str:
        """
        Returns clear, actionable, non-technical instructions for the user.
        """
        err_hint = f"\nError Details: {error_message}" if error_message else ""
        guidance = (
            f"RenderFlow Update Handover Notice ({failure_state}){err_hint}\n\n"
            "Your workspace data, projects, media files, and AI credentials remain 100% safe and intact.\n\n"
            "Recommended Recovery Steps:\n"
            "1. Manual Installation: You can download the latest official installer directly from:\n"
            f"   {GITHUB_RELEASES_PAGE}\n"
            "2. Run the downloaded 'RenderFlow-Setup-*.exe' installer. It will safely update the application.\n"
            "3. If RenderFlow is currently open, close it before running the setup wizard.\n"
            "4. Detailed technical diagnostic logs have been preserved at:\n"
            f"   {self.diagnostics_file}\n"
        )
        return guidance

    def read_recent_diagnostics(self, max_lines: int = 50) -> List[str]:
        """Reads recent diagnostic log entries for UI or debug display."""
        if not self.diagnostics_file.exists():
            return []
        try:
            with open(self.diagnostics_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [line.strip() for line in lines[-max_lines:]]
        except Exception:
            return []
