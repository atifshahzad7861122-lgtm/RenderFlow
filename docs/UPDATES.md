# RenderFlow Software Update Architecture & Recovery Guide

## 1. Overview & Design Philosophy

RenderFlow employs an **authoritative complete-installer update architecture** designed to eliminate partial patching failures, DLL file locks, and broken restart mechanisms on Microsoft Windows.

Instead of performing fragile in-place runtime binary swapping or relying on unreliable PowerShell loops:
1. **GitHub Releases** serves as the authoritative source of truth.
2. The client checks for signed release manifests and verifies them cryptographically before prompting the user.
3. The official standalone Windows setup installer (`RenderFlow-Setup-vX.Y.Z.exe`) is downloaded with streaming SHA-256 validation.
4. The user launches the setup wizard, which cleanly installs the complete updated application while **strictly preserving** all user projects, configurations, media assets, and credentials.

---

## 2. Cryptographic Security Model

Every RenderFlow release is verified using standard, high-assurance cryptography:

* **RFC 8032 Ed25519 Digital Signatures:** Release manifests (`update_manifest.json`) are signed using the RenderFlow Master Release Private Key. The client verifies the signature against the embedded immutable master public key (`tools/release_public_key.pub`).
* **Canonical JSON Formatting:** Manifest bytes are canonicalized (deterministic key ordering, ASCII-safe UTF-8, no whitespace variability) prior to signing and verification.
* **SHA-256 Digest Matching:** Each binary package has its full SHA-256 cryptographic digest verified in chunks during download and validated before the installer can be launched.
* **Domain & Protocol Allowlisting:** Update manifests and binary packages are strictly accepted only over TLS/HTTPS from official domains:
  * `github.com`
  * `objects.githubusercontent.com`
  * `raw.githubusercontent.com`
  Any HTTP or unapproved third-party URL is rejected immediately.

---

## 3. Supported Upgrade Paths

| Source Version | Upgrade Method | Data Preservation | Status |
| :--- | :--- | :--- | :--- |
| **v2.2.0 – v2.2.4** | Complete Windows Installer (`RenderFlow-Setup-*.exe`) | 100% Preserved | Fully Supported |
| **v2.3.0 – v2.4.0** | Complete Windows Installer (`RenderFlow-Setup-*.exe`) | 100% Preserved | Fully Supported |
| **v2.4.1+** | In-App Update Center or Standalone Installer | 100% Preserved | Fully Supported |

### User Data & Workspace Preservation
The installer and updater guarantee that the following workspace locations are never overwritten or deleted:
* `projects/`: User video projects, timeline JSONs, and recorded voice clips.
* `config/settings.json`: UI workstation preferences, bitrate, and preview configurations.
* `credentials.json` & `.env`: Deepgram, OpenAI, ElevenLabs, and AI voice API credentials.
* `output/`: Finished rendered videos and exported media.
* `.cache/updates/backup/`: Automatic safety backup of configurations created before every update.

---

## 4. Update States & UI Truthfulness

RenderFlow's Update Center enforces strict, truthful state management:

1. **Not Checked (`IDLE`):** Displayed on application boot. The UI never reports "Up to date" or displays green badges until an authoritative check succeeds.
2. **Checking (`CHECKING`):** Queries GitHub Releases API.
3. **Up to Date (`UP_TO_DATE`):** Displayed only when the cryptographic check confirms the running version matches or exceeds the latest release on GitHub.
4. **Update Available (`UPDATE_AVAILABLE`):** Displays target version, verified package size, and release notes.
5. **Downloading (`DOWNLOADING`):** Real-time byte count, speed, and percentage progress bar.
6. **Verifying (`VERIFYING`):** Computes complete SHA-256 checksum and verifies Ed25519 digital signature.
7. **Ready to Install (`READY_TO_INSTALL`):** Package verified and staged. The user is prompted to launch the installer.
8. **Installing (`INSTALLING`):** Launches setup wizard with pre-install config backup; gracefully prepares RenderFlow shutdown.
9. **Failed States (`CHECK_FAILED`, `DOWNLOAD_FAILED`, `VERIFICATION_FAILED`):** Clear error messaging with instant **Retry** and **Recovery Guide** options.

---

## 5. Offline & Network-Restricted Environments

RenderFlow does not fail catastrophically when operating in air-gapped or offline environments:
* If GitHub cannot be reached, the UI reports `⚠️ Update server unavailable` without disrupting any video editing or rendering tasks.
* Offline users can manually update at any time by transferring the official `RenderFlow-Setup-vX.Y.Z.exe` on a USB drive and running it.

---

## 6. Safe Manual Recovery Instructions

If an automatic update is interrupted by a power failure, network disconnect, or file permission issue:

1. **Your Data is Safe:** All projects in `projects/` and configurations in `config/` remain intact.
2. **Download Official Installer:** Visit the [RenderFlow Official GitHub Releases](https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases).
3. **Run Setup:** Run `RenderFlow-Setup-vX.Y.Z.exe` and follow the prompt. Choose your existing RenderFlow folder.
4. **Launch RenderFlow:** Launch the app normally. Your workspace and render timelines will load automatically.
5. **Inspect Diagnostic Logs:** Check `.cache/updates/update_diagnostics.log` for details on any failure events.
