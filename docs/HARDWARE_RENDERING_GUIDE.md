# Rendering Studio Engine v2 — Hardware-Aware & 4K Rendering Guide

## 1. Overview

**Rendering Studio Engine v2** includes an intelligent, hardware-adaptive rendering system designed to deliver high-performance video generation across all computer tiers:
- Low-end dual-core laptops with 8 GB RAM.
- Mid-range 4–8 core desktop PCs with integrated or entry GPUs.
- High-end workstations with dedicated NVIDIA, AMD, or Intel hardware encoders.

The engine supports 1080p Full HD, 1440p QHD, and 3840x2160 4K UHD with bounded memory usage, proportional caption scaling, native timeline transitions, and automatic hardware encoder fallback.

---

## 2. Supported Output Resolutions

| Resolution Preset | Canvas Dimensions | Aspect Ratio | Bitrate / Quality Target | Memory Profile | Recommended Hardware |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1080p (Full HD)** | 1920 x 1080 | 16:9 | CRF 22 (~6–8 Mbps) | Low (< 150 MB RSS) | Any PC (2+ cores, 4+ GB RAM) |
| **1440p (QHD / 2K)** | 2560 x 1440 | 16:9 | CRF 21 (~12–16 Mbps) | Moderate (< 200 MB RSS) | Mid-range (4+ cores, 8+ GB RAM) |
| **4K (UHD)** | 3840 x 2160 | 16:9 | CRF 20 (~24–35 Mbps) | Bounded (< 250 MB RSS) | High-end or dedicated hardware encoder |

### Source Image Scaling & Framing Integrity
- Images are dynamically scaled to fit target resolution canvases without stretching or distortion.
- Aspect ratio is strictly preserved using cinematic letterboxing/pillarboxing with high-quality Lanczos/bicubic resampling.
- Preprocessing generates resolution-keyed cached assets (e.g. `image_3840x2160.jpg`), preventing redundant resizing across frames.

---

## 3. Supported Encoders & Parameter Systems

Rendering Studio tests encoder availability at runtime using an active probe before enabling it.

| Encoder | Name | Vendor / Platform | Parameter System | Fallback Path |
| :--- | :--- | :--- | :--- | :--- |
| `libx264` | CPU Software Encoder | Universal (x86/x64) | `-preset veryfast -crf <val>` | Baseline (always present) |
| `h264_nvenc` | NVIDIA NVENC | NVIDIA GeForce / RTX / Quadro | `-preset p4 -cq <val>` | Automatic -> `libx264` |
| `h264_qsv` | Intel Quick Sync Video | Intel Core / Arc | `-preset medium -global_quality <val>` | Automatic -> `libx264` |
| `h264_amf` | AMD Advanced Media Framework | AMD Radeon / APU | `-quality speed/balanced/quality` | Automatic -> `libx264` |
| `h264_mf` | Windows Media Foundation | Windows 10/11 DirectX / MFT | `-b:v <target_bitrate>` | Automatic -> `libx264` |

### Automatic Hardware Fallback
If any hardware encoder fails during startup, pipeline initialization, or chunk rendering:
1. An explicit diagnostic warning is logged: `[WARN] Hardware encoder <name> failed. Falling back to CPU libx264.`
2. The renderer seamlessly switches to `libx264`.
3. The project render completes successfully without crashing or corrupting files.

---

## 4. Hardware Profiles

The engine classifies system capabilities into 4 hardware tiers:

### Profile A: Eco / Low-End
- **Target Hardware**: Dual-core CPU, <= 8 GB RAM, integrated graphics without dedicated hardware encoder.
- **Recommended Output**: 1080p Full HD.
- **Encoder**: CPU `libx264` (`-threads 2`, `-preset veryfast`).
- **Chunking**: Conservative chunks (15–20 scenes) to maintain peak RAM < 150 MB.
- **Parallelism**: Sequential execution to avoid thread contention.

### Profile B: Balanced (Default for Mid-Range PCs)
- **Target Hardware**: 4–8 core CPU, 8–16 GB RAM, integrated or entry-level GPU.
- **Recommended Output**: 1080p or 1440p.
- **Encoder**: Verified hardware encoder if present, otherwise optimized `libx264`.
- **Chunking**: Balanced chunks (25–35 scenes).
- **Parallelism**: Moderate bounded worker pools for image preprocessing.

