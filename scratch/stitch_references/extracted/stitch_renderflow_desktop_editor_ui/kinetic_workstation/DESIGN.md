---
name: Kinetic Workstation
colors:
  surface: '#131315'
  surface-dim: '#131315'
  surface-bright: '#39393b'
  surface-container-lowest: '#0e0e10'
  surface-container-low: '#1b1b1d'
  surface-container: '#1f1f21'
  surface-container-high: '#2a2a2c'
  surface-container-highest: '#353437'
  on-surface: '#e4e2e4'
  on-surface-variant: '#c5c9af'
  inverse-surface: '#e4e2e4'
  inverse-on-surface: '#303032'
  outline: '#8f937b'
  outline-variant: '#444935'
  surface-tint: '#add519'
  primary: '#ffffff'
  on-primary: '#293500'
  primary-container: '#c8f23c'
  on-primary-container: '#566c00'
  inverse-primary: '#516600'
  secondary: '#b4c5ff'
  on-secondary: '#002a78'
  secondary-container: '#0053db'
  on-secondary-container: '#cdd7ff'
  tertiary: '#ffffff'
  on-tertiary: '#4d2600'
  tertiary-container: '#ffdcc3'
  on-tertiary-container: '#995200'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c8f23c'
  primary-fixed-dim: '#add519'
  on-primary-fixed: '#161e00'
  on-primary-fixed-variant: '#3c4d00'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#ffdcc3'
  tertiary-fixed-dim: '#ffb77d'
  on-tertiary-fixed: '#2f1500'
  on-tertiary-fixed-variant: '#6e3900'
  background: '#131315'
  on-background: '#e4e2e4'
  surface-variant: '#353437'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-mono-lg:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-mono-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '400'
    lineHeight: 14px
    letterSpacing: 0.03em
  caption:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '500'
    lineHeight: 12px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.25rem
  margin: 0.5rem
  space-xs: 0.125rem
  space-sm: 0.25rem
  space-md: 0.5rem
  space-lg: 0.75rem
  space-xl: 1rem
---

## Brand & Style
The design system powers an uncompromising, precision-engineered non-linear editing (NLE) environment built specifically for high-throughput desktop video workflows. The brand archetype is calibrated around technical authority, surgical accuracy, and high-performance throughput—evoking the muscle memory and reliability of professional post-production suites like DaVinci Resolve while introducing the kinetic agility of modern AI tooling. 

