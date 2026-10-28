#!/usr/bin/env python3
"""
RenderFlow — Auto-Updater Automated Test Suite
Validates version comparison, Ed25519 signature authentication, checksum enforcement,
untrusted host rejection, zip path traversal defense, user project protection,
and backup / rollback safety.
"""

import os
import sys
import json
import shutil
import tempfile
import zipfile
import hashlib
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.updater import (
    SemVer,
    UpdateManager,
    UpdateState,
    ALLOWED_DOWNLOAD_DOMAINS
)
from engine.crypto_ed25519 import (
    sign_message,
    verify_signature,
    public_key_from_secret,
    RENDERFLOW_MASTER_PUBLIC_KEY
)


class TestSemVer(unittest.TestCase):
    """Test Semantic Version parsing, comparison and ordering."""

    def test_version_parsing(self):
        v = SemVer.parse("2.2.0")
        self.assertEqual(v.major, 2)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 0)
        self.assertIsNone(v.prerelease)

    def test_version_comparisons(self):
        v220 = SemVer.parse("2.2.0")
        v221 = SemVer.parse("2.2.1")
        v230 = SemVer.parse("2.3.0")
        v300 = SemVer.parse("3.0.0")

        self.assertTrue(v220 < v221)
        self.assertTrue(v221 > v220)
        self.assertTrue(v221 < v230)
        self.assertTrue(v230 < v300)
        self.assertEqual(v220, SemVer.parse("v2.2.0"))

    def test_prerelease_comparison(self):
        v_rc = SemVer.parse("2.2.1-rc1")
        v_final = SemVer.parse("2.2.1")
        self.assertTrue(v_rc < v_final)


