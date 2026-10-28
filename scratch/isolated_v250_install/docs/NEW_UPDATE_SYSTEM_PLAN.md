# RenderFlow — New Update Delivery Architecture Plan
**Document Version:** 1.0.0  
**Target Release:** RenderFlow Complete-Installer Update Pipeline  
**Author:** AI With Atif Core Engineering  
**Status:** Approved for Implementation

---

## 1. Executive Summary & Core Mission

RenderFlow's legacy update mechanism relied primarily on in-place ZIP patch extraction (`RenderFlow-Patch-v*.zip`) targeting loose Python files. While bandwidth-efficient, patch-based updates suffer from inherent structural flaws on Windows:
1. **Operating System File Locking:** Running Python executables, native extensions (`.pyd`), DLLs (`python3.dll`, `_internal/`), and bundled tools (`ffmpeg.exe`, `ffprobe.exe`) cannot be modified in-place while loaded in memory without external process termination and replacement.
2. **Binary and Dependency Immobility:** In-place patch extraction cannot upgrade frozen runtime packages (`RenderingStudio.exe`), PyInstaller bootloaders, newly compiled C-extensions, or bundled AI models (`models/whisper/small`).
3. **Partial Failure Vulnerability:** An interrupted or partially applied patch extraction can corrupt the installation, leaving the user with an inconsistent, non-bootable system.

### The New Architecture Mandate
This engineering plan establishes a **Production-Grade, Complete-Installer-Based Update Delivery System** designed around safe failure, cryptographic verification, user data isolation, and reproducible release automation:
- **Primary Delivery Vehicle:** The authoritative, self-contained Windows Inno Setup installer (`RenderFlow-Setup-v*.exe`).
- **Guaranteed Isolation:** User workspaces (`projects/`), active media, credentials (`.env`, `credentials.json`), custom settings (`config/settings.json`), and render profiles are strictly separated from application binaries and guaranteed untouched.
- **Fail-Safe Cryptographic Pipeline:** Releases must pass RFC 8032 Ed25519 signature checks and SHA-256 integrity verification **prior** to any file execution.
- **Truthful Post-Install Health Checks:** An update is declared successful **only** when the newly installed application boots, passes `/api/system_status`, and reports the target version over `/api/update/status`.

---

## 2. Project Discovery & Environmental Analysis

### 2.1 Execution Modes & Runtime Environments
RenderFlow supports two distinct operational modes on 64-bit Windows systems:
1. **Packaged Standalone Distribution (Frozen Mode):**
   - **Executable:** `RenderingStudio.exe` (PyInstaller onedir distribution located at `{autopf}\RenderFlow by AI With Atif` or a custom user directory).
   - **Bootloader Entry:** [`installer/launcher_entry.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/installer/launcher_entry.py) configures bundled environment paths:
     - `bin/ffmpeg.exe`, `bin/ffprobe.exe` prioritized in `PATH` and `FFMPEG_BINARY`.
     - `models/whisper/small` configured in `WHISPER_MODELS_DIR`.
     - Disables online hub calls (`HF_HUB_OFFLINE=1`, `TRANSCRIPTION_OFFLINE=1`).
     - Launches `engine.server_lifecycle.start_server_with_lifecycle(app)`.
2. **Developer & Source Mode:**
   - **Entry Point:** [`web/server.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/web/server.py) or `run_localhost.bat`.
   - **Framework:** FastAPI + Uvicorn server running on Python 3.10–3.14.

### 2.2 User Data Storage & Isolation Audit
The audit confirms that RenderFlow stores user data locally in file-backed structures:
- **`projects/`:** User workspaces. Contains project metadata (`project.json`), timeline definitions, imported audio/video, caption styles, and final rendered videos (`render_output/`). **Must never be touched or removed.**
- **`config/settings.json`:** User preferences, hardware accelerator overrides, default bitrate, and UI theme. **Must never be overwritten with defaults.**
- **`config/render_profiles.json`:** Hardware encoding presets (NVENC, AMF, QSV, CPU).
- **`.env`:** Secure AI provider credentials (Deepgram, Groq, OpenAI, Anthropic, ElevenLabs) managed by [`engine/credentials_manager.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/credentials_manager.py).
- **`credentials.json`:** Secondary local credential store.
- **`.renderflow_instance.json`:** Ephemeral single-instance runtime lock managed by [`engine/server_lifecycle.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/server_lifecycle.py).
- **`.cache/updates/`:** Staging directory for update downloads, manifests, and logs.

