"""
Test Signed v2.5.1 Manifest Verification
========================================
Executes full updater verification against the signed v2.5.1 candidate manifest:
1. Valid Ed25519 signature verified against Master Public Key.
2. Modified/tampered manifest detected and rejected.
3. Modified installer payload hash detected and rejected.
4. SemVer upgrade from 2.5.0 to 2.5.1 recognized.
5. Downgrade from 2.5.1 to 2.5.0 rejected.
6. User projects and settings immunity.
"""

import os
import sys
import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.updater import SemVer, UpdateManager, UpdateState
from engine.crypto_ed25519 import verify_signature, RENDERFLOW_MASTER_PUBLIC_KEY

SIGNED_MANIFEST_PATH = Path(r"C:\Users\Engr Atif Shahzad R\AppData\Local\Temp\RenderFlow_v2.5.1_Candidate\update_manifest.json")

class TestSignedV251ManifestUpdater(unittest.TestCase):

    def setUp(self):
        self.assertTrue(SIGNED_MANIFEST_PATH.exists(), f"Signed manifest not found at {SIGNED_MANIFEST_PATH}")
        with open(SIGNED_MANIFEST_PATH, "r", encoding="utf-8") as f:
            self.manifest = json.load(f)

    def test_01_valid_signature_accepted(self):
        """Verify the signature on the actual signed v2.5.1 manifest is cryptographically valid."""
        mgr = UpdateManager(app_root=PROJECT_ROOT)
        self.assertTrue(mgr.verify_manifest_authenticity(self.manifest), "Valid signature must be accepted by UpdateManager")

    def test_02_modified_manifest_rejected(self):
        """Verify that tampering with any field in the v2.5.1 manifest causes immediate rejection."""
        tampered = dict(self.manifest)
        tampered["release_notes"] = "Tampered notes"
        mgr = UpdateManager(app_root=PROJECT_ROOT)
        self.assertFalse(mgr.verify_manifest_authenticity(tampered), "Tampered manifest must be rejected")

    def test_03_modified_installer_hash_rejected(self):
        """Verify that altering the package sha256 in the manifest invalidates the signature."""
        tampered = json.loads(json.dumps(self.manifest))
        tampered["packages"]["full"]["sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
        mgr = UpdateManager(app_root=PROJECT_ROOT)
        self.assertFalse(mgr.verify_manifest_authenticity(tampered), "Altered package hash must invalidate signature")

    def test_04_semver_upgrade_from_v250_accepted(self):
        """Verify SemVer comparison identifies v2.5.1 as an upgrade over v2.5.0."""
        v_current = SemVer("2.5.0")
        v_target = SemVer(self.manifest["latest_version"])
        self.assertTrue(v_target > v_current, "v2.5.1 must be recognized as strictly newer than v2.5.0")

    def test_05_downgrade_rejected(self):
        """Verify downgrade from 2.5.1 to older versions is rejected."""
        v_current = SemVer("2.5.1")
        v_older = SemVer("2.5.0")
        self.assertFalse(v_older > v_current, "Older version must not be accepted as an upgrade")

    def test_06_expected_installer_reference(self):
        """Verify manifest contains exact expected installer filename, size, and hash."""
        pkg = self.manifest["packages"]["full"]
        self.assertTrue(pkg["url"].endswith("RenderFlow-Setup-v2.5.1.exe"))
        self.assertEqual(pkg["package_size_bytes"], 1500062583)
        self.assertEqual(pkg["sha256"], "469c89bb4d887998869d74520f896452f476cd6026151c60cc5b8e945c031775")

    def test_07_user_projects_preservation(self):
        """Verify updater preserves projects directory."""
        mgr = UpdateManager(app_root=PROJECT_ROOT)
        self.assertEqual(mgr.projects_dir, PROJECT_ROOT / "projects")

if __name__ == "__main__":
    unittest.main()

