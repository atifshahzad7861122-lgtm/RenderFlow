# RenderFlow v2.5.0 — Semantic Intelligence & Sequence Optimizer Release Candidate

RenderFlow v2.5.0 introduces the next-generation **Semantic Intelligence & Sequence Optimizer** engine, bringing fully offline cross-modal scene understanding, speech-pause rhythm alignment, intelligent B-roll indexing, and Hungarian bipartite timeline synchronization to creator workflows.

---

## What's New in v2.5.0

### 1. Neural Semantic Intelligence & Hungarian Bipartite Sequence Optimizer
- **Archive-Order Invariance:** Timeline mapping is mathematically decoupled from file naming or upload order. Shuffled archive uploads yield 100% identical scene-to-narration alignments.
- **Cross-Modal Embedding Alignment:** 512-dimensional joint semantic vector projections accurately distinguish literal visual matches (e.g. soldiers, cities) and abstract emotional narratives (e.g. fear, tension, hope) with offline deterministic fallback.
- **Consecutive Duplicate Penalties & Diversity:** Global timeline optimization distributes visual assets across beats to prevent unintended consecutive duplicate image assignments.
- **Strict User Lock Preservation:** User-locked image assignments and manual scene overrides are strictly honored and never overwritten during re-synchronization.

### 2. Audio Rhythm & Cadence Alignment Engine (`engine/audio_rhythm.py`)
- **Speech-Pause Valley Detection:** Automatically locates natural speech pauses and breath valleys using energy flux and dynamic thresholding.
- **Sub-Frame Cut Snapping:** Snaps scene cuts to natural speech pauses (within ±180ms) to eliminate jarring cuts mid-word while maintaining master timeline clock invariance.
- **Word Protection:** Prohibits automated cuts inside active spoken-word intervals.

### 3. Native Audio Waveform Visualization & Non-Destructive Transcript Ripple
- **Real-Time Waveform Extraction (`engine/audio_waveform.py`):** Multi-resolution RMS envelope generation for high-density frontend audio scrubbers.
- **Deterministic Transcript Ripple (`engine/transcript_ripple.py`):** Enables deletion of transcript segments, word spans, or arbitrary time intervals with automatic downstream visual rippling and non-destructive narration preservation.

### 4. Intelligent B-Roll Indexer & Motion Intelligence
- **Offline B-Roll Cataloging (`engine/broll_indexer.py`):** Automated scene cut detection, visual embedding extraction, and motion scoring for supplementary video clips.
- **L4 Camera Motion Planning (`engine/motion_intelligence.py`):** Dynamic pan, tilt, push, and zoom framing tailored to semantic pacing and visual energy.

### 5. Production Caption Engine
- **Multi-Style ASS Generation (`engine/caption_engine.py`):** Professional kinetic, bold viral, MrBeast, and cinematic subtitle templates rendered via libass.
- **Sub-Millisecond Caption QC:** Automatic detection of overlapping subtitles, line clipping, or timestamp drift.

---

## Artifact Integrity & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.5.0.exe` | 1,430,492,355 | `4f65d9a3a0600cd3a0a16d96866f8274ef031a674a0e9453656b032df20063d7` |
| `RenderFlow-Patch-v2.5.0.zip` | 719,414 | `a9da81e788beadc9fb6615a43435a74c9b699d45b47f4d67716105b449141ae1` |
| `update_manifest_v2.5.0.json` | 1,941 | Signed Ed25519 (`8fa5299ad972cb7b22a2cfa3065b26fe...`) |
| `bundle_manifest_v2.5.0.json` | 74,696 | 436 Files Audited (1,433,531,257 bytes total) |

**Master Public Key:** `661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`

---

## Installation & Upgrade Instructions

### New Users
1. Download **`RenderFlow-Setup-v2.5.0.exe`**.
2. Run the installer and select the desired destination directory.
3. Launch RenderFlow from the desktop shortcut or Start Menu.

### Existing Users (v2.4.0, v2.4.1, v2.4.2, or v2.4.3)
1. Open RenderFlow -> **⚙️ Settings** -> **Update Center**.
2. Click **Check for Updates**.
3. When v2.5.0 is detected, click **Download Latest Version**.
4. Click **Apply Update & Restart**. (All projects, settings, credentials, and custom profiles remain 100% preserved).

### Legacy Users (v2.2.4 or earlier)
1. Run **`RenderFlow-Setup-v2.5.0.exe`** directly over the existing installation. All existing projects and media will be preserved.
