# RenderFlow v2.4.2 — Complete Installer Update Architecture

RenderFlow v2.4.2 delivers the complete-installer software update architecture, replacing legacy partial file extraction with cryptographically signed, full Windows Setup updates.

---

## What's New in v2.4.2

### 1. Complete Installer-Based Update Delivery
- **Standalone Setup Distribution:** In-app updates now download and execute the official self-contained Windows setup installer (`RenderFlow-Setup-v2.4.2.exe`). This eliminates partial overwrite hazards, running DLL lockouts, and fragmented updates.
- **Strict SemVer 2.0.0 Compliance (`engine/updates/semver.py`):** Authoritative version comparison logic supporting `major.minor.patch`, pre-release labels, and build metadata.
- **RFC 8032 Ed25519 Cryptographic Verification (`engine/updates/artifact_verifier.py`):** Canonical JSON manifest serialization with master public key authentication. Untrusted domains or tampered payloads are immediately blocked.

### 2. Redesigned Update Center UI
- **Modernized Action Controls:** Integrated into **⚙️ Settings -> Update Center** with real-time download progress bar, byte counts (`X MB / Y MB`), and dynamic transfer speed telemetry (`KB/s`, `MB/s`).
- **One-Click Diagnostics Viewer:** In-app technical log inspection showing the last 50 events from `.cache/updates/update_diagnostics.log`.
- **Integrated Safe Manual Recovery Guide:** Step-by-step instructions with direct links to official releases, guaranteeing that user projects, media, settings, and credentials remain 100% safe.

### 3. Absolute Data Preservation
- **Pre-Install Configuration Backup:** Automatically backs up `config/settings.json`, `.env`, and `credentials.json` into `.cache/updates/backup/` prior to installer launch.
- **Preserved User Projects:** User timelines, audio recordings, render caches, and AI model weights in `projects/` and `models/` are never overwritten or deleted.
- **User-Space Elevation (`PrivilegesRequired=lowest`):** Installs cleanly in standard user accounts without requiring administrator elevation prompts.

---

## Artifact Integrity & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.4.2.exe` | 1,373,096,907 | `48b77c2382a142b156735d6bff90d855d88522887ed68c3d2afbf6d008c4284e` |
| `RenderFlow-Patch-v2.4.2.zip` | 664,716 | `438791cb11cc411d874ff56d188606d661aafdfdd84dafd07a0c1ed7008f1afa` |
| `update_manifest.json` | 1,613 | (Signed Ed25519: `2f98dd758c733924f1e184f1b2ee0b5b...`) |
| `update_manifest_v2.4.2.json` | 1,613 | (Signed Ed25519: `2f98dd758c733924f1e184f1b2ee0b5b...`) |
| `bundle_manifest_v2.4.2.json` | 74,111 | (432 Files Indexed, 1,511,523,322 Total Bytes) |

**Master Public Key:** `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`

---

## Installation & Upgrade Instructions

### New Users
1. Download **`RenderFlow-Setup-v2.4.2.exe`**.
2. Run the installer and follow the setup wizard.
3. Launch RenderFlow from the desktop shortcut or Start Menu.

### Existing Users (v2.2.4, v2.4.0, or v2.4.1)
1. Open RenderFlow -> **⚙️ Settings** -> **Update Center**.
2. Click **Check for Updates**.
3. When v2.4.2 is detected, click **Download Latest Version**.
4. Click **Launch Installer & Update**. Your workspace, projects, settings, and credentials will be preserved.
