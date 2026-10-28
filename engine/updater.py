"""
RenderFlow — Production Auto-Update Engine
==========================================
Secure, lightweight, and resilient update manager for RenderFlow Workstation.
Supports:
- Cryptographic Ed25519 signature verification of remote manifests
- SHA-256 package checksum verification
- Lightweight patch updates (~1-5 MB) avoiding full 1.21 GB redownloads
- Fallback to full Windows installer when dependencies/models change
- Safe staging, automatic backups, and rollback on failure
- Strict user-project and custom asset preservation
- Real-time download progress and speed reporting
- Asynchronous non-blocking background workers
"""

import os
import sys
import json
import time
import shutil
import hashlib
import zipfile
import threading
import subprocess
import socket
import logging
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
from urllib.request import url2pathname
from typing import Dict, Any, Optional, List, Tuple

from engine.version import (
    __version__ as CURRENT_VERSION,
    UPDATE_MANIFEST_URL,
    UPDATE_MANIFEST_FALLBACK_URL,
    GITHUB_REPO_API,
    GITHUB_RELEASES_PAGE,
    APP_NAME
)
from engine.crypto_ed25519 import verify_signature, RENDERFLOW_MASTER_PUBLIC_KEY

logger = logging.getLogger("renderflow.updater")

ALLOWED_DOMAINS = {
    "raw.githubusercontent.com",
    "github.com",
    "objects.githubusercontent.com",
    "api.github.com",
    "github-releases.githubusercontent.com"
}
ALLOWED_DOWNLOAD_DOMAINS = ALLOWED_DOMAINS


class SemVer:
    """Semantic version parser and comparator (e.g. 2.2.0, 2.2.1-beta)."""
    def __init__(self, version_str: str):
        self.raw = version_str.strip().lstrip("v")
        if "-" in self.raw:
            main_part, self.prerelease = self.raw.split("-", 1)
        else:
            main_part = self.raw
            self.prerelease = None
        parts = main_part.split(".")
        self.major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
        self.minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        self.patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    @classmethod
    def parse(cls, version_str: str) -> "SemVer":
        return cls(version_str)

    def tuple(self) -> Tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: "SemVer") -> bool:
        if self.tuple() != other.tuple():
            return self.tuple() < other.tuple()
        # Same major.minor.patch: non-prerelease > prerelease
        if self.prerelease is None and other.prerelease is not None:
            return False
        if self.prerelease is not None and other.prerelease is None:
            return True
        if self.prerelease and other.prerelease:
            return self.prerelease < other.prerelease
        return False

    def __le__(self, other: "SemVer") -> bool:
        return self < other or self == other

    def __gt__(self, other: "SemVer") -> bool:
        return not (self <= other)

    def __ge__(self, other: "SemVer") -> bool:
        return not (self < other)

    def __eq__(self, other: "SemVer") -> bool:
        return self.tuple() == other.tuple() and self.prerelease == other.prerelease

    def __str__(self) -> str:
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            s += f"-{self.prerelease}"
        return s

class UpdateState:
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    UP_TO_DATE = "up_to_date"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    APPLYING = "applying"
    READY_TO_RESTART = "ready_to_restart"
    INSTALLER_READY = "installer_ready"
    ERROR = "error"

