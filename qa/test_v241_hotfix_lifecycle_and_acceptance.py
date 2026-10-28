#!/usr/bin/env python3
"""
RenderFlow v2.4.1 Hotfix — Acceptance & Lifecycle Regression Suite
Tests the exact v2.4.1 release artifacts on a clean isolated v2.2.4 installation:
1. Manifest & Patch cryptographic verification (Ed25519 & SHA-256)
2. Package size reporting (no 0 B)
3. Patch application & atomic staging
4. User project, credential, settings, and media preservation
5. Restart script generation (-ArgumentList, port release buffer, process termination)
6. Subprocess boot, health check (/api/system_status), and running version verification (/api/update/status -> 2.4.1)
7. Automatic rollback on failure
"""

import os
import sys
import json
import shutil
import hashlib
import tempfile
import asyncio
import unittest
import threading
import subprocess
import socket
import http.server
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.crypto_ed25519 import ed25519_sign, ed25519_verify
from engine.updater import UpdateManager, UpdateState, SemVer


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class MockReleaseServer:
    def __init__(self, port: int, release_dir: Path):
        self.port = port
        self.release_dir = release_dir
        self.httpd = None
        self.thread = None

    def start(self):
        handler = lambda *args, **kwargs: http.server.SimpleHTTPRequestHandler(*args, directory=str(self.release_dir), **kwargs)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