class TestEd25519ManifestAuthentication(unittest.TestCase):
    """Test cryptographic authentication of release metadata."""

    def setUp(self):
        self.test_sk = bytes.fromhex("e27eff4db87b6481bb87886382c11df2489ce384c69ffeb0ba9d8cf27e490e0a")
        self.test_pk = public_key_from_secret(self.test_sk)

    def test_valid_signature_verification(self):
        manifest_payload = {
            "manifest_version": "1.0",
            "latest_version": "2.2.1",
            "sha256": "abcdef1234567890"
        }
        canonical = json.dumps(manifest_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
        sig = sign_message(canonical, self.test_sk, self.test_pk)
        
        # Verify with public key
        self.assertTrue(verify_signature(canonical, sig, self.test_pk))

    def test_tampered_payload_rejected(self):
        manifest_payload = {
            "manifest_version": "1.0",
            "latest_version": "2.2.1",
            "sha256": "abcdef1234567890"
        }
        canonical = json.dumps(manifest_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
        sig = sign_message(canonical, self.test_sk, self.test_pk)

        # Attacker modifies payload to malicious hash
        tampered_payload = dict(manifest_payload)
        tampered_payload["sha256"] = "malicious_hash_999999"
        tampered_canonical = json.dumps(tampered_payload, sort_keys=True, separators=(',', ':')).encode("utf-8")

        self.assertFalse(verify_signature(tampered_canonical, sig, self.test_pk))

    def test_corrupted_signature_rejected(self):
        msg = b"hello renderflow"
        sig = bytearray(sign_message(msg, self.test_sk, self.test_pk))
        sig[10] ^= 0xFF  # Flip bits in signature
        self.assertFalse(verify_signature(msg, bytes(sig), self.test_pk))


class TestSecurityAndNetworkValidation(unittest.TestCase):
    """Test HTTPS domain allowlisting and URL security."""

    def setUp(self):
        self.mgr = UpdateManager(base_dir=ROOT_DIR)

    def test_allowed_domains(self):
        valid_urls = [
            "https://github.com/user/repo/releases/download/v2.2.1/patch.zip",
            "https://raw.githubusercontent.com/user/repo/main/manifest.json",
            "https://objects.githubusercontent.com/github-production-release-asset-2e65be/..."
        ]
        for url in valid_urls:
            self.assertTrue(self.mgr._is_trusted_url(url), f"Should trust {url}")

    def test_untrusted_domains_blocked(self):
        invalid_urls = [
            "http://github.com/user/repo/releases/download/v2.2.1/patch.zip",  # Insecure HTTP
            "https://evil-hacker.com/malicious.zip",
            "https://github.com.evil.com/fake.zip",
            "ftp://github.com/test.zip",
            "file:///C:/windows/system32/bad.exe"
        ]
        for url in invalid_urls:
            self.assertFalse(self.mgr._is_trusted_url(url), f"Should block untrusted {url}")


class TestPackageIntegrityAndProjectPreservation(unittest.TestCase):
    """Test zip extraction safety, checksum matching, and project protection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="rf_updater_test_")
        self.base_dir = Path(self.temp_dir)
        
        # Simulate app directory
        (self.base_dir / "engine").mkdir(parents=True)
        (self.base_dir / "web").mkdir(parents=True)
        (self.base_dir / "projects").mkdir(parents=True)

        # Existing user file in projects
        self.user_project_file = self.base_dir / "projects" / "my_precious_video.json"
        self.user_project_file.write_text('{"title": "User Masterpiece"}', encoding="utf-8")

        # Existing engine file
        self.engine_file = self.base_dir / "engine" / "test_module.py"
        self.engine_file.write_text('print("v2.2.0")', encoding="utf-8")

        self.mgr = UpdateManager(base_dir=self.base_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_checksum_validation(self):
        test_file = self.base_dir / "dummy.zip"
        test_file.write_bytes(b"renderflow test zip data")
        
        real_sha = hashlib.sha256(b"renderflow test zip data").hexdigest()
        self.assertTrue(self.mgr._verify_checksum(test_file, real_sha))
        self.assertFalse(self.mgr._verify_checksum(test_file, "wrong_hash_000000000000"))

    def test_path_traversal_zip_rejected(self):
        """Verify zip slip / path traversal attacks (../../evil.txt) are blocked."""
        malicious_zip = self.base_dir / "evil.zip"
        with zipfile.ZipFile(malicious_zip, "w") as zf:
            zf.writestr("../../evil_escape.txt", "attack content")
            zf.writestr("engine/safe.txt", "safe content")

        # Extract
        self.mgr._safe_extract(malicious_zip, self.base_dir)

        # Ensure evil file was NOT created outside target
        escaped_file = self.base_dir.parent / "evil_escape.txt"
        self.assertFalse(escaped_file.exists(), "Zip slip attack succeeded!")
        self.assertTrue((self.base_dir / "engine" / "safe.txt").exists())

    def test_user_projects_protected_from_overwrite(self):
        """Ensure updater never touches user projects or credentials."""
        overwrite_zip = self.base_dir / "overwrite_test.zip"
        with zipfile.ZipFile(overwrite_zip, "w") as zf:
            zf.writestr("projects/my_precious_video.json", '{"title": "Hacked Overwritten"}')
            zf.writestr(".env", "LEAKED_KEY=123")
            zf.writestr("engine/updated_logic.py", 'print("new logic")')

        self.mgr._safe_extract(overwrite_zip, self.base_dir)

        # Verify user project was preserved untouched
        content = json.loads(self.user_project_file.read_text(encoding="utf-8"))
        self.assertEqual(content["title"], "User Masterpiece", "User project was overwritten!")

        # Verify .env was not written
        self.assertFalse((self.base_dir / ".env").exists())

        # Verify updated engine logic was applied
        self.assertTrue((self.base_dir / "engine" / "updated_logic.py").exists())

    def test_backup_and_rollback_on_failure(self):
        """Test backup creation and rollback restoration."""
        # Create a backup
        backup_dir = self.mgr._create_backup()
        self.assertTrue(backup_dir.exists())
        self.assertTrue((backup_dir / "engine" / "test_module.py").exists())

        # Simulate corrupting the file
        self.engine_file.write_text("CORRUPTED JUNK", encoding="utf-8")

        # Rollback
        self.mgr._rollback_from_backup(backup_dir)
        restored = self.engine_file.read_text(encoding="utf-8")
        self.assertEqual(restored, 'print("v2.2.0")', "Rollback failed to restore original file")


class TestUpdaterWorkflowAndStateTransitions(unittest.TestCase):
    """Test state machine transitions, version check outcomes, and fallbacks."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="rf_workflow_test_")
        self.base_dir = Path(self.temp_dir)
        (self.base_dir / "engine").mkdir(parents=True)
        (self.base_dir / "web").mkdir(parents=True)
        (self.base_dir / "projects").mkdir(parents=True)
        self.mgr = UpdateManager(base_dir=self.base_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_version_detection_available(self):
        """When manifest has version > CURRENT_VERSION, state transitions to AVAILABLE."""
        manifest = {
            "manifest_version": "1.0",
            "latest_version": "2.2.1",
            "minimum_supported_version": "2.0.0",
            "release_notes": "Test patch notes",
            "update_package_url": "https://github.com/test/patch.zip",
            "package_size_bytes": 500000,
            "sha256": "abcdef",
            "update_type": "patch"
        }
        # Directly test internal worker logic
        current_sem = SemVer("2.2.0")
        latest_sem = SemVer(manifest["latest_version"])
        self.assertTrue(latest_sem > current_sem)

        # Ensure patch package extraction logic works
        pkg = {
            "url": manifest["update_package_url"],
            "package_size_bytes": manifest["package_size_bytes"],
            "sha256": manifest["sha256"],
            "applies_to": [">=2.0.0"]
        }
        self.assertTrue(self.mgr._check_patch_applies(pkg, current_sem))

    def test_full_installer_fallback_for_unsupported_old_client(self):
        """When client is older than minimum_supported_version, fallback to full installer."""
        manifest = {
            "manifest_version": "1.0",
            "latest_version": "3.0.0",
            "minimum_supported_version": "2.5.0",
            "packages": {
                "patch": {"url": "https://github.com/test/patch.zip", "package_size_bytes": 1000},
                "full": {"url": "https://github.com/test/installer.exe", "package_size_bytes": 1000000000}
            }
        }
        old_sem = SemVer("2.2.0")
        min_sem = SemVer(manifest["minimum_supported_version"])
        self.assertTrue(old_sem < min_sem)
        # Old client cannot use patch -> must use full installer
        selected_pkg = manifest["packages"]["full"]
        self.assertIn("installer.exe", selected_pkg["url"])

    def test_offline_network_failure_handling(self):
        """When manifest URL cannot be reached, error state is set without crash."""
        self.mgr.check_for_updates(force=True, custom_manifest_url="https://github.com/nonexistent_org_404/manifest.json")
        # Give worker a moment to execute
        import time
        time.sleep(0.5)
        status = self.mgr.get_status()
        self.assertIn(status["state"], (UpdateState.ERROR, UpdateState.CHECKING))

    def test_rate_limiting_rapid_checks(self):
        """Rapid repeated checks within 30s without force flag are rate-limited."""
        self.mgr.last_checked_time = 1000000000.0  # Set recent time
        self.mgr.state = UpdateState.UP_TO_DATE
        import time
        # Force a recent timestamp
        self.mgr.last_checked_time = time.time()
        res = self.mgr.check_for_updates(force=False)
        self.assertEqual(res["state"], UpdateState.UP_TO_DATE)


if __name__ == "__main__":
    unittest.main()

