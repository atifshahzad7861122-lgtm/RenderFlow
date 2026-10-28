#!/usr/bin/env python3
"""
RenderFlow — Updater Connectivity, Security & Status Integrity Test Suite
========================================================================
Validates the complete update-check lifecycle:
1. Initial unverified state ('not_checked', is_verified=False, never green)
2. Remotely verified latest version ('verified_latest', is_verified=True, green)
3. Available update detection ('update_available', is_verified=True, cyan)
4. Unreachable server / offline simulation ('check_failed', is_verified=False)
5. HTTP 404 / 500 server error response handling
6. Corrupted / malformed JSON manifest handling
7. Forged / invalid Ed25519 digital signature rejection
8. Network timeout handling
9. Automatic fallback manifest endpoint failover
10. Synchronous FastAPI /api/update/check endpoint response schema
"""

import os
import sys
import json
import time
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from urllib.error import URLError, HTTPError

WORKSPACE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE))

from engine.updater import (
    SemVer,
    UpdateManager,
    UpdateState,
    canonicalize_manifest
)
from engine.crypto_ed25519 import (
    sign_message,
    verify_signature,
    public_key_from_secret,
    RENDERFLOW_MASTER_PUBLIC_KEY
)

# Test Ed25519 keypair for cryptographic testing
TEST_SECRET_KEY = bytes.fromhex("e27eff4db87b6481bb87886382c11df2489ce384c69ffeb0ba9d8cf27e490e0a")
TEST_PUBLIC_KEY = public_key_from_secret(TEST_SECRET_KEY)


def make_signed_manifest(manifest_payload: dict, secret_key: bytes, public_key: bytes) -> tuple[dict, bytes]:
    """Generates a valid cryptographically signed manifest dictionary and canonical bytes."""
    clean = dict(manifest_payload)
    clean["public_key"] = public_key.hex()
    canonical = json.dumps(
        {k: v for k, v in clean.items() if k not in ("signature", "signature_ed25519", "public_key")},
        sort_keys=True,
        separators=(',', ':')
    ).encode("utf-8")
    sig = sign_message(canonical, secret_key, public_key)
    clean["signature_ed25519"] = sig.hex()
    clean["signature"] = sig.hex()
    raw_bytes = json.dumps(clean, indent=2).encode("utf-8")
    return clean, raw_bytes