### 2.3 Installer Technology
- **Engine:** Inno Setup 6 (`installer/RenderingStudioSetup_v*.iss`).
- **AppId:** `{{9F82A4C1-4B9E-431A-9721-5082E004BA2B}`.
- **Default Path:** `{autopf}\RenderFlow by AI With Atif` (`PrivilegesRequired=lowest`).
- **Excludes Clause:** `projects\*`, `config\settings.json`, `*.key`.
- **Command-Line Capabilities:** Inno Setup natively supports:
  - `/SILENT` / `/VERYSILENT`: Background execution without wizard prompts.
  - `/NORESTART`: Prevents unintended system reboots.
  - `/CLOSEAPPLICATIONS`: Prompts running apps to close or signals them gracefully.
  - `/DIR="..."`: Overrides target directory.
  - `/LOG="..."`: Emits detailed installation step logs.

### 2.4 Supported Operating Systems
- **Windows 10 (64-bit):** Version 1809 (Build 17763) or higher.
- **Windows 11 (64-bit):** All builds.
- **Architecture:** `x64` (`x64compatible`).

---

## 3. Modular Subsystem Architecture

The new update engine is located in a dedicated, decoupled package: [`engine/updates/`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/updates).

```
engine/updates/
├── __init__.py               # Public package interface & exports
├── models.py                 # Immutable data classes & state enumerations
├── semver.py                 # RFC-compliant SemVer parser & comparator
├── manifest_validator.py     # Schema validation, release filtering, compatibility
├── download_service.py       # Resilient HTTP chunked streaming with retry & speed calc
├── artifact_verifier.py      # Ed25519 cryptographic & SHA-256 verification
├── installer_launcher.py     # Safe process shutdown & Inno Setup execution
├── post_update_verifier.py   # Health checking & post-restart version validation
├── recovery_service.py       # Diagnostic logging, error capture & manual recovery
└── update_service.py         # Thread-safe facade & state machine controller
```

### Component Responsibilities

| Component | Responsibility | Failure Handling |
| :--- | :--- | :--- |
| **`UpdateService`** | Thread-safe coordinator, public API facade, and state machine manager. | Maintains state, ensures reentrant safety with locks, never raises unhandled exceptions. |
| **`ReleaseManifestValidator`** | Queries GitHub API `/releases/latest`, parses manifest metadata, filters drafts/prereleases. | Handles GitHub rate limits (HTTP 403), connection timeouts, and missing assets. Never reports "up to date" on failure. |
| **`SecureDownloadService`** | Streams installer to `.cache/updates/downloads/`, tracks progress, bytes, and transfer speed. | Auto-retries on connection drops; enforces timeout boundaries; cleans up incomplete downloads. |
| **`ArtifactVerifier`** | Computes SHA-256 hash; authenticates Ed25519 digital signature against pinned public key. | Immediately quarantines/deletes invalid downloads; blocks launcher if signature or checksum mismatches. |
| **`InstallerLauncher`** | Interacts with `server_lifecycle` to shut down server cleanly, release port 8000, and launch installer. | Verifies binary existence before exit; supports attended and silent modes; records launch failures in diagnostic log. |
| **`PostUpdateVerifier`** | Executes health check against `/api/system_status` and `/api/update/status`. | Bounded polling (up to 45s); flags version mismatches; prevents false-positive success notifications. |
| **`UpdateRecoveryService`** | Centralizes diagnostics in `.cache/updates/update_diagnostics.log`. Generates user-actionable recovery guides. | Always accessible even in offline mode; provides direct links to GitHub Releases. |

---

## 4. State Machine Specification

The updater operates as a deterministic, bounded state machine:

```
[IDLE] ──(check_for_updates)──► [CHECKING]
                                  │
         ┌────────────────────────┴────────────────────────┐
         ▼                                                 ▼
   [UP_TO_DATE]                                    [UPDATE_AVAILABLE]
         │                                                 │
   (user re-check)                                   (start_download)
         │                                                 │
         └────────────────────────┐                        ▼
                                  │                  [DOWNLOADING]
                                  │                        │
                                  │                (download finished)
                                  │                        │
                                  │                        ▼
                                  │                   [VERIFYING]
                                  │                        │
                                  │                (checksum & sig ok)
                                  │                        │
                                  │                        ▼
                                  │                [READY_TO_INSTALL]
                                  │                        │
                                  │                (launch_installer)
                                  │                        │
                                  │                        ▼
                                  │                   [INSTALLING]
                                  │                        │
                                  │                (backend restarted)
                                  │                        │
                                  │                        ▼
                                  │               [VERIFYING_INSTALL]
                                  │                        │
                                  │                 (version matches)
                                  │                        │
                                  │                        ▼
                                  │                    [SUCCESS]
                                  │                        │
                                  └────────────────────────┘
```

