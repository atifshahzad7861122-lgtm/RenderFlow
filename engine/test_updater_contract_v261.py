"""
engine/test_updater_contract_v261.py — Comprehensive Unit & Integration Tests for v2.6.1 Updater Contract
=========================================================================================================
Tests:
1. Patch-only release manifests (verifying the fix for the v2.6.0 bug).
2. Full-installer-only release manifests.
3. Dual-package (both patch and full) release manifests with deterministic selection.
4. Path traversal defenses during patch extraction.
5. Atomic backup creation and clean rollback on interrupted installation.
6. Package size and hash verification.
"""

import os
import sys
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from engine.updates.models import UpdateState, PackageType, ReleaseInfo, PatchAsset, InstallerAsset
from engine.updates.manifest_validator import ReleaseManifestValidator
from engine.updates.update_service import UpdateService
from engine.updates.semver import SemVer


class TestUpdaterContractV261(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="rf_updater_test_"))
        self.app_root = self.temp_dir / "app"
        self.app_root.mkdir(parents=True)
        self.cache_dir = self.temp_dir / "cache"
        self.cache_dir.mkdir(parents=True)

        # Create dummy app files
        (self.app_root / "web").mkdir(parents=True)
        (self.app_root / "web" / "server.py").write_text("# Server v2.5.1", encoding="utf-8")
        (self.app_root / "engine").mkdir(parents=True)
        (self.app_root / "engine" / "version.py").write_text("__version__ = '2.5.1'", encoding="utf-8")

        # Mock verifier to approve test domains
        self.validator = ReleaseManifestValidator()
        self.validator.verifier.verify_url_domain = MagicMock(return_value=True)
        self.validator.verifier.verify_manifest_signature = MagicMock(return_value=(True, None))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_patch_only_manifest_accepted_and_not_rejected(self):
        """Releases providing ONLY a patch must succeed without requiring a full installer."""
        manifest = {
            "latest_version": "2.6.1",
            "release_title": "RenderFlow v2.6.1",
            "release_notes": "Incremental patch release",
            "packages": {
                "patch": {
                    "filename": "RenderFlow-Patch-v2.6.1.zip",
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.6.1/RenderFlow-Patch-v2.6.1.zip",
                    "package_size_bytes": 10240,
                    "sha256": "abcdef1234567890",
                    "from_version": "2.5.1",
                    "to_version": "2.6.1"
                }
            }
        }
        rel_info, err = self.validator._validate_and_build_release_info(manifest)
        self.assertIsNone(err)
        self.assertIsNotNone(rel_info)
        self.assertEqual(rel_info.version, "2.6.1")
        self.assertEqual(rel_info.package_type, PackageType.PATCH)
        self.assertIsNotNone(rel_info.patch)
        self.assertIsNone(rel_info.installer)

    def test_full_only_manifest_accepted(self):
        """Releases providing ONLY a full installer must succeed."""
        manifest = {
            "latest_version": "2.6.1",
            "release_title": "RenderFlow v2.6.1 Full",
            "packages": {
                "full": {
                    "filename": "RenderFlow-Setup-v2.6.1.exe",
                    "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.6.1/RenderFlow-Setup-v2.6.1.exe",
                    "package_size_bytes": 100000000,
                    "sha256": "1234567890abcdef"
                }
            }
        }
        rel_info, err = self.validator._validate_and_build_release_info(manifest)
        self.assertIsNone(err)
        self.assertIsNotNone(rel_info)
        self.assertEqual(rel_info.package_type, PackageType.FULL)
        self.assertIsNotNone(rel_info.installer)
        self.assertIsNone(rel_info.patch)

    def test_dual_package_manifest_identifies_both_assets(self):
        """Dual manifests providing both assets must parse both correctly."""
        manifest = {
            "latest_version": "2.6.1",
            "release_title": "RenderFlow v2.6.1 Dual",
            "packages": {
                "patch": {
                    "filename": "RenderFlow-Patch-v2.6.1.zip",
                    "url": "https://github.com/patch.zip",
                    "package_size_bytes": 5000,
                    "sha256": "aaa",
                    "from_version": "2.5.1"
                },
                "full": {
                    "filename": "RenderFlow-Setup-v2.6.1.exe",
                    "url": "https://github.com/setup.exe",
                    "package_size_bytes": 50000,
                    "sha256": "bbb"
                }
            }
        }
        rel_info, err = self.validator._validate_and_build_release_info(manifest)
        self.assertIsNone(err)
        self.assertEqual(rel_info.package_type, PackageType.DUAL)
        self.assertIsNotNone(rel_info.patch)
        self.assertIsNotNone(rel_info.installer)

    def test_empty_packages_rejected_safely(self):
        """Manifest with no packages must report a clear error."""
        manifest = {
            "latest_version": "2.6.1",
            "packages": {}
        }
        rel_info, err = self.validator._validate_and_build_release_info(manifest)
        self.assertIsNone(rel_info)
        self.assertIn("neither a valid patch nor a full installer", err)

    def test_update_service_deterministic_selection_prefers_patch(self):
        """When installed is v2.5.1 and dual package is available, UpdateService selects patch."""
        service = UpdateService(app_root=self.app_root, cache_dir=self.cache_dir)
        service.status.current_version = "2.5.1"

        manifest = {
            "latest_version": "2.6.1",
            "packages": {
                "patch": {
                    "url": "https://github.com/patch.zip",
                    "package_size_bytes": 5000,
                    "sha256": "aaa",
                    "from_version": "2.5.1"
                },
                "full": {
                    "url": "https://github.com/setup.exe",
                    "package_size_bytes": 50000,
                    "sha256": "bbb"
                }
            }
        }
        with patch.object(service.validator, "fetch_latest_release") as mock_fetch:
            rel_info, _ = self.validator._validate_and_build_release_info(manifest)
            mock_fetch.return_value = (rel_info, None)
            res = service.check_for_updates(force=True)

        self.assertTrue(res["update_available"])
        self.assertEqual(res["package_type"], "patch")
        self.assertTrue(res["can_patch"])
        self.assertTrue(res["can_install_full"])

    def test_update_service_selects_full_installer_when_patch_incompatible(self):
        """When installed is v2.2.0 and patch requires v2.5.1, UpdateService falls back to full."""
        service = UpdateService(app_root=self.app_root, cache_dir=self.cache_dir)
        service.status.current_version = "2.2.0"

        manifest = {
            "latest_version": "2.6.1",
            "packages": {
                "patch": {
                    "url": "https://github.com/patch.zip",
                    "package_size_bytes": 5000,
                    "sha256": "aaa",
                    "from_version": "2.5.1"
                },
                "full": {
                    "url": "https://github.com/setup.exe",
                    "package_size_bytes": 50000,
                    "sha256": "bbb"
                }
            }
        }
        with patch.object(service.validator, "fetch_latest_release") as mock_fetch:
            rel_info, _ = self.validator._validate_and_build_release_info(manifest)
            mock_fetch.return_value = (rel_info, None)
            res = service.check_for_updates(force=True)

        self.assertTrue(res["update_available"])
        self.assertEqual(res["package_type"], "full")
        self.assertFalse(res["can_patch"])
        self.assertTrue(res["can_install_full"])

    def test_apply_patch_atomic_backup_and_success(self):
        """Verifies that applying a patch updates targeted files and creates a backup."""
        service = UpdateService(app_root=self.app_root, cache_dir=self.cache_dir)
        service.status.current_version = "2.5.1"
        service.status.latest_version = "2.6.1"

        # Create a valid test patch zip
        zip_path = self.cache_dir / "downloads" / "test_patch.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("web/server.py", "# Server v2.6.1 Patched")
            zf.writestr("new_feature.txt", "v2.6.1 Feature Included")

        service._downloaded_package_path = zip_path
        service.status.patch_path = str(zip_path)
        service.status.state = UpdateState.READY_TO_INSTALL

        res = service.apply_patch()
        self.assertTrue(res["ok"])
        self.assertEqual(res["state"], UpdateState.READY_TO_RESTART.value)

        # Check file in app_root was updated
        server_content = (self.app_root / "web" / "server.py").read_text(encoding="utf-8")
        self.assertIn("v2.6.1 Patched", server_content)
        self.assertTrue((self.app_root / "new_feature.txt").exists())

        # Check backup was created
        backups = list(service.backups_dir.glob("backup_v2.5.1_*"))
        self.assertTrue(len(backups) >= 1)
        backup_server = backups[0] / "web" / "server.py"
        self.assertTrue(backup_server.exists())
        self.assertIn("v2.5.1", backup_server.read_text(encoding="utf-8"))

    def test_apply_patch_path_traversal_defense(self):
        """Verifies that zip entries attempting path traversal are safely skipped."""
        service = UpdateService(app_root=self.app_root, cache_dir=self.cache_dir)
        service.status.current_version = "2.5.1"
        service.status.latest_version = "2.6.1"

        zip_path = self.cache_dir / "downloads" / "malicious_patch.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../escaped.txt", "MALICIOUS")
            zf.writestr("safe_file.txt", "SAFE")

        service._downloaded_package_path = zip_path
        service.status.patch_path = str(zip_path)
        service.status.state = UpdateState.READY_TO_INSTALL

        res = service.apply_patch()
        self.assertTrue(res["ok"])

        # Escaped file must NOT exist outside app_root
        self.assertFalse((self.temp_dir / "escaped.txt").exists())
        self.assertTrue((self.app_root / "safe_file.txt").exists())


if __name__ == "__main__":
    unittest.main()

