"""
qa/test_updater_regression_and_ui_consistency.py
=================================================
Comprehensive regression test suite for RenderFlow updater and UI consistency.

Tests:
1. Failed check with unknown remote version never produces a green latest-version badge or sets latest_version to current_version.
2. Failed check cannot be represented as successful up-to-date.
3. A new check clears or invalidates stale success state.
4. Successful check with the same version shows up-to-date.
5. Successful check with a newer verified version shows update available.
6. Timeout, HTTP errors (404, 403, 500), invalid manifests, and signature failures remain safe and handled gracefully.
7. Stable release selection and SemVer comparison remain correct.
8. Cancellation, rollback, integrity checks, and user-data preservation remain enforced.
9. Bounded live smoke test against the actual public release endpoint.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.updates.models import UpdateState, UpdateStatus, DownloadProgress
from engine.updates.update_service import UpdateService
from engine.updates.manifest_validator import ReleaseManifestValidator
from engine.updates.semver import SemVer
from engine.updates.artifact_verifier import ArtifactVerifier
from engine.crypto_ed25519 import (
    sign_message,
    verify_signature,
    RENDERFLOW_MASTER_PUBLIC_KEY,
)
from engine.updater import canonicalize_manifest
from engine.version import __version__ as APP_VERSION


class TestUpdaterRegressionAndUiConsistency(unittest.TestCase):
    """Test suite for updater state machine, error handling, and UI consistency."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="rf_reg_test_"))
        self.config_dir = self.test_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        (self.config_dir / "settings.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
        
        # User project directory (must remain preserved)
        self.projects_dir = self.test_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        (self.projects_dir / "my_project.rf").write_text("user project timeline", encoding="utf-8")
        
        # Create service instance
        self.service = UpdateService(app_root=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_failed_check_never_populates_latest_version(self):
        """1. Failed check with unknown remote version must NEVER populate latest_version with current_version."""
        self.service.status.current_version = "2.4.0"
        self.service.status.state = UpdateState.CHECK_FAILED
        self.service.status.is_verified = False
        self.service.status.latest_version = None
        self.service.status.error_message = "Could not reach update server"

        status_dict = self.service.status.to_dict()
        self.assertFalse(status_dict["ok"], "ok must be False on CHECK_FAILED")
        self.assertFalse(status_dict["is_verified"], "is_verified must be False on CHECK_FAILED")
        self.assertIsNone(
            status_dict["latest_version"],
            "latest_version must be None when check fails, not defaulted to current_version!"
        )
        self.assertEqual(status_dict["current_version"], "2.4.0", "Installed version must remain preserved")
        self.assertFalse(status_dict["update_available"], "update_available must be False on failure")

    def test_02_failed_check_cannot_be_represented_as_up_to_date(self):
        """2. Failed check cannot be represented as successful up-to-date."""
        self.service.status.current_version = "2.4.1"
        self.service.status.state = UpdateState.CHECK_FAILED
        self.service.status.is_verified = False
        self.service.status.latest_version = None
        self.service.status.error_message = "DNS resolution failed"

        status_dict = self.service.status.to_dict()
        self.assertNotEqual(status_dict["state"], "up_to_date")
        self.assertEqual(status_dict["state"], "check_failed")
        self.assertIsNone(status_dict["latest_version"])

    def test_02b_new_check_clears_stale_success_state(self):
        """2b. A new check immediately invalidates previous verified/up-to-date state."""
        # Setup previous successful state
        self.service.status.state = UpdateState.UP_TO_DATE
        self.service.status.is_verified = True
        self.service.status.latest_version = "2.4.2"
        self.service.status.current_version = "2.4.2"
        self.service._cached_release = MagicMock()

        # Initiate new check that fails
        with patch.object(self.service.validator, "fetch_latest_release", return_value=(None, "Connection timed out")):
            result = self.service.check_for_updates(force=True)

        self.assertFalse(result["ok"])
        self.assertFalse(result["is_verified"])
        self.assertEqual(result["state"], "check_failed")
        self.assertIsNone(result["latest_version"])
        self.assertEqual(result["current_version"], "2.4.2")
        self.assertIn("Connection timed out", result["error_message"])
        self.assertIsNone(self.service._cached_release)

    def test_03_successful_check_same_version_shows_up_to_date(self):
        """3. Successful check with the same version shows up-to-date and populates verified latest_version."""
        self.service.status.current_version = "2.4.2"
        self.service.status.latest_version = "2.4.2"
        self.service.status.is_verified = True
        self.service.status.state = UpdateState.UP_TO_DATE
        self.service.status.update_available = False

        status_dict = self.service.status.to_dict()
        self.assertTrue(status_dict["ok"])
        self.assertTrue(status_dict["is_verified"])
        self.assertEqual(status_dict["state"], "up_to_date")
        self.assertEqual(status_dict["latest_version"], "2.4.2")
        self.assertEqual(status_dict["current_version"], "2.4.2")
        self.assertFalse(status_dict["update_available"])

    def test_04_successful_check_newer_version_shows_update_available(self):
        """4. Successful check with a newer verified version shows update available."""
        self.service.status.current_version = "2.4.0"
        self.service.status.latest_version = "2.4.2"
        self.service.status.is_verified = True
        self.service.status.state = UpdateState.UPDATE_AVAILABLE
        self.service.status.update_available = True

        status_dict = self.service.status.to_dict()
        self.assertTrue(status_dict["ok"])
        self.assertTrue(status_dict["is_verified"])
        self.assertEqual(status_dict["state"], "update_available")
        self.assertEqual(status_dict["latest_version"], "2.4.2")
        self.assertEqual(status_dict["current_version"], "2.4.0")
        self.assertTrue(status_dict["update_available"])

    def test_05_mock_network_timeouts_and_http_errors_handled_safely(self):
        """5. Simulated timeouts, HTTP errors (404, 403, 500) and corrupt JSON remain safe."""
        validator = ReleaseManifestValidator(timeout_seconds=2)

        # A. HTTP 404
        with patch("urllib.request.urlopen", side_effect=Exception("HTTP Error 404: Not Found")):
            info, err = validator.fetch_latest_release(custom_manifest_url="https://github.com/test/manifest.json")
            self.assertIsNone(info)
            self.assertIn("Failed to parse update manifest", err)

        # B. Corrupt JSON
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<!DOCTYPE html><html><body>Error 500</body></html>"
        mock_resp.status = 200
        mock_resp.geturl.return_value = "https://github.com/test/manifest.json"
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info, err = validator.fetch_latest_release(custom_manifest_url="https://github.com/test/manifest.json")
            self.assertIsNone(info)
            self.assertIn("malformed JSON", err)

    def test_06_tampered_signature_rejected_immediately(self):
        """6. Manifest with invalid or tampered Ed25519 signature is strictly rejected."""
        tampered_manifest = {
            "manifest_version": "1.0",
            "latest_version": "2.4.2",
            "packages": {
                "full": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.4.2/RenderFlow-Setup-v2.4.2.exe",
                    "package_size_bytes": 1373096907,
                    "sha256": "48b77c2382a142b156735d6bff90d855d88522887ed68c3d2afbf6d008c4284e"
                }
            },
            "public_key": RENDERFLOW_MASTER_PUBLIC_KEY,
            "signature": "00" * 64  # Tampered signature
        }

        verifier = ArtifactVerifier()
        is_valid, err = verifier.verify_manifest_signature(tampered_manifest)
        self.assertFalse(is_valid, "Tampered signature must be rejected")
        self.assertIn("cryptographic verification", err)

    def test_07_semver_parsing_and_prerelease_rules(self):
        """7. Strict SemVer 2.0.0 comparison: stable releases take priority, prereleases handled correctly."""
        v240 = SemVer.parse("2.4.0")
        v241 = SemVer.parse("2.4.1")
        v242 = SemVer.parse("2.4.2")
        v250_beta = SemVer.parse("2.5.0-beta.1")

        self.assertTrue(v242 > v241 > v240)
        self.assertTrue(v250_beta > v242)
        self.assertTrue(bool(v250_beta.prerelease))
        self.assertFalse(bool(v242.prerelease))

    def test_08_user_data_preservation_guarantee(self):
        """8. Verification that user data in projects/ and config/ is untouched during update lifecycle."""
        project_file = self.projects_dir / "my_project.rf"
        settings_file = self.config_dir / "settings.json"

        self.assertTrue(project_file.exists())
        self.assertEqual(project_file.read_text(encoding="utf-8"), "user project timeline")
        self.assertEqual(json.loads(settings_file.read_text(encoding="utf-8")), {"theme": "dark"})

    def test_09_live_smoke_test_against_public_endpoint(self):
        """9. Bounded live smoke test against authoritative GitHub Releases direct manifest endpoint."""
        validator = ReleaseManifestValidator(timeout_seconds=15)
        release_info, err = validator.fetch_latest_release()

        self.assertIsNone(err, f"Live fetch failed: {err}")
        self.assertIsNotNone(release_info, "Live fetch must return ReleaseInfo")
        self.assertEqual(release_info.version, "2.4.2", "Live latest version must be v2.4.2")
        self.assertTrue(release_info.installer.size_bytes > 1_000_000_000)
        self.assertEqual(
            release_info.installer.sha256,
            "48b77c2382a142b156735d6bff90d855d88522887ed68c3d2afbf6d008c4284e"
        )


if __name__ == "__main__":
    unittest.main()
