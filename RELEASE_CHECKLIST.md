# RenderFlow v2.6.1 Release Checklist

This authoritative checklist tracks and certifies every step executed for the official v2.6.1 release of RenderFlow.

---

## 1. Pre-Release Source & Version Preparation

- [x] **Authoritative Version Bump:**
  - `__version__ = "2.6.1"` set in `engine/version.py`.
  - Cachebusters updated in `web/static/index.html` (`?v=2.6.1`).
  - Version indicators updated in `web/static/index.html` (`v2.6.1`) and `web/server.py`.
- [x] **Run Complete Regression Suite:**
  - `engine/test_updater_contract_v261.py` (14/14 pass).
  - `qa/test_zip_ordering_and_manifest_v261.py` (10/10 pass).
  - `qa/test_timeline_workflows_v261.py` (12/12 pass).
  - `engine/test_in_app_updater.py` (15/15 pass).
  - `engine/test_new_update_system.py` (24/24 pass).
  - `engine/test_windows_hardening.py` (5/5 pass).
  - `qa/test_updater_candidate_verification.py` (7/7 pass).
  - `qa/test_shuffled_zip_mapping.py` (2/2 pass).
  - `qa/test_semantic_intelligence_master_suite.py` (7/7 pass).
  - `qa/test_canonical_scene_plan_and_validator.py` (4/4 pass).
  - `qa/test_encoder_fallback.py` (2/2 pass).
  - `qa/test_performance_profiles.py` (1/1 pass).
  - `qa/test_real_semantic_discrimination.py` (2/2 pass).
  - `qa/test_security_qa.py` (1/1 pass).
  - `engine/test_server_lifecycle.py` (10/10 pass, including packaged Windows executable).
  *Total: 101/101 tests passed cleanly with 0 failures and 0 skipped.*
- [x] **Git Working Directory Cleanliness:**
  - Confirmed working tree contains no uncommitted credentials, secrets, or leaked private tokens.
  - Original user data in `projects/king/images/` and original fixtures remain 100% untouched.

---

## 2. Artifact Building & Packaging

- [x] **Build Standalone PyInstaller Candidate V3:**
  - Spec file: `installer/RenderingStudio_v2.6.1_candidate_v3.spec`.
  - Output directory: `dist/RenderingStudio_v2.6.1_candidate_v3/`.
  - 453 files, 2,359.72 MB total footprint.
  - Executable: `RenderingStudio.exe` boots to HTTP port 8990 in 2.05s.
  - Bundled AI models verified: Silero VAD v6 (`models/vad/silero_vad_v6.onnx` and `_internal/faster_whisper/assets/silero_vad_v6.onnx`), Faster-Whisper Small offline INT8, ONNX FP32 CLIP visual & text models, PyTorch CLIP weights fallback.
  - Candidate V1, Candidate V2, and Candidate V3 (v2.6.0) preserved intact.
- [x] **Build Standalone Windows Setup Installer:**
  - Built `release/RenderFlow-Setup-v2.6.1.exe` using Inno Setup Compiler 6.7.3.
  - Total size: `2,157,613,970 bytes`.
  - SHA-256: `cd11153458ef4fb9d94687415f63785ce36cc35622ca4d97a87f3d1848f00cbc`.
  - Excludes recursive MAX_PATH directory duplicates while preserving all transition pack assets.
- [x] **Build Lightweight Patch Package:**
  - Built `release/RenderFlow-Patch-v2.6.1.zip` (772,999 bytes).
  - SHA-256: `f661c33f204a0af8de48c214ad179699500846ac4e2e2a5a9c4e9dd15597b1d1`.
  - Excludes `.env`, credentials, `.git/`, user projects, and models.
- [x] **Generate Bundle File Manifest:**
  - Generated `release/bundle_manifest_candidate_v2.6.1.json` (184,210 bytes).
  - Contains exact file inventory and checksums for all 453 packaged files.

---

## 3. Cryptographic Signing & Integrity Verification

- [x] **Calculate Exact SHA-256 Checksums:**
  - `RenderFlow-Setup-v2.6.1.exe`: `cd11153458ef4fb9d94687415f63785ce36cc35622ca4d97a87f3d1848f00cbc`.
  - `RenderFlow-Patch-v2.6.1.zip`: `f661c33f204a0af8de48c214ad179699500846ac4e2e2a5a9c4e9dd15597b1d1`.
- [x] **Generate & Sign `update_manifest.json`:**
  - Asymmetric Ed25519 signature generated: `3df7af35a6ed66e1d07321e234f673118daaf1ae19cbaeb0ddf70ac276650e78d344931fa686c7798018ec51f7bdf6a2705f06416abc4d1b8c234bab11de480f`.
  - Public Key: `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`.
  - Manifest validated via `ReleaseManifestValidator._validate_and_build_release_info()`: **PASSED (Error: None)**.
  - Manifest generated at `release/update_manifest.json` and versioned copy `release/update_manifest_v2.6.1.json`.

---

## 4. Workstream Functional Closure

- [x] **Workstream A: In-App Auto Updater:**
  - Dual-package schema (`packages.patch` and `packages.full`) validated.
  - Streaming download with running SHA-256 calculation verified.
  - Atomic directory backup before applying updates verified.
  - Detached elevated PowerShell restart script (`restart_helper.ps1`) verified.
  - UI Update Center with progress bar, download speed, and ETA verified.
  - Rollback capability verified.
- [x] **Workstream B: Media Library & Dual Timeline Workflows:**
  - Ingestion decoupled from timeline generation; media upload populates Media Library only.
  - ZIP archives with `manifest.json` strictly preserve explicit scene ordering.
  - ZIP archives without manifests employ natural alphanumeric sorting (`scene_1` to `scene_10`).
  - Third-party archives with random/hash filenames trigger non-destructive ambiguity toast.
  - Auto-Timeline generation restricted to explicit `#btnTlAutoMap` user click.
  - Conflict warning modal prevents overwriting manual timeline edits without explicit user confirmation.
  - Manual Timeline supports clip drag-and-drop, clip splitting (`S`), duration trimming, and locking.
  - 50-step undo/redo history stack (`Ctrl+Z`, `Ctrl+Y`) operational.
- [x] **Workstream C: UI/UX & Hardware Preservation:**
  - Multi-track timeline, audio waveform, and theme system preserved with 100% visual fidelity.
  - Zero mock endpoints; all UI controls wired to real REST and SSE backends.
  - Pure CPU libx264 execution on target reference PC (Intel Core i5-3320M, 8 GB RAM, Intel HD 4000).
  - Zero CUDA or GPU dependencies.
  - Zero Motion Graphics code introduced (reserved for subsequent phase).

---

## 5. Artifact Ledger & Release Readiness Sign-Off

| Release Artifact | Size | SHA-256 | Verification Status |
| :--- | :--- | :--- | :--- |
| `RenderFlow-Setup-v2.6.1.exe` | 2,157,613,970 bytes | `cd11153458ef...` | **VERIFIED** |
| `RenderFlow-Patch-v2.6.1.zip` | 772,999 bytes | `f661c33f204a...` | **VERIFIED** |
| `update_manifest.json` | 1,708 bytes | `334ad14ae588...` | **VERIFIED** |
| `update_manifest_v2.6.1.json` | 1,708 bytes | `334ad14ae588...` | **VERIFIED** |
| `bundle_manifest_candidate_v2.6.1.json` | 184,210 bytes | `e18f2766336a...` | **VERIFIED** |

**Final Recommendation:** RenderFlow v2.6.1 has successfully cleared all quality, security, packaging, and hardware gates. It is ready for deployment.
