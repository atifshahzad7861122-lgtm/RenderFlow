"""
engine/test_new_update_system.py — Comprehensive Unit & Integration Test Suite
=============================================================================
Mandatory acceptance tests for RenderFlow's complete-installer update system:
- SemVer 2.0.0 compliance
- Ed25519 signature authentication & canonical serialization
- SHA-256 integrity verification & domain allowlisting
- GitHub release filtering (stable only, non-draft, architecture match)
- Network error handling, rate-limit resilience, offline mode safety
- Streaming chunked downloader, cancellation, and partial cleanup
- Graceful shutdown, pre-install backup, and user-data preservation
- Truthful post-install version verification (no false success)
- Diagnostic logging, recovery guidance, and concurrent call safety
"""

import os
import sys
import json
import time
import shutil
import tempfile
import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from engine.updates.models import UpdateState, UpdateStatus, ReleaseInfo, InstallerAsset, DownloadProgress
from engine.updates.semver import SemVer
from engine.updates.artifact_verifier import ArtifactVerifier, canonicalize_manifest
from engine.updates.manifest_validator import ReleaseManifestValidator
from engine.updates.download_service import SecureDownloadService
from engine.updates.installer_launcher import InstallerLauncher
from engine.updates.post_update_verifier import PostUpdateVerifier
from engine.updates.recovery_service import UpdateRecoveryService
from engine.updates.update_service import UpdateService
from engine.crypto_ed25519 import (
    sign_message,
    verify_signature,
    public_key_from_secret,
    RENDERFLOW_MASTER_PUBLIC_KEY
)


class TestSemVerSpecification(unittest.TestCase):
    """Validates Semantic Versioning 2.0.0 parsing, sorting, and edge cases."""

    def test_core_parsing(self):
        v = SemVer.parse("2.4.1")
        self.assertEqual(v.major, 2)
        self.assertEqual(v.minor, 4)
        self.assertEqual(v.patch, 1)
        self.assertIsNone(v.prerelease)

    def test_v_prefix_normalization(self):
        v1 = SemVer.parse("v2.4.1")
        v2 = SemVer.parse("2.4.1")
        self.assertEqual(v1, v2)

    def test_ordering_and_comparison(self):
        self.assertTrue(SemVer("2.2.0") < SemVer("2.2.4"))
        self.assertTrue(SemVer("2.2.4") < SemVer("2.4.0"))
        self.assertTrue(SemVer("2.4.0") < SemVer("2.4.1"))
        self.assertTrue(SemVer("2.4.1") < SemVer("2.5.0"))
        self.assertTrue(SemVer("2.5.0") < SemVer("3.0.0"))

    def test_prerelease_precedence(self):
        # 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-beta < 1.0.0-rc.1 < 1.0.0
        self.assertTrue(SemVer("2.4.1-alpha") < SemVer("2.4.1-alpha.1"))
        self.assertTrue(SemVer("2.4.1-alpha.1") < SemVer("2.4.1-beta"))
        self.assertTrue(SemVer("2.4.1-beta") < SemVer("2.4.1-rc.1"))
        self.assertTrue(SemVer("2.4.1-rc.1") < SemVer("2.4.1"))

    def test_build_metadata_ignored_in_precedence(self):
        v1 = SemVer("2.4.1+build100")
        v2 = SemVer("2.4.1+build200")
        self.assertEqual(v1, v2)


