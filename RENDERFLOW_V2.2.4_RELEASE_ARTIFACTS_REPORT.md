# RenderFlow v2.2.4 — Release Artifacts & Verification Report

**Date:** 2026-10-16  
**Status:** READY FOR RELEASE APPROVAL  
**Release Target:** v2.2.4 Hotfix  
**Source Candidate:** `dist/RenderingStudio_v2.2.4_hotfix/`  
**Deployment State:** Staged locally in `release/` — NO remote publication or deployment performed.

---

## Executive Summary

Official release artifacts for **RenderFlow v2.2.4** have been compiled, packaged, cryptographically signed with the project master Ed25519 key, and comprehensively verified.

- **Full Windows Installer:** `RenderFlow-Setup-v2.2.4.exe` (1,372,736,514 bytes) compiled via Inno Setup 6 from the audited candidate directory.
- **Updater Patch Package:** `RenderFlow-Patch-v2.2.4.zip` (575,229 bytes) packaged with high-compression zip, containing 78 updated files across `engine/`, `web/`, and `config/`.
- **Authenticated Manifest:** `release/update_manifest_v2.2.4.json` (1,833 bytes) signed with the master Ed25519 private key (`tools/release_signing_key.priv`), supporting both dual-package schema (`packages.patch` and `packages.full`) and flat legacy schema.
- **Bundle Inventory:** `release/bundle_manifest_v2.2.4.json` (71,775 bytes) inventorying 417 files (1,511,127,010 bytes uncompressed).
- **Existing Production Assets:** Preserved 100% unaltered (v2.2.3 installer, patch, bundle manifest, and `update_manifest.json` have identical SHA-256 hashes to baseline).
- **Remote Operations:** Strictly zero network calls, zero Git tags, zero GitHub releases, and zero remote modifications.

---

## 1. Official v2.2.4 Release Artifacts

| Artifact Role | File Path | File Size (Bytes) | SHA-256 Checksum |
| :--- | :--- | :--- | :--- |
| **Full Windows Installer** | `release/RenderFlow-Setup-v2.2.4.exe` | **1,372,736,514** | `2bd5d3a4c7b563592ed0204363efaae6923df2fff7c92958098854cfaab72473` |
| **Updater Patch Archive** | `release/RenderFlow-Patch-v2.2.4.zip` | **575,229** | `5544ceebe52ee5f2047b7e7eb3f5c063302f00f7643e306d56bded5511b103f9` |
| **Signed Release Manifest** | `release/update_manifest_v2.2.4.json` | **1,833** | `dcd726f51547fff8798dd615f553691a543872f92ebcb70df598a88acb0f3cd8` |
| **Release Bundle Inventory** | `release/bundle_manifest_v2.2.4.json` | **71,775** | `afebbfe1a6575d71465a7ee7a68bb09113e19f5829880d7bcea82ad1e3df39b7` |

---

## 2. Cryptographic Signature & Manifest Validation

The update manifest was signed using the authentic master release signing key (`tools/release_signing_key.priv`) using Ed25519 over the canonical JSON payload (`sort_keys=True, separators=(',', ':')` excluding signature and public key fields).

### Ed25519 Digital Signature
```
135aa9e2f0fcba3985741d5fcf1d101e1279da7c2b8ab7afd5bd5de353c268073a0f3b793c4076a54ac23e79cd3cbb627447b28e75d122bb621db696de29ac0c
```

### Public Key (Matches RENDERFLOW_MASTER_PUBLIC_KEY)
```
661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e
```

