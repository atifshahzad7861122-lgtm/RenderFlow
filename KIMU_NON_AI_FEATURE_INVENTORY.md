# Kimu Video Editor — Non-AI Feature Inventory & Compatibility Matrix

**Audit Date**: October 10, 2026  
**Auditor**: RenderFlow Advanced Engineering Team  
**Upstream Target**: `https://github.com/trykimu/videoeditor` (Commit/Branch: `main`)  
**Target Workstation**: RenderFlow / Rendering Studio Engine v2 (Windows Local Workstation)

---

## 1. Executive Summary

This inventory documents all functional, technical, and non-generative capabilities discovered in the open-source Kimu Video Editor repository (`scratch/kimu_research/videoeditor-main/`). Each feature has been inspected at the source-code level, evaluated for architectural compatibility with RenderFlow's local FFmpeg-based workstation, and categorized for integration, adaptation, independent reimplementation, deferral, or exclusion.

In accordance with safety and architectural directives:
- **Zero Generative AI**: All LLM assistant, text-to-video, text-to-image, and generative prompt modules from Kimu's backend and frontend are strictly excluded.
- **Zero Mandatory Cloud Dependencies**: No external PostgreSQL, Redis, AWS S3, OAuth, or paid subscription services are imported.
- **Audio-First Native FFmpeg Preservation**: RenderFlow's rock-solid 4K hardware-accelerated chunked FFmpeg rendering pipeline remains the sole authoritative output engine.

---

## 2. Upstream Architecture & Module Inventory

The Kimu repository is organized into a full-stack web application:
- **Frontend (`app/`)**: React 19, React Router v7, Vite, Tailwind CSS, Radix UI, Remotion (`@remotion/player`, `@remotion/renderer`), Lucide icons, Zod schemas.
- **Backend (`backend/`)**: FastAPI/Python, Uvicorn, PostgreSQL (`psycopg`/`asyncpg`), Redis (`ioredis`), AWS S3 SDK, and generative AI clients (`OpenAI`, `Google Gemini`, `fal.ai`, `ElevenLabs`).

### Non-AI Upstream Modules Breakdown:

