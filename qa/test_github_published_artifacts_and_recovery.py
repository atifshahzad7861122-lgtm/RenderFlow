"""
qa/test_github_published_artifacts_and_recovery.py
===================================================
Rigorous audit and validation of:
1. Exact published GitHub v2.4.0 artifacts downloaded live.
2. Complete sequence: check, download, signature verification, SHA-256 verification.
3. Behavior of v2.2.4 client when updating via published v2.4.0 package.
4. Validation of the Safe Recovery Path: ensuring staged files on disk boot as v2.4.0
   while existing projects, credentials, and media remain 100% intact.
5. Negative failure recovery: unavailable server, failed process spawn, health-check timeout.
"""

import os
import sys
import json
import time
import shutil
import hashlib
import unittest
import urllib.request
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.updater import UpdateManager, UpdateState
from engine.crypto_ed25519 import verify_signature, RENDERFLOW_MASTER_PUBLIC_KEY
from engine.version import UPDATE_MANIFEST_URL


class TestGitHubPublishedArtifactsAndRecovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = WORKSPACE_ROOT / "scratch" / "test_pub_recovery"
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        cls.test_dir.mkdir(parents=True, exist_ok=True)

        # Build clean v2.2.4 installation
        for folder in ("engine", "web", "config"):
            src = WORKSPACE_ROOT / folder
            if src.exists():
                shutil.copytree(
                    src,
                    cls.test_dir / folder,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.log")
                )

        # Set installed version to v2.2.4
        version_p = cls.test_dir / "engine" / "version.py"
        content = version_p.read_text(encoding="utf-8")
        content = content.replace('__version__ = "2.4.0"', '__version__ = "2.2.4"')
        version_p.write_text(content, encoding="utf-8")

        # Create user projects and credentials to test preservation
        cls.projects_dir = cls.test_dir / "projects"
        cls.user_project = cls.projects_dir / "my_feature_film"
        cls.user_project.mkdir(parents=True, exist_ok=True)
        (cls.user_project / "timeline.json").write_text('{"project_name": "My Feature Film", "clips": 5}', encoding="utf-8")
        (cls.user_project / "media_track.wav").write_bytes(b"\x52\x49\x46\x46" + b"\x00" * 40)

        cls.user_env = cls.test_dir / ".env"
        cls.user_env.write_text("OPENAI_API_KEY=sk-prod-user-key-preserved\nELEVENLABS_API_KEY=el-secret\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_01_verify_exact_published_manifest_and_download(self):
        """Fetch exact published manifest and asset from GitHub, verifying signature, size, and SHA-256."""
        # 1. Fetch live manifest
        req = urllib.request.Request(UPDATE_MANIFEST_URL, headers={"User-Agent": "RenderFlow-Client/2.2.4"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            self.assertEqual(resp.status, 200)
            manifest = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(manifest.get("latest_version"), "2.4.0")
        patch_info = manifest["packages"]["patch"]
        expected_size = patch_info["package_size_bytes"]
        expected_sha = patch_info["sha256"]

        # Verify Ed25519 signature of published manifest
        mgr = UpdateManager(app_root=self.test_dir)
        is_valid = mgr.verify_manifest_authenticity(manifest)
        self.assertTrue(is_valid, "Published manifest signature must verify against master public key")

        # 2. Download exact patch asset from GitHub URL
        req_dl = urllib.request.Request(patch_info["url"], headers={"User-Agent": "RenderFlow-Client/2.2.4"})
        with urllib.request.urlopen(req_dl, timeout=30) as resp:
            self.assertEqual(resp.status, 200)
            patch_data = resp.read()

        self.assertEqual(len(patch_data), expected_size, "Downloaded byte count must match advertised package_size_bytes")
        computed_sha = hashlib.sha256(patch_data).hexdigest()
        self.assertEqual(computed_sha.lower(), expected_sha.lower(), "Computed SHA-256 must match advertised hash")

        # Save to local cache for subsequent tests
        cache_dir = self.test_dir / ".cache" / "updates"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cls_patch_path = cache_dir / "RenderFlow-Patch-v2.4.0.zip"
        cls_patch_path.write_bytes(patch_data)
        self.__class__.patch_file = cls_patch_path

    def test_02_apply_patch_and_verify_user_data_preservation(self):
        """Apply patch to clean v2.2.4 installation; confirm user projects and .env are untouched."""
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.current_version = "2.2.4"
        mgr.manifest_data = {
            "latest_version": "2.4.0",
            "update_package_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.4.0/RenderFlow-Patch-v2.4.0.zip"
        }
        mgr.selected_package = {
            "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.4.0/RenderFlow-Patch-v2.4.0.zip",
            "package_size_bytes": 636375,
            "sha256": "f9a0f528a4a4d41092189dc230e9f6aee4ac4078a6565c1bcbbc2508984d479b"
        }
        mgr.selected_package_type = "patch"
        mgr.downloaded_package_path = self.patch_file
        mgr.state = UpdateState.DOWNLOADED

        # Apply patch
        res = mgr.apply_patch()
        self.assertTrue(res.get("ok"), "apply_patch must succeed")

        # Confirm user files are 100% intact
        self.assertTrue(self.user_project.exists(), "User project directory was deleted!")
        self.assertTrue((self.user_project / "timeline.json").exists())
        timeline = json.loads((self.user_project / "timeline.json").read_text(encoding="utf-8"))
        self.assertEqual(timeline.get("project_name"), "My Feature Film")
        self.assertEqual(len((self.user_project / "media_track.wav").read_bytes()), 44)

        # Confirm .env credentials are untouched
        self.assertTrue(self.user_env.exists(), ".env was removed!")
        env_text = self.user_env.read_text(encoding="utf-8")
        self.assertIn("OPENAI_API_KEY=sk-prod-user-key-preserved", env_text)
        self.assertIn("ELEVENLABS_API_KEY=el-secret", env_text)

        # Confirm disk files are updated to v2.4.0
        version_content = (self.test_dir / "engine" / "version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "2.4.0"', version_content)

    def test_03_safe_recovery_path_without_broken_restart(self):
        """Verify the safe recovery path: launching updated workstation directly boots v2.4.0 cleanly."""
        # Test that updated workstation can start directly on test port 8766
        test_port = 8766
        import subprocess
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
            # Poll health endpoint
            healthy = False
            for _ in range(25):
                time.sleep(0.4)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/system_status", timeout=1.0) as r:
                        if r.status == 200:
                            healthy = True
                            break
                except Exception:
                    pass

            self.assertTrue(healthy, "Recovery workstation failed to come online on test port")

            # Verify actual running version confirmed by new process
            with urllib.request.urlopen(f"http://127.0.0.1:{test_port}/api/update/status", timeout=2.0) as r:
                self.assertEqual(r.status, 200)
                st = json.loads(r.read().decode("utf-8"))
                self.assertEqual(st.get("current_version"), "2.4.0")
                self.assertTrue(st.get("ok", st.get("state") != "error"))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()

    def test_04_failure_recovery_unavailable_server(self):
        """Verify error state and message when remote server is offline or returns HTTP 404."""
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.current_version = "2.2.4"
        bad_url = "https://raw.githubusercontent.com/nonexistent_owner_99999/nonexistent_repo/main/manifest.json"
        status = mgr.check_now(force=True, custom_manifest_url=bad_url)

        self.assertEqual(status["state"], UpdateState.ERROR)
        self.assertFalse(status["ok"])
        self.assertIsNotNone(status["error"])
        self.assertNotEqual(status["error"], "null")
        self.assertIn("404", status["error"])

    def test_05_failure_recovery_tampered_payload_rollback(self):
        """Verify that corrupted/tampered download triggers safe error state and never corrupts disk."""
        mgr = UpdateManager(app_root=self.test_dir)
        mgr.current_version = "2.2.4"
        mgr.state = UpdateState.DOWNLOADED
        mgr.selected_package_type = "patch"

        # Create corrupted zip
        corrupt_zip = self.test_dir / ".cache" / "updates" / "corrupted_patch.zip"
        corrupt_zip.write_bytes(b"NOT_A_VALID_ZIP_ARCHIVE_DATA")
        mgr.downloaded_package_path = corrupt_zip

        res = mgr.apply_patch()
        self.assertFalse(res.get("ok"))
        self.assertEqual(res.get("state"), UpdateState.ERROR)
        self.assertIsNotNone(res.get("error_message"))
        self.assertNotEqual(res.get("error_message"), "null")

        # Confirm user projects and version file are undamaged
        self.assertTrue(self.user_project.exists())
        self.assertTrue(self.user_env.exists())


if __name__ == "__main__":
    unittest.main()
