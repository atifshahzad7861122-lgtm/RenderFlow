# RenderFlow v2.4.0 — Master Upgrade V2

RenderFlow v2.4.0 introduces AI Semantic Image Mapping, Narration Intelligence, and comprehensive reliability enhancements across captions, transitions, rendering, and in-app updates.

---

## What's New in v2.4.0

### 1. AI Semantic Image Mapping & Narration Intelligence
- **Intelligent Asset Placement:** Automatic semantic mapping between narration text and uploaded image assets, ensuring content-accurate scene placement even when filenames are shuffled, non-sequential, or misleading.
- **Manual Lock Preservation:** Full respect for user-pinned and locked scene assets during automatic re-mapping.
- **Visual Mood & Taxonomy Detection:** Automatic scene classification (nature, water, urban, conflict, portrait, history) based on visual attributes and color profiles.

### 2. Caption Reliability & Multilingual Excellence
- **Zero-Dropout Boundary Alignment:** 0.0s opening speech protection and trailing silence hold guarantees, eliminating early caption cutoffs.
- **60+ Native Typography Styles:** Full support for kinetic pop, karaoke, editorial, and documentary subtitle styling with libass rendering.
- **Multilingual RTL & Complex Scripts:** Flawless rendering for 9 major script families (English, Urdu, Arabic, Hindi, Spanish, French, German, Chinese, Japanese) with preserved Unicode integrity.
- **Multi-Format Export:** Simultaneous export to SRT, ASS, VTT, and JSON sidecars.

### 3. Production In-App Auto-Updater
- **Ed25519 Cryptographic Verification:** All release manifests and patches are digitally signed with RenderFlow's master key.
- **Lightweight Delta Patching:** Existing v2.0.0+ installations can upgrade via lightweight in-app patch archives (~636 KB) without downloading the full 1.37 GB installer.
- **Atomic Staging & Rollback Protection:** Zero risk of corrupt installations; automated file locking rollback restores original state if interrupted.
- **Truthful Status Reporting:** UI strictly reflects real remote verification status with timestamped confirmation.

---

## Artifact Integrity & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.4.0.exe` | 1,372,914,277 | `82cbc10c80271682edafd10175d53163e904fe732057d4cf7d6d51d2d0b01303` |
| `RenderFlow-Patch-v2.4.0.zip` | 636,375 | `f9a0f528a4a4d41092189dc230e9f6aee4ac4078a6565c1bcbbc2508984d479b` |
| `update_manifest.json` | 1,737 | (Signed Ed25519) |
| `update_manifest_v2.4.0.json` | 1,737 | (Signed Ed25519) |
| `bundle_manifest_v2.4.0.json` | 72,580 | (421 Files Indexed) |

---

## Installation & Upgrade Instructions

### New Installations
1. Download **`RenderFlow-Setup-v2.4.0.exe`**.
2. Run the installer and follow the on-screen setup wizard.
3. Launch RenderFlow from the desktop shortcut or Start Menu.

### Existing Users (v2.2.4 or v2.2.3)
1. Open RenderFlow.
2. Open **⚙️ Settings** -> **Updates**.
3. Click **Check for Updates**.
4. RenderFlow will detect v2.4.0 as available. Click **Download and Install** to apply the lightweight patch.
