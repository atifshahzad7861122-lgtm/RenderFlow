# RenderFlow Release Checklist

This authoritative checklist must be followed for every official release of RenderFlow.

---

## 1. Pre-Release Source & Version Preparation

- [ ] **Authoritative Version Bump:**
  - Update `__version__ = "X.Y.Z"` in `engine/version.py`.
  - Update cachebusters in `web/static/index.html` (`?v=X.Y.Z`).
  - Update version badges in `web/static/index.html` and `web/server.py`.
- [ ] **Run Complete Regression Suite:**
  - Run `python -m unittest engine/test_new_update_system.py` (24/24 pass).
  - Run `python -m unittest engine/test_updater.py` (16/16 pass).
  - Run `python -m unittest engine/test_in_app_updater.py` (15/15 pass).
  - Run `python -m unittest qa/test_project_deletion.py` (5/5 pass).
  - Run `python -m unittest qa/test_updater_connectivity_and_status.py` (11/11 pass).
  - Run `python -m unittest qa/test_v241_hotfix_lifecycle_and_acceptance.py` (6/6 pass).
  - Run `python -m unittest qa/test_real_user_update_lifecycle.py` (5/5 pass).
  - Run `python -m unittest qa/test_github_published_artifacts_and_recovery.py` (5/5 pass).
  *Total: 87/87 tests must pass cleanly.*
- [ ] **Git Working Directory Cleanliness:**
  - Confirm `git status` contains no uncommitted secrets, scratch files, or sensitive credentials.

---

## 2. Artifact Building & Packaging

- [ ] **Build Standalone Windows Setup Installer:**
  - Build `RenderFlow-Setup-vX.Y.Z.exe` using Inno Setup or PyInstaller release toolchain.
  - Verify executable integrity and target architecture (Windows 64-bit).
- [ ] **Build Lightweight Patch Package:**
  - Run `python tools/build_release_patch.py --target X.Y.Z`.
  - Generates `release/RenderFlow-Patch-vX.Y.Z.zip`.
  - Verify patch zip excludes `.env`, `credentials.json`, `.git/`, `.cache/`, and user projects.
- [ ] **Generate Bundle File Manifest:**
  - Run `python tools/generate_bundle_manifest.py --version X.Y.Z`.
  - Output: `release/bundle_manifest_vX.Y.Z.json`.

---

## 3. Cryptographic Signing & Integrity Verification

- [ ] **Calculate Exact SHA-256 Checksums:**
  - Compute SHA-256 for `RenderFlow-Setup-vX.Y.Z.exe`.
  - Compute SHA-256 for `RenderFlow-Patch-vX.Y.Z.zip`.
- [ ] **Generate & Sign `update_manifest.json`:**
  - Run `python tools/sign_release.py --version X.Y.Z --setup release/RenderFlow-Setup-vX.Y.Z.exe --patch release/RenderFlow-Patch-vX.Y.Z.zip`.
  - Verifies Ed25519 signature against `tools/release_public_key.pub`.
  - Confirms canonical JSON byte format.

---

## 4. GitHub Draft Release & Asset Upload

- [ ] **Create GitHub Release as DRAFT:**
  - Tag: `vX.Y.Z`.
  - Flag: `--draft` (MUST remain draft until all smoke tests pass).
  - Title: `RenderFlow vX.Y.Z`.
  - Notes: `release/RELEASE_NOTES_vX.Y.Z.md`.
- [ ] **Upload All 5 Required Assets:**
  - `RenderFlow-Setup-vX.Y.Z.exe`
  - `RenderFlow-Patch-vX.Y.Z.zip`
  - `update_manifest.json`
  - `update_manifest_vX.Y.Z.json`
  - `bundle_manifest_vX.Y.Z.json`
- [ ] **Verify Uploaded Assets:**
  - Verify exact byte counts and remote SHA-256 checksums match local build files.

---

## 5. Isolated Clean Installation & Lifecycle Smoke Test

- [ ] **Test Clean Upgrade from v2.2.4:**
  - Deploy clean mock v2.2.4 installation into isolated directory.
  - Query draft manifest or local HTTP mock server.
  - Download installer package.
  - Verify Ed25519 signature and SHA-256 validation.
  - Launch installer and verify user data (`projects/`, `config/`, `.env`) is 100% intact.
  - Boot server and verify running version reports `vX.Y.Z`.
- [ ] **Confirm Published Assets Untouched:**
  - Ensure previous release assets (e.g., `v2.4.0`) have not been modified or overwritten.

---

## 6. Publication & Post-Release Verification

- [ ] **Publish Release:**
  - Run `gh release edit vX.Y.Z --draft=false`.
- [ ] **Live In-App Verification:**
  - Open RenderFlow client.
  - Click **Settings > Update Center > Check for Updates**.
  - Verify release is discovered, correctly sized, and verified.
