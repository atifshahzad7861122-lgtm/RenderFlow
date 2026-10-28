# RenderFlow — In-App Auto-Update System Implementation Plan

**Document:** `docs/IN_APP_AUTO_UPDATER_IMPLEMENTATION_PLAN.md`  
**Date:** 2026-10-17  
**Author:** Senior Video-Rendering Pipeline & Systems Engineer  
**Status:** APPROVED FOR IMPLEMENTATION  

---

## 1. Executive Overview

This document defines the architectural specification and implementation roadmap for the complete in-app automatic update system for the RenderFlow desktop workstation (`RenderFlow by AI With Atif / Rendering Studio`).

The system enables users to check for updates, read release notes, download verified lightweight patches or full installers with real-time speed and progress reporting, apply updates with atomic backup and rollback guarantees, cleanly restart the application, and verify the updated version — with zero risk to user projects, settings, or render outputs.

---

## 2. Repository & Architectural Discovery

### 2.1 Desktop Application & Entry Point
- **Runtime Stack:** Python 3.10+ / 3.14 embedded runtime, FastAPI + Uvicorn server, and modern HTML5 / Vanilla CSS / JavaScript workstation frontend.
- **Entry Points:**
  - Source development: `python web/server.py` or `run_localhost.bat`.
  - Packaged desktop executable: `RenderingStudio.exe` (generated via PyInstaller and Inno Setup 6).
