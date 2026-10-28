# RenderFlow v2.4.3 — Updater UI Hotfix Release Candidate

RenderFlow v2.4.3 delivers the verified updater UI and state machine hotfix, eliminating stale green "up-to-date" indicators and ensuring complete cryptographic authentication across all update channels.

---

## What's New in v2.4.3

### 1. Truthful Updater State Telemetry & Stale Badge Elimination
- **Stale Green Badge Invalidation (`web/static/js/app.js`):** The `updateLatestBadge` is explicitly reset and hidden whenever a check begins, fails, or remains unverified. The green badge only appears when a remote version has been cryptographically validated with an Ed25519 signature.
- **Strict Verification State (`engine/updates/models.py`, `engine/updates/update_service.py`):** `latest_version` is strictly set to `None` on failed checks or idle state, never falling back to `current_version`. `check_status` explicitly distinguishes `check_failed`, `checking`, `update_available`, and `verified_latest`.
- **API Guardrails (`web/server.py`):** `/api/update/check` strictly requires `is_verified == True` and `state != CHECK_FAILED` before acknowledging a verified up-to-date state.

### 2. Direct Asset CDN Manifest Discovery (`engine/updates/manifest_validator.py`)
- **Rate-Limit Immune Updates:** Primary update discovery queries the official signed `update_manifest.json` directly from GitHub Releases CDN. This bypasses the GitHub REST API's 60 req/hr unauthenticated rate limit.
- **Graceful Multi-Tier Fallback:** If the CDN is temporarily unreachable, the updater falls back to GitHub Releases REST API, followed by repository main-branch manifest discovery.

### 3. Absolute Data Preservation & Seamless Upgrades
- **Zero Data Loss:** All user workspaces (`projects/`), media timelines, render caches, user configurations (`config/settings.json`), and credentials remain 100% untouched.
- **Supported Version Patching:** Versions `>= 2.4.0` (v2.4.0, v2.4.1, v2.4.2) can apply the lightweight patch (`RenderFlow-Patch-v2.4.3.zip`).
- **Legacy Version Protection:** Versions `< 2.4.0` (including v2.2.4) automatically fall back to downloading and launching the full Windows installer (`RenderFlow-Setup-v2.4.3.exe`) to prevent unsafe in-process file overwrites.

---

## Artifact Integrity & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.4.3.exe` | 1,304,672,195 | `c70adc7b0bc7d40dc3c94a436eba0d6dc82e2edb723e20f0a978aa2b1d3293c7` |
| `RenderFlow-Patch-v2.4.3.zip` | 665,078 | `471bae52bbea7c52120486481c57a1697f271adb650c87f4b3451bbae986b696` |
| `update_manifest_v2.4.3.json` | 1,601 | (Signed Ed25519: `58387ee0f83033904897d4888aa50296...`) |
| `bundle_manifest_v2.4.3.json` | 73,478 | (Audited Release Assets) |

**Master Public Key:** `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`

---

## Installation & Upgrade Instructions

### New Users
1. Download **`RenderFlow-Setup-v2.4.3.exe`**.
2. Run the installer and follow the setup wizard.
3. Launch RenderFlow from the desktop shortcut or Start Menu.

### Existing Users (v2.4.0, v2.4.1, or v2.4.2)
1. Open RenderFlow -> **⚙️ Settings** -> **Update Center**.
2. Click **Check for Updates**.
3. When v2.4.3 is detected, click **Download Latest Version**.
4. Click **Apply Update & Restart**.

### Legacy Users (v2.2.4)
1. Run **`RenderFlow-Setup-v2.4.3.exe`** directly over the existing installation. All existing projects and media will be preserved.
