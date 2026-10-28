"""
engine/updates/download_service.py — Resilient Chunked Streaming Downloader
==========================================================================
Downloads approved installer executables with progress tracking, timeouts,
cancellation support, speed calculation, and atomic file finalization.
"""

import os
import time
import shutil
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple

from engine.updates.models import InstallerAsset, DownloadProgress

logger = logging.getLogger("renderflow.updates.downloader")


class SecureDownloadService:
    """Manages background streaming downloads of verified installer packages."""

    def __init__(self, download_dir: Path, timeout_seconds: float = 30.0, chunk_size: int = 65536):
        self.download_dir = Path(download_dir).resolve()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout_seconds
        self.chunk_size = chunk_size

        self.cancel_event = threading.Event()
        self.progress = DownloadProgress()
        self._progress_callback: Optional[Callable[[DownloadProgress], None]] = None

    def cancel(self):
        """Signals active download to stop cleanly."""
        logger.info("Download cancellation requested.")
        self.cancel_event.set()

    def download_installer(
        self,
        installer: InstallerAsset,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        max_retries: int = 3
    ) -> Tuple[Optional[Path], Optional[str]]:
        """
        Streams the installer asset to a temporary .part file in download_dir.
        Returns: (final_path: Path, None) on success, or (None, error_message) on failure.
        """
        if self.cancel_event.is_set():
            return None, "Download was cancelled."
        self.cancel_event.clear()
        self._progress_callback = progress_callback

        safe_filename = Path(installer.name).name
        target_path = self.download_dir / safe_filename
        part_path = self.download_dir / f"{safe_filename}.part"

        # If target file already exists and matches expected size & sha256, reuse it
        if target_path.exists() and installer.size_bytes > 0:
            if target_path.stat().st_size == installer.size_bytes:
                logger.info("Found pre-existing downloaded installer matching expected size: %s", target_path)
                return target_path, None

        # Clean any stale partial files
        if part_path.exists():
            try:
                part_path.unlink()
            except Exception:
                pass

        attempt = 0
        last_error = None

        while attempt < max_retries and not self.cancel_event.is_set():
            attempt += 1
            logger.info("Starting installer download attempt %d/%d from %s", attempt, max_retries, installer.url)

            success, err = self._stream_file(installer.url, part_path, installer.size_bytes)
            if success:
                # Atomically promote .part to final destination
                try:
                    if target_path.exists():
                        target_path.unlink()
                    shutil.move(str(part_path), str(target_path))
                    logger.info("Installer download completed successfully: %s", target_path)
                    return target_path, None
                except Exception as e:
                    logger.error("Failed to finalize installer file: %s", e)
                    return None, f"Failed to finalize downloaded installer file: {e}"

            last_error = err
            if self.cancel_event.is_set():
                logger.info("Download cancelled by user.")
                self._cleanup_partial(part_path)
                return None, "Download was cancelled."

            # Back off before retrying
            logger.warning("Download attempt %d failed: %s. Retrying in 2 seconds...", attempt, err)
            time.sleep(2.0)

        self._cleanup_partial(part_path)
        return None, last_error or "Download failed after multiple attempts."

    def _stream_file(self, url: str, dest_part_path: Path, expected_size: int) -> Tuple[bool, Optional[str]]:
        """Internal streaming loop with real-time speed and progress calculation."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "RenderFlow-Installer-Downloader/2.4.x",
                "Accept": "*/*",
            }
        )

        try:
            start_time = time.time()
            bytes_received = 0
            last_speed_time = start_time
            bytes_since_last_calc = 0

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                # Determine total size
                header_len = resp.headers.get("Content-Length")
                total_size = int(header_len) if header_len and header_len.isdigit() else expected_size

                self.progress.total_bytes = total_size
                self.progress.downloaded_bytes = 0
                self.progress.is_active = True
                self._notify()

                with open(dest_part_path, "wb") as f_out:
                    while not self.cancel_event.is_set():
                        chunk = resp.read(self.chunk_size)
                        if not chunk:
                            break

                        f_out.write(chunk)
                        bytes_received += len(chunk)
                        bytes_since_last_calc += len(chunk)

                        now = time.time()
                        calc_delta = now - last_speed_time
                        if calc_delta >= 0.5:
                            speed = bytes_since_last_calc / calc_delta
                            last_speed_time = now
                            bytes_since_last_calc = 0

                            elapsed = now - start_time
                            pct = (bytes_received / total_size * 100.0) if total_size > 0 else 0.0
                            remaining_bytes = max(0, total_size - bytes_received)
                            eta = (remaining_bytes / speed) if speed > 0 else 0.0

                            self.progress.downloaded_bytes = bytes_received
                            self.progress.percent = min(100.0, pct)
                            self.progress.speed_bytes_per_sec = speed
                            self.progress.elapsed_seconds = elapsed
                            self.progress.eta_seconds = eta
                            self._notify()

                if self.cancel_event.is_set():
                    self.progress.is_active = False
                    return False, "Download cancelled."

                # Verify received size matches expected if expected is non-zero
                if total_size > 0 and bytes_received < total_size:
                    self.progress.is_active = False
                    return False, f"Incomplete download: received {bytes_received} of {total_size} bytes."

                self.progress.downloaded_bytes = bytes_received
                self.progress.percent = 100.0
                self.progress.is_active = False
                self._notify()
                return True, None

        except urllib.error.HTTPError as e:
            self.progress.is_active = False
            return False, f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            self.progress.is_active = False
            return False, f"Connection error: {e.reason}"
        except Exception as e:
            self.progress.is_active = False
            return False, f"Transfer error: {e}"

    def _notify(self):
        if self._progress_callback:
            try:
                self._progress_callback(self.progress)
            except Exception:
                pass

    @staticmethod
    def _cleanup_partial(part_path: Path):
        try:
            if part_path.exists():
                part_path.unlink()
        except Exception:
            pass