| Module Path | Core Purpose | Implemented Capabilities | Relevance to RenderFlow |
|---|---|---|---|
| `app/components/timeline/TimelineTracks.tsx` | Multi-track timeline canvas | Tracks container, drag-over detection, clip placement, scroll synchronization, track deletion | **High** (Directly informs timeline track architecture) |
| `app/components/timeline/Scrubber.tsx` | Clip element & manipulation | Direct-DOM transforms (60fps drag & resize), trim left/right handles, magnetic snapping (grid, playhead, clip boundaries), context menu (split, delete, speed), selection ring | **Critical** (Core interactive editing model) |
| `app/components/timeline/TimelineRuler.tsx` | Timecode ruler & scrubbing | Tick marks (major/minor), timecode formatting (`HH:MM:SS.mmm`), click-to-seek, drag scrub, jump to timecode input | **Critical** (Accurate timeline navigation) |
| `app/components/timeline/ClipInspector.tsx` | Per-clip inspector popup | Start time, end time, duration, volume slider, mute toggle, playback speed presets (0.25x - 4x), position/dimension coordinates | **High** (Detailed clip parameter control) |
| `app/components/timeline/TransitionOverlay.tsx` | Clip boundary transitions | Overlay between adjacent clips, overlap/gap detection, transition type badge, delete transition | **High** (Visual transition boundary management) |
| `app/components/timeline/MediaBin.tsx` | Media library & asset bin | Multi-format asset grid (video, audio, image, text), duration & resolution badges, audio preview waveform player, search, sort | **High** (Professional media management) |
| `app/components/timeline/v2/TrackLabelColumn.tsx` | Track header column | Track name label, eye icon (hide/show track in preview), volume/mute toggle, track deletion | **High** (Clear multi-track hierarchy) |
| `app/components/timeline/v2/ZoomSlider.tsx` | Timeline zoom controls | Dynamic `pixelsPerSecond` zoom scaling (zoom in/out/reset) | **High** (Precise editing at varied time scales) |
| `app/components/editor/InspectorPanel.tsx` | Dedicated sidebar inspector | Detailed clip inspection (timing, volume, playback speed, transform X/Y/W/H), empty state placeholder | **High** (Desktop NLE inspector workflow) |
| `app/components/media/Transitions.tsx` | Transition browser | Visual transition cards, drag-and-drop payload generator for fade, wipe, slide, flip, clockWipe, iris | **Medium** (Complementary to RenderFlow's 74 YouTube transitions) |
| `app/schemas/timeline.ts` | Data schema definitions | Zod models for TrackState, ScrubberState, Transition, Keyframe, MediaBinItem | **High** (Standardized data interchange format) |

---

## 3. Detailed Feature Evaluation & Decision Matrix

| # | Feature Name | Upstream Source | Upstream Implemented Behavior | RenderFlow Relevance & Impact | Integration Decision | Technical Rationale & Implementation Approach |
|---|---|---|---|---|---|---|
| **1** | **Multi-Track Layered Timeline** | `TimelineTracks.tsx`, `v2/TrackRows.tsx`, `TrackLabelColumn.tsx` | Renders stacked tracks (Track 1, Track 2, etc.) with dedicated label column, mute/visibility buttons, and clip rows. | High. Replaces RenderFlow's single-strip timeline with a professional multi-track layout (Master Audio, Visual Scenes, Captions, Transitions). | **Adapt & Implement** | Implement as high-performance CSS Grid/Flexbox multi-track UI in `web/static/js/app.js` and `web/static/css/style.css`. Clean-room vanilla JS implementation avoids React dependency. |
| **2** | **Direct-DOM Drag & Trimming Handles** | `Scrubber.tsx` (lines 68–260) | Direct DOM `translate3d` manipulation on `mousemove` (bypassing React re-renders) for 60fps clip dragging and left/right trimming. | Critical. RenderFlow previously had static blocks; dynamic dragging and edge trimming elevates it to a true NLE. | **Adapt & Implement** | Port the direct-DOM drag/trim mathematical model into RenderFlow's timeline controller. Commit changes on `mouseup` to update the project plan. |
| **3** | **Magnetic Snapping Engine** | `Scrubber.tsx` (lines 138–152) | Snaps clip boundaries to grid points, playhead ruler, and adjacent clips within a configurable snap distance (10px). | High. Prevents accidental gaps or misaligned cuts during manual edits. | **Adapt & Implement** | Implement `findSnap(px)` utility supporting playhead snap, cut boundary snap, and 1-second grid snap. |
| **4** | **Timecode Ruler & Playhead Scrubbing** | `TimelineRuler.tsx`, `Scrubber.tsx` | Renders dynamic ticks with timecode strings (`MM:SS.mmm`), supports scrubbing with real-time timecode updates and jump-to-timecode input. | Critical. Essential for scrubbing narration and video preview simultaneously. | **Adapt & Implement** | Create interactive ruler canvas/element above timeline tracks; link mouse drag directly to HTML5 audio seek and video preview. |
| **5** | **Clip Split at Playhead** | `Scrubber.tsx`, `useTimeline.ts` | Cuts the active clip at the current playhead position into two distinct clips, recalculating durations. | High. Enables fine-grained scene splitting without re-running Auto-Map. | **Adapt & Implement** | Add "Split at Playhead" action (`S` key and context menu) which splits a scene segment and updates `plan.json`. |
| **6** | **Clip Selection & Context Menu** | `Scrubber.tsx`, `InspectorPanel.tsx` | Selection ring on clip click, right-click context menu (Split, Duplicate, Delete, Speed, Mute). | High. Standard desktop editing ergonomics. | **Adapt & Implement** | Implement custom dark-themed context menu and selection styling in RenderFlow's studio canvas. |
| **7** | **Clip Inspector Panel** | `ClipInspector.tsx`, `InspectorPanel.tsx` | Side panel showing clip timing (Start, End, Duration), image asset switcher, transition selector, fit/motion mode, and volume. | High. Replaces cluttered modal dialogs with an integrated inspector. | **Adapt & Implement** | Integrate into RenderFlow's right sidebar (`#sceneTableBody` area) with real-time two-way synchronization to selected clips. |
| **8** | **Timeline Zoom Controls** | `v2/ZoomSlider.tsx` | Scales `pixelsPerSecond` (0.5x, 1x, 2x, 5x, fit-to-view), adjusting ruler ticks and clip widths dynamically. | High. Allows users to view a 10-minute project at glance or zoom in to 0.1s cut precision. | **Adapt & Implement** | Add zoom button group (`[-]`, `[1x]`, `[+]`, `[Fit]`) and zoom slider into timeline header bar. |
| **9** | **Media Bin Metadata Badges** | `MediaBin.tsx` (lines 65–120) | Displays asset duration, dimensions (width×height), file size, type badge, and preview thumbnails. | High. Enhances RenderFlow's Media Bin with actionable technical metadata. | **Adapt & Implement** | Enhance image and audio asset tiles with resolution (e.g., `1920×1080`), aspect ratio (e.g., `16:9`), and file size badges. |
| **10** | **Keyboard Shortcuts** | `TimelineTracks.tsx`, `Scrubber.tsx` | Space (Play/Pause), Delete/Backspace (Delete clip), S (Split), Ctrl+Z (Undo), Ctrl+Y (Redo), Ctrl+S (Save). | High. Dramatically speeds up editor productivity. | **Adapt & Implement** | Implement global keyboard listener in `app.js` with shortcut cheat sheet modal (`?` or `Ctrl+/`). |
| **11** | **Undo / Redo History** | `useTimeline.ts` | History stack storing timeline states for undo/redo actions. | High. Protects users from accidental trims or deletions. | **Adapt & Implement** | Implement an in-memory command/history stack (up to 50 states) with Ctrl+Z / Ctrl+Y hotkeys. |
| **12** | **Transition Boundary Overlays** | `TransitionOverlay.tsx`, `Transitions.tsx` | Visual badges on track between clips representing transition type (dissolve, wipe, slide, film burn) and duration. | High. Integrates with RenderFlow's 74 YouTube transition packs and 8 built-in cinematic transitions. | **Adapt & Implement** | Display interactive transition badges at scene cut points on the timeline with direct transition picker. |
| **13** | **Remotion Headless Renderer** | `videorender/`, `@remotion/renderer` | Server-side React component rendering to MP4 via headless Chrome / Puppeteer. | Low / Incompatible. Heavy Node.js/Chromium dependency, slower than native FFmpeg, commercial license restrictions. | **Exclude** | Retain RenderFlow's native C++ FFmpeg filtergraph pipeline (hardware accelerated, chunked, 4K UHD, zero drift). |
| **14** | **AI Assistant / Chat Editing** | `app/components/chat/`, `backend/ai/` | LLM-driven prompt editing ("make video fast", "cut silent parts") via OpenAI / Gemini. | Incompatible with User Request. Prompt-driven editing requires remote API keys and internet. | **Exclude** | Completely omitted as per non-AI mandate. |
| **15** | **Cloud Auth & PostgreSQL** | `backend/auth/`, `backend/db.py` | Google OAuth, session cookies, remote PostgreSQL database for project storage. | Incompatible. RenderFlow is a 100% local Windows desktop application. | **Exclude** | Retain RenderFlow's local filesystem project format (`projects/{name}/plan.json`). |

---

## 4. Priority Implementation Plan

### Priority A — Core Editing Experience
1. **Multi-Track Timeline Container**:
   - Track 1: Master Narration Audio (with interactive waveform).
   - Track 2: Visual Scene Clips (image/video blocks with trim handles, selection ring, drag support).
   - Track 3: Captions & Overlays (timed subtitle spans).
   - Track 4: Transition FX Overlays (cut boundary badges).
2. **Interactive Playhead & Ruler**:
   - Top timecode ruler with major/minor tick marks and timecode label (`00:00:00.00`).
   - Drag scrubbing synchronizing audio element and live preview canvas.
3. **Editing Interactions**:
   - Trimming left/right handles on clips.
   - Magnetic snapping to cuts, playhead, and 1s grid.
   - Clip split at playhead (`S`), duplicate, and delete (`Del`).
   - Undo/Redo (`Ctrl+Z`, `Ctrl+Y`) history manager.
   - Keyboard shortcuts for Play/Pause (`Space`), Zoom (`Ctrl++`/`Ctrl+-`), and Save (`Ctrl+S`).

### Priority B — Media Library Enhancements
1. Metadata badges on asset tiles (resolution, aspect ratio, duration, size).
2. Drag-and-drop asset assignment onto timeline clips.
3. Search and type filter in Media Bin.

### Priority C — Live Preview & Playhead Synchronization
1. Synchronous frame preview on scrubbing.
2. Aspect ratio container preservation (16:9 widescreen, 9:16 portrait, 1:1 square).
3. Frame nudging buttons (-1f / +1f).

### Priority D — Clip Inspector Panel
1. Real-time inspector for active clip: start/end/duration, image asset, transition, fit/motion, volume.
2. Two-way binding between inspector changes, timeline display, and project plan.

### Priority E — Project Persistence & Renderer Adapter
1. Timeline changes immediately update canonical `plan.json` model with `user_override: true`.
2. Seamless integration with `fast_pipeline.py` FFmpeg rendering.
3. Backward compatibility with existing RenderFlow projects.