The aesthetic is functional brutalist-modernism tailored for digital work surfaces: pitch-dark structural architecture (#0E0E10), dense multi-pane tool dockings, tight hairline segmentation, and aggressive neon focal points led by an electric lime (#CBF53F). The emotional response should be one of total control, spatial discipline, and deep-focus immersion. Extraneous decoration, floaty drop shadows, and oversized margins are discarded in favor of maximum usable viewport space, low eye fatigue during 12-hour master editing sessions, and high-contrast timeline legibility.

## Colors
The color architecture enforces strict operational hierarchies to reduce cognitive load while editing multi-layered AV timelines.

### Base Surfaces & Panels
- **Canvas / Root Background (`#0E0E10`)**: Anchors outer frame borders, empty canvas zones, and monitor surrounds for pitch-black light absorption.
- **Panel Surface (`#212123`)**: Applied to all primary panels, inspector groups, media pool containers, and the timeline track header area.
- **Structural Partition / Border (`#19191B`)**: Used for 1px hairline dividers between splitters, docked panes, and inactive frame segments.
- **Elevated Controls & Wells (`#2B2B2E`)**: Houses interactive inputs, scrubbing fields, slider troughs, drop zones, and active timeline clips before selection.

### Accents & Broadcast Cues
- **Primary Accent (`#CBF53F` - Electric Lime)**: Reserved for high-priority user intentions: playhead current indicator, global render action buttons, active tool status, clip selection highlights, and keyframe points.
- **Primary Text (`#F4F4F5`)**: High-contrast, optical-grade white for clip names, primary timecodes, and active labels.
- **Secondary Text (`#A1A1AA`)**: Neutral gray for non-active parameter labels, secondary metadata, unit designations, and unselected tab headers.

### Timeline Domain Palette
Tracks use designated, high-distinction chromatic signatures with muted backgrounds for body visibility and bright borders for active operations:
- **Video Tracks**: Dark Base `#1E3A8A` / Active Boundary `#2563EB`
- **Audio / Narration Tracks**: Dark Base `#064E3B` / Waveform & Highlight `#059669`
- **Caption / Subtitle Tracks**: Dark Base `#4C0519` / Accent Boundary `#9F1239`
- **Transitions / FX Indicators**: Warm Amber `#D97706`

## Typography
Typography is treated as a clinical calibration tool. Scale ranges are intentionally compact (10px–18px) to preserve screen real estate for preview monitors, scopes, node graphs, and timeline rulers. 

- **Primary UI (Inter)**: Handles interface scaffolding, property names, track names, context menus, and status alerts. Text sizes never exceed 18px in desktop editing mode to maintain dense information parity.
- **Technical & Tabular Data (JetBrains Mono)**: Applied universally to all SMPTE timecode indicators (`01:14:22:18`), framerate tags (`23.976 fps`), audio decibel readouts (`-6.0 dB`), parameter values (rotation, scale, crop values), and timeline ruler subdivisions. The fixed glyph width eliminates structural layout jitter during high-speed scrubbing.

## Layout & Spacing
The layout adheres to a pane-based docking layout typical of workstation software. It rejects traditional web-like page flow in favor of an absolute viewport-filling grid matrix with resizable split panes:
- **Top Bar**: Fixed 40px utility strip (Project info, layout workspaces, export button).
- **Core Viewport**: Tri-pane horizontal layout (Left: Media Pool/Effects library, Center: Source/Program Monitors, Right: Contextual Inspector).
- **Lower Viewport**: Timeline assembly (Track Headers, Timeline Ruler, Track Canvas, Audio Master VU Meters).

### Spatial Rhythm & Scaling
- Micro-spacing (`0.125rem` / 2px to `0.25rem` / 4px) anchors interior control sets, knob pads, track label insets, and keyframe diamond gaps.
- Panel separation uses a constant `0.25rem` gutter with a rigid 1px structural splitter boundary.
- Outer canvas margins (`0.5rem`) frame the application window without bleed-through.
- Responsive reflow on narrow desktop windows shifts the side inspector into a collapsable drawer rather than wrapping elements, keeping the timeline and viewport at full visual dominance.

## Elevation & Depth
Elevation is articulated exclusively through flat tonal layering and precise 1px hairline segmentations. Deep drop shadows and ambient blurs are excluded because they interfere with pixel-level color grading and visual clutter.

- **Level 0 (Canvas Well - `#0E0E10`)**: The deepest tier. Timeline track backing canvas and video monitor surrounds.
- **Level 1 (Docked Surfaces - `#212123`)**: Standard panel tiers. Outlined with `1px solid #19191B`.
- **Level 2 (Interactive Controls - `#2B2B2E`)**: Inputs, timecode chips, track meters, button groups, and unselected media cards.
- **Level 3 (Overlays & Menus - `#2B2B2E`)**: Context menus, dropdown trays, and floating tool palettes. Elevated via a razor-sharp `0 4px 12px rgba(0, 0, 0, 0.65)` shadow with a 1px border of `#38383C`.
- **Level 4 (Active Spatial Cursor - `#CBF53F`)**: The playhead line and dragging clips create an optical elevation purely through color vibrancy and a subtle `0 0 8px rgba(203, 245, 63, 0.4)` accent bloom.

## Shapes
Geometry is utilitarian and hyper-disciplined. Corner radiuses conform strictly to `0.25rem` (4px) across inputs, buttons, timeline clips, and inspector cards. System panels and main viewport dock windows use completely square (`0px`) corners to allow seamless flush alignment along split-screen grid divisions. Chips, clip handles, and status pill badges use `0.25rem` to avoid toy-like circular soft aesthetics, ensuring the tool maintains an industrial, broadcast-grade demeanor.

## Components

### Buttons & Action Triggers
- **Primary Action (Global Export / Render)**: Background `#CBF53F`, text `#0E0E10`, font weight 600, border radius `4px`, padding `6px 14px`. Hover state: `#B8DE35`.
- **Panel Secondary Buttons**: Background `#2B2B2E`, text `#F4F4F5`, 1px border `#19191B`. Hover state: background `#38383C`.
- **Transport Controls (Play, Loop, In/Out)**: Seamless button cluster (`28x28px` hit target), dark neutral state, activating to `#CBF53F` icon fill when toggled.

### Timecode & Scrubber Inputs
- Formatted as rectangular monospaced cells (`#2B2B2E`), height 24px, 1px border `#19191B`.
- Typography: `JetBrains Mono` 12px, text `#F4F4F5`.
- Scrub interaction: Cursor transforms to a double-ended horizontal arrow. While dragging to scrub values, the border changes to `1px solid #CBF53F` and numeric output changes to `#CBF53F`.

### Timeline Tracks & Clips
- **Track Bounds**: Horizontal rails separated by a 1px `#19191B` divider.
- **Video Clips**: `#1E3A8A` base, 1px rounded edge, showing clip title in `#F4F4F5` with thumbnail filmstrip beneath.
- **Audio Clips**: `#064E3B` base, displaying a rendered `#059669` RMS waveform overlay.
- **Active Clip Selection**: Overrides the border with a high-intensity `2px solid #CBF53F` and displays corner transform handles.

### Checkboxes, Switches, & Radio Buttons
- **Checkboxes**: 14x14px square, background `#2B2B2E`, border 1px `#38383C`. When checked, filled with `#CBF53F` with an ink-black tick icon (`#0E0E10`).
- **Track Solo/Mute Toggles**: Micro-toggles (18x18px). "M" (Mute) triggers active warm amber (`#D97706`). "S" (Solo) triggers active electric lime (`#CBF53F`).

### Media Pool Cards & Tree Lists
- Dense row lists with alternating `#212123` and `#1C1C1E` striping. Selection creates a flush left 2px vertical bar in `#CBF53F`.
- Media thumbnails render with embedded duration labels in the lower right corner using `JetBrains Mono` 10px on a `#0E0E10` (80% opacity) background pad.