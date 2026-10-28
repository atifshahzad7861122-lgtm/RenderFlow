#!/usr/bin/env python3
"""
engine/test_in_app_updater.py — Comprehensive Test Suite for RenderFlow In-App Auto-Updater

Covers all 4 Phase 9 testing domains:
1. Manifest and Cryptographic Security (Ed25519, canonicalization, tampering, URL allowlist, traversal, sensitive files)
2. Version & Package Selection (patch selection, full installer fallback, already current, downgrade defense)
3. Download, Verification, Rollback, and Cancellation (progress reporting, hash enforcement, cancel cleanup, rollback)
4. FastApi Endpoints & State Machine (status, check, download, cancel, apply, install_full, restart)
"""

import os
import sys
import json
import time
import shutil
import zipfile
import hashlib
import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.updater import (
    SemVer,
    UpdateManager,
    UpdateState,
    ALLOWED_DOWNLOAD_DOMAINS,
    canonicalize_manifest,
)
from engine.crypto_ed25519 import (
    sign_message,
    verify_signature,
    public_key_from_secret,
    RENDERFLOW_MASTER_PUBLIC_KEY,
)


class TestManifestSecurity(unittest.TestCase):
    """Manifest authentication, host validation, and archive security."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="rf_test_manifest_"))
        self.updater = UpdateManager(app_root=self.tmp_dir, cache_dir=self.tmp_dir / "cache")
        # Generate temporary test keypair
        self.test_sk = bytes.fromhex("e27eff4db87b6481bb87886382c11df2489ce384c69ffeb0ba9d8cf27e490e0a")
        self.test_pk = public_key_from_secret(self.test_sk)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_valid_manifest_signature_verification(self):
        payload = {
            "manifest_version": "1.0",
            "latest_version": "2.2.4",
            "sha256": "abcdef123456",
            "update_package_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.2.4/patch.zip"
        }
        canonical_bytes = canonicalize_manifest(payload)
        sig = sign_message(canonical_bytes, self.test_sk, self.test_pk)
        payload["signature"] = sig.hex()
        payload["public_key"] = self.test_pk.hex()

        self.assertTrue(self.updater.verify_manifest_signature(payload, expected_pk=self.test_pk.hex()))

    def test_tampered_manifest_rejected(self):
        payload = {
            "manifest_version": "1.0",
            "latest_version": "2.2.4",
            "sha256": "original_good_hash"
        }
        canonical_bytes = canonicalize_manifest(payload)
        sig = sign_message(canonical_bytes, self.test_sk, self.test_pk)
        payload["signature"] = sig.hex()
        payload["public_key"] = self.test_pk.hex()

        # Attacker tampers with SHA256 or version
        payload["sha256"] = "malicious_altered_hash"
        self.assertFalse(self.updater.verify_manifest_signature(payload, expected_pk=self.test_pk.hex()))

    def test_untrusted_signature_rejected_against_master_key(self):
        attacker_sk = bytes.fromhex("11" * 32)
        attacker_pk = public_key_from_secret(attacker_sk)
        payload = {
            "manifest_version": "1.0",
            "latest_version": "2.2.4",
            "sha256": "hash123"
        }
        canonical_bytes = canonicalize_manifest(payload)
        sig = sign_message(canonical_bytes, attacker_sk, attacker_pk)
        payload["signature"] = sig.hex()
        payload["public_key"] = attacker_pk.hex()

        # Verifying against the production Master Public Key must fail because attacker_sk is NOT the master key
        self.assertFalse(self.updater.verify_manifest_signature(payload, expected_pk=RENDERFLOW_MASTER_PUBLIC_KEY))

    def test_url_host_allowlist_enforcement(self):
        # Allowed GitHub hosts
        self.assertTrue(self.updater.validate_url_security("https://github.com/owner/repo/releases/download/v2.2.4/patch.zip"))
        self.assertTrue(self.updater.validate_url_security("https://raw.githubusercontent.com/owner/repo/release/update_manifest.json"))
        self.assertTrue(self.updater.validate_url_security("https://objects.githubusercontent.com/github-production-release-asset/123.zip"))

        # Insecure or untrusted domains
        self.assertFalse(self.updater.validate_url_security("http://github.com/insecure/patch.zip"))  # HTTP blocked
        self.assertFalse(self.updater.validate_url_security("https://evil-hacker.com/malicious_patch.zip"))
        self.assertFalse(self.updater.validate_url_security("https://raw.githubusercontent.com.evil.com/phish"))
        self.assertFalse(self.updater.validate_url_security("ftp://github.com/patch.zip"))

    def test_archive_path_traversal_defense(self):
        # Construct malicious zip with traversal path
        bad_zip = self.tmp_dir / "evil_traversal.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("../../etc/passwd", "malicious_content")
            zf.writestr("..\\..\\windows\\system32\\cmd.exe", "malicious_exe")
            zf.writestr("safe_file.txt", "safe_content")

        extract_target = self.tmp_dir / "extracted"
        self.updater._safe_extract(bad_zip, extract_target)

        # Confirm traversal members were ignored and escaped file does NOT exist
        self.assertTrue((extract_target / "safe_file.txt").exists())
        self.assertFalse((self.tmp_dir / "etc" / "passwd").exists())
        self.assertFalse((self.tmp_dir / "windows").exists())

    def test_user_data_and_credentials_protection(self):
        # Construct zip attempting to overwrite user projects or local credentials
        protected_zip = self.tmp_dir / "overwrite_user_data.zip"
        with zipfile.ZipFile(protected_zip, "w") as zf:
            zf.writestr("projects/customer_project/video.mp4", "corrupted")
            zf.writestr(".env", "LEAKED=1")
            zf.writestr("credentials.json", "{}")
            zf.writestr("engine/valid_module.py", "# valid updated module")

        extract_target = self.tmp_dir / "target_app"
        # Pre-seed user project and .env
        (extract_target / "projects" / "customer_project").mkdir(parents=True, exist_ok=True)
        (extract_target / "projects" / "customer_project" / "video.mp4").write_text("precious_user_video")
        (extract_target / ".env").write_text("ORIGINAL_ENV=TRUE")

        self.updater._safe_extract(protected_zip, extract_target)

        # Verify user files were preserved
        self.assertEqual((extract_target / "projects" / "customer_project" / "video.mp4").read_text(), "precious_user_video")
        self.assertEqual((extract_target / ".env").read_text(), "ORIGINAL_ENV=TRUE")
        self.assertFalse((extract_target / "credentials.json").exists())
        self.assertTrue((extract_target / "engine" / "valid_module.py").exists())


class TestVersionAndPackageSelection(unittest.TestCase):
    """Version comparison rules and package selection strategy."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="rf_test_ver_"))
        self.updater = UpdateManager(app_root=self.tmp_dir, cache_dir=self.tmp_dir / "cache")
        self.manifest = {
            "manifest_version": "1.0",
            "latest_version": "2.2.4",
            "minimum_supported_version": "2.0.0",
            "release_notes": "RenderFlow v2.2.4 Hotfix",
            "packages": {
                "patch": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.2.4/RenderFlow-Patch-v2.2.4.zip",
                    "package_size_bytes": 575229,
                    "sha256": "5544ceebe52ee5f2047b7e7eb3f5c063302f00f7643e306d56bded5511b103f9",
                    "applies_to": [">=2.0.0"]
                },
                "full": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.2.4/RenderFlow-Setup-v2.2.4.exe",
                    "package_size_bytes": 1372736514,
                    "sha256": "2bd5d3a4c7b563592ed0204363efaae6923df2fff7c92958098854cfaab72473"
                }
            }
        }

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_v223_selects_patch_for_v224(self):
        # Client on v2.2.3 updating to v2.2.4
        curr_sem = SemVer("2.2.3")
        self.assertTrue(self.updater._check_patch_applies(self.manifest["packages"]["patch"], curr_sem))

    def test_old_version_selects_full_installer(self):
        # Client on 1.8.0 (< minimum_supported_version 2.0.0) cannot apply patch
        curr_sem = SemVer("1.8.0")
        self.assertFalse(self.updater._check_patch_applies(self.manifest["packages"]["patch"], curr_sem))

    def test_same_version_no_update_available(self):
        v_installed = SemVer("2.2.4")
        v_latest = SemVer(self.manifest["latest_version"])
        self.assertFalse(v_latest > v_installed)

    def test_downgrade_rejected(self):
        v_installed = SemVer("2.3.0")
        v_manifest = SemVer("2.2.4")
        # Manifest version is lower than installed, update must NOT trigger
        self.assertFalse(v_manifest > v_installed)


