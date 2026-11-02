# Changelog

All notable changes to the RenderFlow Video Rendering Studio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.6.0] - 2026-11-03

### Added
- **17-Point Precalculated Curves LUTs:** Added precalculated 1D tone curves for `cinematic_warm`, `moody_noir`, and `vivid_tech` photographic color grading styles in `engine/fast_pipeline.py`, accelerating color grading by 2.86x (42.1 ms/frame vs 120.4 ms/frame) with 45.29 dB PSNR.
- **Native YUV420P Pipeline Composition:** Native `format=yuv420p,setsar=1` video stream composition avoiding expensive RGB planar format conversions.
- **Bicubic Alpha Overlay Scaling:** High-efficiency bicubic scaling on transition overlays, accelerating overlay blends from 51.9 ms/frame to 30.3 ms/frame.
- **Multi-Threaded Asset Preprocessing:** Parallelized image validation and normalization via `ThreadPoolExecutor`, reducing asset prep time by 69.4% (0.71s vs 2.31s).
- **Adaptive Memory-Aware Chunk Sizing:** Dynamic scene chunking in `engine/render_profiles.py` tuned to system RAM (16 scenes default for 1080p, automatically clamping to 14 scenes on low-RAM $\le 8\text{GB}$ systems) keeping memory strictly $<50\text{ MB}$ RSS.
- **Silero VAD Multi-Path Resolution:** Self-healing Silero VAD model discovery in `engine/transcribe.py` checking `models/vad/` and `_internal/faster_whisper/assets/` with direct fallback protection.

### Fixed
- **Silero VAD Packaging Defect:** Resolved missing model runtime error (`[ONNXRuntimeError] : 3 : NO_SUCHFILE`) by bundling `silero_vad_v6.onnx` into both `models/vad/` and `_internal/faster_whisper/assets/` in `installer/build_production_bundle.py`.
- **Dip-to-Black Verification Failure:** Fixed false-positive uniform black classification during deliberate `fadeblack` transitions in `engine/verify_output.py`.
- **Server Lifecycle Port Conflicts:** Enhanced duplicate startup prevention to exit cleanly with code 0 and protect unrelated third-party applications on port 8000 from termination.

### Performance
- **Active Encoding Speedup:** 2.66x faster on 1080p libx264 (6.82 FPS -> 18.13 FPS).
- **Turnaround Time:** Projected 14:30 project render reduced from 150 minutes down to under 25 minutes on low-end dual-core CPUs.
- **Peak RAM RSS:** 46.3 MB during active 1080p single-pass rendering.

---

## [2.5.1] - 2026-10-30

### Added
- **Neural Cosine Discrimination:** Joint 512-dimensional semantic projection engine to mathematically discriminate visual subject matter from narration concepts.
- **Safe `NEEDS_REVIEW` Status:** Unmatched or ambiguous scenes are flagged for manual review rather than bound to arbitrary images.
- **Preview Transition Shader Compositor:** Real-time WebGL transition preview with bidirectional lookahead buffers.
- **Multi-Provider AI Gateway:** Resilient dynamic provider routing supporting Groq, Gemini, OpenAI, Claude, and local heuristic rules.
- **OpenMontage Discovery:** Visual stock discovery adapter with licensing provenance metadata.
- **RFC 8032 Ed25519 Cryptographic Verification:** Authentic digital signatures on release manifests.

---

## [2.5.0] - 2026-10-26

### Added
- **Semantic Scene Analyzer:** Cross-modal vision engine with CLIP ONNX FP32 CPU and PyTorch fallback.
- **Hungarian Global Sequence Optimizer:** Temporal invariance and duplicate reuse penalties.
- **Audio Rhythm Alignment:** Waveform-informed transition triggers and transcript ripple compensation.
- **In-App Auto-Updater:** Production updater client with atomic rollback and SemVer compliance.

---

## [2.4.3] - 2026-10-20

### Fixed
- Fixed audio duration alignment and edge-case padding in single-pass ffmpeg filtergraph.
- Improved portable launcher environment variable precedence.

---

## [2.4.0] - 2026-10-19

### Added
- Modular timeline validation engine and canonical scene plan validator.
- Hardware-adaptive encoding profile selector.
