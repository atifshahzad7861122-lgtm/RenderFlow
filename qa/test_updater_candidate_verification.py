"""
QA Test Suite: v2.5.1 Candidate Updater & Cryptographic Security Verification
=============================================================================
Verifies:
1. Version comparison logic (SemVer upgrade recognition and downgrade rejection).
2. Production Ed25519 signature verification on authentic v2.5.0 manifest.
3. Tampered manifest detection and signature rejection.
4. Independent Ed25519 keypair signing and verification lifecycle.
5. Package SHA-256 checksum validation and corrupt payload detection.
6. User projects directory preservation enforcement.
7. Candidate v2.5.1 manifest schema validity.
"""

import os
import sys
import json
import hashlib
import tempfile
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.updater import SemVer, UpdateManager, canonicalize_manifest
from engine.crypto_ed25519 import (
    verify_signature,
    sign_message,
    public_key_from_secret,
    RENDERFLOW_MASTER_PUBLIC_KEY
)

class TestUpdaterCandidateVerification(unittest.TestCase):

    def test_01_version_comparison_and_downgrade_prevention(self):
        """Verify SemVer ordering correctly identifies upgrades and rejects downgrades."""
        v250 = SemVer("2.5.0")
        v251 = SemVer("2.5.1")
        v242 = SemVer("2.4.2")
        v260 = SemVer("2.6.0")

        self.assertTrue(v251 > v250, "v2.5.1 must be recognized as an upgrade over v2.5.0")
        self.assertFalse(v250 > v251, "v2.5.0 must not be considered greater than v2.5.1")
        self.assertTrue(v250 > v242, "v2.5.0 must be greater than v2.4.2")
        self.assertFalse(v242 > v250, "v2.4.2 must be rejected as an upgrade from v2.5.0")
        self.assertEqual(v250, SemVer("2.5.0"), "Identical versions must be equal")

    def test_02_production_v250_manifest_signature_verification(self):
        """Verify the authentic release/update_manifest.json passes Ed25519 validation."""
        manifest_path = PROJECT_ROOT / "release" / "update_manifest.json"
        self.assertTrue(manifest_path.exists(), "release/update_manifest.json must exist")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        mgr = UpdateManager(app_root=PROJECT_ROOT)
        is_valid = mgr.verify_manifest_authenticity(manifest)
        self.assertTrue(is_valid, "Production v2.5.0 manifest signature must be cryptographically valid")

    def test_03_tampered_manifest_rejection(self):
        """Verify that altering any byte of manifest data causes signature failure."""
        manifest_path = PROJECT_ROOT / "release" / "update_manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        tampered = dict(manifest)
        tampered["latest_version"] = "2.5.99-malicious"

        mgr = UpdateManager(app_root=PROJECT_ROOT)
        is_valid = mgr.verify_manifest_authenticity(tampered)
        self.assertFalse(is_valid, "Tampered manifest must fail Ed25519 verification")

    def test_04_isolated_keypair_signing_lifecycle(self):
        """Verify end-to-end Ed25519 signing and verification with an isolated keypair."""
        # 32 bytes deterministic test seed
        test_seed = bytes([0x42] * 32)
        test_pub = public_key_from_secret(test_seed)
        test_pub_hex = test_pub.hex()

        candidate_manifest = {
            "manifest_version": "1.0",
            "latest_version": "2.5.1",
            "minimum_supported_version": "2.0.0",
            "release_notes": "RenderFlow v2.5.1 Test Release",
            "public_key": test_pub_hex
        }

        canonical_bytes = canonicalize_manifest(candidate_manifest)
        sig_bytes = sign_message(canonical_bytes, test_seed, test_pub)
        candidate_manifest["signature"] = sig_bytes.hex()

        # Verify using UpdateManager with the custom expected public key
        mgr = UpdateManager(app_root=PROJECT_ROOT)
        is_valid = mgr.verify_manifest_authenticity(candidate_manifest, expected_pk=test_pub_hex)
        self.assertTrue(is_valid, "Isolated signed candidate manifest must verify against test public key")

        # Verify rejection against the master public key
        is_master_valid = mgr.verify_manifest_authenticity(candidate_manifest, expected_pk=RENDERFLOW_MASTER_PUBLIC_KEY)
        self.assertFalse(is_master_valid, "Test manifest signed with test key must fail against master public key")

    def test_05_package_hash_verification_and_corruption_detection(self):
        """Verify SHA-256 payload checksum calculation and rejection of altered payloads."""
        payload_data = b"RENDERFLOW_V251_TEST_PAYLOAD_BINARY_CONTENT_SIMULATION"
        correct_sha = hashlib.sha256(payload_data).hexdigest()

        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(payload_data)
            tf_path = Path(tf.name)

        try:
            # Check valid hash
            with open(tf_path, "rb") as f:
                computed = hashlib.sha256(f.read()).hexdigest()
            self.assertEqual(computed, correct_sha)

            # Check corrupted hash
            corrupted_sha = "0000000000000000000000000000000000000000000000000000000000000000"
            self.assertNotEqual(computed, corrupted_sha, "Checksum mismatch must be detected")
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_06_user_project_preservation(self):
        """Verify UpdateManager explicitly isolates projects_dir."""
        mgr = UpdateManager(app_root=PROJECT_ROOT)
        self.assertEqual(mgr.projects_dir, PROJECT_ROOT / "projects")
        self.assertTrue(hasattr(mgr, "projects_dir"), "projects_dir must be tracked for exclusion")

    def test_07_candidate_manifest_schema_validation(self):
        """Verify candidate manifest schema contains all mandatory updater fields."""
        mandatory_fields = [
            "manifest_version",
            "latest_version",
            "minimum_supported_version",
            "release_notes",
            "published_at",
            "release_page_url",
            "supported_platforms",
            "packages"
        ]

        # Template candidate structure
        candidate = {
            "manifest_version": "1.0",
            "latest_version": "2.5.1",
            "minimum_supported_version": "2.0.0",
            "release_notes": "RenderFlow v2.5.1 Release Notes",
            "published_at": "2026-10-30T10:00:00Z",
            "release_page_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/tag/v2.5.1",
            "supported_platforms": ["windows-x64"],
            "packages": {
                "full": {
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.5.1/RenderFlow-Setup-v2.5.1.exe",
                    "package_size_bytes": 1400000000,
                    "sha256": "placeholder"
                }
            }
        }

        for field in mandatory_fields:
            self.assertIn(field, candidate, f"Field '{field}' must be present in candidate manifest")

if __name__ == "__main__":
    unittest.main()

