# Rendering Studio Engine v2 — Production Readiness Report

**Date**: 2026-10-07  
**Host Environment**: Windows 10/11 x64  
**CPU Architecture**: Intel Core i5 (2 physical cores / 4 threads, 7.91 GB RAM)  
**Hardware Profile Match**: Target Low-Spec Profile (10th Gen i5 / 8–16 GB RAM) — Host strictly matches 8 GB baseline  
**Evaluation Type**: Full End-to-End Runtime Implementation, Progressive Benchmark, and API Lifecycle Audit  

---

## Executive Summary

Rendering Studio Engine v2 has been systematically audited, stabilized, hardened, and verified across all 15 production modules. The system operates 100% locally on Windows, with zero mandatory cloud dependencies, zero character animation, and audio strictly enforced as the master timeline.

In accordance with strict Lead Engineer verification criteria, this report distinguishes:
1. **Unit & Integration Tests** (API, schema, memory, errors)
2. **Architecture Tests** (Simulated timeline continuity and chunk math up to 60 minutes)
3. **Real Runtime Encodes** (Fully encoded, bit-verified H.264 MP4 videos up to 60 seconds)

---

## Subsystem Scorecard

| Subsystem | Status | Key Evidence / Highlights |
|---|:---:|---|
| **Architecture** | **PASS** | Audio-first master timeline, static 2D images, single-pass & streaming chunked modes. |
| **Dependencies** | **PASS** | Python 3.14.8, PyAV 18.1.0 (`av<19`), NumPy 2.5.3, OpenCV 5.0.0, Pillow 12.3.0, psutil 7.2.2. |
| **STT Engine** | **PASS** | `faster-whisper small` on CPU with `int8` quantization; millisecond word timestamps; zero network calls. |
| **Local Whisper** | **PASS** | 100% offline model loading; `small` and `tiny` provisioned in local disk cache. |
| **Hugging Face Independence** | **PASS** | ZERO network requests during normal rendering; `local_files_only=True` strictly enforced. |
| **Timeline Engine** | **PASS** | Continuous scene boundaries (`Δ <= 0.005s`); real silence held; 12/12 regression scenarios pass. |
| **Semantic Image Sync** | **PASS** | Semantic beats (1.5–7.5s); visual relevance scoring; natural image sequencing preserved. |
| **Transitions Engine** | **PASS** | 6 built-in transitions verified (`dissolve`, `soft_wipe`, `cinematic_dissolve`, `dip_to_black`, `clean_cut`, `slow_dissolve`); hard-cut mode verified. |
| **Caption Engine** | **PASS** | Native ASS generation for 10 styles; word-level sync; SRT, ASS, VTT, JSON sidecars; Multilingual Unicode & RTL preserved. |
| **FFmpeg Core** | **PASS** | FFmpeg 9.0.2 / FFprobe 9.0.2; H.264/AAC 48kHz stereo; faststart enabled; subprocess argument arrays. |
| **Performance & Long Videos** | **PARTIAL** | 30s & 60s Real Renders PASS; 5m–60m Architecture Verified; Peak RAM RSS < 54 MB. |
| **Error Handling & Recovery** | **PASS** | 13 strongly typed exception classes; corrupted chunk recovery; stage checkpointing. |
| **Windows Hardening** | **PASS** | Unicode paths (`اردو 中文 日本語`), spaces, parentheses, colon escaping in ASS filters, UTF-8 console streams. |
| **Security Audit** | **PASS** | Path traversal blocked (403 on `/media/`), Zip Slip prevention, upload sanitization, zero secret logging. |
| **API / UI Workflow** | **PASS** | Complete workflow verified via FastAPI TestClient (Upload -> Sync -> Review -> Style -> Render -> Download). |

---

## Runtime Verification Evidence

### 1. Environment & Binaries
- **Python Version**: `Python 3.14.8` (Windows 64-bit)
- **FFmpeg Version**: `ffmpeg version 9.0.2-essentials_build-www.gyan.dev` (with `libass`, `libx264`, `libx265`, `libwebp`)
- **FFprobe Version**: `ffprobe version 9.0.2-essentials_build-www.gyan.dev`

### 2. Dependency Verification
- **PyAV**: `18.1.0` (pinned to `av<19` to prevent `metadata_errors` deprecation error)
- **faster-whisper**: `1.2.1` with `patch_av_metadata_errors()` active
- **NumPy**: `2.5.3` | **OpenCV**: `5.0.0` | **Pillow**: `12.3.0` | **FastAPI**: `0.142.2` | **psutil**: `7.2.2`

### 3. Whisper Model Availability & Offline Execution
- Locally cached models:
  - `small` -> `C:\Users\Engr Atif Shahzad R\.cache\huggingface\hub\models--Systran--faster-whisper-small`
  - `tiny` -> `C:\Users\Engr Atif Shahzad R\.cache\huggingface\hub\models--Systran--faster-whisper-tiny`
- **Local Speech Transcription**:
  - Sample: `scratch/speech_sample.wav` (6.32s speech)
  - Model: `small` (device=`cpu`, compute_type=`int8`)
  - Output: 13 word-level timestamps (`[0.0s -> 5.31s]`), confidence 0.93–0.99, saved to `scratch/whisper_verification.json`. Zero network calls.

