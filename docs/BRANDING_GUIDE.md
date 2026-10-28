# RenderFlow — Official Brand & Identity Guide
### By AI With Atif

---

## 1. Executive Brand Identity

| Dimension | Specification |
| :--- | :--- |
| **Product Name** | **RenderFlow** |
| **Parent Brand** | **AI With Atif** |
| **Tagline** | *Professional Cinematic Rendering Workstation* |
| **Platform Target** | Windows Desktop (10/11 x64, Native & High-DPI 4K) |
| **Category** | Professional Desktop Creative Workstation & Video Engine |
| **Brand Promise** | Hardware-adaptive intelligence, cinematic timeline precision, and zero-compromise production rendering. |

---

## 2. Official Brand Lockups

### Primary Brand Lockup (Stacked)
```text
  ██████╗ ███████╗███╗   ██╗██████╗ ███████╗██████╗ ███████╗██╗      ██████╗ ██╗    ██╗
  ██╔══██╗██╔════╝████╗  ██║██╔══██╗██╔════╝██╔══██╗██╔════╝██║     ██╔═══██╗██║    ██║
  ██████╔╝█████╗  ██╔██╗ ██║██║  ██║█████╗  ██████╔╝█████╗  ██║     ██║   ██║██║ █╗ ██║
  ██╔══██╗██╔══╝  ██║╚██╗██║██║  ██║██╔══╝  ██╔══██╗██╔══╝  ██║     ██║   ██║██║███╗██║
  ██║  ██║███████╗██║ ╚████║██████╔╝███████╗██║  ██║██║     ███████╗╚██████╔╝╚███╔███╔╝
  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝ 

                             b y   A I   W i t h   A t i f
```

### Inline / Header Lockup
```text
RenderFlow · AI With Atif
```

### Desktop Window Title & Installer Presentation
```text
RenderFlow by AI With Atif — Professional Cinematic Rendering Workstation
```

---

## 3. Brand Governance & Absolute Negative Rules

To protect commercial product integrity and professional positioning:

1. **Absolute Legacy Purge**:
   - Zero references to legacy names (specifically *RehmaniX* or unbranded templates) across all user-facing surfaces.
   - Prohibited in: UI headers, command bars, splash screens, About modal dialogs, browser title tags, console banners, installer wizards, Start Menu shortcuts, tooltips, and release notes.
2. **Attribution Authenticity**:
   - Every build, installer package, web UI, and terminal session must proudly present the creator identity: **AI With Atif**.
3. **No Clone Aesthetics**:
   - RenderFlow must maintain its original aesthetic. Avoid copying proprietary third-party logos, Apple trademarked shapes, Omni proprietary SVGs, or official F1 team badges.
4. **Hardware Honesty**:
   - The brand is founded on technical excellence. Hardware detection, GPU acceleration status, and render progress counters must reflect **100% verified system telemetry**, never simulated or spoofed metrics.

---

## 4. Typography Hierarchy

| Level | Typeface / Stack | Weight | Tracking | Case | Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Display Wordmark** | Inter, -apple-system, sans-serif | 800 (Extrabold) | -0.04em | Title Case | Splash screen, Top App Bar, About title |
| **Brand Byline** | Inter, sans-serif | 600 (Semibold) | +0.08em | Upper/Mixed | "by AI With Atif" subtitle, footer lockup |
| **Section Headings (H1/H2)** | Inter, sans-serif | 700 (Bold) | -0.02em | Title Case | Workflow tabs, modal titles, stage headers |
| **Body & Controls** | Inter, sans-serif | 400 / 500 | Normal | Sentence | Form fields, buttons, descriptions |
| **Telemetry & Metrics** | JetBrains Mono, Consolas, monospace | 500 / 700 | -0.01em | Normal | Timecodes, frame counts, bitrates, resolutions |

---

## 5. Core Color Palette

### Primary Brand Accents
- **Flow Cyan** (`#00f0ff` / `hsla(184, 100%, 50%, 1)`): Symbolizes high-throughput rendering streams, digital precision, and active processing states.
- **Electric Indigo** (`#4f46e5` / `hsla(245, 82%, 67%, 1)`): Secondary brand anchor providing cinematic depth, contrast, and structural focus.
- **Pure Energy** (`#ffffff` / `hsla(0, 0%, 100%, 1)`): High-contrast foreground element for primary typography.

### Functional System Colors
- **Engine Success**: Emerald (`#10b981` / `hsla(158, 64%, 52%, 1)`) — Signals successful encoding, verified FFmpeg, complete tasks.
- **Engine Warning**: Amber (`#f59e0b` / `hsla(38, 92%, 50%, 1)`) — Signals high memory, CPU fallback, missing optional assets.
- **Engine Danger / Error**: Crimson (`#ef4444` / `hsla(0, 84%, 60%, 1)`) — Signals encode errors, file missing, invalid parameters.
- **Engine Hardware Info**: Cyan (`#06b6d4` / `hsla(189, 94%, 43%, 1)`) — NVENC, QSV, AMF, VRAM diagnostics.

---

## 6. Theme Brand Adaptability

RenderFlow features four distinct themes. The brand signature (`RenderFlow · AI With Atif`) harmoniously adapts across all four while maintaining instant brand recognition:

```
┌─────────────────┬──────────────────────────────────────────────────────────────┐
│ Theme           │ Brand Treatment                                              │
├─────────────────┼──────────────────────────────────────────────────────────────┤
│ 1. Glass        │ Holographic cyan glow, ultra-frosted blur backdrop (16px)   │
│ 2. Muddy        │ Warm golden-amber accent, deep espresso charcoal background  │
│ 3. Apple Spatial│ Crisp obsidian surface, restrained vivid indigo highlight    │
│ 4. F1 Telemetry │ Race-day telemetry red/cyan, monospaced tech stats, grid bg  │
└─────────────────┴──────────────────────────────────────────────────────────────┘
```

---

## 7. Application Asset Checklist

- [x] **Web Studio Browser Title**: `RenderFlow · AI With Atif`
- [x] **Terminal ASCII Banner**: 68-column multi-color banner in `web/banner.py`
- [x] **API Title & Metadata**: `RenderFlow by AI With Atif` in `web/server.py`
- [x] **Inno Setup Windows Installer**: `RenderFlow by AI With Atif` in `RenderingStudioSetup.iss`
- [x] **Desktop Shortcut**: `RenderFlow.lnk` $\to$ `RenderFlow by AI With Atif`
- [x] **Standalone Launcher**: `RenderFlow.bat` portable runner
- [x] **In-App Splash Screen**: Interactive Remotion-inspired branded entrance with dismiss
- [x] **About Workstation Modal**: Full engine, hardware, Whisper, and license credits