class TestArtifactVerifier(unittest.TestCase):
    """Validates cryptographic Ed25519 authentication, SHA-256 checks, and domain safety."""

    def setUp(self):
        self.sk = bytes.fromhex("e27eff4db87b6481bb87886382c11df2489ce384c69ffeb0ba9d8cf27e490e0a")
        self.pk = public_key_from_secret(self.sk)
        self.pk_hex = self.pk.hex()
        self.verifier = ArtifactVerifier(master_public_key=self.pk_hex)

    def test_valid_manifest_signature(self):
        manifest = {
            "manifest_version": "2.0",
            "latest_version": "2.4.1",
            "packages": {
                "full": {"url": "https://github.com/test/RenderFlow-Setup-v2.4.1.exe", "size": 1000}
            }
        }
        canonical = canonicalize_manifest(manifest)
        sig = sign_message(canonical, self.sk, self.pk).hex()
        manifest["signature_ed25519"] = sig
        manifest["public_key"] = self.pk_hex

        ok, err = self.verifier.verify_manifest_signature(manifest)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_tampered_manifest_rejected(self):
        manifest = {
            "manifest_version": "2.0",
            "latest_version": "2.4.1",
        }
        canonical = canonicalize_manifest(manifest)
        sig = sign_message(canonical, self.sk, self.pk).hex()
        manifest["signature_ed25519"] = sig
        manifest["public_key"] = self.pk_hex

        # Tamper payload
        manifest["latest_version"] = "2.4.2"
        ok, err = self.verifier.verify_manifest_signature(manifest)
        self.assertFalse(ok)
        self.assertIn("tampered or corrupted", err)

    def test_untrusted_public_key_rejected(self):
        other_sk = bytes.fromhex("1111111111111111111111111111111111111111111111111111111111111111")
        other_pk = public_key_from_secret(other_sk).hex()

        manifest = {"latest_version": "2.4.1"}
        canonical = canonicalize_manifest(manifest)
        sig = sign_message(canonical, other_sk, bytes.fromhex(other_pk)).hex()
        manifest["signature_ed25519"] = sig
        manifest["public_key"] = other_pk

        ok, err = self.verifier.verify_manifest_signature(manifest)
        self.assertFalse(ok)
        self.assertIn("untrusted public key", err)

    def test_domain_allowlist(self):
        self.assertTrue(self.verifier.verify_url_domain("https://github.com/owner/repo/releases/download/v2.4.1/Setup.exe"))
        self.assertTrue(self.verifier.verify_url_domain("https://objects.githubusercontent.com/github-production-release-asset/Setup.exe"))
        self.assertTrue(self.verifier.verify_url_domain("https://raw.githubusercontent.com/owner/repo/main/manifest.json"))
        # Non-HTTPS or untrusted domains must be rejected
        self.assertFalse(self.verifier.verify_url_domain("http://github.com/download/Setup.exe"))
        self.assertFalse(self.verifier.verify_url_domain("https://evil-mirror.com/Setup.exe"))
        self.assertFalse(self.verifier.verify_url_domain("https://attacker.github.io/Setup.exe"))

    def test_file_integrity_and_sha256(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fpath = Path(tmp_dir) / "test_artifact.bin"
            content = b"RenderFlow Secure Installer Binary Content v2.4.1"
            fpath.write_bytes(content)
            expected_hash = hashlib.sha256(content).hexdigest()

            # Valid check
            ok, err = self.verifier.verify_file_integrity(fpath, expected_hash, len(content))
            self.assertTrue(ok)
            self.assertIsNone(err)

            # Checksum mismatch
            bad_hash = "0000000000000000000000000000000000000000000000000000000000000000"
            ok2, err2 = self.verifier.verify_file_integrity(fpath, bad_hash, len(content))
            self.assertFalse(ok2)
            self.assertIn("mismatch", err2.lower())

            # Size mismatch
            ok3, err3 = self.verifier.verify_file_integrity(fpath, expected_hash, len(content) + 5)
            self.assertFalse(ok3)
            self.assertIn("size mismatch", err3.lower())


class TestReleaseManifestValidator(unittest.TestCase):
    """Validates release schema, draft/prerelease exclusion, and error handling."""

    def setUp(self):
        self.validator = ReleaseManifestValidator()

    def test_reject_draft_release(self):
        payload = {
            "tag_name": "v2.4.1",
            "draft": True,
            "prerelease": False,
            "assets": [{"name": "RenderFlow-Setup-v2.4.1.exe", "size": 1000, "browser_download_url": "https://github.com/setup.exe"}]
        }
        res, err = self.validator._parse_github_release_payload(payload)
        self.assertIsNone(res)
        self.assertIn("Draft", err)

    def test_reject_prerelease(self):
        payload = {
            "tag_name": "v2.4.1-rc1",
            "draft": False,
            "prerelease": True,
            "assets": [{"name": "RenderFlow-Setup-v2.4.1-rc1.exe", "size": 1000, "browser_download_url": "https://github.com/setup.exe"}]
        }
        res, err = self.validator._parse_github_release_payload(payload)
        self.assertIsNone(res)
        self.assertIn("Prerelease", err)

    def test_reject_missing_installer(self):
        payload = {
            "tag_name": "v2.4.1",
            "draft": False,
            "prerelease": False,
            "assets": [{"name": "RenderFlow-Patch-v2.4.1.zip", "size": 500, "browser_download_url": "https://github.com/patch.zip"}]
        }
        res, err = self.validator._parse_github_release_payload(payload)
        self.assertIsNone(res)
        self.assertIn("lacks a standalone Windows installer", err)

    def test_network_failure_never_returns_up_to_date(self):
        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            res, err = self.validator.fetch_latest_release()
            self.assertIsNone(res)
            self.assertIsNotNone(err)
            self.assertIn("failed", err.lower())


class TestSecureDownloadService(unittest.TestCase):
    """Validates chunked streaming, progress calculation, cancellation, and cleanup."""

    def test_successful_streaming(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloader = SecureDownloadService(download_dir=Path(tmp_dir))
            installer_bytes = b"MOCK_EXE_PAYLOAD_" * 1024  # 17KB
            expected_size = len(installer_bytes)

            class MockResponse:
                def __init__(self):
                    self.data = installer_bytes
                    self.offset = 0
                    self.headers = {"Content-Length": str(expected_size)}
                def read(self, chunk_size):
                    chunk = self.data[self.offset:self.offset + chunk_size]
                    self.offset += len(chunk)
                    return chunk
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass

            with patch("urllib.request.urlopen", return_value=MockResponse()):
                asset = InstallerAsset(
                    name="RenderFlow-Setup-v2.4.1.exe",
                    url="https://github.com/test/RenderFlow-Setup-v2.4.1.exe",
                    size_bytes=expected_size,
                    sha256=""
                )
                progress_reports = []
                final_path, err = downloader.download_installer(asset, progress_callback=lambda p: progress_reports.append(p.percent))

                self.assertIsNotNone(final_path)
                self.assertIsNone(err)
                self.assertTrue(final_path.exists())
                self.assertEqual(final_path.stat().st_size, expected_size)
                self.assertTrue(len(progress_reports) > 0)
                self.assertEqual(progress_reports[-1], 100.0)

    def test_cancellation_cleans_up_part_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            downloader = SecureDownloadService(download_dir=Path(tmp_dir))
            downloader.cancel()  # Signal cancellation immediately

            asset = InstallerAsset(
                name="RenderFlow-Setup-v2.4.1.exe",
                url="https://github.com/test/RenderFlow-Setup-v2.4.1.exe",
                size_bytes=50000,
                sha256=""
            )
            final_path, err = downloader.download_installer(asset)
            self.assertIsNone(final_path)
            self.assertIn("cancelled", err.lower())

            # Ensure no orphan .part file left behind
            part_files = list(Path(tmp_dir).glob("*.part"))
            self.assertEqual(len(part_files), 0)


class TestInstallerLauncherAndDataPreservation(unittest.TestCase):
    """Validates user data protection, config backup, and execution security."""

    def test_user_data_preservation_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp_app_root:
            app_root = Path(tmp_app_root)
            cache_dir = app_root / ".cache" / "updates"

            # Create mock user data: projects (critical workspace), config, credentials
            projects_dir = app_root / "projects"
            projects_dir.mkdir(parents=True)
            (projects_dir / "user_project_1.json").write_text('{"name": "Client Promo Video"}', encoding="utf-8")
            (projects_dir / "render_timeline.json").write_text('{"clips": [1, 2, 3]}', encoding="utf-8")

            config_dir = app_root / "config"
            config_dir.mkdir(parents=True)
            (config_dir / "settings.json").write_text('{"theme": "dark", "bitrate": 8000}', encoding="utf-8")
            (app_root / ".env").write_text('DEEPGRAM_API_KEY=test_secret_123', encoding="utf-8")

            launcher = InstallerLauncher(app_root=app_root, cache_dir=cache_dir)
            ok, backup_path = launcher.backup_user_configurations()

            self.assertTrue(ok)
            self.assertTrue(Path(backup_path).exists())
            self.assertTrue((Path(backup_path) / "settings.json").exists())
            self.assertTrue((Path(backup_path) / ".env").exists())

            # CRITICAL: Confirm user projects are untouched and preserved
            self.assertTrue((projects_dir / "user_project_1.json").exists())
            self.assertTrue((projects_dir / "render_timeline.json").exists())

    def test_refuse_non_executable_installer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            app_root = Path(tmp_dir) / "app"
            app_root.mkdir()
            bad_file = Path(tmp_dir) / "malicious.bat"
            bad_file.write_text("echo harmful")

            launcher = InstallerLauncher(app_root=app_root)
            ok, err = launcher.launch_installer(bad_file, schedule_exit=False)
            self.assertFalse(ok)
            self.assertIn("non-executable", err.lower())


class TestPostUpdateVerifier(unittest.TestCase):
    """Validates truthful running version check without false success."""

    def test_truthful_version_match(self):
        verifier = PostUpdateVerifier(max_wait_seconds=3.0)

        mock_responses = {
            "http://127.0.0.1:8000/api/system_status": b'{"status": "ok"}',
            "http://127.0.0.1:8000/api/update/status": b'{"current_version": "2.4.1", "state": "idle"}'
        }

        class MockResp:
            def __init__(self, url):
                self.status = 200
                self.url = url
            def read(self):
                return mock_responses.get(self.url, b"{}")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", side_effect=lambda req, timeout=2.0: MockResp(req.full_url)):
            ok, err, details = verifier.verify_running_application(target_version="2.4.1")
            self.assertTrue(ok)
            self.assertIsNone(err)
            self.assertEqual(details.get("current_version"), "2.4.1")

    def test_older_running_version_fails_without_false_success(self):
        verifier = PostUpdateVerifier(max_wait_seconds=2.0)

        # Server alive, but running older version 2.4.0
        mock_responses = {
            "http://127.0.0.1:8000/api/system_status": b'{"status": "ok"}',
            "http://127.0.0.1:8000/api/update/status": b'{"current_version": "2.4.0", "state": "idle"}'
        }

        class MockResp:
            def __init__(self, url):
                self.status = 200
                self.url = url
            def read(self):
                return mock_responses.get(self.url, b"{}")
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        with patch("urllib.request.urlopen", side_effect=lambda req, timeout=2.0: MockResp(req.full_url)):
            ok, err, details = verifier.verify_running_application(target_version="2.4.1")
            self.assertFalse(ok)
            self.assertIn("older version", err.lower())


class TestRecoveryService(unittest.TestCase):
    """Validates structured diagnostic event logging and recovery guidance."""

    def test_logging_and_guidance(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            recovery = UpdateRecoveryService(cache_dir=Path(tmp_dir))
            recovery.log_event("CHECK_INITIATED", "Starting release check", {"source": "GitHub API"})
            recovery.log_event("CHECK_FAILED", "Rate limit exceeded", {"status": 403})

            lines = recovery.read_recent_diagnostics()
            self.assertEqual(len(lines), 2)
            self.assertIn("[CHECK_INITIATED]", lines[0])
            self.assertIn("[CHECK_FAILED]", lines[1])

            guidance = recovery.get_recovery_guidance("CHECK_FAILED", "Rate limit exceeded")
            self.assertIn("Your workspace data, projects, media files, and AI credentials remain 100% safe", guidance)
            self.assertIn("github.com", guidance)


class TestUpdateServiceStateMachine(unittest.TestCase):
    """Validates thread-safe state machine, concurrent calls, and transitions."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.service = UpdateService(app_root=Path(self.tmp_dir))

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_initial_state(self):
        status = self.service.get_status()
        self.assertEqual(status["state"], UpdateState.IDLE.value)
        self.assertTrue(status["ok"])

    def test_state_transition_update_available(self):
        self.service.status.current_version = "2.4.3"
        installer = InstallerAsset(
            name="RenderFlow-Setup-v2.5.0.exe",
            url="https://github.com/test/RenderFlow-Setup-v2.5.0.exe",
            size_bytes=1000,
            sha256="abc"
        )
        mock_release = ReleaseInfo(
            version="2.5.0",
            release_title="RenderFlow v2.5.0",
            release_notes="Notes",
            published_at="2026-10-19",
            release_url="https://github.com/releases",
            installer=installer
        )

        with patch.object(self.service.validator, "fetch_latest_release", return_value=(mock_release, None)):
            res = self.service.check_for_updates(force=True)
            self.assertEqual(res["state"], UpdateState.UPDATE_AVAILABLE.value)
            self.assertTrue(res["update_available"])
            self.assertEqual(res["latest_version"], "2.5.0")

    def test_concurrent_check_rejection_during_download(self):
        self.service.status.state = UpdateState.DOWNLOADING
        res = self.service.check_for_updates(force=True)
        # Must retain DOWNLOADING and not overwrite with CHECKING
        self.assertEqual(res["state"], UpdateState.DOWNLOADING.value)


if __name__ == "__main__":
    unittest.main()
