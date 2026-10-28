# Concat UI/UX Replacement Implementation Plan for RenderFlow

**Document Version:** 2.0.0  
**Phase:** Complete Concat-Style Editor UI Replacement  
**Target:** RenderFlow Workstation Engine  
**Status:** **ACTIVE MIGRATION SPECIFICATION**  

---

## 1. Executive Summary & Objective

The objective is to **completely replace the existing fragmented RenderFlow editor interface with a unified, professional, high-density Non-Linear Editor (NLE) workspace** closely modeled on the observable UI/UX of the open-source Concat video editor and modern desktop editors like CapCut.

This is **NOT** a theme-picker addition or surface recoloring of the legacy interface. Instead, the legacy 10-view fragmented sidebar navigation (`view-home`, `view-media`, etc.) is retired from the primary editing path. All core editing functions—media management, canvas preview monitor, properties inspector, multi-track timeline, and export orchestration—are unified into a single desktop workspace.

### Core Architectural Principles:
1. **Unified Multi-Pane Workspace:** 
   - Top Application Header & Toolbar (`rf-nle-topbar`)
   - Left Media & Asset Library (`rf-nle-media-pane`)
   - Center Program Preview Monitor (`rf-nle-preview-pane`)
   - Right Contextual Properties Inspector (`rf-nle-inspector-pane`)
   - Bottom Multi-Track Timeline & Tool Tray (`rf-nle-timeline-pane`)
2. **Direct Data Model Binding:**
   - Real two-way synchronization with `plan.json`, `narration.wav`, `transcription.json`, and backend APIs. Zero mock state.
3. **Preservation of Rendering Engine:**
   - Audio-first master narration authority is strictly preserved.
   - FFmpeg chunk rendering (`fast_pipeline.py`) remains intact.
4. **Clean-Room Compliance:**
   - Independent HTML5, CSS3, and JavaScript implementation. No GPL/AGPL source code, compiled binaries, or proprietary assets bundled.

---

## 2. Design System Tokens & Typography (Verified Upstream Concat)

### 2.1 Color Tokens
- Canvas / Deepest Ground: `--nle-page: #0e0e10;`
- Surface / Pane Background: `--nle-panel: #212123;`
- Well / Sunken Stage & Lanes: `--nle-well: #19191b;`
- Raised / Cards & Toolbar: `--nle-raised: #2b2b2e;`
- Field / Inputs & Dropdowns: `--nle-field: #323235;`
- Field Hover: `--nle-field-hover: #3b3b3e;`
- Field Active: `--nle-field-active: #46464a;`
- Borders / Hairlines: `--nle-line: rgba(255, 255, 255, 0.10);`
- Strong Separators: `--nle-line-strong: rgba(255, 255, 255, 0.20);`
- Primary Text: `--nle-fg: #f5f5f7;`
- Muted Text / Labels: `--nle-fg-muted: #a1a1a6;`
- Dim Text / Headings: `--nle-fg-dim: #6e6e73;`
- Signature Accent: `--nle-accent: #cbf53f;` (Lime)
- Accent Hover: `--nle-accent-hover: #d9ff63;`
- On-Accent Dark Ink: `--nle-on-accent: #15220a;`
- Playhead Color: `--nle-playhead: #cbf53f;`

### 2.2 Track & Media Kind Tokens
- Audio Track: `--nle-audio-well: #12301c;`, `--nle-audio-accent: #34c46f;`
- Video Track: `--nle-video-well: #142238;`, `--nle-video-accent: #3373d1;`
- Captions Track: `--nle-caption-well: #321c29;`, `--nle-caption-accent: #cf5a99;`
- Transitions Track: `--nle-trans-well: #19191b;`, `--nle-trans-accent: #eab308;`
- Ruler Surface: `--nle-ruler-bg: #171719;`