def canonicalize_manifest(manifest_dict: Dict[str, Any]) -> bytes:
    """Returns canonical UTF-8 JSON bytes excluding signature and public_key fields."""
    clean_dict = {k: v for k, v in manifest_dict.items() if k not in ("signature_ed25519", "signature", "public_key")}
    return json.dumps(clean_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")

class UpdateManager:
    """Core update controller managing manifest checks, downloads, and patch installations."""

    def __init__(self, app_root: Optional[Path] = None, base_dir: Optional[Path] = None, cache_dir: Optional[Path] = None):
        target = base_dir if base_dir is not None else app_root
        if target is None:
            if getattr(sys, "frozen", False):
                target = Path(sys.executable).resolve().parent
            else:
                target = Path(__file__).resolve().parent.parent
        self.app_root = Path(target).resolve()
        
        # User project directory that must NEVER be overwritten
        self.projects_dir = self.app_root / "projects"
        
        # Staging & Temporary paths
        if cache_dir is not None:
            self.cache_dir = Path(cache_dir).resolve()
        else:
            self.cache_dir = self.app_root / ".cache" / "updates"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.stage_dir = self.cache_dir / "staged"
        self.backup_dir = self.cache_dir / "backup"

        # State management (RLock prevents reentrant deadlocks)
        self.lock = threading.RLock()
        self.state = UpdateState.IDLE
        self.error_message: Optional[str] = None
        self.last_checked_time: float = 0.0

        # Installed version resolution: prioritize app_root/engine/version.py, fallback to module CURRENT_VERSION
        self.current_version = CURRENT_VERSION
        v_file = self.app_root / "engine" / "version.py"
        if v_file.exists():
            try:
                for line in v_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("__version__"):
                        self.current_version = line.split("=")[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass
        
        # Manifest & Target payload
        self.manifest_data: Optional[Dict[str, Any]] = None
        self.is_verified: bool = False
        self.selected_package: Optional[Dict[str, Any]] = None
        self.selected_package_type: str = "patch"  # 'patch' or 'full'
        self.downloaded_package_path: Optional[Path] = None
        
        # Download telemetry & cancellation
        self.download_bytes_received: int = 0
        self.download_total_bytes: int = 0
        self.download_percent: float = 0.0
        self.download_speed_kbps: float = 0.0
        self.download_active: bool = False
        self._cancel_requested: bool = False

    def get_status(self) -> Dict[str, Any]:
        """Return real-time update telemetry for the API and frontend."""
        with self.lock:
            latest_v = self.manifest_data.get("latest_version") if self.manifest_data else None
            notes = self.manifest_data.get("release_notes") if self.manifest_data else None
            pkg_size = self.selected_package.get("package_size_bytes") if self.selected_package else 0
            
            update_avail = False
            if self.is_verified and self.manifest_data:
                latest_v_str = self.manifest_data.get("latest_version", "0.0.0")
                try:
                    update_avail = (SemVer(latest_v_str) > SemVer(self.current_version))
                except Exception:
                    update_avail = False
            if self.state == UpdateState.AVAILABLE:
                update_avail = True

            # Determine strict 4-state lifecycle status:
            # 'not_checked' | 'checking' | 'verified_latest' | 'update_available' | 'check_failed'
            if self.state == UpdateState.CHECKING:
                check_status = "checking"
            elif self.state == UpdateState.ERROR:
                check_status = "check_failed"
            elif not self.is_verified or self.last_checked_time == 0.0 or self.state == UpdateState.IDLE:
                check_status = "not_checked"
            elif self.state == UpdateState.UP_TO_DATE:
                check_status = "verified_latest"
            elif self.state == UpdateState.AVAILABLE:
                check_status = "update_available"
            elif self.state in (
                UpdateState.DOWNLOADING,
                UpdateState.DOWNLOADED,
                UpdateState.APPLYING,
                UpdateState.READY_TO_RESTART,
                UpdateState.INSTALLER_READY
            ):
                check_status = self.state
            else:
                check_status = "not_checked"

            err = self.error_message if self.state == UpdateState.ERROR else None
            return {
                "current_version": self.current_version,
                "latest_version": latest_v,
                "state": self.state,
                "check_status": check_status,
                "is_verified": self.is_verified,
                "error": err,
                "error_message": err,
                "last_checked": self.last_checked_time,
                "package_type": self.selected_package_type,
                "package_size_bytes": pkg_size,
                "package_size": pkg_size,
                "ok": (self.state != UpdateState.ERROR),
                "success": (self.state in (UpdateState.READY_TO_RESTART, UpdateState.UP_TO_DATE)),
                "message": err if err else ("Update ready to restart." if self.state == UpdateState.READY_TO_RESTART else None),
                "download_progress": {
                    "received_bytes": self.download_bytes_received,
                    "total_bytes": self.download_total_bytes,
                    "percent": round(self.download_percent, 1),
                    "speed_kbps": round(self.download_speed_kbps, 1),
                    "active": self.download_active
                },
                "download_percent": round(self.download_percent, 1),
                "download_speed_kbps": round(self.download_speed_kbps, 1),
                "downloaded_bytes": self.download_bytes_received,
                "total_bytes": self.download_total_bytes or pkg_size,
                "can_cancel": self.download_active,
                "update_available": update_avail,
                "release_notes": notes,
                "release_page_url": self.manifest_data.get("release_page_url") if self.manifest_data else GITHUB_RELEASES_PAGE,
                "can_restart": (self.state == UpdateState.READY_TO_RESTART),
                "can_install_full": (self.state == UpdateState.INSTALLER_READY)
            }

    def validate_url_security(self, url: str) -> bool:
        """Enforce HTTPS and strict allowlisting of trusted domains."""
        try:
            parsed = urlparse(url)
            # Allow local staging/test URLs only when explicitly enabled in test mode
            is_staging_test = os.environ.get("RENDERFLOW_STAGING_MODE", "").strip().lower() in ("1", "true", "yes")
            if is_staging_test:
                if parsed.scheme.lower() == "file":
                    return True
                hostname = (parsed.hostname or "").lower()
                if hostname in ("localhost", "127.0.0.1", ""):
                    return True

            if parsed.scheme.lower() != "https":
                return False
            hostname = parsed.hostname.lower() if parsed.hostname else ""
            return any(hostname == domain or hostname.endswith("." + domain) for domain in ALLOWED_DOMAINS)
        except Exception:
            return False

    def verify_manifest_authenticity(self, manifest_dict: Dict[str, Any], manifest_bytes: Optional[bytes] = None, expected_pk: Optional[str] = None) -> bool:
        """
        Verify Ed25519 digital signature of the release manifest.
        The signature is computed over the canonical JSON representation excluding signature and public_key fields.
        """
        if isinstance(manifest_dict, bytes) and isinstance(manifest_bytes, dict):
            # Handle swapped args
            manifest_dict, manifest_bytes = manifest_bytes, manifest_dict

        sig_hex = manifest_dict.get("signature_ed25519") or manifest_dict.get("signature")
        if not sig_hex:
            return False

        canonical_bytes = canonicalize_manifest(manifest_dict)

        try:
            sig_bytes = bytes.fromhex(sig_hex)
            target_pk = expected_pk or RENDERFLOW_MASTER_PUBLIC_KEY
            pub_hex = manifest_dict.get("public_key") or target_pk
            if pub_hex.lower() != target_pk.lower():
                return False
            pub_bytes = bytes.fromhex(pub_hex)
            return verify_signature(canonical_bytes, sig_bytes, pub_bytes)
        except Exception:
            return False

    verify_manifest_signature = verify_manifest_authenticity

    def check_now(self, force: bool = False, custom_manifest_url: Optional[str] = None) -> Dict[str, Any]:
        """
        Synchronously fetch and cryptographically authenticate update manifest.
        Returns authoritative status dictionary.
        """
        now = time.time()
        # Rate-limiting: do not spam if checked less than 30s ago unless forced
        if not force and (now - self.last_checked_time < 30.0) and self.state not in (UpdateState.IDLE, UpdateState.ERROR):
            return self.get_status()

        with self.lock:
            self.state = UpdateState.CHECKING
            self.error_message = None

        self._worker_check(custom_manifest_url=custom_manifest_url)
        return self.get_status()

    def check_for_updates(self, force: bool = False, custom_manifest_url: Optional[str] = None, wait: bool = False) -> Dict[str, Any]:
        """
        Check remote manifest for updates.
        If wait=True, executes synchronously. If wait=False, spawns background worker.
        """
        if wait:
            return self.check_now(force=force, custom_manifest_url=custom_manifest_url)

        now = time.time()
        # Rate-limiting: do not spam if checked less than 30s ago unless forced
        if not force and (now - self.last_checked_time < 30.0) and self.state not in (UpdateState.IDLE, UpdateState.ERROR):
            return self.get_status()

        with self.lock:
            self.state = UpdateState.CHECKING
            self.error_message = None

        thread = threading.Thread(target=self._worker_check, args=(custom_manifest_url,), daemon=True)
        thread.start()
        return self.get_status()

    def _worker_check(self, custom_manifest_url: Optional[str] = None):
        if custom_manifest_url:
            candidate_urls = [custom_manifest_url]
        elif "RENDERFLOW_UPDATE_MANIFEST_URL" in os.environ and os.environ["RENDERFLOW_UPDATE_MANIFEST_URL"].strip():
            candidate_urls = [os.environ["RENDERFLOW_UPDATE_MANIFEST_URL"].strip()]
        else:
            candidate_urls = [UPDATE_MANIFEST_URL]
            if UPDATE_MANIFEST_FALLBACK_URL and UPDATE_MANIFEST_FALLBACK_URL != UPDATE_MANIFEST_URL:
                candidate_urls.append(UPDATE_MANIFEST_FALLBACK_URL)

        self.last_checked_time = time.time()
        logger.info("Initiating update check against candidate URLs: %s", [u.split("?")[0] for u in candidate_urls])

        raw_data = None
        last_network_error = None
        chosen_url = None

        for url in candidate_urls:
            if not self.validate_url_security(url):
                logger.warning("Manifest URL rejected by security policy: %s", url)
                last_network_error = f"Untrusted manifest URL domain: {url}"
                continue

            try:
                logger.debug("Attempting to fetch manifest from: %s", url)
                if url.startswith("file://"):
                    local_path_str = url2pathname(urlparse(url).path)
                    raw_data = Path(local_path_str).read_bytes()
                else:
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": f"{APP_NAME}-AutoUpdater/{CURRENT_VERSION}"}
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        raw_data = resp.read()

                chosen_url = url
                logger.info("Successfully fetched update manifest (%d bytes) from %s", len(raw_data), url)
                break
            except urllib.error.HTTPError as e:
                logger.warning("HTTP %d error fetching manifest from %s", e.code, url)
                last_network_error = f"HTTP {e.code} error from update server ({e.reason})"
            except urllib.error.URLError as e:
                logger.warning("Network connection failed for %s: %s", url, e.reason)
                last_network_error = f"Network offline or connection failed: {e.reason}"
            except (TimeoutError, socket.timeout):
                logger.warning("Timeout fetching update manifest from %s", url)
                last_network_error = f"Update server timed out while connecting to {urlparse(url).netloc}"
            except Exception as e:
                logger.warning("Unexpected error fetching update manifest from %s: %s", url, str(e))
                last_network_error = f"Update check failed: {str(e)}"

        if raw_data is None:
            with self.lock:
                self.state = UpdateState.ERROR
                self.is_verified = False
                self.error_message = last_network_error or "Could not reach update server"
            logger.error("Update check failed across all endpoints: %s", self.error_message)
            return

        try:
            manifest = json.loads(raw_data.decode("utf-8"))
        except json.JSONDecodeError as e:
            with self.lock:
                self.state = UpdateState.ERROR
                self.is_verified = False
                self.error_message = f"Failed to parse update manifest JSON: {str(e)}"
            logger.error("Manifest JSON decoding failed: %s", e)
            return
        except Exception as e:
            with self.lock:
                self.state = UpdateState.ERROR
                self.is_verified = False
                self.error_message = f"Update check failed: {str(e)}"
            logger.error("Unexpected error parsing manifest: %s", e)
            return

        # Verify cryptographic authenticity
        is_valid_sig = self.verify_manifest_authenticity(raw_data, manifest)
        if not is_valid_sig:
            with self.lock:
                self.state = UpdateState.ERROR
                self.is_verified = False
                self.error_message = "Cryptographic signature verification failed! Update rejected."
            logger.error("Ed25519 manifest digital signature verification FAILED. Update rejected.")
            return

        logger.info("Cryptographic Ed25519 signature verified successfully for manifest.")

        latest_str = manifest.get("latest_version", "0.0.0")
        current_sem = SemVer(self.current_version)
        latest_sem = SemVer(latest_str)
        logger.info("Version check: installed=%s, latest=%s", current_sem, latest_sem)

        if latest_sem > current_sem:
            # Support both flat manifest format (Phase 2 spec) and nested packages dict
            packages = manifest.get("packages", {})
            patch_pkg = packages.get("patch")
            full_pkg = packages.get("full")

            if not patch_pkg and not full_pkg and "update_package_url" in manifest:
                up_type = manifest.get("update_type", "patch").lower()
                flat_pkg = {
                    "url": manifest["update_package_url"],
                    "package_size_bytes": manifest.get("package_size_bytes", 0),
                    "sha256": manifest.get("sha256", ""),
                    "applies_to": [">=2.0.0"]
                }
                if up_type == "patch":
                    patch_pkg = flat_pkg
                else:
                    full_pkg = flat_pkg

            # Prefer patch if available and within compatibility window
            selected_pkg = None
            pkg_type = "patch"

            min_supported = SemVer(manifest.get("minimum_supported_version", "0.0.0"))
            if current_sem < min_supported:
                # Current installation is too old for patch -> Must use full installer
                selected_pkg = full_pkg
                pkg_type = "full"
            elif patch_pkg and self._check_patch_applies(patch_pkg, current_sem):
                selected_pkg = patch_pkg
                pkg_type = "patch"
            elif full_pkg:
                selected_pkg = full_pkg
                pkg_type = "full"

            if not selected_pkg:
                with self.lock:
                    self.state = UpdateState.ERROR
                    self.is_verified = False
                    self.error_message = "No compatible package found in manifest."
                logger.warning("No compatible package found in manifest for version %s", current_sem)
                return

            with self.lock:
                self.manifest_data = manifest
                self.selected_package = selected_pkg
                self.selected_package_type = pkg_type
                self.state = UpdateState.AVAILABLE
                self.is_verified = True
                self.error_message = None
            logger.info("Update available: v%s (%s package)", latest_sem, pkg_type)
        else:
            with self.lock:
                self.manifest_data = manifest
                self.state = UpdateState.UP_TO_DATE
                self.is_verified = True
                self.error_message = None
            logger.info("Installed version v%s is up to date (remote=%s).", current_sem, latest_sem)

    def _check_patch_applies(self, patch_pkg: Dict[str, Any], current_sem: SemVer) -> bool:
        """Check if patch package is compatible with current installed version."""
        applies_rules = patch_pkg.get("applies_to", ["*"])
        for rule in applies_rules:
            if rule == "*":
                return True
            if rule.startswith(">=") and current_sem >= SemVer(rule[2:]):
                return True
            if rule.startswith("==") and current_sem == SemVer(rule[2:]):
                return True
        return False

    def start_download(self) -> Dict[str, Any]:
        """Initiate asynchronous background download of the selected package."""
        with self.lock:
            if self.state != UpdateState.AVAILABLE or not self.selected_package:
                return self.get_status()
            self.state = UpdateState.DOWNLOADING
            self.download_active = True
            self.error_message = None

        thread = threading.Thread(target=self._worker_download, daemon=True)
        thread.start()
        return self.get_status()

    def download_update_sync(self) -> bool:
        """Synchronously download update package (useful for tests and automation)."""
        with self.lock:
            if self.state != UpdateState.AVAILABLE or not self.selected_package:
                return False
            self.state = UpdateState.DOWNLOADING
            self.download_active = True
            self.error_message = None
        self._worker_download()
        return self.state in (UpdateState.DOWNLOADED, UpdateState.INSTALLER_READY)

    def _worker_download(self):
        pkg = self.selected_package
        url = pkg.get("url")
        expected_size = pkg.get("package_size_bytes", 0)
        expected_sha256 = pkg.get("sha256", "").lower()

        if not self.validate_url_security(url):
            with self.lock:
                self.state = UpdateState.ERROR
                self.download_active = False
                self.error_message = "Download URL rejected: untrusted host or insecure protocol."
            return

        # Pre-check disk space (at least 2x package size required)
        try:
            free_space = shutil.disk_usage(self.cache_dir).free
            if free_space < expected_size * 2 + 50_000_000:
                with self.lock:
                    self.state = UpdateState.ERROR
                    self.download_active = False
                    self.error_message = "Insufficient disk space for update package."
                return
        except Exception:
            pass

        filename = os.path.basename(urlparse(url).path) or "update_package.bin"
        target_path = self.cache_dir / filename
        temp_path = self.cache_dir / f"{filename}.part"

        try:
            hasher = hashlib.sha256()
            received = 0
            start_time = time.time()
            last_speed_time = start_time
            last_speed_bytes = 0

            if url.startswith("file://"):
                local_path_str = url2pathname(urlparse(url).path)
                source_p = Path(local_path_str)
                total_len = source_p.stat().st_size
                with self.lock:
                    self.download_total_bytes = total_len
                chunk_size = 64 * 1024
                with open(source_p, "rb") as f_in, open(temp_path, "wb") as f_out:
                    while True:
                        if self._cancel_requested:
                            break
                        chunk = f_in.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        hasher.update(chunk)
                        received += len(chunk)
                        with self.lock:
                            self.download_bytes_received = received
                            self.download_percent = (received / total_len * 100.0) if total_len > 0 else 100.0
                            self.download_speed_kbps = 50000.0
            else:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": f"{APP_NAME}-AutoUpdater/{CURRENT_VERSION}"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp, open(temp_path, "wb") as f_out:
                    total_len = int(resp.headers.get("Content-Length", expected_size))
                    with self.lock:
                        self.download_total_bytes = total_len

                    chunk_size = 64 * 1024  # 64 KB
                    while True:
                        if self._cancel_requested:
                            break
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f_out.write(chunk)
                        hasher.update(chunk)
                        received += len(chunk)

                        now = time.time()
                        elapsed_speed = now - last_speed_time
                        if elapsed_speed >= 0.5:
                            speed = (received - last_speed_bytes) / elapsed_speed / 1024.0
                            last_speed_time = now
                            last_speed_bytes = received
                            with self.lock:
                                self.download_bytes_received = received
                                self.download_percent = (received / total_len * 100.0) if total_len > 0 else 0.0
                                self.download_speed_kbps = speed

            # Check if canceled during download
            if self._cancel_requested:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                with self.lock:
                    self.state = UpdateState.AVAILABLE
                    self.download_active = False
                    self._cancel_requested = False
                    self.download_bytes_received = 0
                    self.download_percent = 0.0
                    self.download_speed_kbps = 0.0
                    self.error_message = None
                return

            # Complete file verification
            calc_sha256 = hasher.hexdigest().lower()
            if expected_sha256 and calc_sha256 != expected_sha256:
                if temp_path.exists():
                    temp_path.unlink()
                with self.lock:
                    self.state = UpdateState.ERROR
                    self.download_active = False
                    self.error_message = f"Checksum mismatch! Expected {expected_sha256}, got {calc_sha256}."
                return

            # Atomic rename to final path
            if target_path.exists():
                target_path.unlink()
            temp_path.rename(target_path)

            with self.lock:
                self.downloaded_package_path = target_path
                self.download_bytes_received = received
                self.download_percent = 100.0
                self.download_active = False
                if self.selected_package_type == "patch":
                    self.state = UpdateState.DOWNLOADED
                else:
                    self.state = UpdateState.INSTALLER_READY

        except Exception as e:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            with self.lock:
                self.state = UpdateState.ERROR
                self.download_active = False
                self.error_message = f"Download interrupted or failed: {str(e)}"

    def cancel_download(self) -> Dict[str, Any]:
        """
        Safely signals an active download worker to cancel, clean up temporary files,
        and revert updater state back to AVAILABLE.
        """
        with self.lock:
            if self.state == UpdateState.DOWNLOADING and self.download_active:
                self._cancel_requested = True
        return self.get_status()

    def launch_installer(self) -> bool:
        """
        Launches the downloaded full installer package executable.
        """
        with self.lock:
            pkg_path = self.downloaded_package_path
            if not pkg_path or not Path(pkg_path).exists():
                self.error_message = "No installer package available to launch."
                return False
            installer_target = str(pkg_path)

        try:
            subprocess.Popen(
                [installer_target],
                cwd=str(self.app_root),
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
            return True
        except Exception as e:
            with self.lock:
                self.error_message = f"Failed to launch installer: {e}"
            return False

    def apply_patch_update(self) -> Dict[str, Any]:
        """
        Safely unpack and install a lightweight patch update.
        Implements atomic file replacement, automated backups, and instant rollback on failure.
        """
        with self.lock:
            if self.state != UpdateState.DOWNLOADED or not self.downloaded_package_path:
                return self.get_status()
            if self.selected_package_type != "patch":
                return self.get_status()
            self.state = UpdateState.APPLYING
            self.error_message = None

        try:
            zip_path = self.downloaded_package_path
            shutil.rmtree(self.stage_dir, ignore_errors=True)
            self.stage_dir.mkdir(parents=True, exist_ok=True)

            # 1. Unpack only safe verified members into staging
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    target_member_path = member.filename
                    norm_path = os.path.normpath(target_member_path)
                    # Security check: Block directory traversal attempts
                    if norm_path.startswith("..") or os.path.isabs(norm_path) or ".." in Path(norm_path).parts:
                        continue
                    # Security check: Never overwrite user projects or local credentials
                    parts = [p.lower() for p in Path(norm_path).parts]
                    if any(p in ("projects", ".env", "credentials.json") for p in parts):
                        continue
                    zf.extract(member, self.stage_dir)

            # 2. Create backup of current files that will be overwritten
            shutil.rmtree(self.backup_dir, ignore_errors=True)
            self.backup_dir.mkdir(parents=True, exist_ok=True)

            staged_files: List[Tuple[Path, Path, Path]] = []
            for root, _, files in os.walk(self.stage_dir):
                for f in files:
                    s_file = Path(root) / f
                    rel_p = s_file.relative_to(self.stage_dir)
                    parts = [p.lower() for p in rel_p.parts]
                    if any(p in ("projects", ".env", "credentials.json") for p in parts):
                        continue
                    dest_file = self.app_root / rel_p
                    backup_file = self.backup_dir / rel_p
                    staged_files.append((s_file, dest_file, backup_file))

            # Copy existing target files to backup
            for _, dest_file, backup_file in staged_files:
                if dest_file.exists():
                    backup_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dest_file, backup_file)

            # 3. Apply staged files into application root
            applied_files: List[Path] = []
            try:
                for s_file, dest_file, _ in staged_files:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(s_file, dest_file)
                    applied_files.append(dest_file)
            except Exception as copy_err:
                # ROLLBACK: Restore backups
                print(f"[UPDATER] Error applying patch: {copy_err}. Initiating automatic rollback...")
                for _, dest_file, backup_file in staged_files:
                    if backup_file.exists():
                        shutil.copy2(backup_file, dest_file)
                raise RuntimeError(f"Patch application failed, rolled back cleanly: {copy_err}")

            with self.lock:
                self.state = UpdateState.READY_TO_RESTART
                # Update current active memory version if version file was updated
                new_v = self.manifest_data.get("latest_version")
                if new_v:
                    self.current_version = new_v
            st = self.get_status()
            st["ok"] = True
            st["success"] = True
            st["message"] = "Patch applied successfully. Restart required."
            return st

        except Exception as e:
            with self.lock:
                self.state = UpdateState.ERROR
                self.error_message = f"Patch installation error: {str(e)}"
            st = self.get_status()
            st["ok"] = False
            st["success"] = False
            st["message"] = self.error_message
            st["error"] = self.error_message
            st["error_message"] = self.error_message
            return st

    def restart_application(self, spawn: bool = True) -> bool:
        """
        Triggers a clean application restart.
        Spawns detached launcher helper and terminates current process gracefully.
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
                    target_args = 'web\\server.py'

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

# 1. Wait for old process to exit
if ($targetPid -gt 0) {{
    $waitCount = 0
    while ((Get-Process -Id $targetPid -ErrorAction SilentlyContinue) -and ($waitCount -lt 20)) {{
        Start-Sleep -Milliseconds 500
        $waitCount++
    }}
    if (Get-Process -Id $targetPid -ErrorAction SilentlyContinue) {{
        Write-Log "Old process PID $targetPid did not exit within 10 seconds. Forcing termination..."
        Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 1000
    }} else {{
        Write-Log "Old process PID $targetPid exited cleanly."
    }}
}}

# 2. Port release buffer
Start-Sleep -Milliseconds 1200
Set-Location -Path $workDir

# 3. Launch updated application
try {{
    if ($targetArgs.Length -gt 0) {{
        Write-Log "Starting process: $targetExe with args: $targetArgs in $workDir"
        $proc = Start-Process -FilePath $targetExe -ArgumentList $targetArgs -WorkingDirectory $workDir -PassThru
    }} else {{
        Write-Log "Starting process: $targetExe (no args) in $workDir"
        $proc = Start-Process -FilePath $targetExe -WorkingDirectory $workDir -PassThru
    }}
    if ($proc) {{
        Write-Log "Successfully spawned updated process PID: $($proc.Id)"
    }} else {{
        Write-Log "Start-Process returned null process object."
    }}
}} catch {{
    Write-Log "ERROR spawning new process: $($_.Exception.Message)"
}}
"""
            restart_ps1.write_text(script_content, encoding="utf-8")

            if spawn:
                # Spawn detached powershell process
                subprocess.Popen(
                    ["powershell.exe", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(restart_ps1)],
                    cwd=str(self.app_root),
                    creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
            return True
        except Exception as e:
            logger.error("Failed to launch restart helper: %s", e)
            self.error_message = f"Restart failed: {e}"
            return False

    def _verify_checksum(self, filepath: Path, expected_sha256: str) -> bool:
        """Utility to verify file matches expected SHA-256."""
        sha = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    sha.update(chunk)
            return sha.hexdigest().lower() == expected_sha256.lower()
        except Exception:
            return False

    def _safe_extract(self, zip_path: Path, target_dir: Path):
        """Safely extract zip archive with path traversal and user-project protections."""
        target_dir = Path(target_dir).resolve()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.infolist():
                norm_name = os.path.normpath(member.filename)
                # Block path traversal attempts
                if norm_name.startswith("..") or os.path.isabs(norm_name) or ".." in Path(norm_name).parts:
                    continue
                # Block protected user files and credentials
                parts = [p.lower() for p in Path(norm_name).parts]
                if any(p in ("projects", ".env", "credentials.json") for p in parts):
                    continue
                dest_file = target_dir / norm_name
                if member.is_dir():
                    dest_file.mkdir(parents=True, exist_ok=True)
                else:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

    def _create_backup(self) -> Path:
        """Create a backup of current modifiable directories (engine, web, config)."""
        backup_path = self.cache_dir / f"backup_{int(time.time())}"
        backup_path.mkdir(parents=True, exist_ok=True)
        for d in ("engine", "web", "config"):
            src_d = self.app_root / d
            if src_d.exists() and src_d.is_dir():
                shutil.copytree(src_d, backup_path / d, dirs_exist_ok=True)
        return backup_path

    def _rollback_from_backup(self, backup_dir: Path):
        """Restore files from backup directory."""
        if not backup_dir.exists():
            return
        for root, _, files in os.walk(backup_dir):
            for f in files:
                b_file = Path(root) / f
                rel_p = b_file.relative_to(backup_dir)
                dest_file = self.app_root / rel_p
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(b_file, dest_file)

    # API aliases
    download_update = start_download
    apply_patch = apply_patch_update
    restart_app = restart_application
    _is_trusted_url = validate_url_security
    cancel = cancel_download
    install_full = launch_installer

ALLOWED_DOWNLOAD_DOMAINS = ALLOWED_DOMAINS

# Global Singleton
update_manager = UpdateManager()

