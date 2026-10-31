# RenderFlow v2.5.1 — Candidate Installer Integrity & Packaging Audit Report

**Date:** 2026-10-30  
**Repository Branch:** `feature/v2.5.1-ai-sync-and-preview-fix`  
**Development Commit:** `89dcc4f`  
**Compiler:** Inno Setup 6 (Engine v6.7.3)  
**Status:** **COMPILED & VERIFIED (ISOLATED STAGING CONFIRMED)**

---

## 1. Executive Summary

A standalone Windows production installer candidate for **RenderFlow v2.5.1** was compiled using the official Inno Setup 6 toolchain. To avoid workspace disk exhaustion on Drive `F:\` and to maintain absolute release isolation, compilation was staged on Drive `C:\` in an isolated directory.

The active production release assets (`release/RenderFlow-Setup-v2.5.0.exe` and `release/update_manifest.json`) were monitored and remained **100% untouched and bit-for-bit identical to baseline**.

---

## 2. Cryptographic Checksum & Dimension Verification

### 2.1 Candidate Release Artifacts (v2.5.1)

| Artifact | Staging File Path | Exact Size (Bytes) | Size (MB) | SHA-256 Hash |
| :--- | :--- | :--- | :--- | :--- |
| **Setup Candidate** | `C:\Users\Engr Atif Shahzad R\AppData\Local\Temp\RenderFlow_v2.5.1_Candidate\RenderFlow-Setup-v2.5.1.exe` | **1,500,062,583** | **1,430.57 MB** | `469c89bb4d887998869d74520f896452f476cd6026151c60cc5b8e945c031775` |
| **Update Manifest** | `C:\Users\Engr Atif Shahzad R\AppData\Local\Temp\RenderFlow_v2.5.1_Candidate\update_manifest_v2.5.1_candidate.json` | **1,192** | **1.16 KB** | `5ca62e5572a129031c69c6762fb1aa369c02ff56da14aa90e66ec3aa044439c2` |

### 2.2 Baseline Production Release Artifacts (v2.5.0) — Strict Baseline Verification

| Production Asset | Tracked Repository Path | Recorded Baseline SHA-256 | Current Post-Compile SHA-256 | Status |
| :--- | :--- | :--- | :--- | :--- |
| **v2.5.0 Installer** | `release/RenderFlow-Setup-v2.5.0.exe` | `4f65d9a3a0600cd3a0a16d96866f8274ef031a674a0e9453656b032df20063d7` | `4f65d9a3a0600cd3a0a16d96866f8274ef031a674a0e9453656b032df20063d7` | **100% MATCH (UNTOUCHED)** |
| **v2.5.0 Manifest** | `release/update_manifest.json` | `f00c29d93c9e5f97df39eb7fe349db24d791c3045a284c885ef063479c72f232` | `f00c29d93c9e5f97df39eb7fe349db24d791c3045a284c885ef063479c72f232` | **100% MATCH (UNTOUCHED)** |

---

## 3. PE File Header & Metadata Inspection

Inspection of the compiled executable PE header via Windows API:
```powershell
(Get-Item 'C:\Users\Engr Atif Shahzad R\AppData\Local\Temp\RenderFlow_v2.5.1_Candidate\RenderFlow-Setup-v2.5.1.exe').VersionInfo
```
- **Product Name:** `RenderFlow by AI With Atif`
- **Product Version:** `2.5.1`
- **File Description:** `RenderFlow by AI With Atif Setup`
- **Compiler Version:** `Inno Setup 6.7.3`
- **Architecture:** `x64 (Windows 64-bit native)`

---

## 4. Payload Contents & Bundled Runtime Verification

The installer package embeds and extracts the full production runtime payload:
1. **Core Executable & Launchers:** `RenderingStudio.exe`, `RenderFlow.bat`, `RenderingStudio.bat`.
2. **Media Processing Binaries:** Bundled static 64-bit `ffmpeg.exe` and `ffprobe.exe` (`bin/`).
3. **Embedded Python Runtime:** Fully packaged Python 3.14 runtime environment (`_internal/`) bundling PySide6, Torch, OpenCV (`cv2`), PyAV (`av`), NumPy, and CTranslate2.
4. **AI Models:** Bundled Whisper small model (`models/whisper/small/model.bin`, `config.json`).
5. **Cinematic Transition Pack:** 136 transition video loops and audio norm tracks (`transition_pack/`).
6. **Frontend UI Assets:** Responsive HTML, CSS, JavaScript, and WebGL transition shaders (`web/`).
7. **User Project Isolation:** Setup script explicitly configures installation rules to preserve existing projects in `projects/` without overwriting user data.

---

## 5. Candidate Update Manifest Schema

The staged manifest `update_manifest_v2.5.1_candidate.json` matches the official production schema:
```json
{
  "manifest_version": "1.0",
  "latest_version": "2.5.1",
  "minimum_supported_version": "2.0.0",
  "release_notes": "RenderFlow v2.5.1 — AI Synchronization, Visual Intelligence & Preview Rendering Fix\n• Audio-to-Visual Semantic Synchronization & Unmatched Scene Rejection\n• Multi-Provider AI Gateway (Groq, Gemini, OpenAI, Claude, Local Rule Engine)\n• OpenMontage Stock Visual Discovery & Licensing Metadata Tracking\n• Built-In Preview Transition Shader Compositor with Real-Time Scrub & Seek\n• High-Fidelity Export Parity across 9 Cinematic Transitions\n• RFC 8032 Ed25519 Cryptographic Manifest Authentication",
  "published_at": "2026-10-30T10:45:00Z",
  "release_page_url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/tag/v2.5.1",
  "supported_platforms": ["windows-x64"],
  "packages": {
    "full": {
      "url": "https://github.com/atifshahzad7861122-lgtm/RenderFlow/releases/download/v2.5.1/RenderFlow-Setup-v2.5.1.exe",
      "package_size_bytes": 1500062583,
      "sha256": "469c89bb4d887998869d74520f896452f476cd6026151c60cc5b8e945c031775"
    }
  },
  "signing_status": "PENDING_MAINTAINER_SIGNATURE",
  "public_key": "661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e"
}
```

---

## 6. Conclusion

The RenderFlow v2.5.1 Release Candidate installer is compiled, verified, and safely isolated. Baseline release v2.5.0 remains untouched. The installer is ready for maintainer code-signing and public distribution upon final approval.