### Manifest Schema & Download Asset Mapping
```json
{
  "manifest_version": "1.0",
  "latest_version": "2.2.4",
  "minimum_supported_version": "2.0.0",
  "release_notes": "RenderFlow v2.2.4 Hotfix: Resolved false-positive render verification failures at cut boundaries via frame-accurate discrete seeking and multi-metric visual change detection; Fixed transition verification false negatives for dissolve and wipe transitions; Hardened encoder selection and memory stability on systems with <= 8.0 GiB RAM; Preserved project and transition asset integrity.",
  "published_at": "2026-10-16T15:53:09Z",
  "release_page_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/tag/v2.2.4",
  "update_package_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.2.4/RenderFlow-Patch-v2.2.4.zip",
  "package_size_bytes": 575229,
  "sha256": "5544ceebe52ee5f2047b7e7eb3f5c063302f00f7643e306d56bded5511b103f9",
  "update_type": "patch",
  "supported_platforms": ["windows-x64"],
  "packages": {
    "patch": {
      "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.2.4/RenderFlow-Patch-v2.2.4.zip",
      "package_size_bytes": 575229,
      "sha256": "5544ceebe52ee5f2047b7e7eb3f5c063302f00f7643e306d56bded5511b103f9",
      "applies_to": [">=2.0.0"]
    },
    "full": {
      "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.2.4/RenderFlow-Setup-v2.2.4.exe",
      "package_size_bytes": 1372736514,
      "sha256": "2bd5d3a4c7b563592ed0204363efaae6923df2fff7c92958098854cfaab72473"
    }
  },
  "signature": "135aa9e2f0fcba3985741d5fcf1d101e1279da7c2b8ab7afd5bd5de353c268073a0f3b793c4076a54ac23e79cd3cbb627447b28e75d122bb621db696de29ac0c",
  "public_key": "661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e"
}
```

### Signature Verification Results
- **Direct Ed25519 verification:** `ed25519_verify(canonical_bytes, sig_bytes, pub_bytes)` returns `True`.
- **`UpdateManager.verify_manifest_authenticity()`:** Returns `True`.
- **Tamper resistance test:** Changing any byte in the manifest payload immediately results in `verify_signature` returning `False`.

---

## 3. Installer & Patch Contents Verification

### Full Windows Installer (`RenderFlow-Setup-v2.2.4.exe`)
- **Compiler:** Inno Setup 6.4.1 (Unicode).
- **Target OS:** Windows 10 / 11 (x64).
- **Embedded Components:**
  - Python 3.14 embedded runtime with all dependencies (`cv2`, `torch`, `onnxruntime`, `whisper`, etc.).
  - Bundled FFmpeg 9.0.2 & FFprobe binaries (`bin/ffmpeg.exe`, `bin/ffprobe.exe`).
  - Bundled Whisper speech models (`models/whisper/small/` and `models/whisper/tiny/`).
  - Complete transition pack: 25 keyed MOV transitions + 25 raw MP4 reference assets + transition metadata (`pack.json`, `assets_manifest.json`, `audit_results.json`).
  - Web UI assets (HTML, CSS, JS, icons).
  - Production-audited `engine/verify_output.py` with frame-accurate discrete seeking fix.
  - Correct version identifier: `__version__ = "2.2.4"`.
- **Clean uninstall / project protection:** Inno Setup script preserves user `projects/` directory during upgrades or uninstalls.

### Updater Patch Archive (`RenderFlow-Patch-v2.2.4.zip`)
- **Total Files Included:** 78 files across `engine/`, `web/`, `config/`, and `requirements.txt`.
- **Excluded:** Zero `.pyc`, zero `.git`, zero `__pycache__`, zero user projects, zero keys, zero temporary files.
- **Key Modules Verified in Patch:**
  - `engine/verify_output.py`: SHA-256 `48c762d19a7bd7263d2a4c1a4ea675bab83fb00477c4a27bd93a79ef7cce1023` (includes discrete seek time calculation $T = (N - 0.5) / \text{fps}$ and multi-metric visual change detection).
  - `engine/version.py`: SHA-256 `2581837bef16e80cc71e4b59ed22d012df8f23a21ce8b42a1f982b841b8ad55d` (`__version__ = "2.2.4"`).
  - `engine/fast_pipeline.py`, `engine/render_profiles.py`, `engine/updater.py`, etc.

---

## 4. Update Compatibility & Upgrade Path Verification

We verified the client-side updater behavior using `engine/test_updater.py` and direct `UpdateManager` tests:

