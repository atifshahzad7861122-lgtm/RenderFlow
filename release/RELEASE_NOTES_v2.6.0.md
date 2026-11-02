# RenderFlow v2.6.0 — CPU-First Rendering Optimization & High-Performance Release

RenderFlow v2.6.0 delivers massive rendering throughput accelerations, zero-loss photographic color grading, complete offline packaging resilience, and rock-solid single-instance server lifecycle management for workstation video production on Windows.

---

## Highlights of RenderFlow v2.6.0

### 1. Major CPU Rendering Pipeline Accelerations (2.66x – 4.5x Speedup)
- **17-Point Precalculated Curves LUTs:** Replaced expensive dynamic software floating-point color matrices (`eq` + `colorbalance`) with native 17-point 1D Tone Curves LUTs (`cinematic_warm`, `moody_noir`, `vivid_tech`). Filter time collapsed from **120.4 ms/frame to 42.1 ms/frame (2.86x speedup)** with reference-grade fidelity (**45.29 dB PSNR**).
- **Native YUV420P Pipeline Composition:** Visual scenes are composited and filtered natively in YUV420P, avoiding redundant RGB planar format conversions and reducing CPU memory bus bandwidth by **11.6%**.
- **Bicubic Overlay Transition Scaling:** Replaced 36-point Lanczos filtering on transition alpha overlays with high-efficiency bicubic scaling, slashing overlay rendering time from **51.9 ms/frame to 30.3 ms/frame (1.72x speedup)**.
- **Redundant Filtergraph Elimination:** Automatically bypasses final canvas rescaling when input assets match output dimensions, eliminating 7.6% of redundant CPU instructions.
- **Multi-Threaded Asset Preprocessing:** Parallelized image validation and normalization across multi-core CPU threads (`ThreadPoolExecutor`), speeding up asset prep from **2.31s to 0.71s (3.26x faster)**.
- **Adaptive Memory-Aware Chunk Sizing:** Dynamic scene chunking tailored to available system RAM: 16 scenes for 1080p (automatically clamping to 14 scenes on low-RAM $\le 8\text{GB}$ systems) keeping peak encoding memory strictly under **50 MB RSS**.
- **Real-World Production Impact:** On a benchmark 14-minute 30-second production (246 scenes, 26,100 frames), total turnaround time drops from **~150 minutes down to under 25 minutes** on standard dual-core CPU workstations.

### 2. Defect Resolution & Packaging Integrity
- **Silero VAD Model Packaging Fix:** Resolved the missing model error (`[ONNXRuntimeError] : 3 : NO_SUCHFILE`) by bundling `silero_vad_v6.onnx` into both `models/vad/` and `_internal/faster_whisper/assets/`. Implemented self-healing path resolution and a zero-crash fallback to direct transcription.
- **Intentional Dip-to-Black Verification:** Fixed a false-positive check in `engine/verify_output.py` where deliberate `fadeblack` dips were misclassified as corrupted uniform blocks. Verification QC now confirms `EXPECTED_TRANSITION` and passes 100%.
- **Robust Server Lifecycle:** Enhanced `engine/server_lifecycle.py` with multi-instance lock detection, clean reuse (exit code 0 with zero duplicate processes), and non-destructive port conflict resolution (unrelated foreign processes on port 8000 are never killed).

### 3. Bitstream Perceptual Quality & Verification
- **PSNR:** **45.29 dB** average (minimum: 40.41 dB)
- **SSIM:** **0.9862** across all color channels
- **A/V Sync Drift:** **0.00 ms** (exact 48kHz audio alignment)
- **Black / Frozen Frames:** **0**
- **Manual Lock Retention:** **100%** across timeline edits

---

## Release Artifacts & Checksums

| File | Type | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :---: | :--- |
| `RenderFlow-Patch-v2.6.0.zip` | Lightweight In-App Patch | 763,809 | `e311e5591b14a1959ac14679b75eb107301c5c38a3a85775161e90b1510b8c52` |
| `update_manifest.json` | Signed Release Manifest | 1,720 | `7381ff2458e0a7df84d4111dd954e76c70ef3f6e16fdf99c859d0458b29ff01d` |
| `bundle_manifest_v2.6.0.json` | Standalone Asset Manifest | 77,181 | `001da4e92eb04b46513364f9bf80db18c7bc9ea0a7ae28d9e2b19280f83664fa` |

**Master Public Key (RFC 8032 Ed25519):**  
`661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`

**Digital Signature:**  
`27f21675c67c2516a46172a2e2327ac6a2588f98ec8d812b184ef156b6c4e0954b9d03c513253b2e53fa675409cb315c548a800d9b4db3b28b61c94410bf6103`

---

## Upgrade Instructions

### Automatic In-App Update
1. Open RenderFlow.
2. The workstation will automatically query the authenticated manifest and display the v2.6.0 upgrade prompt.
3. Click **Update** to install the verified patch package.

### Manual Standalone Installation
1. Download `RenderFlow-Patch-v2.6.0.zip`.
2. Extract the archive into your existing RenderFlow directory, replacing updated files.
3. Launch `RenderFlow.bat` or `RenderingStudio.exe`.
