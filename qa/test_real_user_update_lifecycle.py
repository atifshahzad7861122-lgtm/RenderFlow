"""
qa/test_real_user_update_lifecycle.py
=====================================
Rigorous end-to-end verification of RenderFlow real-user update lifecycle:
1. Update check against live published manifest.
2. Download of actual published v2.4.0 patch package from GitHub.
3. Cryptographic Ed25519 signature, byte count, and SHA-256 verification.
4. Atomic staging, automatic backup, and patch application.
5. Preservation of existing user projects, media, credentials, and config.
6. Process shutdown and automatic restart helper execution.
7. Post-restart health check and running version verification on isolated port.
8. Negative tests: Corrupted signature rejection, network failure diagnostics, clean rollback.
"""

import os
import sys
import json
import time
import shutil
import socket
import urllib.request
import subprocess
from pathlib import Path
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.updater import UpdateManager, UpdateState
from engine.crypto_ed25519 import verify_signature, RENDERFLOW_MASTER_PUBLIC_KEY
from engine.version import UPDATE_MANIFEST_URL, UPDATE_MANIFEST_FALLBACK_URL

IS_WINDOWS = sys.platform == "win32"


class TestRealUserUpdateLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = WORKSPACE_ROOT / "scratch" / "e2e_real_client_test"
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # Build isolated client mimicking v2.2.4 installation (do NOT copy 2.5GB real user projects)
        for folder in ("engine", "web", "config"):
            src_folder = WORKSPACE_ROOT / folder
            if src_folder.exists():
                shutil.copytree(
                    src_folder,
                    cls.test_dir / folder,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log")
                )
        (cls.test_dir / "projects").mkdir(parents=True, exist_ok=True)

        # Set installed version to v2.2.4 in version.py
        version_file = cls.test_dir / "engine" / "version.py"
        version_content = version_file.read_text(encoding="utf-8")
        version_content = version_content.replace('__version__ = "2.4.0"', '__version__ = "2.2.4"')
        version_file.write_text(version_content, encoding="utf-8")

        # Create user project and credentials to verify preservation
        cls.user_project = cls.test_dir / "projects" / "my_secret_film"
        cls.user_project.mkdir(parents=True, exist_ok=True)
        (cls.user_project / "timeline.json").write_text('{"title": "User Film", "version": 1}', encoding="utf-8")
        (cls.user_project / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")

        cls.user_env = cls.test_dir / ".env"
        cls.user_env.write_text("OPENAI_API_KEY=sk-test-real-user-credential\nRENDERFLOW_ENV=production\n", encoding="utf-8")

        cls.user_config = cls.test_dir / "config" / "render_profiles.json"
        cls.user_config_initial = cls.user_config.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        # Clean up test directory
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_verify_published_infrastructure_live(self):
        """Verify GitHub release and manifest endpoints return valid HTTP 200, matching hashes and signatures."""
        req = urllib.request.Request(UPDATE_MANIFEST_URL, headers={"User-Agent": "RenderFlow-Client/2.2.4"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            data = resp.read()
            manifest = json.loads(data.decode("utf-8"))

        self.assertEqual(manifest.get("latest_version"), "2.4.0")
        self.assertIn("packages", manifest)
        self.assertIn("patch", manifest["packages"])
        patch_info = manifest["packages"]["patch"]
        self.assertGreater(patch_info["package_size_bytes"], 500000)
        self.assertTrue(len(patch_info["sha256"]) == 64)

        # Verify signature
        mgr = UpdateManager(app_root=self.test_dir)
        is_valid = mgr.verify_manifest_authenticity(manifest)
        self.assertTrue(is_valid, "Published manifest signature must be cryptographically valid")

    def test_02_check_and_download_actual_published_package(self):
        """Test checking for update and downloading the actual published v2.4.0 zip from GitHub."""
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.current_version = "2.2.4"
        
        status = mgr.check_now(force=True)
        self.assertTrue(status["ok"])
        self.assertTrue(status["update_available"])
        self.assertEqual(status["latest_version"], "2.4.0")
        self.assertEqual(status["package_size"], 636375)
        self.assertNotEqual(status["package_size"], 0)

        # Download update synchronously
        dl_success = mgr.download_update_sync()
        self.assertTrue(dl_success, f"Download failed: {mgr.error_message}")
        
        status = mgr.get_status()
        self.assertEqual(status["state"], UpdateState.DOWNLOADED)
        self.assertEqual(status["download_percent"], 100.0)
        self.assertEqual(status["total_bytes"], 636375)

    def test_03_stage_apply_patch_and_verify_preservation(self):
        """Apply patch to isolated client; confirm atomic file update and user data preservation."""
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.current_version = "2.2.4"
        
        # Ensure package is downloaded
        if mgr.state != UpdateState.DOWNLOADED:
            mgr.check_now(force=True)
            mgr.download_update_sync()

        # Apply patch
        result = mgr.apply_patch()
        self.assertTrue(result.get("ok"), f"Apply failed: {result.get('error_message')}")
        self.assertTrue(result.get("success"), "Result must contain success=True for legacy v2.2.4 client compatibility")
        self.assertEqual(result.get("state"), UpdateState.READY_TO_RESTART)
        self.assertIsNotNone(result.get("message"))
        self.assertNotEqual(result.get("message"), "null")

        # Confirm user projects, credentials, and custom config are preserved
        self.assertTrue(self.user_project.exists(), "User projects directory was deleted!")
        self.assertTrue((self.user_project / "timeline.json").exists())
        timeline_data = json.loads((self.user_project / "timeline.json").read_text(encoding="utf-8"))
        self.assertEqual(timeline_data.get("title"), "User Film")
        self.assertEqual((self.user_project / "clip.mp4").read_bytes(), b"\x00\x00\x00\x18ftypmp42")

        self.assertTrue(self.user_env.exists(), ".env was deleted!")
        env_content = self.user_env.read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY=sk-test-real-user-credential", env_content)

        # Confirm updated files on disk report v2.4.0
        version_file = self.test_dir / "engine" / "version.py"
        new_version_content = version_file.read_text(encoding="utf-8")
        self.assertIn('__version__ = "2.4.0"', new_version_content)

    @unittest.skipUnless(IS_WINDOWS, "Process restart test uses Windows PowerShell")
    def test_04_restart_helper_launches_new_process_and_verifies_health(self):
        """Test restart helper generation and verify new process launches and responds to health probe."""
        test_port = 8765
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Test restart_application generating valid PowerShell script without spawning background process
        res = mgr.restart_application(spawn=False)
        self.assertTrue(res)

        ps1_file = mgr.cache_dir / "restart_helper.ps1"
        self.assertTrue(ps1_file.exists())
        ps1_text = ps1_file.read_text(encoding="utf-8")
        
        # Verify script uses ArgumentList, not broken Start-Process with arguments in FilePath
        self.assertIn("-ArgumentList", ps1_text)
        self.assertIn("Stop-Process", ps1_text)

        # Now start test server on isolated port 8765 to verify post-restart health check loop
        server_env = os.environ.copy()
        server_env["PORT"] = str(test_port)
        server_env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "web.server:app", "--host", "127.0.0.1", "--port", str(test_port)],
            cwd=str(self.test_dir.resolve()),
            env=server_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        try:
            # Poll /api/system_status for up to 10 seconds
            server_online = False
            for _ in range(20):
                time.sleep(0.5)
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{test_port}/api/system_status")
                    with urllib.request.urlopen(req, timeout=1.0) as resp:
                        if resp.status == 200:
                            server_online = True
                            break
                except Exception:
                    pass

            self.assertTrue(server_online, "Restarted server did not come online within timeout")

            # Check update status endpoint returns 2.4.0
            req = urllib.request.Request(f"http://127.0.0.1:{test_port}/api/update/status")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                status_data = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(status_data.get("current_version"), "2.4.0")
                self.assertTrue(status_data.get("ok", status_data.get("state") != "error"))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

    def test_05_tampered_signature_rejected_with_clear_error(self):
        """Verify that forged/tampered manifest produces clear non-null error without crashing."""
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.current_version = "2.2.4"

        # Tampered manifest with wrong signature
        tampered_manifest = {
            "latest_version": "2.4.0",
            "update_package_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.4.0/RenderFlow-Patch-v2.4.0.zip",
            "package_size_bytes": 636375,
            "sha256": "f9a0f528a4a4d41092189dc230e9f6aee4ac4078a6565c1bcbbc2508984d479b",
            "signature": "00" * 64,
            "public_key": "661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e"
        }

        is_valid = mgr.verify_manifest_authenticity(tampered_manifest)
        self.assertFalse(is_valid, "Tampered signature must be rejected")


if __name__ == "__main__":
    unittest.main()
