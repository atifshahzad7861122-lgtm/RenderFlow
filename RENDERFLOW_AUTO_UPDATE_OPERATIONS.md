# RenderFlow — Permanent Auto-Update Operations Guide (SOP)

**Project:** RenderFlow by AI With Atif / Rendering Studio  
**Target Audience:** Release Engineers, Maintainers, and Systems Developers  
**Scope:** Standard Operating Procedure (SOP) for preparing, signing, testing, and deploying future RenderFlow releases directly into the In-App Update Pipeline.

---

## 1. System Architecture Overview

RenderFlow's update pipeline delivers updates directly to user workstations via two distinct distribution methods:
1. **Lightweight Patches (~500 KB – 5 MB):** Distributed as `.zip` packages for compatible minor and patch upgrades. Patches contain only modified code, assets, and configurations, avoiding full 1.37 GB re-downloads.
2. **Full Windows Standalone Installers (~1.37 GB):** Distributed as Inno Setup `.exe` bundles containing frozen runtime binaries, bundled FFmpeg 9.0.2 essentials, and faster-whisper AI models. Automatically delivered to clean installs and legacy versions prior to v2.0.0.

```
                           +----------------------------------------+
                           |  https://raw.githubusercontent.com/... |
                           |       release/update_manifest.json     |
                           +-------------------+--------------------+
                                               |
                                     (1) HTTPS GET Manifest
                                               |
                                               v
                               +-------------------------------+
                               | RenderFlow Desktop Workstation|
                               |  - Verifies Ed25519 Signature |
                               |  - Compares SemVer > Current  |
                               +---------------+---------------+
                                               |
                   +---------------------------+---------------------------+
                   |                                                       |
        (Current Version >= 2.0.0)                               (Legacy Version < 2.0.0)
                   |                                                       |
                   v                                                       v
     [Patch Package: ~582 KB]                                  [Full Installer: ~1.37 GB]
- Download with % & speed telemetry                       - Download with progress telemetry
- Verify SHA-256 Checksum                                 - Verify SHA-256 Checksum
- Atomic staging & pre-apply backup                       - Launch setup installer detached
- Swap files & single-instance restart                    - User completes standard wizard
- Automatic rollback on write error
```

---

## 2. Cryptographic Security Invariants

### 2.1 RFC 8032 Ed25519 Signature Verification
Every release manifest is cryptographically signed using RenderFlow's master release private key and verified against the embedded public key:
- **Master Public Key (Hex):**
  ```
  661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e
  ```
- **Private Key Storage:** Stored in `tools/release_signing_key.priv`. **NEVER commit, push, or distribute this file.**
- **Canonical Serialization:** Digital signatures are computed over canonical JSON bytes (keys sorted alphabetically, compact separators `','` and `':'`, UTF-8 encoded) excluding the `"signature"` and `"public_key"` fields.

### 2.2 Network Allowlist
The auto-updater enforces HTTPS and strictly restricts download domains in [`engine/updater.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/updater.py) to:
- `raw.githubusercontent.com`
- `github.com`
- `objects.githubusercontent.com`
- `api.github.com`
- `github-releases.githubusercontent.com`

---

## 3. Step-by-Step Procedure for Future Releases (e.g. v2.2.5)

Follow this exact workflow for every subsequent bug fix or feature release:

### Step 1: Update Application Version Metadata
Edit [`engine/version.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/version.py):
```python
__version__ = "2.2.5"
```
Also update `#define MyAppVersion "2.2.5"` in [`installer/RenderingStudioSetup_v2.2.4.iss`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/installer/RenderingStudioSetup_v2.2.4.iss) (or create `RenderingStudioSetup_v2.2.5.iss`).

### Step 2: Build the Candidate Distribution
Compile and assemble the updated distribution directory (e.g. `dist/RenderingStudio_v2.2.5/`):
```powershell
python installer/build_production_bundle.py --version 2.2.5
```

### Step 3: Run Full Regression Suites
Ensure all deterministic tests pass before proceeding:
```powershell
python engine/test_hotfix_regression.py
python -m unittest engine/test_updater.py engine/test_in_app_updater.py
```