### Explicit Error States
Every active phase has an explicit, non-fatal error state that provides actionable diagnostics and allows user retries:
- `CHECKING` -> `CHECK_FAILED`
- `DOWNLOADING` -> `DOWNLOAD_FAILED`
- `VERIFYING` -> `VERIFICATION_FAILED`
- `READY_TO_INSTALL` / `INSTALLING` -> `INSTALL_FAILED`
- `VERIFYING_INSTALL` -> `VERIFY_FAILED`

---

## 5. Security & Cryptographic Integrity

### 5.1 Pinned Master Public Key
Authentication relies on RFC 8032 Ed25519 digital signatures with the pinned authoritative key:
```
661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e
```
Verification is performed using [`engine/crypto_ed25519.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/crypto_ed25519.py), a pure-Python, zero-dependency implementation.

### 5.2 Canonical Manifest Serialization
Signatures are validated against the canonical JSON bytes of the manifest, sorted by key, stripped of formatting whitespace, and excluding the signature and public key fields:
```python
clean = {k: v for k, v in manifest.items() if k not in ("signature", "signature_ed25519", "public_key")}
canonical_bytes = json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

### 5.3 URL and Domain Allowlisting
Installer downloads are strictly constrained to trusted GitHub domains:
- `github.com`
- `objects.githubusercontent.com`
- `github-releases.githubusercontent.com`
- `api.github.com`

Any asset URL resolving outside these domains is immediately rejected with a security violation error.

---

## 6. Migration Strategy & Backward Compatibility

To avoid breaking existing frontend clients and automated tests:
1. **Facade Compatibility:** [`engine/updater.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/engine/updater.py) will remain in place as a backward-compatible wrapper that forwards calls to `engine.updates.UpdateService`.
2. **API Endpoint Preservation:** All existing endpoints in [`web/server.py`](file:///f:/yt%20tool/Rendering%20Engine%20By%20Ai%20With%20Atif%20-%20Copy/web/server.py) (`/api/update/status`, `/api/update/check`, `/api/update/download`, `/api/update/cancel`, `/api/update/install_full`, `/api/update/restart`) will be maintained and mapped cleanly to the new subsystem.
3. **Deprecation of In-Place Patching:** Legacy patch endpoints (`/api/update/apply`) will return clear guidance directing the client to the verified installer workflow.
4. **Data Safety Guarantee:** The installer configuration maintains strict exclusions preventing overwrites of `projects/`, `config/settings.json`, and `.env`.

---

## 7. Risk Analysis & Mitigation Matrix

| Risk Scenario | Probability | Impact | Architectural Mitigation |
| :--- | :---: | :---: | :--- |
| **Executable File Locking** | High | Critical | The installer launcher executes the standalone setup wizard, signals the application to close gracefully, and waits for PID termination before file replacement. |
| **Interrupted / Corrupted Download** | Medium | High | Downloads stream to `.part` files; SHA-256 hash and Ed25519 signatures are verified before execution. Corrupt files are deleted. |
| **GitHub API Rate Limiting** | Medium | Medium | Implements short-lived caching (5 minutes) for update checks; falls back gracefully to direct manifest downloads; displays explicit rate-limit messages with retry timers. |
| **Accidental User Data Overwrite** | Low | Critical | Inno Setup script strictly excludes `projects\*` and `config\settings.json`. The launcher creates an automatic backup in `.cache/updates/backup/` before launching setup. |
| **Antivirus False Positives** | Medium | Medium | Detailed logging in `.cache/updates/update_diagnostics.log`; informative UI banners instructing the user on how to unblock or run the installer manually if needed. |

---

## 8. Test Plan & Acceptance Gates

The implementation must pass comprehensive automated and isolated lifecycle test suites:
1. **Unit & Component Testing:**
   - Semantic version parsing, sorting, and edge-case comparisons (`v2.4.0` vs `v2.4.1` vs `v2.4.1-beta`).
   - Manifest schema validation, missing fields, and rate-limit HTTP handling.
   - Ed25519 cryptographic verification and deliberate tampering detection.
   - SHA-256 hash calculation and verification.
2. **Download & Resumption Testing:**
   - Chunked streaming, cancellation, timeout enforcement, and partial download cleanup.
3. **Process & Lifecycle Integration:**
   - Clean shutdown signaling, port 8000 release buffer, and detached installer execution.
   - User data preservation verification across simulated updates.
4. **Post-Install Health Check Simulation:**
   - Verification loop behavior under success, failure, and delayed boot conditions.
5. **Clean Windows Installation Acceptance:**
   - Clean machine simulation confirming full installer execution without dependencies.

---
*End of Plan. Implementation proceeds to Phase 2.*
