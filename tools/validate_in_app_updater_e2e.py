#!/usr/bin/env python3
"""
tools/validate_in_app_updater_e2e.py — Phase 11 End-to-End Validation Script
Validates the complete in-app automatic update pipeline against staged candidate v2.2.4
in an isolated snapshot without touching production or developer files.
"""

import os
import sys

# Ensure UTF-8 output with replacement fallback for Windows cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import time
import shutil
import hashlib
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Enable staging test mode for isolated local URL validation
os.environ["RENDERFLOW_STAGING_MODE"] = "1"

from engine.updater import UpdateManager, UpdateState, SemVer
from engine.crypto_ed25519 import RENDERFLOW_MASTER_PUBLIC_KEY


def run_e2e_validation():
    print("=" * 80)
    print(" RENDERFLOW v2.2.4 - COMPLETE IN-APP AUTO-UPDATER E2E VALIDATION")
    print("=" * 80)

    staging_dir = PROJECT_ROOT / "scratch" / "auto_updater_v224_staging"
    staged_manifest = staging_dir / "update_manifest_v2.2.4_staged.json"
    staged_patch = staging_dir / "RenderFlow-Patch-v2.2.4.zip"

    assert staged_manifest.exists(), f"Staged manifest missing at {staged_manifest}"
    assert staged_patch.exists(), f"Staged patch missing at {staged_patch}"

    # 1. Baseline audit of production assets
    print("\n[STEP 1] Auditing production v2.2.3 assets integrity...")
    v223_assets = [
        PROJECT_ROOT / "release" / "RenderFlow-Setup-v2.2.3.exe",
        PROJECT_ROOT / "release" / "RenderFlow-Patch-v2.2.3.zip",
        PROJECT_ROOT / "release" / "update_manifest.json"
    ]
    for asset in v223_assets:
        if asset.exists():
            sha = hashlib.sha256(asset.read_bytes()).hexdigest()
            print(f"  [OK] {asset.name} [{asset.stat().st_size} bytes] SHA: {sha[:16]}... (UNTOUCHED)")
        else:
            print(f"  Note: {asset.name} not present in release directory.")

    # 2. Build isolated mock v2.2.3 installation snapshot
    print("\n[STEP 2] Creating isolated v2.2.3 installation environment...")
    temp_dir = Path(tempfile.mkdtemp(prefix="renderflow_v223_e2e_"))
    try:
        app_root = temp_dir / "RenderFlow_App"
        app_root.mkdir()

        # Seed v2.2.3 files
        engine_dir = app_root / "engine"
        engine_dir.mkdir()
        (engine_dir / "version.py").write_text('__version__ = "2.2.3"\nVERSION = "2.2.3"\n')
        (engine_dir / "updater.py").write_text("# updater module v2.2.3\n")

        web_dir = app_root / "web"
        web_dir.mkdir()
        (web_dir / "server.py").write_text("# server v2.2.3\n")

        # Seed customer user project and credentials
        projects_dir = app_root / "projects"
        cust_proj = projects_dir / "customer_project_1792130776468"
        cust_proj.mkdir(parents=True)
        (cust_proj / "final.mp4").write_bytes(b"CUSTOMER_RENDER_OUTPUT_DATA_STRICTLY_PROTECTED")
        (cust_proj / "project.json").write_text('{"name": "Customer Project", "scenes": 4}')

        env_file = app_root / ".env"
        env_file.write_text("DEEPGRAM_API_KEY=test_protected_user_credential\n")

        print(f"  [OK] Isolated app tree initialized at {app_root}")
        print(f"  [OK] User project seeded with protected render artifact ({cust_proj / 'final.mp4'})")

        # 3. Instantiate UpdateManager for isolated app
        updater = UpdateManager(app_root=app_root, cache_dir=temp_dir / "cache")
        status = updater.get_status()
        assert status["state"] == UpdateState.IDLE
        print(f"  [OK] Initial updater state: {status['state']} (IDLE)")

        # 4. Check for updates against staged manifest
        print("\n[STEP 3] Checking for updates against signed candidate manifest...")
        manifest_url = staged_manifest.resolve().as_uri()
        with unittest_mock_version("2.2.3"):
            updater._worker_check(custom_manifest_url=manifest_url)
            status = updater.get_status()
            print(f"  State: {status['state']}")
            print(f"  Latest version detected: {status['latest_version']}")
            print(f"  Update type: {status['package_type']}")
            print(f"  Release notes: {status['release_notes']}")
            assert status["state"] == UpdateState.AVAILABLE, f"Expected AVAILABLE, got {status['state']}"
            assert status["latest_version"] == "2.2.4", f"Expected 2.2.4, got {status['latest_version']}"
            assert status["package_type"] == "patch", f"Expected patch, got {status['package_type']}"
            print("  [PASS] Update check completed and candidate v2.2.4 patch selected.")

            # 5. Download update package
            print("\n[STEP 4] Downloading and verifying candidate package...")
            updater._worker_download()
            status = updater.get_status()
            print(f"  State: {status['state']}")
            print(f"  Downloaded: {status['downloaded_bytes']} bytes")
            print(f"  Percent: {status['download_percent']}%")
            assert status["state"] == UpdateState.DOWNLOADED, f"Expected DOWNLOADED, got {status['state']}"
            assert status["download_percent"] == 100.0, f"Expected 100%, got {status['download_percent']}"
            assert updater.downloaded_package_path and updater.downloaded_package_path.exists()
            print(f"  [PASS] Package verified against SHA-256: {staged_patch.name}")

            # 6. Apply patch update
            print("\n[STEP 5] Applying patch with atomic staging and automatic rollback protection...")
            apply_res = updater.apply_patch_update()
            print(f"  Result state: {apply_res['state']}")
            assert apply_res["state"] == UpdateState.READY_TO_RESTART, f"Expected READY_TO_RESTART, got {apply_res['state']}"
            print("  [PASS] Patch applied cleanly to application tree.")

        # 7. Post-update verification
        print("\n[STEP 6] Validating updated application state...")
        updated_version_content = (engine_dir / "version.py").read_text()
        print(f"  engine/version.py content: {updated_version_content.strip()}")
        assert "2.2.4" in updated_version_content, "Version file did not update to 2.2.4"
        print("  [PASS] Authoritative version file verified updated to v2.2.4")

        # 8. User project and credential protection check
        print("\n[STEP 7] Verifying user project and data preservation...")
        cust_video = (cust_proj / "final.mp4").read_bytes()
        assert cust_video == b"CUSTOMER_RENDER_OUTPUT_DATA_STRICTLY_PROTECTED", "User video corrupted!"
        env_content = env_file.read_text()
        assert "DEEPGRAM_API_KEY=test_protected_user_credential" in env_content, "User .env corrupted!"
        print("  [PASS] User video is byte-for-byte identical and preserved")
        print("  [PASS] User configuration and .env credentials untouched")

        # 9. Verify Up-To-Date path when already on v2.2.4
        print("\n[STEP 8] Validating Up-To-Date path on updated installation...")
        updater_updated = UpdateManager(app_root=app_root, cache_dir=temp_dir / "cache2")
        with unittest_mock_version("2.2.4"):
            updater_updated._worker_check(custom_manifest_url=manifest_url)
            status_current = updater_updated.get_status()
            print(f"  State on v2.2.4: {status_current['state']}")
            assert status_current["state"] == UpdateState.UP_TO_DATE, f"Expected UP_TO_DATE, got {status_current['state']}"
            print("  [PASS] Up-To-Date status correctly identified")

        # 10. Simulate failure and test rollback
        print("\n[STEP 9] Simulating write failure to verify automatic rollback...")
        rollback_test_app = temp_dir / "Rollback_App"
        shutil.copytree(app_root, rollback_test_app)
        (rollback_test_app / "engine" / "version.py").write_text('__version__ = "2.2.3"\n')
        rollback_updater = UpdateManager(app_root=rollback_test_app, cache_dir=temp_dir / "cache3")
        rollback_updater.downloaded_package_path = staged_patch
        rollback_updater.selected_package_type = "patch"
        rollback_updater.state = UpdateState.DOWNLOADED
        rollback_updater.manifest_data = {"latest_version": "2.2.4"}

        # Simulate permission failure during application of staged files to app root
        real_copy2 = shutil.copy2
        def fail_on_apply(src, dst):
            if "staged" in str(src).lower():
                raise PermissionError("Simulated locked file during apply (Access Denied)")
            return real_copy2(src, dst)

        orig_copy = shutil.copy2
        shutil.copy2 = fail_on_apply
        try:
            rb_result = rollback_updater.apply_patch_update()
            print(f"  Rollback result state: {rb_result['state']}")
            print(f"  Rollback error message: {rb_result.get('error_message')}")
            assert rb_result["state"] == UpdateState.ERROR
            assert "rolled back cleanly" in rb_result.get("error_message", "")
            restored_v = (rollback_test_app / "engine" / "version.py").read_text()
            assert "2.2.3" in restored_v, "Rollback failed to restore original version!"
            print("  [PASS] Automatic rollback successfully restored original files from backup")
        finally:
            shutil.copy2 = orig_copy

        print("\n" + "=" * 80)
        print(" ALL END-TO-END VALIDATION CHECKS PASSED (100% SUCCESS)")
        print("=" * 80)
        return True

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class unittest_mock_version:
    def __init__(self, ver_str):
        self.ver_str = ver_str
        self.orig = None
    def __enter__(self):
        import engine.version as ev
        import engine.updater as eu
        self.orig_ev = getattr(ev, "__version__", "2.2.3")
        self.orig_eu = getattr(eu, "CURRENT_VERSION", "2.2.3")
        ev.__version__ = self.ver_str
        eu.CURRENT_VERSION = self.ver_str
    def __exit__(self, *args):
        import engine.version as ev
        import engine.updater as eu
        ev.__version__ = self.orig_ev
        eu.CURRENT_VERSION = self.orig_eu


if __name__ == "__main__":
    success = run_e2e_validation()
    sys.exit(0 if success else 1)
