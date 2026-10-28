# RenderFlow — UI/UX Design System Specification
### Omni-Inspired Cinematic Creative Workstation · AI With Atif

---

## 1. Design Philosophy & Vision

RenderFlow is architected as a **cinematic creative workstation**, establishing a distinct visual identity centered on:
- **Spatial Depth Without Clutter**: Translucent frosted glass layers, micro-thin borders, and calibrated specular highlights replace heavy, flat SaaS cards.
- **Immediate Information Radiance**: Key hardware metrics, encoder readiness, project timecodes, and render chunk progress are accessible at a single glance.
- **Fluid Micro-Interactions**: Predictable, hardware-accelerated transitions that respond to user input with tactile precision.
- **Workflow Clarity**: An unambiguous step-by-step production flow from asset ingestion to final 4K export.

---

## 2. Desktop Shell Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│  [Logo] RENDERFLOW by AI With Atif  │  [Project: My 4K Cut] [1080p/4K] [NVENC ✓] [⌘K] │
├──────────────┬─────────────────────────────────────────────────────────────────────────┤
│              │  WORKFLOW STEPPER: Upload ──► Sync ──► Review ──► Style ──► Render      │
│              ├─────────────────────────────────────────────────────────────────────────┤
│  SIDEBAR     │                                                                         │
│  ──────────  │  MAIN WORKSPACE VIEWPORT                                                │
│  [📁 Media]  │                                                                         │
│  [⏱ Timeline]│  • Media Dropzone / Asset Grid                                          │
│  [🎨 Style]  │  • Audio-First Waveform & Scene Blocks                                  │
│  [⚡ Render]  │  • Style Customization & Live Previews                                  │
│  [🖥 System]  │  • 3D Render-Core & Hardware Telemetry                                   │
│  [⚙ Settings]│                                                                         │
│              │                                                                         │
├──────────────┴─────────────────────────────────────────────────────────────────────────┤
│  STATUS BAR: Ready · Whisper Small (Offline) · FFmpeg Local · Memory: Safe (34 MB)     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Structural Components

### 3.1. Top Command Bar
- **Brand Lockup**: Bold `RenderFlow` wordmark with `AI With Atif` byline.
- **Project State Badge**: Displays project name and modification timestamp.
- **Format Telemetry**: Live indicators for Canvas Resolution (`1080p`, `1440p`, `4K UHD`), Framerate (`24`, `30`, `60 FPS`), and Encoder (`NVENC`, `QSV`, `AMF`, `CPU`).
- **Command Palette Trigger**: Quick-action pill button displaying `⌘K` / `Ctrl+K`.
- **Theme Quick Switcher**: Interactive dropdown with Glass, Muddy, Apple, and F1 themes.

### 3.2. Workflow Stepper
The production lifecycle is codified into six clear, sequential phases:
$$\text{Upload} \longrightarrow \text{Sync} \longrightarrow \text{Review} \longrightarrow \text{Style} \longrightarrow \text{Render} \longrightarrow \text{Download}$$
Each stage provides 4 discrete visual states:
- **Completed** (Green checkmark, filled connector)
- **Active** (Pulsing accent ring, highlighted label)
- **Pending** (Subtle muted line, low contrast)
- **Error / Attention** (Amber/red alert badge)

### 3.3. Left Workspace Sidebar
- Smoothly toggleable between expanded (labels + icons) and compact rail (icons + tooltips).
- Retains state across sessions via `localStorage`.
- Direct keyboard navigable via standard tab and arrow traversal.

---

## 4. Reusable Component Primitives

### 4.1. Buttons
- `.rf-btn-primary`: Vibrant accent gradient, subtle glow on hover, active depression.
- `.rf-btn-secondary`: Translucent frosted surface with micro-border.
- `.rf-btn-danger`: Controlled crimson tint for destructive operations.
- `.rf-btn-telemetry`: Monospaced data button for hardware inspections.

### 4.2. GlassPanels & Cards
- Built using `--rf-surface` and `--rf-panel` tokens.
- Dynamic `backdrop-filter: blur(var(--rf-glass-blur))` with hardware fallback.
- Micro-thin inner stroke (`rgba(255, 255, 255, 0.08)`) simulating light refraction.

### 4.3. Command Palette (`Ctrl+K`)
- Centered modal overlay with frosted dark scrim.
- Search input with real-time fuzzy filtering.
- Arrow up/down keyboard navigation with Enter activation.
- Commands cover navigation, theme switches, resolution selection, and hardware diagnostics.

---

## 5. Keyboard Navigation & Shortcuts

| Shortcut | Action | Scope |
| :--- | :--- | :--- |
| `Ctrl + K` / `Cmd + K` | Open Command Palette | Global |
| `Ctrl + N` | New Project | Global |
| `Ctrl + O` | Open Project Dialog | Global |
| `Ctrl + S` | Save Current Project | Global |
| `Ctrl + R` | Trigger Video Render | Global |
| `Space` | Play / Pause Preview Playhead | Timeline Workspace |
| `Esc` | Close Active Modal / Dismiss Palette | Global |

---

## 6. Multi-Resolution & High-DPI Adaptation

Tested and verified across key display viewports:
- **1366 × 768 (Budget Laptop)**: Sidebar automatically defaults to icon rail mode; timeline controls collapse secondary metrics.
- **1920 × 1080 (Full HD Desktop)**: Standard workstation baseline with all panels expanded.
- **2560 × 1440 (2K QHD)**: Optimal widescreen presentation with side-by-side timeline and scene inspector.
- **3840 × 2160 (4K UHD & Windows DPI 150%/200%)**: High-DPI font scaling guarantees crisp typography without clipping or microscopic UI elements.