| Client Scenario | Current Client Version | Compatibility Rule | Selected Package | Behavior / Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **Existing v2.2.3 Workstation** | `2.2.3` | `latest_sem > current_sem` AND `current_sem >= "2.0.0"` | **Patch** (`RenderFlow-Patch-v2.2.4.zip`, 575 KB) | **Seamless background download** (~0.57 MB), atomic staging, file replacement in-place, zero re-download of 1.3 GB models/transitions. |
| **Older Workstation (v2.2.0 - v2.2.2)** | `2.2.0` - `2.2.2` | `latest_sem > current_sem` AND `current_sem >= "2.0.0"` | **Patch** (`RenderFlow-Patch-v2.2.4.zip`, 575 KB) | Fast in-place patch application. |
| **Legacy Installation (< 2.0.0)** | `1.9.0` | `current_sem < min_supported ("2.0.0")` | **Full Installer** (`RenderFlow-Setup-v2.2.4.exe`, 1.37 GB) | Automatic fallback to full Windows setup executable to ensure complete binary prerequisites. |
| **v2.2.4 Already Installed** | `2.2.4` | `latest_sem == current_sem` | *None* | Reports `UpdateState.UP_TO_DATE`. |

---

## 5. Preservation of Existing Production Assets

All v2.2.3 production files in `release/` were verified before and after packaging to ensure zero drift:

| Asset | Expected SHA-256 Checksum | Verified Current Checksum | Status |
| :--- | :--- | :--- | :--- |
| `release/update_manifest.json` (v2.2.3) | `28646fac7f093118a6ecc529570449c61bbac7816b0cf3266f93a1095e0523e9` | `28646fac7f093118a6ecc529570449c61bbac7816b0cf3266f93a1095e0523e9` | **IDENTICAL (100% Intact)** |
| `release/RenderFlow-Patch-v2.2.3.zip` | `387b1477df58017300c44275c92f7919dae65131bb63af8dd5ff867754fd49c3` | `387b1477df58017300c44275c92f7919dae65131bb63af8dd5ff867754fd49c3` | **IDENTICAL (100% Intact)** |
| `release/RenderFlow-Setup-v2.2.3.exe` | `f38c153ab6f4486f8e57f666c4bc0ad700216bc95b9738b299f0f6c1d98fae21` | `f38c153ab6f4486f8e57f666c4bc0ad700216bc95b9738b299f0f6c1d98fae21` | **IDENTICAL (100% Intact)** |
| `release/bundle_manifest.json` (v2.2.3) | `7b4ccabe632c22e5950f1a5764a679fdb83716ad3d81887e316b115cd75836a2` | `7b4ccabe632c22e5950f1a5764a679fdb83716ad3d81887e316b115cd75836a2` | **IDENTICAL (100% Intact)** |

---

## 6. Publication Safety & Deployment Guardrails

In strict compliance with requirements:
1. **GitHub Releases:** No release drafted or published on GitHub.
2. **Git Tags:** No `v2.2.4` git tag pushed or created.
3. **Asset Uploads:** No files uploaded to GitHub, S3, or any remote server.
4. **Production Update Manifest:** The active update manifest `release/update_manifest.json` remains at version 2.2.3. The v2.2.4 manifest is staged as `release/update_manifest_v2.2.4.json`.
5. **Disk Space:** Workspace drive F: maintained at 4.58 GB free space.

---

## 7. Remaining Blockers

**None.** There are zero technical, cryptographic, packaging, or compatibility blockers.

The release artifacts are fully verified, authenticated, and staged locally awaiting user authorization.

---

## 8. Files Ready for Release Approval

When authorized to publish v2.2.4:
1. `release/RenderFlow-Setup-v2.2.4.exe` (Upload to GitHub Release `v2.2.4` assets)
2. `release/RenderFlow-Patch-v2.2.4.zip` (Upload to GitHub Release `v2.2.4` assets)
3. `release/update_manifest_v2.2.4.json` (Copy to `release/update_manifest.json` and push to `main` branch to activate auto-update)
4. `release/bundle_manifest_v2.2.4.json` (Release audit trail)