### Step 4: Build Release Artifacts & Sign Manifest
Run the release builder tool to generate the lightweight patch, full installer, and Ed25519-signed manifest:
```powershell
python tools/build_release.py `
  --version 2.2.5 `
  --type patch `
  --source-dir dist/RenderingStudio_v2.2.5 `
  --installer-path release/RenderFlow-Setup-v2.2.5.exe `
  --notes "RenderFlow v2.2.5: Summary of changes and improvements." `
  --bundle-source dist/RenderingStudio_v2.2.5
```
This automatically produces:
- `release/RenderFlow-Patch-v2.2.5.zip`
- `release/RenderFlow-Setup-v2.2.5.exe`
- `release/update_manifest_v2.2.5.json` (signed)
- `release/bundle_manifest_v2.2.5.json`

### Step 5: Create and Publish GitHub Release
Using GitHub CLI (`gh`):
```powershell
gh release create v2.2.5 `
  "release/RenderFlow-Setup-v2.2.5.exe" `
  "release/RenderFlow-Patch-v2.2.5.zip" `
  "release/update_manifest.json" `
  "release/bundle_manifest.json" `
  --title "RenderFlow v2.2.5" `
  --notes-file "release/RELEASE_NOTES_v2.2.5.md" `
  --repo atifshahzad7861122-lgtm/RenderFlow
```

### Step 6: Promote the Stable Production Manifest
Copy the signed v2.2.5 manifest to the live update endpoint:
```powershell
# Copy in local release directory
Copy-Item release/update_manifest_v2.2.5.json release/update_manifest.json -Force

# Commit and push to git repository main branch
git -C scratch/rf_git_repo pull origin main
Copy-Item release/update_manifest.json scratch/rf_git_repo/release/update_manifest.json -Force
git -C scratch/rf_git_repo add release/update_manifest.json
git -C scratch/rf_git_repo commit -m "chore(release): update production manifest to v2.2.5"
git -C scratch/rf_git_repo push origin main
```

### Step 7: Verify Live Update Detection
Run the automated lifecycle validation against live GitHub URLs:
```powershell
python tools/test_live_updater_lifecycle.py
```
Ensure all 10 checks return `[PASS]`.

---

## 4. Operational Troubleshooting Playbook

| Issue | Root Cause | Resolution |
| :--- | :--- | :--- |
| **"Cryptographic signature verification failed"** | The manifest was edited after signing, or signed with an unauthorized private key. | Re-run `tools/build_release.py` using `tools/release_signing_key.priv`. Never edit the manifest JSON manually after signing. |
| **"Checksum mismatch"** | Package zip/exe was rebuilt or modified after the manifest was generated. | Recalculate package SHA-256 and regenerate the manifest via `tools/build_release.py`. |
| **"Access Denied: File locked by running process"** | Antivirus or active render process locked a Python binary or DLL. | The updater automatically initiates instant rollback and restores files from backup. Instruct user to close other instances or run `RenderFlow-Setup-vX.X.X.exe`. |
| **"Insufficient disk space"** | Workstation drive has less than `2x package size + 50 MB` free space. | User must free up disk space before downloading. |
| **"Untrusted manifest URL domain"** | Custom manifest URL is not in the allowlist. | Ensure domain is in `ALLOWED_DOMAINS` in [`engine/updater.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/updater.py). For local automated testing, set `RENDERFLOW_STAGING_MODE=1`. |

---

## 5. Summary of Live Infrastructure Configuration

- **GitHub Organization / User:** `atifshahzad7861122-lgtm`
- **Repository:** `RenderFlow`
- **Primary Branch:** `main`
- **Stable In-App Update Manifest URL:**
  ```
  https://raw.githubusercontent.com/atifshahzad7861122-lgtm/RenderFlow/main/release/update_manifest.json
  ```
- **Latest Release Tag:** `v2.4.1`
- **Current Production Build:** `RenderFlow v2.4.1 (Complete Installer Architecture, Self-Contained Windows x64)`
- **Authoritative Release Checklist:** See [RELEASE_CHECKLIST.md](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/RELEASE_CHECKLIST.md)
- **Detailed Update & Recovery Guide:** See [docs/UPDATES.md](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/docs/UPDATES.md)