### 2.3 Typography & Metrics
- Fonts: `'Hanken Grotesk'`, `'Plus Jakarta Sans'`, `-apple-system`, BlinkMacSystemFont, `'Segoe UI'`, sans-serif
- Technical Font: `'JetBrains Mono'`, `'SF Mono'`, Consolas, monospace
- Scale: `fs-xs: 10px`, `fs-sm: 11px`, `fs: 12px` (base), `fs-lg: 13px`, `fs-xl: 14px`, `fs-input: 15px`
- Control Height: `28px` standard NLE control height
- Timeline Tray Height: `40px`
- Gap: `6px`; Padding: `14px`; Label Width: `62px`
- Radii: `r-xs: 3px`, `r-sm: 5px`, `r: 7px`, `r-lg: 12px`, `r-xl: 16px`

---

## 3. Detailed Component Hierarchy & Layout

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│ 1. Application Top Bar (44px)                                                               │
│    [Logo: RenderFlow NLE] [Project: Berlin_1953] [Menu: File, Edit, View]  [1080p·30] [⚡ Export] │
├──────────────────────────────┬──────────────────────────────┬───────────────────────────────┤
│ 2. Left Media Pane (340px)   │ 3. Center Preview Monitor    │ 4. Right Properties Inspector │
│    - Tabs: Media, FX, Text   │    (Flex: 1.2)               │    (340px)                    │
│    - Upload Dropzone         │    - Aspect Ratio (16:9)     │    - State A: Sequence Facts  │
│    - Asset Cards Grid        │    - 16:9 Sunken Stage Canvas│      (Res, FPS, Dur, Audio)   │
│    - Transitions Catalog(20) │    - Playback Transport Tray │    - State B: Clip Inspector  │
│    - Captions Typography(67) │      [|◀] [◀] [ ▶ ] [▶] [▶|] │      (Timing, Asset, Motion,  │
│                              │      00:04.20 / 00:20.00     │       Transitions, Split)     │
├──────────────────────────────┴──────────────────────────────┴───────────────────────────────┤
│ 5. Bottom Multi-Track Timeline Dock (320px)                                                 │
│    - 40px Tool Tray: [Undo] [Redo] | [Select V] [Split S] [Del] | [🧲 Snap] | [- Zoom + Fit] │
│    - Track Headers: 🎙️ Audio Master (#12301c) | 🎬 Video Scenes (#142238) | 💬 Captions     │
│    - Viewport: Timecode Ruler | Lime Playhead (#cbf53f) | Audio Waveform | Scene Clips      │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Implementation Milestones

### Milestone A: UI Audit & Migration Plan
- Verify all Slint tokens, fonts, and component metrics.
- Produce comprehensive audit document (`docs/CONCAT_UI_UX_AUDIT.md`) and migration specification.

### Milestone B: Replace Main Workspace & Global Design System
- Update `web/static/css/style.css` with the default NLE visual system (`--nle-*` tokens).
- Redesign `web/static/index.html` to instantiate the unified NLE shell as the default editor interface.
- Retire legacy disjointed views (`view-home`, etc.) from the default editing flow into integrated panels and modal dialogs.

### Milestone C: Connect Media Library, Preview & Project State
- Wire Media Library tab strip (Media Bin, Transitions, Captions, Visual Styles) to real backend assets.
- Wire audio upload and image dropzone directly to project folders.
- Wire Central Preview Monitor stage to canvas rendering and audio playback.
- Implement timecode readout and transport controls (Play/Pause, Step Frame, Seek).

### Milestone D: Integrate Timeline Selection, Split, Trim & Editing Controls
- Wire Bottom Timeline Dock to `TimelineNormalizer` and `plan.json`.
- Support playhead scrubbing, clip selection, drag move, and trimming.
- Wire Split-at-Playhead (`S`) to `POST /api/timeline/split_scene` with 0.3s boundary validation.

### Milestone E: Integrate Properties Inspector, Captions & Export Workflow
- Two-State Properties Inspector: Sequence Facts when unselected, Clip Inspector when selected.
- Wire caption editing and style selection.
- Wire Export modal to `POST /api/render` with live progress, chunk tracking, and terminal logs.

### Milestone F: Testing, Responsiveness, Regression & Verification
- Execute full test suite (68 tests across unit, API, continuity, regression, updater, and production acceptance).
- Verify responsive desktop layout at 1920x1080, 1440x900, 1280x720.
- Compile completion report in `docs/CONCAT_PHASE_2A_REPORT.md`.