class TestUpdaterConnectivityAndStatus(unittest.TestCase):
    """Automated tests for updater server connectivity and strict status categorization."""

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="rf_updater_qa_"))
        self.app_root = self.temp_dir / "app"
        self.app_root.mkdir(parents=True, exist_ok=True)
        (self.app_root / "projects").mkdir(parents=True, exist_ok=True)
        (self.app_root / "engine").mkdir(parents=True, exist_ok=True)

        # Set installed version to 2.4.0
        v_file = self.app_root / "engine" / "version.py"
        v_file.write_text('__version__ = "2.4.0"\n', encoding="utf-8")

        self.updater = UpdateManager(app_root=self.app_root, cache_dir=self.temp_dir / "cache")
        # Allow test file:// URLs during QA
        os.environ["RENDERFLOW_STAGING_MODE"] = "1"

    def tearDown(self):
        os.environ.pop("RENDERFLOW_STAGING_MODE", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_initial_unverified_status(self):
        """Verify initial state is 'not_checked', is_verified=False, never green/up_to_date."""
        status = self.updater.get_status()
        self.assertEqual(status["state"], UpdateState.IDLE)
        self.assertEqual(status["check_status"], "not_checked")
        self.assertFalse(status["is_verified"])
        self.assertEqual(status["last_checked"], 0.0)
        self.assertFalse(status["update_available"])
        self.assertIsNone(status["latest_version"])
        self.assertIsNone(status["error"])

    def test_02_verified_latest_version(self):
        """Verify remote check confirming installed version is current produces 'verified_latest'."""
        manifest_payload = {
            "manifest_version": "1.0",
            "latest_version": "2.4.0",
            "minimum_supported_version": "2.0.0",
            "release_notes": "RenderFlow v2.4.0 Current Stable",
            "packages": {
                "patch": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.4.0/patch.zip",
                    "package_size_bytes": 1024,
                    "sha256": "abcdef1234567890",
                    "applies_to": [">=2.0.0"]
                }
            }
        }
        manifest_dict, raw_bytes = make_signed_manifest(manifest_payload, TEST_SECRET_KEY, TEST_PUBLIC_KEY)
        manifest_file = self.temp_dir / "manifest_uptodate.json"
        manifest_file.write_bytes(raw_bytes)

        # Test check against authenticated manifest matching installed version
        with patch.object(self.updater, "verify_manifest_authenticity", return_value=True):
            status = self.updater.check_now(force=True, custom_manifest_url=manifest_file.as_uri())

        self.assertEqual(status["state"], UpdateState.UP_TO_DATE)
        self.assertEqual(status["check_status"], "verified_latest")
        self.assertTrue(status["is_verified"])
        self.assertFalse(status["update_available"])
        self.assertEqual(status["latest_version"], "2.4.0")
        self.assertGreater(status["last_checked"], 0.0)

    def test_03_available_update_detection(self):
        """Verify remote check confirming newer version produces 'update_available'."""
        manifest_payload = {
            "manifest_version": "1.0",
            "latest_version": "2.5.0",
            "minimum_supported_version": "2.0.0",
            "release_notes": "RenderFlow v2.5.0 Performance Release",
            "packages": {
                "patch": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.5.0/patch.zip",
                    "package_size_bytes": 2048,
                    "sha256": "1234567890abcdef",
                    "applies_to": [">=2.0.0"]
                }
            }
        }
        manifest_dict, raw_bytes = make_signed_manifest(manifest_payload, TEST_SECRET_KEY, TEST_PUBLIC_KEY)
        manifest_file = self.temp_dir / "manifest_available.json"
        manifest_file.write_bytes(raw_bytes)

        with patch.object(self.updater, "verify_manifest_authenticity", return_value=True):
            status = self.updater.check_now(force=True, custom_manifest_url=manifest_file.as_uri())

        self.assertEqual(status["state"], UpdateState.AVAILABLE)
        self.assertEqual(status["check_status"], "update_available")
        self.assertTrue(status["is_verified"])
        self.assertTrue(status["update_available"])
        self.assertEqual(status["latest_version"], "2.5.0")
        self.assertEqual(status["package_type"], "patch")

    def test_04_unreachable_server_offline_operation(self):
        """Verify offline / connection failure produces 'check_failed', preserves usability."""
        status = self.updater.check_now(
            force=True,
            custom_manifest_url="https://raw.githubusercontent.com/nonexistent_org_renderflow_offline/test.json"
        )
        self.assertEqual(status["state"], UpdateState.ERROR)
        self.assertEqual(status["check_status"], "check_failed")
        self.assertFalse(status["is_verified"])
        self.assertFalse(status["update_available"])
        self.assertIsNotNone(status["error_message"])
        self.assertTrue(
            "offline" in status["error_message"].lower() or
            "failed" in status["error_message"].lower() or
            "404" in status["error_message"].lower() or
            "not found" in status["error_message"].lower() or
            "http" in status["error_message"].lower()
        )
        # Verify app is still fully usable (version resolved, projects dir untouched)
        self.assertEqual(status["current_version"], "2.4.0")
        self.assertTrue(self.updater.projects_dir.exists())

    def test_05_http_404_error_handling(self):
        """Verify HTTP 404 server response produces clear diagnostic error."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = HTTPError(
                url="https://raw.githubusercontent.com/test/update_manifest.json",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=None
            )
            status = self.updater.check_now(
                force=True,
                custom_manifest_url="https://raw.githubusercontent.com/test/update_manifest.json"
            )

        self.assertEqual(status["state"], UpdateState.ERROR)
        self.assertEqual(status["check_status"], "check_failed")
        self.assertFalse(status["is_verified"])
        self.assertIn("HTTP 404", status["error_message"])

    def test_06_malformed_json_manifest_handling(self):
        """Verify malformed non-JSON server payload produces decode error."""
        corrupt_file = self.temp_dir / "corrupted_manifest.json"
        corrupt_file.write_bytes(b"<html><head><title>502 Bad Gateway</title></head><body>Bad Gateway</body></html>")

        status = self.updater.check_now(force=True, custom_manifest_url=corrupt_file.as_uri())
        self.assertEqual(status["state"], UpdateState.ERROR)
        self.assertEqual(status["check_status"], "check_failed")
        self.assertFalse(status["is_verified"])
        self.assertIn("JSON", status["error_message"])

    def test_07_forged_ed25519_signature_rejection(self):
        """Verify tampered payload or forged Ed25519 signature is strictly rejected."""
        manifest_payload = {
            "manifest_version": "1.0",
            "latest_version": "2.9.9",
            "minimum_supported_version": "2.0.0",
            "release_notes": "Forged Release",
            "update_package_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.9.9/patch.zip",
            "signature_ed25519": "00" * 64,  # Invalid dummy signature
            "signature": "00" * 64,
            "public_key": RENDERFLOW_MASTER_PUBLIC_KEY
        }
        forged_file = self.temp_dir / "forged_manifest.json"
        forged_file.write_text(json.dumps(manifest_payload), encoding="utf-8")

        status = self.updater.check_now(force=True, custom_manifest_url=forged_file.as_uri())
        self.assertEqual(status["state"], UpdateState.ERROR)
        self.assertEqual(status["check_status"], "check_failed")
        self.assertFalse(status["is_verified"])
        self.assertIn("signature verification failed", status["error_message"].lower())

    def test_08_connection_timeout_handling(self):
        """Verify network connection timeout is caught cleanly without hanging."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = TimeoutError("Connection timed out after 15s")
            status = self.updater.check_now(
                force=True,
                custom_manifest_url="https://raw.githubusercontent.com/test/update_manifest.json"
            )

        self.assertEqual(status["state"], UpdateState.ERROR)
        self.assertEqual(status["check_status"], "check_failed")
        self.assertFalse(status["is_verified"])
        self.assertIn("timed out", status["error_message"].lower())

    def test_09_automatic_manifest_fallback(self):
        """Verify that when primary manifest fails, fallback manifest endpoint is automatically used."""
        valid_payload = {
            "manifest_version": "1.0",
            "latest_version": "2.4.0",
            "minimum_supported_version": "2.0.0",
            "release_notes": "RenderFlow Fallback Manifest",
            "packages": {
                "patch": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.4.0/patch.zip",
                    "package_size_bytes": 1024,
                    "sha256": "abcdef1234567890",
                    "applies_to": [">=2.0.0"]
                }
            }
        }
        _, valid_bytes = make_signed_manifest(valid_payload, TEST_SECRET_KEY, TEST_PUBLIC_KEY)

        call_count = 0

        def mock_urlopen_handler(req, timeout=15):
            nonlocal call_count
            call_count += 1
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if call_count == 1:
                raise URLError(f"DNS resolution failed for {url}")
            # Fallback URL succeeds
            mock_resp = MagicMock()
            mock_resp.read.return_value = valid_bytes
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=mock_urlopen_handler):
            with patch.object(self.updater, "verify_manifest_authenticity", return_value=True):
                # When no custom URL is given, it evaluates [UPDATE_MANIFEST_URL, UPDATE_MANIFEST_FALLBACK_URL]
                status = self.updater.check_now(force=True)

        self.assertGreaterEqual(call_count, 2)
        self.assertEqual(status["state"], UpdateState.UP_TO_DATE)
        self.assertEqual(status["check_status"], "verified_latest")
        self.assertTrue(status["is_verified"])

    def test_10_api_check_endpoint_schema(self):
        """Verify synchronous FastAPI /api/update/check endpoint response schema and error safety."""
        from fastapi.testclient import TestClient
        from web.server import app

        client = TestClient(app)

        # Mock check_now to simulate verified up to date
        mock_status = {
            "current_version": "2.4.0",
            "latest_version": "2.4.0",
            "state": UpdateState.UP_TO_DATE,
            "check_status": "verified_latest",
            "is_verified": True,
            "error": None,
            "error_message": None,
            "last_checked": time.time(),
            "package_type": "patch",
            "package_size_bytes": 0,
            "download_progress": {"percent": 0.0, "active": False},
            "update_available": False,
            "release_notes": "Up to date",
            "can_restart": False,
            "can_install_full": False
        }

        with patch("web.server.update_manager.check_now", return_value=mock_status):
            res = client.post("/api/update/check")

        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["update_available"])
        self.assertEqual(data["check_status"], "verified_latest")
        from engine.version import __version__
        self.assertEqual(data["current_version"], __version__)
        self.assertIn("up to date", data["message"].lower())

    def test_11_reproduce_and_verify_no_attribute_error_on_update_state(self):
        """Regression test: Confirm UpdateState uses string constants and server endpoints never call .value."""
        # 1. Type confirmation: UpdateState members must be strings without .value
        self.assertIsInstance(UpdateState.DOWNLOADING, str)
        self.assertIsInstance(UpdateState.APPLYING, str)
        self.assertIsInstance(UpdateState.AVAILABLE, str)
        self.assertIsInstance(UpdateState.DOWNLOADED, str)
        self.assertFalse(hasattr(UpdateState.DOWNLOADING, "value"), "UpdateState.DOWNLOADING must not have .value")

        # 2. Test live server in scratch/test_v223_install
        from fastapi.testclient import TestClient
        import importlib.util

        scratch_server_path = WORKSPACE / "scratch" / "test_v223_install" / "web" / "server.py"
        self.assertTrue(scratch_server_path.exists())

        spec = importlib.util.spec_from_file_location("scratch_server", str(scratch_server_path))
        scratch_server_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scratch_server_mod)

        scratch_client = TestClient(scratch_server_mod.app)
        res = scratch_client.post("/api/update/check")
        self.assertNotEqual(res.status_code, 500, "Must not throw HTTP 500 AttributeError: 'str' object has no attribute 'value'")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("ok", data)
        self.assertIn("check_status", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