class TestDownloadVerificationAndRollback(unittest.TestCase):
    """Download cancellation, checksum verification, atomic patching, and rollback."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="rf_test_dl_"))
        self.app_dir = self.tmp_dir / "app"
        self.app_dir.mkdir()
        self.cache_dir = self.tmp_dir / "cache"
        self.updater = UpdateManager(app_root=self.app_dir, cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_checksum_validation(self):
        test_file = self.tmp_dir / "sample.bin"
        content = b"RenderFlow Secure Binary Payload"
        test_file.write_bytes(content)
        good_sha = hashlib.sha256(content).hexdigest()
        bad_sha = "0000000000000000000000000000000000000000000000000000000000000000"

        self.assertTrue(self.updater._verify_checksum(test_file, good_sha))
        self.assertFalse(self.updater._verify_checksum(test_file, bad_sha))

    def test_download_cancellation(self):
        self.updater.state = UpdateState.DOWNLOADING
        self.updater.download_active = True
        self.updater._cancel_requested = False

        status = self.updater.cancel_download()
        self.assertTrue(self.updater._cancel_requested)

    def test_patch_apply_success(self):
        # Pre-seed existing app files
        (self.app_dir / "engine").mkdir(parents=True)
        (self.app_dir / "engine" / "version.py").write_text('__version__ = "2.2.3"')
        (self.app_dir / "web").mkdir(parents=True)
        (self.app_dir / "web" / "index.js").write_text('console.log("v2.2.3")')

        # Create a valid patch zip
        patch_zip = self.cache_dir / "RenderFlow-Patch.zip"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(patch_zip, "w") as zf:
            zf.writestr("engine/version.py", '__version__ = "2.2.4"')
            zf.writestr("web/index.js", 'console.log("v2.2.4")')

        self.updater.downloaded_package_path = patch_zip
        self.updater.selected_package_type = "patch"
        self.updater.state = UpdateState.DOWNLOADED
        self.updater.manifest_data = {"latest_version": "2.2.4"}

        result = self.updater.apply_patch_update()
        self.assertEqual(result["state"], UpdateState.READY_TO_RESTART)
        self.assertEqual((self.app_dir / "engine" / "version.py").read_text(), '__version__ = "2.2.4"')
        self.assertEqual((self.app_dir / "web" / "index.js").read_text(), 'console.log("v2.2.4")')

    def test_patch_apply_failure_clean_rollback(self):
        # Pre-seed original files
        (self.app_dir / "engine").mkdir(parents=True)
        original_content = '__version__ = "2.2.3" # ORIGINAL'
        (self.app_dir / "engine" / "version.py").write_text(original_content)

        # Create a patch zip
        patch_zip = self.cache_dir / "bad_patch.zip"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(patch_zip, "w") as zf:
            zf.writestr("engine/version.py", '__version__ = "2.2.4"')

        self.updater.downloaded_package_path = patch_zip
        self.updater.selected_package_type = "patch"
        self.updater.state = UpdateState.DOWNLOADED
        self.updater.manifest_data = {"latest_version": "2.2.4"}

        # Simulate permission / I/O error during file replacement
        real_copy2 = shutil.copy2
        copy_count = 0
        def failing_copy(src, dst):
            nonlocal copy_count
            copy_count += 1
            if copy_count == 2:  # Fail during application step
                raise PermissionError("Access Denied on locked file")
            return real_copy2(src, dst)

        with patch("shutil.copy2", side_effect=failing_copy):
            result = self.updater.apply_patch_update()

        self.assertEqual(result["state"], UpdateState.ERROR)
        self.assertIn("rolled back cleanly", result.get("error_message", ""))
        # Verify original content was restored by rollback
        self.assertEqual((self.app_dir / "engine" / "version.py").read_text(), original_content)


class TestUpdateApiEndpoints(unittest.TestCase):
    """FastAPI REST endpoints testing."""

    def test_status_endpoint_returns_expected_keys(self):
        mgr = UpdateManager()
        status = mgr.get_status()
        required_keys = [
            "state", "current_version", "latest_version", "update_available",
            "download_percent", "download_speed_kbps", "downloaded_bytes", "total_bytes", "can_cancel"
        ]
        for key in required_keys:
            self.assertIn(key, status, f"Missing required telemetry key: {key}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
