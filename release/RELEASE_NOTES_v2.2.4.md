# RenderFlow v2.2.4 — Release Notes

RenderFlow v2.2.4 delivers critical video-rendering pipeline quality control fixes and introduces an integrated, cryptographically authenticated In-App Automatic Update System.

---

## What's New in v2.2.4

### 1. Rendering Engine & QC Verification Hardening
- **Frame-Accurate Discrete Seeking:** Replaced continuous timestamp interpolation seeking with exact frame-quantized seeking across timeline cuts, eliminating false-positive verification errors at chunk boundaries (resolving `Verification checks failed: ['cut@21.07s visible change']`).
- **Multi-Metric Visual Change Detection:** Transitioned from single-metric pixel delta to multi-metric validation using mean absolute difference, maximum pixel delta, and 95th percentile delta to accurately detect cut boundaries while preventing false frozen-frame alarms.
- **Transition-Aware Sampling:** Evaluation frames for dissolves, wipes, and transitions are now sampled strictly outside active transition intervals ($T_{\text{cut}} \pm \frac{1}{2} D_{\text{trans}} + \delta$).
- **Adaptive Memory Management:** Automatically bounds chunk sizing when running on hardware with $\le 8.0$ GiB RAM, preventing FFmpeg out-of-memory crashes during multi-scene timeline concatenation.
- **Persistent Encoder Fallback:** Enhanced automatic encoder detection (NVENC, QSV, AMF) with seamless CPU `libx264` fallback.

### 2. Built-in In-App Auto-Updater
- **Direct Updates Inside Settings & About:** Check for updates, inspect release notes, and install patches directly from within the RenderFlow desktop UI.
- **Cryptographic Authentication:** Every release manifest is verified against RenderFlow's embedded Ed25519 master public key (`661a024a191bfeb43cc9cc8412676dd8064fd1686ca3bdf9cb604ef71b24830e`).
- **Lightweight Patches (~582 KB):** Existing installations (v2.0.0+) can download lightweight patch packages instead of re-downloading the entire 1.37 GB installer.
- **Full Installer Fallback:** Legacy clients automatically fall back to the full standalone installer.
- **Atomic Staging & Rollback Protection:** Files are verified, backed up, and atomically applied. Any write permission or file access failure triggers instant automatic rollback to the existing installation.
- **User Data Isolation:** Strict guarantees ensure customer projects (`projects/`), media bins, custom assets, and `.env` credentials remain 100% untouched.

---

## Installation & Upgrade Instructions

### New Installations
1. Download **`RenderFlow-Setup-v2.2.4.exe`**.
2. Run the installer and follow the on-screen setup wizard.
3. Launch RenderFlow from the desktop shortcut or Start Menu.

### Existing Users (v2.2.3)
1. Open RenderFlow.
2. Click **⚙️ Settings** or **🚀 Updates** in the top navigation bar.
3. Click **Check for Updates**.
4. When v2.2.4 is displayed, click **⬇️ Download and Install**.
5. Once downloaded, click **⚡ Install & Restart Now**.

---

## Artifact Integrity & Checksums

| File | Size (Bytes) | SHA-256 Checksum |
| :--- | :---: | :--- |
| `RenderFlow-Setup-v2.2.4.exe` | 1,372,736,514 | `2bd5d3a4c7b563592ed0204363efaae6923df2fff7c92958098854cfaab72473` |
| `RenderFlow-Patch-v2.2.4.zip` | 582,922 | `d0c5d919668df8d7c7fd251158edf1430cef3fc02cc7d7ac37e679df0373f9de` |
| `update_manifest.json` | 1,985 | `24bde7bda7e583d2ed737fed263b6476068a3ed53698a9e6f1cf0aaad97ec033` |
| `bundle_manifest.json` | 71,929 | `6eb4a3e81d32cd95059ec0b7bb93f17c686c258b34ffb08bc10b6306a6750a10` |