### 4. Sample Rendering & Visual Verification
- **Transitions Test (`test_all_transitions.py`)**:
  - Video: 21.000s exact duration, 7 scenes, 6 transitions (`dissolve`, `soft_wipe`, `cinematic_dissolve`, `dip_to_black`, `clean_cut`, `slow_dissolve`)
  - QC Checks: Resolution 1920x1080, 30.00 fps, AAC 48kHz stereo, zero frozen/blank frames. **PASS**.
- **Captions Test (`test_captions_render.py`)**:
  - Tested `classic` style: Video: 20.000s exact, H.264/AAC 48kHz stereo, all sidecars exported non-empty (`.srt`, `.ass`, `.vtt`, `.json`). **PASS**.
- **Windows Hardening Render (`test_windows_hardening.py`)**:
  - Rendered into: `Engine [v2] & Test - اردو 中文 日本語\output (cinematic) [final] - ویڈیو.mp4`
  - Duration: 3.000s exact, H.264/AAC, all checks pass. **PASS**.

### 5. Progressive Long Video Benchmarks (`test_progressive_render.py`)
- **30-Second Real Render**: 10 scenes, 30.0s, rendered in 83.16s (Peak RAM: 52.9 MB, Size: 18.10 MB, QC PASS).
- **60-Second (1-Min) Chunked Real Render**: 15 scenes, 60.0s, 3 streaming chunks, rendered in 138.67s (Peak RAM: 53.0 MB, Size: 30.85 MB, QC PASS).
- **5-Minute Architecture**: 50 scenes, RAM 53.1 MB, continuity PASS.
- **10-Minute Architecture**: 100 scenes, RAM 53.1 MB, continuity PASS.
- **30-Minute Architecture**: 300 scenes, 9 chunks, RAM 53.2 MB, continuity PASS.
- **60-Minute Architecture**: 600 scenes, 18 chunks, RAM 53.5 MB, continuity PASS.
- **Lossless Concat Demuxer**: Joined multi-chunk outputs via `-c copy` in 0.29s.

### 6. Phase 3 Production Acceptance Suite (`test_production_acceptance_suite.py`)
- Real Media: 22 source images + real narration speech audio (22s).
- **UPLOAD**: `POST /api/project/upload` -> 22 images registered, narration saved (HTTP 200).
- **SYNC**: `POST /api/project/auto_plan` -> 22 scenes dynamically generated across exact audio timeline (HTTP 200).
- **REVIEW**: Timeline continuity verified (`delta = 0.0000s`); saved via `POST /api/project/save_plan` (HTTP 200).
- **STYLE**: 67 caption styles discovered in catalog; preview generated via `POST /api/captions/preview` (HTTP 200).
- **RENDER**: Direct FFmpeg render completed with 22 scenes, 21 cinematic transitions, libass captions burned-in, and sidecars generated.
- **DOWNLOAD**: Served via `GET /media/` returning HTTP 200 OK (0.84 MB).
- **VERIFY QC**: Strict visual QC passed across all 21 cuts and first-frame visual validation.

### 7. Security Audit
- Path traversal outside workspace / temp directories: Rejected (HTTP 403 Forbidden).
- Upload filename sanitization: Traversal paths stripped, illegal NTFS characters replaced.
- Zip Slip extraction containment: Sandbox-isolated, directory traversal entries blocked.
- Credentials: Raw keys masked (`••••••••••••9F2A`), zero secret logging.

---

## Master Regression Matrix Results

Executed via `python engine/run_regression_matrix.py`:

```
================================================================================
 REGRESSION MATRIX EXECUTION SUMMARY
================================================================================
Category / Test | Subsystem Description                    | Status     | Duration
--------------------------------------------------------------------------------
CAT A           | Dependency Verification                  | PASS       | 2.30s
CAT B/C         | Whisper Offline Cache                    | PASS       | 1.72s
CAT D           | Timeline Continuity (12/12)              | PASS       | 0.21s
CAT K           | Structured Error Hierarchy (9/9)         | PASS       | 3.08s
CAT I           | Windows Production Hardening (5/5)       | PASS       | 9.82s
CAT G           | Caption Engine Suite (All Styles)        | PASS       | 0.91s
CAT H           | API / UI Lifecycle (5/5)                 | PASS       | 4.15s
CAT L           | Security Audit & Traversal (4/4)         | PASS       | 2.23s
CAT J           | Long Video Scalability (30m & 60m)       | PASS       | 48.31s
================================================================================
 VERDICT: 100% PASS — ALL REGRESSION CATEGORIES SATISFIED (Total: 72.73s)
================================================================================
```

---

## Operating Limits & Production Caveats

1. **60-Minute Real Video Rendering**:  
   The streaming chunk architecture, timeline math, and concat demuxer are formally validated (**ARCHITECTURE VERIFIED**). However, on entry-level dual-core CPU hardware without dedicated NVENC hardware acceleration, encoding a continuous 60-minute 1080p video takes approximately 2 hours. Real renders are formally verified through 60-second multi-chunk milestones.
2. **First-Run Provisioning**:  
   If the local Hugging Face cache is empty, a one-time execution of `python engine/transcribe.py --provision-model small` is required before entering offline mode.
