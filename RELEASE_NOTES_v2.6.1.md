# RenderFlow v2.6.1 Release Notes

**Version:** 2.6.1  
**Release Date:** November 3, 2026  
**Target Platform:** Windows 10/11 x64 (Pure CPU Software Rendering Architecture)  
**Distribution:** Standalone Desktop Application & In-App Incremental Patch  

---

## Overview

RenderFlow v2.6.1 is an essential reliability, workflow, and updater release. It resolves critical defects in the In-App Auto Updater and Media Ingestion/Timeline subsystems while maintaining 100% visual and ergonomic fidelity with the existing user interface.

This release establishes a deterministic **Dual-Package Architecture** for updates (lightweight ~770 KB incremental ZIP patches vs. full ~2.06 GB / 1.92 GiB standalone installers), completely decouples media ingestion from timeline generation, introduces manifest-aware and natural alphanumeric ZIP ordering, provides an explicit Auto-Timeline workflow with overwrite conflict guards, and expands the Manual Timeline with clip splitting, drag-and-drop sequencing, and a 50-step undo/redo stack.

---

## Major Improvements & New Features

### 1. In-App Auto Updater Overhaul (Workstream A)
- **Dual-Package Architecture:** Releases now publish both an incremental `.zip` patch package for existing installations and a full `.exe` standalone setup installer for fresh machines or major version transitions.
- **Deterministic Package Selection:** The application automatically inspects installation topology. Installed instances pull the lightweight patch (~772 KB), conserving bandwidth and time. If a patch delta is incompatible, it falls back seamlessly to the full installer.
- **Ed25519 Cryptographic Manifest Signing:** All update manifests are cryptographically signed using asymmetric Ed25519 digital signatures verified against the embedded public key (`661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`). Unsigned, forged, or tampered manifests are rejected immediately.
- **Streaming Chunk Verification:** Updates download with running SHA-256 verification and throughput calculation. Corrupted or interrupted payloads are automatically purged.
- **Transactional Atomic Rollback:** Target directories (`engine/`, `web/`, `models/`) are automatically backed up prior to patch extraction. If extraction fails, changes are cleanly reverted.
- **Detached Restart Supervisor (`restart_helper.ps1`):** PowerShell helper tracks the parent process PID, waits for graceful socket release, replaces application files, and relaunches the application without Windows file sharing violations.
- **Modernized Update Center Modal:** Enhanced UI with real-time percentage progress bar, download speed indicator (MB/s), ETA estimation, and restart alert.

### 2. Media Library Decoupling & ZIP Ingestion (Workstream B)
- **Decoupled Ingestion Pipeline:** Media uploads (WAV/MP3 audio or ZIP archives) populate the project Media Library without modifying, erasing, or rearranging the active timeline.
- **Manifest-Aware ZIP Ordering:** ZIP archives containing `manifest.json` maintain exact creator-defined scene sequencing.
- **Natural Alphanumeric Sorting:** Replaced naive ASCII sort with natural sorting. Files such as `scene_1.png` through `scene_10.png` sort in proper numerical order (`1, 2, ..., 9, 10`) instead of lexicographical order (`1, 10, 2`).
- **Ambiguity Detection Toast:** Archives with non-sequential, random hash filenames (e.g., `8f3b2a.png`) are detected and flagged with helpful guidance advising the user to apply Auto-Timeline matching or arrange manually.
- **Path Traversal Protection:** ZIP extraction strictly prevents directory traversal attacks (`../` paths rejected).

### 3. Auto vs. Manual Timeline Workflows (Workstream B)
- **Explicit Auto Timeline Generation:** Auto-Timeline alignment runs only when the user explicitly clicks the **Generate Auto Timeline** button (`#btnTlAutoMap`).
- **Conflict Warning Modal:** Prevents accidental loss of manual edits. If manual edits or locks exist, clicking Auto-Timeline opens a confirmation modal offering **Overwrite & Proceed** or **Cancel**.
- **Clip Splitting at Playhead:** Slices a selected scene at the current playhead (`S` shortcut or `#btnTlSplit`), preserving continuity and transitions.
- **Manual Clip Reordering & Trimming:** Drag-and-drop scene clips on canvas with real-time boundary snapping.
- **Clip Locking:** Protect individual scenes from being modified during auto-rebalancing.
- **Undo / Redo Stack:** 50-step timeline history stack accessible via `Ctrl+Z` and `Ctrl+Y` / `Ctrl+Shift+Z`.

### 4. UI/UX & Backend Integration (Workstream C)
- **Zero UI Regression:** Multi-track canvas (Visual, Audio, Captions), high-DPI waveform visualizer, and custom themes (Studio Dark, Apple Pro, F1 Racing, Muddy Dark) preserved with complete visual fidelity.
- **Active REST Endpoints:** Zero mock endpoints. Every button, toggle, and trigger connects directly to active REST endpoints and real-time Server-Sent Events (SSE) telemetry.
- **Offline Model Hardening:** Fixed Silero VAD packaging defect (`NO_SUCHFILE: silero_vad_v6.onnx`) by bundling model at both `models/vad/` and `_internal/faster_whisper/assets/`. Faster-Whisper Small INT8, ONNX FP32 CLIP models, and PyTorch CLIP weights are fully bundled.

---

## Performance & System Compatibility

- **Pure CPU Software Rendering:** Zero mandatory CUDA or GPU dependencies. Uses multi-threaded `libx264` software encoding and ONNX Runtime CPU execution.
- **Memory Ceiling Compliance:** Peak application RAM during 1080p rendering is ~1.19 GB, comfortably within the 8.0 GB RAM envelope of target legacy hardware (Intel Core i5-3320M, 8 GB RAM, Intel HD Graphics 4000).
- **Fast Cold Boot:** Standalone executable boots to HTTP readiness on port 8990 in ~2.05 seconds.

---

## Known Limitations

1. **Motion Graphics:** Motion Graphics development remains frozen for this release; its dedicated seven-phase roadmap will commence in a subsequent release cycle.
2. **GPU Acceleration:** Dedicated NVENC/QSV hardware encoding is optional; if hardware encoders are absent or unsupported, the engine deterministically falls back to multi-threaded CPU software encoding.
3. **Single Active Render:** To guarantee memory safety on 8 GB systems, concurrent video rendering jobs are queued sequentially.

---

## Installation & Upgrade Instructions

### A. Fresh Installation (Standalone Setup)
1. Download `RenderFlow-Setup-v2.6.1.exe` (2,065,367,886 bytes / 1.92 GiB).
2. Run the installer and choose an installation directory.
3. Launch `RenderFlow` from the desktop shortcut or Start Menu.
4. All AI models (Faster-Whisper, Silero VAD, CLIP) are pre-bundled and ready for instant offline operation.

### B. In-App Upgrade (Existing Users of v2.0.0 – v2.6.0)
1. Launch RenderFlow and open **Settings -> Update Center**.
2. Click **Check for Updates**. The application will detect v2.6.1 and select the lightweight **RenderFlow-Patch-v2.6.1.zip** (~772 KB).
3. Click **Download Update**. Progress is displayed live.
4. Click **Apply Update & Restart**. RenderFlow will create a transactional backup, extract the patch, and relaunch automatically into v2.6.1.

### C. Rollback Instructions
If you need to revert to the previous version after an update:
1. Open **Settings -> Update Center**.
2. If a prior backup exists, the **Rollback to Previous Version** button will be active.
3. Click **Rollback**. The application restores previous directories from `backups/` and restarts.

