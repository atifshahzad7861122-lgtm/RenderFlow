# RenderFlow v2.4.1 — Hotfix Release

RenderFlow v2.4.1 is a critical hotfix release that resolves in-app updater restart failures, false-success reporting, updater package size display, and project deletion async blocking.

---

## What's Fixed in v2.4.1

### 1. In-App Auto-Updater Restart Reliability Fix
- **PowerShell Process Launch Arguments (`-ArgumentList`):** Fixed PowerShell restart script syntax where arguments were erroneously passed inside `-FilePath`, causing Windows process launcher to fail with `The system cannot find the file specified`. Arguments are now strictly passed via `-ArgumentList`.
- **Parent Process Exit Wait Loop & Port Release Buffer:** Added a 10-second wait loop with bounded `Stop-Process -Force` fallback and a 1.2-second TCP port release buffer to prevent TCP port 8000 collisions upon restart.
- **Explicit Success/Error Responses:** Fixed legacy updater compatibility where responses now guarantee `ok: true` and `success: true` booleans along with explicit non-null error messaging, preventing `"Update failed: null"` errors.

### 2. Truthful Post-Restart Verification & UI Status
- **Post-Restart Health Check Polling:** Eliminated premature green success banners. The UI now displays Sky Blue/Amber transition states during update application and polls `/api/system_status` for up to 35 seconds.
- **Verified Running Version Confirmation:** Green installed confirmation (`✓ Successfully updated to RenderFlow v2.4.1!`) is displayed **only** after the newly spawned backend responds with HTTP 200 and confirms running version `2.4.1` via `/api/update/status`.
- **Accurate Package Size Reporting:** Fixed UI display reporting `"0 B"`; package size is now formatted and displayed correctly (`623.4 KB`).

### 3. Project Deletion Async Non-Blocking Fix
- **Async Sleep Restoration:** Fixed `AttributeError: module 'time' has no attribute 'sleep'` in project deletion by replacing synchronous blocking calls with non-blocking `await asyncio.sleep(0.3)` and ensuring `import time` is present.

---

## Artifact Integrity & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.4.1.exe` | 1,372,920,626 | `ed07a1a41deac6306c5c2e0a77e3dd93ff417796ae501246d3c7824dc2c4a593` |
| `RenderFlow-Patch-v2.4.1.zip` | 638,387 | `cdfe4e18128ab7b035b3557078005c82fdf8b30c660e8139c2f166162b07004e` |
| `update_manifest.json` | 1,613 | (Signed Ed25519: `ceaa5dc6a11778c1932b4f4e3c14a511...`) |
| `update_manifest_v2.4.1.json` | 1,613 | (Signed Ed25519: `ceaa5dc6a11778c1932b4f4e3c14a511...`) |
| `bundle_manifest_v2.4.1.json` | 72,580 | (421 Files Indexed, 1,511,434,330 Total Bytes) |

**Signing Key:** Ed25519 Master Public Key: `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`

---

## Installation & Upgrade Instructions

### New Installations
1. Download **`RenderFlow-Setup-v2.4.1.exe`**.
2. Run the installer and follow the on-screen setup wizard.
3. Launch RenderFlow from the desktop shortcut or Start Menu.

### Existing Users (v2.2.4 or v2.4.0)
1. Open RenderFlow.
2. Open **⚙️ Settings** -> **Updates**.
3. Click **Check for Updates**.
4. RenderFlow will detect v2.4.1 as available. Click **Download and Install** to apply the lightweight hotfix patch.
5. If upgrading from an unpatched v2.2.4 or v2.4.0 where the legacy updater process exits before restarting, launch `run_localhost.bat` or `RenderingStudio.exe` once; all updated files are staged cleanly on disk and all projects, media, credentials, and settings remain 100% preserved.