- **Process Lifecycle:** Managed by [`engine/server_lifecycle.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/server_lifecycle.py) using an active lock file (`.renderflow_instance.json`), single-instance PID tracking, Windows Console Control Handler, and port 8000 allocation.

### 2.2 Existing Updater Architecture
- **Core Controller:** [`engine/updater.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/updater.py) defines `UpdateManager`, `SemVer`, and `UpdateState`.
- **Cryptographic Security:** [`engine/crypto_ed25519.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/crypto_ed25519.py) verifies digital signatures against the hardcoded master public key `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`.
- **Release Packaging:** [`tools/build_release.py`](file:///F:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/tools/build_release.py) creates lightweight patch archives (~575 KB) and generates dual-package signed manifests (`packages.patch` and `packages.full`).
- **Production Manifest URL:** Configured in `engine/version.py` as:
  `https://raw.githubusercontent.com/atifshahzad7861122-lgtm/RenderFlow/main/release/update_manifest.json`

### 2.3 Existing Gaps & Deficiencies Identified
1. **Backend Attribute Bug in `web/server.py`:** Endpoints reference `UpdateState.DOWNLOADING.value`, `UpdateState.APPLYING.value`, etc. However, `UpdateState` is a class with string constants (not a Python `Enum`), causing `AttributeError: 'str' object has no attribute 'value'` when hit.
2. **State Casing Inconsistency:** `UpdateManager` emits lowercase states (`"idle"`, `"checking"`, `"available"`, `"downloading"`, `"downloaded"`, `"applying"`, `"ready_to_restart"`, `"installer_ready"`, `"error"`), while existing frontend prototype checks uppercase strings (`state === 'CHECKING'`), preventing state transitions.
3. **Download Progress Telemetry Mismatch:** `UpdateManager.get_status()` returns a dictionary under `download_progress` (`received_bytes`, `total_bytes`, `percent`, `speed_kbps`, `active`), but frontend JS expects flat numeric properties.
4. **Missing Download Cancellation:** No mechanism exists to cancel an active background download safely.
5. **Missing Full Installer Launcher:** While `INSTALLER_READY` is set when downloading a full installer, no method exists to launch the installer detached and cleanly exit RenderFlow.
6. **Restart Coordination:** `restart_application()` spawns a detached PowerShell helper waiting 1.5s for the current PID to close, but `web/server.py` does not trigger graceful server shutdown after the restart endpoint is called, leaving port 8000 occupied and causing a port collision.
7. **Production Manifest Status:** The live remote URL currently returns HTTP 404 (since v2.2.4 is staged locally and has not yet been merged/published remotely). The client must gracefully report this status and provide an isolated staging test configuration without altering production constants.
8. **Hardcoded UI Version in About Modal:** `aboutModal` in `index.html` hardcodes `v2.2.3-STABLE` rather than dynamically reflecting the true installed version.

---

## 3. Reusable Components

| Component | File Path | Reuse Strategy |
| :--- | :--- | :--- |
| **Ed25519 Engine** | `engine/crypto_ed25519.py` | Full reuse. Authentic Ed25519 signature verification against hardcoded master public key. |
| **Atomic Staging & Rollback** | `engine/updater.py` | Full reuse. Existing backup creation, file staging, and rollback routines are sound. |
| **Zip Slip Defense** | `engine/updater.py` | Full reuse. Path normalization and directory traversal blocks. |
| **User Data Isolation** | `engine/updater.py` | Full reuse. `projects/`, `.env`, and credential protection. |
| **Domain Allowlist** | `engine/updater.py` | Full reuse. Strict domain checking for HTTPS GitHub asset downloads. |
| **Release Builder** | `tools/build_release.py` | Full reuse. Dual-package manifest generation and Ed25519 signing. |
| **UI Design System** | `web/static/css/style.css`, `themes.css` | Full reuse. RenderFlow glassmorphism, accent glows, modal overlays, and buttons. |

---

## 4. Required Code Changes

### 4.1 Core Updater Engine (`engine/updater.py`)
- **Add Cancellation Support:**
  - Add `cancel_download()` method to set an abort flag and clean up partial `.part` downloads immediately.
- **Add Full Installer Launch Support:**
  - Add `launch_installer()` method to spawn `RenderFlow-Setup-v2.2.4.exe` detached with `/SILENT` or standard interactive wizard and initiate server exit.
- **Robust Launcher Detection in `restart_application()`:**
  - Check for `RenderingStudio.exe` (frozen), `run_localhost.bat` (Windows script), or `sys.executable` with `web/server.py` (direct Python), ensuring reliable restart across both compiled and development environments.
  - In `restart_helper.ps1`, add explicit process waiting (`Wait-Process -Id <pid> -Timeout 15`) to ensure port 8000 is released before launching the new instance.
- **Staging / Local Test Manifest Support:**
  - Allow `check_for_updates(custom_manifest_url=...)` to accept a local file URI (e.g. `file:///...`) or localhost endpoint when running in explicit staging/test mode, while keeping default production URL strictly intact.

### 4.2 Backend API Router (`web/server.py`)
- **Fix `UpdateState` String Comparison Bug:**
  - Remove invalid `.value` property accesses. Compare directly against string values or `UpdateState` constants.
- **Add `/api/update/cancel` Endpoint:**
  - Provide safe cancellation of active background downloads.
- **Add `/api/update/install_full` Endpoint:**
  - Handle execution of downloaded full setup executables.
- **Coordinate Process Exit on Restart:**
  - In `/api/update/restart`, call `update_manager.restart_app()` and trigger graceful Uvicorn server exit via `app.state.uvicorn_server.should_exit = True` or lifecycle manager after sending response.
- **Normalized Telemetry API:**
  - Ensure `/api/update/status` exposes both structured `download_progress` and normalized top-level metrics for frontend binding.

### 4.3 In-App Update Center UI (`web/static/index.html` & `style.css`)
- **Update Center Location:**
  - Embedded prominently in the Settings Modal (`#settingsModal`) under "Software Updates".
  - Dedicated "Check for Updates" trigger and version display in the About Modal (`#aboutModal`).
- **12 Required UI States:**
  1. *Idle:* Displays installed version, last checked time, and "Check for Updates" button.
  2. *Checking:* Spinner animation, disabled button, "Checking for updates..." feedback.
  3. *Up to Date:* Green checkmark banner, "RenderFlow is up to date", shows current version.
  4. *Update Available:* Vibrant highlight banner, new version badge, package type (Patch / Full Installer), download size, release notes container, and "Download Update" action.
  5. *Downloading:* Active dual-color progress bar, percentage counter, downloaded/total bytes, real-time speed in KB/s or MB/s, and "Cancel" button.
  6. *Verifying Package:* Progress bar at 100%, "Verifying SHA-256 and digital signature...", disabled actions.
  7. *Ready to Install (Patch):* Green verification badge, "Package verified & ready to install", and "Install & Restart Now" action.
  8. *Ready to Install (Full Installer):* Blue package badge, "Full installer ready", and "Run Setup Wizard & Exit" action.
  9. *Installing:* "Creating backup and staging updates...", spinner indicator.
  10. *Restart Required:* "Restarting RenderFlow...", guidance on instance re-initialization.
  11. *Update Successful:* Confirmation toast / banner showing verified active version post-restart.
  12. *Error / Offline:* Red error banner with sanitized error description, "Retry" button, and fallback instructions.

### 4.4 Frontend Reactive Controller (`web/static/js/app.js`)
- Implement normalized state machine mapping both lowercase and uppercase states.
- High-frequency polling (400ms) during active download; low-frequency passive check on settings modal open.
- Graceful handling of server disconnects during restarts.
- Dynamic population of installed version across About and Settings modals.

---

## 5. Security & Safety Analysis

| Threat / Risk | Likelihood | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Forged or Malicious Manifest** | Medium | Critical | Mandatory Ed25519 signature verification against hardcoded master public key before reading or acting upon version metadata. |
| **Tampered Update Package** | Medium | Critical | SHA-256 checksum recalculated over full downloaded byte stream and compared against the signed manifest value before staging. |
| **Man-In-The-Middle (MITM)** | Medium | High | Strict HTTPS protocol enforcement; domain allowlist restricted to authorized GitHub hosting domains. |
| **Path Traversal (Zip Slip)** | Low | High | Member paths normalized; extraction strictly rejects any entry starting with `..`, absolute paths, or escaping destination directory. |
| **User Data Overwrite** | Low | Critical | Extraction and staging logic explicitly excludes `projects/`, `.env`, `credentials.json`, and output folders. |
| **Corrupted Installation / Brick** | Low | High | Automated pre-update backup of `engine/`, `web/`, and `config/` created in `.cache/updates/backup/`. If any copy operation fails, the updater automatically restores all original files and reports error. |
| **Private Key Exposure** | Low | Critical | Private signing key (`release_signing_key.priv`) is strictly excluded from all client builds, patch archives, manifests, and git index. |

---

## 6. Staging & Production Isolation Strategy

- **Production Integrity:** The live update manifest `release/update_manifest.json` and v2.2.3 release assets remain byte-for-byte unchanged.
- **Staging Directory:** An isolated staging area `scratch/auto_updater_v224_staging/` will host mock/test manifests and packages for integration testing.
- **Staging Mode Switch:** The updater will only query staging endpoints when explicitly commanded via test environment variable `RENDERFLOW_UPDATE_MANIFEST_URL` or during programmatic test runs. Production builds default to the official repository URL.

---

## 7. Testing Strategy

1. **Unit & Security Tests (`engine/test_updater.py`):**
   - Manifest signature verification with valid and forged keys.
   - Tampered manifest payload detection.
   - Package SHA-256 mismatch rejection.
   - Path traversal attempt blocking.
   - User data preservation assertions.
   - Download cancellation and disk space pre-checks.
2. **API Endpoint Tests (`engine/test_updater_api.py`):**
   - Test FastAPI `/api/update/*` endpoints for status, check, download, cancel, apply, and restart.
   - Verify non-blocking behavior and concurrency lockouts.
3. **Sandbox Installation & Rollback Test:**
   - Execute update against an isolated v2.2.3 snapshot directory.
   - Simulate write failure midway and verify automatic rollback.
4. **UI & End-to-End Browser Verification:**
   - Verify UI rendering across all 12 states in Settings and About modals.
   - Verify real-time progress bar, speed meter, release notes, and cancellation.
5. **Production Baseline Hash Audit:**
   - Confirm all v2.2.3 production files remain 100% byte-for-byte identical.

---

## 8. Implementation Phases & Milestones

- **Phase 1:** Repository Discovery & Architecture Plan (`docs/IN_APP_AUTO_UPDATER_IMPLEMENTATION_PLAN.md`) -> **COMPLETED**
- **Phase 2:** In-App Update Center UI Enhancement (`index.html`, `style.css`, `app.js`)
- **Phase 3:** Backend API & Updater Engine Integration (`engine/updater.py`, `web/server.py`)
- **Phase 4:** Patch and Full-Package Download & Cancellation Logic
- **Phase 5:** Safe Staging, Backup, and Rollback Helper
- **Phase 6:** Process Restart & Version Confirmation
- **Phase 7:** User Data & Customer Project Protection
- **Phase 8:** Isolated Staging Configuration
- **Phase 9:** Comprehensive Automated Test Suite
- **Phase 10:** Versioned Candidate Packaging
- **Phase 11:** Final End-to-End Validation & Release Report (`RENDERFLOW_IN_APP_AUTO_UPDATER_REPORT.md`)