### Profile C: Performance
- **Target Hardware**: High-end CPU (8+ cores), 16+ GB RAM, dedicated GPU with NVENC/QSV/AMF.
- **Recommended Output**: 1080p, 1440p, or 4K UHD.
- **Encoder**: Hardware accelerated (`h264_nvenc` / `h264_qsv` / `h264_amf`).
- **Chunking**: High-throughput chunks (45–60 scenes).
- **Parallelism**: Concurrent image preprocessing and pipeline stages.

### Profile D: Max Quality
- **Target Hardware**: High-end multi-core workstations or render servers.
- **Recommended Output**: 4K UHD.
- **Encoder**: High-quality hardware or CPU encoder profile (`CRF 18` / high bitrate).
- **Chunking**: High memory budget chunks.
- **Visuals**: Maximum fidelity scaling, highest precision caption rasterization.

---

## 5. User Settings & Control

The Web UI and REST API expose explicit rendering controls under **Render Settings**:

### Resolution Selection
- `1080p` (Fast — Recommended for everyday production)
- `1440p` (High Quality — Sharp 2K/QHD output)
- `4K UHD` (Maximum Quality — Professional 3840x2160 output)

### Performance Mode
- `Auto` (Recommended — Detects hardware and selects optimal profile)
- `Eco` (Conserves CPU and battery; low memory usage)
- `Balanced` (Default balance between rendering speed and visual fidelity)
- `Performance` (Maximizes GPU and multi-core throughput)
- `Max Quality` (Prioritizes visual precision at 4K)

### Encoder Selection
- `Auto` (Probes hardware and selects best verified encoder)
- `CPU (libx264)`
- `NVIDIA NVENC`
- `Intel Quick Sync (QSV)`
- `AMD AMF`
- `Windows Media Foundation (MF)`

---

## 6. Proportional 4K Caption Scaling

Captions are generated using resolution-aware ASS styles. Font sizes, subtitle margins, outline thicknesses, and shadow offsets scale proportionally with the canvas height:

$$\text{Scale Factor} = \frac{\text{Target Height}}{1080}$$

- **1080p**: Scale = $1.0\times$ (Font size 38pt, MarginV 50px, Outline 3px).
- **1440p**: Scale = $1.33\times$ (Font size 51pt, MarginV 67px, Outline 4px).
- **4K UHD**: Scale = $2.0\times$ (Font size 76pt, MarginV 100px, Outline 6px).

This guarantees that subtitles remain perfectly legible, properly padded from bottom margins, and crisp at all resolutions.

---

## 7. 4K Memory Safety Architecture

4K uncompressed video frames consume ~24.8 MB per frame in memory. In naive rendering systems, buffering 1,000 frames in memory requires ~25 GB of RAM.

Rendering Studio Engine v2 guarantees bounded memory safety via:
1. **Incremental Streaming & Chunking**: Video frames are streamed directly through FFmpeg pipes into encoded disk containers; never buffered into global Python lists.
2. **Resolution-Keyed Disk Cache**: Preprocessed images are cached on disk and loaded on demand.
3. **Explicit Garbage Collection**: Inter-chunk garbage collection cleans up intermediate buffers, keeping peak Python RSS under 200 MB even for 4K renders.

---

## 8. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| Hardware encoder not selected in Auto mode | GPU driver does not support hardware encoder or FFmpeg probe failed | Run `python -m engine.hardware_detector` to view detected capabilities. Update GPU graphics drivers. |
| 4K render speed slower than 1080p | 4K requires processing 4x more pixels (8.3M vs 2.1M pixels/frame) | On systems without NVENC/QSV, use 1080p or 1440p for daily renders and reserve 4K for final master export. |
| Subtitles appear small on 4K | Fixed font sizes configured in custom overrides | Clear custom font overrides to allow automatic proportional scaling. |
| Low disk space warning | High resolution temporary chunks require disk storage | Ensure at least 10 GB free space on working drive for 4K video exports. |