class TestRenderFlowV241HotfixRelease(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release_dir = ROOT_DIR / "release"
        cls.patch_zip = cls.release_dir / "RenderFlow-Patch-v2.4.1.zip"
        cls.setup_exe = cls.release_dir / "RenderFlow-Setup-v2.4.1.exe"
        cls.manifest_json = cls.release_dir / "update_manifest_v2.4.1.json"
        cls.pub_key_file = ROOT_DIR / "tools" / "release_public_key.pub"
        cls.priv_key_file = ROOT_DIR / "tools" / "release_signing_key.priv"

        assert cls.patch_zip.is_file(), f"Missing {cls.patch_zip}"
        assert cls.setup_exe.is_file(), f"Missing {cls.setup_exe}"
        assert cls.manifest_json.is_file(), f"Missing {cls.manifest_json}"

        cls.pub_key_bytes = bytes.fromhex(cls.pub_key_file.read_text().strip())
        cls.priv_key_bytes = bytes.fromhex(cls.priv_key_file.read_text().strip())

        # Start mock HTTP release server on dynamic port
        cls.server_port = find_free_port()
        cls.mock_server = MockReleaseServer(cls.server_port, cls.release_dir)
        cls.mock_server.start()

        # Build a staging manifest pointing directly to local mock server for isolated download test
        staging_data = json.loads(cls.manifest_json.read_text(encoding="utf-8"))
        staging_data["update_package_url"] = f"http://127.0.0.1:{cls.server_port}/{cls.patch_zip.name}"
        if "packages" in staging_data and "patch" in staging_data["packages"]:
            staging_data["packages"]["patch"]["url"] = f"http://127.0.0.1:{cls.server_port}/{cls.patch_zip.name}"

        # Re-sign staging manifest with authoritative private key
        to_sign = dict(staging_data)
        to_sign.pop("signature", None)
        to_sign.pop("public_key", None)
        can_bytes = json.dumps(to_sign, sort_keys=True, separators=(',', ':')).encode("utf-8")
        sig = ed25519_sign(can_bytes, cls.priv_key_bytes)
        staging_data["signature"] = sig.hex()
        staging_data["public_key"] = cls.pub_key_bytes.hex()

        cls.staging_manifest_path = cls.release_dir / "staging_test_manifest_v241.json"
        cls.staging_manifest_path.write_text(json.dumps(staging_data, indent=2), encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.mock_server.stop()
        if cls.staging_manifest_path.exists():
            cls.staging_manifest_path.unlink()

    def setUp(self):
        # Create isolated clean installation directory
        self.temp_dir = tempfile.TemporaryDirectory(prefix="renderflow_v241_qa_")
        self.app_dir = Path(self.temp_dir.name) / "RenderFlow_v224"
        self.app_dir.mkdir(parents=True, exist_ok=True)

        # Baseline v2.2.4 structure: copy full engine, web, and config trees
        for folder in ("engine", "web", "config"):
            src = ROOT_DIR / folder
            if src.exists():
                shutil.copytree(
                    src,
                    self.app_dir / folder,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log")
                )

        (self.app_dir / "projects" / "test_user_proj").mkdir(parents=True, exist_ok=True)

        # Set installed version to v2.2.4 in version.py while preserving all URLs and constants
        orig_version = (ROOT_DIR / "engine" / "version.py").read_text(encoding="utf-8")
        import re
        v224_version = re.sub(r'__version__\s*=\s*"[^"]+"', '__version__ = "2.2.4"', orig_version)
        (self.app_dir / "engine" / "version.py").write_text(v224_version, encoding="utf-8")

        # User data to preserve
        (self.app_dir / "credentials.json").write_text('{"api_key": "user_secret_xyz123"}', encoding="utf-8")
        (self.app_dir / ".env").write_text("RENDERFLOW_PORT=8000\nSECRET_TOKEN=secure987\n", encoding="utf-8")
        (self.app_dir / "config" / "settings.json").write_text('{"theme": "apple", "saved_bitrate": 18000}', encoding="utf-8")
        (self.app_dir / "projects" / "test_user_proj" / "project.json").write_text('{"name": "Client Commercial", "duration": 45.2}', encoding="utf-8")
        (self.app_dir / "projects" / "test_user_proj" / "audio.wav").write_bytes(b"RIFF....WAVEfmt ....data....test_audio_samples")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_manifest_cryptographic_and_metadata_integrity(self):
        """Verifies Ed25519 signature, SHA-256 hashes, sizes, and compatibility metadata."""
        manifest_text = self.manifest_json.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)

        self.assertEqual(manifest["latest_version"], "2.4.1")
        self.assertEqual(manifest["update_type"], "patch")
        self.assertEqual(manifest["minimum_supported_version"], "2.0.0")

        # Verify Ed25519 signature
        sig_hex = manifest["signature"]
        pub_hex = manifest["public_key"]
        self.assertEqual(bytes.fromhex(pub_hex), self.pub_key_bytes)

        canonical_data = dict(manifest)
        canonical_data.pop("signature", None)
        canonical_data.pop("public_key", None)
        canonical_bytes = json.dumps(canonical_data, sort_keys=True, separators=(',', ':')).encode("utf-8")

        is_valid = ed25519_verify(canonical_bytes, bytes.fromhex(sig_hex), self.pub_key_bytes)
        self.assertTrue(is_valid, "Ed25519 signature on update_manifest.json failed verification!")

        # Verify Patch sha256 & size
        patch_size = self.patch_zip.stat().st_size
        patch_sha = hashlib.sha256(self.patch_zip.read_bytes()).hexdigest()
        self.assertEqual(manifest["package_size_bytes"], patch_size)
        self.assertEqual(manifest["sha256"], patch_sha)

        # Verify Full Installer sha256 & size
        setup_size = self.setup_exe.stat().st_size
        hasher = hashlib.sha256()
        with open(self.setup_exe, "rb") as f:
            while chunk := f.read(1024 * 1024):
                hasher.update(chunk)
        setup_sha = hasher.hexdigest()
        self.assertEqual(manifest["packages"]["full"]["package_size_bytes"], setup_size)
        self.assertEqual(manifest["packages"]["full"]["sha256"], setup_sha)

    def test_02_e2e_update_check_download_and_package_size(self):
        """Tests update check, truthful package-size reporting (not 0 B), and signature verification."""
        os.environ["RENDERFLOW_STAGING_MODE"] = "1"
        updater = UpdateManager(app_root=self.app_dir)
        updater.current_version = "2.2.4"
        manifest_url = f"http://127.0.0.1:{self.server_port}/staging_test_manifest_v241.json"

        # Check for update synchronously
        check_res = updater.check_now(force=True, custom_manifest_url=manifest_url)
        self.assertTrue(check_res.get("ok"), f"Check failed: {check_res.get('error_message')}")
        self.assertTrue(check_res.get("update_available"))
        self.assertEqual(check_res.get("latest_version"), "2.4.1")
        self.assertEqual(check_res.get("state"), UpdateState.AVAILABLE)

        # Verify status reports correct package size, not 0 B
        st = updater.get_status()
        pkg_size = st.get("package_size_bytes") or st.get("package_size")
        self.assertEqual(pkg_size, self.patch_zip.stat().st_size)
        self.assertGreater(pkg_size, 500000)
        self.assertTrue(st.get("ok"))

        # Synchronous download
        dl_success = updater.download_update_sync()
        self.assertTrue(dl_success, f"Download failed: {updater.error_message}")
        st_after_dl = updater.get_status()
        self.assertEqual(st_after_dl.get("state"), UpdateState.DOWNLOADED)
        self.assertTrue(updater.downloaded_package_path.exists())
        self.assertEqual(updater.downloaded_package_path.stat().st_size, pkg_size)

    def test_03_patch_application_and_user_data_preservation(self):
        """Applies v2.4.1 patch and verifies all user assets, projects, credentials, and settings are preserved."""
        os.environ["RENDERFLOW_STAGING_MODE"] = "1"
        updater = UpdateManager(app_root=self.app_dir)
        updater.current_version = "2.2.4"
        manifest_url = f"http://127.0.0.1:{self.server_port}/staging_test_manifest_v241.json"

        updater.check_now(force=True, custom_manifest_url=manifest_url)
        updater.download_update_sync()

        # Apply patch update
        apply_res = updater.apply_patch_update()
        self.assertTrue(apply_res.get("ok"), f"apply_patch_update failed: {apply_res}")
        self.assertTrue(apply_res.get("success"), f"apply_patch_update missing success: {apply_res}")
        self.assertEqual(apply_res.get("state"), UpdateState.READY_TO_RESTART)

        # Verify version on disk updated to 2.4.1
        ver_file = self.app_dir / "engine" / "version.py"
        self.assertIn('__version__ = "2.4.1"', ver_file.read_text(encoding="utf-8"))

        # Verify engine/updater.py has -ArgumentList
        updater_code = (self.app_dir / "engine" / "updater.py").read_text(encoding="utf-8")
        self.assertIn("-ArgumentList", updater_code)

        # Verify web/server.py has import time and async sleep in project deletion
        server_code = (self.app_dir / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn("import time", server_code)
        self.assertIn("await asyncio.sleep(0.3)", server_code)

        # Verify web/static/js/app.js has restartPollTimer
        app_js_code = (self.app_dir / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("restartPollTimer", app_js_code)

        # CRITICAL: Verify all user data was preserved intact
        self.assertTrue((self.app_dir / "credentials.json").exists())
        self.assertEqual(
            json.loads((self.app_dir / "credentials.json").read_text(encoding="utf-8"))["api_key"],
            "user_secret_xyz123"
        )
        self.assertTrue((self.app_dir / ".env").exists())
        self.assertIn("SECRET_TOKEN=secure987", (self.app_dir / ".env").read_text(encoding="utf-8"))

        self.assertTrue((self.app_dir / "config" / "settings.json").exists())
        self.assertEqual(
            json.loads((self.app_dir / "config" / "settings.json").read_text(encoding="utf-8"))["theme"],
            "apple"
        )

        user_proj = self.app_dir / "projects" / "test_user_proj"
        self.assertTrue(user_proj.exists())
        self.assertTrue((user_proj / "project.json").exists())
        self.assertTrue((user_proj / "audio.wav").exists())
        self.assertEqual((user_proj / "audio.wav").read_bytes(), b"RIFF....WAVEfmt ....data....test_audio_samples")

    def test_04_restart_script_syntax_and_arguments(self):
        """Verifies the generated PowerShell restart script contains -ArgumentList and safe port buffer."""
        updater = UpdateManager(app_root=self.app_dir)
        success = updater.restart_application(spawn=False)
        self.assertTrue(success)

        restart_ps1 = self.app_dir / ".cache" / "updates" / "restart_helper.ps1"
        self.assertTrue(restart_ps1.exists(), f"Restart script not found at {restart_ps1}")
        script_text = restart_ps1.read_text(encoding="utf-8")

        self.assertIn("Start-Process -FilePath $targetExe -ArgumentList $targetArgs", script_text)
        self.assertIn("Start-Sleep -Milliseconds 1200", script_text)
        self.assertIn("Get-Process -Id $targetPid", script_text)
        self.assertIn("Stop-Process -Id $targetPid -Force", script_text)

    def test_05_live_subprocess_boot_and_post_restart_verification(self):
        """Boots a live server process from the updated installation and verifies running version reports 2.4.1."""
        os.environ["RENDERFLOW_STAGING_MODE"] = "1"
        updater = UpdateManager(app_root=self.app_dir)
        updater.current_version = "2.2.4"
        manifest_url = f"http://127.0.0.1:{self.server_port}/staging_test_manifest_v241.json"
        updater.check_now(force=True, custom_manifest_url=manifest_url)
        updater.download_update_sync()
        updater.apply_patch_update()

        test_port = find_free_port()
        env = os.environ.copy()
        env["RENDERFLOW_PORT"] = str(test_port)
        env["PYTHONPATH"] = str(self.app_dir)

        # Launch server process from the updated installation
        cmd = [sys.executable, "-m", "uvicorn", "web.server:app", "--host", "127.0.0.1", "--port", str(test_port)]
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.app_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        import urllib.request
        import time

        try:
            started = False
            for _ in range(25):
                time.sleep(0.4)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/system_status", timeout=1.0) as resp:
                        if resp.status == 200:
                            started = True
                            break
                except Exception:
                    pass

            if not started:
                # Capture stderr for diagnosis if boot fails
                err_out = proc.stderr.read() if proc.stderr else "No stderr"
                self.fail(f"Updated server failed to start on port {test_port}. Stderr:\n{err_out}")

            # Truthful post-restart running version verification (/api/update/status)
            with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/update/status", timeout=2.0) as resp:
                self.assertEqual(resp.status, 200)
                status_data = json.loads(resp.read().decode("utf-8"))

            self.assertEqual(status_data.get("current_version"), "2.4.1", f"Server running version is not 2.4.1: {status_data}")
            self.assertTrue(status_data.get("ok"), "Server reported ok=False")

        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()

    def test_06_rollback_protection_on_corrupt_patch(self):
        """Simulates patch failure during application and verifies automatic rollback cleanly restores files."""
        updater = UpdateManager(app_root=self.app_dir)
        original_ver = (self.app_dir / "engine" / "version.py").read_text(encoding="utf-8")
        
        # Inject corrupted zip file into download target
        bad_zip = self.app_dir / ".cache" / "updates" / "bad_patch.zip"
        bad_zip.parent.mkdir(parents=True, exist_ok=True)
        bad_zip.write_bytes(b"CORRUPTED_ZIP_HEADER_NOT_A_VALID_ARCHIVE")

        updater.downloaded_package_path = bad_zip
        updater.state = UpdateState.DOWNLOADED
        updater.selected_package = {"package_size_bytes": 40, "sha256": "fake"}

        result = updater.apply_patch_update()
        self.assertFalse(result.get("ok"))
        self.assertFalse(result.get("success"))
        self.assertEqual(result.get("state"), UpdateState.ERROR)
        self.assertIn("Patch installation error", result.get("error_message", ""))

        # Verify original files were preserved without corruption
        restored_ver = (self.app_dir / "engine" / "version.py").read_text(encoding="utf-8")
        self.assertEqual(original_ver, restored_ver)
        self.assertTrue((self.app_dir / "projects" / "test_user_proj").exists())
        self.assertTrue((self.app_dir / "credentials.json").exists())


if __name__ == "__main__":
    unittest.main()
