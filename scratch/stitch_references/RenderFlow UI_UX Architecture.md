# RenderFlow UI/UX Architecture

## 1. Product Positioning

RenderFlow should present itself as a **narration-first cinematic production workstation**: more guided than a traditional NLE, but more controllable than an automatic video generator.

The interface should consistently answer three questions:

1. **What is being said?** — narration, script, captions, and timing.
2. **What is being shown?** — scenes, assets, motion, transitions, and visual coverage.
3. **What will be delivered?** — preview quality, render status, and export settings.

The product should feel premium, focused, and dependable rather than futuristic or overloaded with AI controls.

## 2. Recommended Application Structure

Use a single-window desktop workspace with a persistent top bar, contextual left navigation, a central work area, and a bottom timeline.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Project / Save state     Workspace tabs        Undo Redo   Preview  Export   │
├──────────────┬───────────────────────────────────────────────┬──────────────┤
│ Workspace    │                                               │ Inspector    │
│ navigation   │                 Central canvas                 │ contextual   │
│              │             preview / browser / editor        │ properties   │
├──────────────┴───────────────────────────────────────────────┴──────────────┤
│ Narration / captions / visual / overlays / markers timeline                 │
│ Playhead, time ruler, zoom, snapping, track controls                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Primary workspaces

1. **Create** — import narration, analyze it, generate or arrange initial scenes.
2. **Edit** — full manual timeline editing and visual composition.
3. **Captions** — review, correct, style, and time captions.
4. **Audio** — inspect narration, music, sound effects, and levels.
5. **Export** — configure output and monitor rendering.

These should be workspace modes rather than separate applications. The project, media, timeline, and undo history remain shared.

A compact workspace switcher in the top bar should make the current mode obvious. Users should always be able to return to Edit without losing context.

## 3. Global Shell

### Top bar

The top bar should contain only high-value global actions:

- RenderFlow logo and project name.
- Save state indicator: `Saved`, `Saving…`, or `Changes not saved`.
- Undo and redo.
- Workspace switcher.
- Preview quality selector.
- Render queue/status indicator.
- Help and settings.
- Primary **Export** button.

The project name should be editable in place. Avoid a dense traditional menu bar in the default view; place advanced commands under menus and command search.

### Command search

Provide a searchable command palette, such as `Ctrl/Cmd + K`, for actions including split, ripple delete, fit timeline, import media, generate captions, and export. Display keyboard shortcuts beside commands.

### Persistent status feedback

Use non-blocking notifications for ordinary events and a persistent status area for important system state:

- Media import progress.
- AI analysis progress.
- Autosave state.
- Render progress.
- Missing media or project recovery warnings.

Never communicate important failures only through a transient toast.

## 4. Create Workspace: Guided Narration-First Production

The Create workspace should make the automated workflow understandable as a sequence without trapping the user in a wizard.

### Recommended layout

- **Left:** workflow steps and project readiness checklist.
- **Center:** narration waveform, script/transcript, and scene outline.
- **Right:** AI suggestions and generation controls.
- **Bottom:** simplified scene strip, expandable into the full timeline.

### Production stages

1. Import narration or script.
2. Analyze narration and generate transcript/captions.
3. Detect logical beats and propose scene boundaries.
4. Add or match visual assets.
5. Review scene coverage and timing.
6. Open in Edit for detailed adjustments.

Each AI action should show a preview of proposed changes before applying them. Use language such as **Suggest scene structure**, **Match assets**, or **Draft captions**, not irreversible-sounding automation labels.

### Readiness checklist

The checklist should identify actionable gaps:

- Narration loaded.
- Transcript available.
- Captions reviewed.
- Scenes cover the narration duration.
- Missing visuals resolved.
- No offline media.
- Export settings selected.

## 5. Edit Workspace: Core Professional Layout

The Edit workspace is the default long-term home for experienced users.

### Left panel: Media and project context

Use tabs rather than multiple permanently visible panels:

- **Media** — bins, search, filters, thumbnails, metadata, import.
- **Scenes** — scene list with duration, coverage status, and thumbnail.
- **Captions** — caption segments and review status.
- **Audio** — narration, music, and effects.
- **AI Assist** — contextual suggestions for the selected scene or timeline range.

Allow the panel to collapse to an icon rail. Preserve the last selected tab per project.

### Center: Preview canvas

The preview should use a neutral dark background with a clear safe-area overlay option. Controls below the canvas should include:

- Play/pause.
- Previous/next edit or scene.
- Timecode.
- Loop range.
- Preview resolution.
- Fit, 100%, and zoom controls.
- Full-screen preview.

When no scene is selected, show the current frame and project context. When media is missing, show a meaningful replacement state with **Relink**, **Replace**, and **Locate in Media** actions.

### Right panel: Inspector

The Inspector is context-sensitive and should never become a dumping ground. Organize properties into concise sections:

- Transform: position, scale, rotation, opacity.
- Crop and fit behavior.
- Motion: pan, zoom, keyframes where supported.
- Transition.
- Caption/text.
- Audio.
- Clip metadata and timing.

Use progressive disclosure. Show the most frequently changed controls first and place technical options under expandable sections.

## 6. Media Library

The Media panel should support both browsing and production readiness.

### Asset presentation

Offer a thumbnail grid by default, with a list view for metadata-heavy workflows. Each asset card may show:

- Thumbnail or waveform.
- Asset name.
- Type and duration.
- Resolution or sample rate where relevant.
- Used-in-scenes count.
- Offline/missing indicator.
- AI relevance or match score only when meaningful.

Do not make AI match scores the primary visual hierarchy. They are recommendations, not truth.

### Organization

Support bins/folders, search, type filters, duration filters, aspect-ratio filters, and a `Used` / `Unused` filter. ZIP imports should behave like a normal import job and show progress plus a clear destination.

### Drag-and-drop behavior

Dragging an asset onto the preview should replace or add to the selected scene based on the drop target. Dragging onto the timeline should show a placement preview and preserve narration timing by default.

## 7. Narration-First Timeline Design

The timeline is the product's defining interaction and should visually encode the audio-first model.

### Track hierarchy

Use a fixed, clearly labeled track stack:

1. **Narration** — locked by default and visually dominant.
2. **Captions** — aligned with narration segments.
3. **Visual scenes** — one or more visual tracks.
4. **Music** — optional.
5. **Sound effects** — optional.
6. **Overlays / titles** — optional.

The narration track should have a distinct accent color and a lock icon. A tooltip and onboarding hint should explain that it defines project duration and primary timing.

### Timeline features

- Time ruler with readable timecode.
- Scene boundary markers and scene names.
- Caption segment markers.
- Playhead with a high-contrast handle.
- Snap toggle and snapping feedback.
- Zoom slider plus fit-to-project shortcut.
- Track height controls.
- Mute, solo, lock, and visibility controls.
- Horizontal scroll independent of vertical track scroll.
- Range selection and loop playback.

### Safe editing rules

By default, visual edits should be non-destructive to narration timing:

- Moving or trimming a visual clip changes coverage, not the narration track.
- Splitting a visual clip preserves its total placement and scene relationship.
- Deleting a visual clip exposes a visible coverage gap rather than silently shifting narration.
- Any operation that can change global timing should be explicit and labeled, such as **Ripple shift all tracks**.

When a scene does not cover its narration segment, show a subtle but persistent warning on the scene marker and in the readiness checklist.

## 8. Scene Model and Scene Inspector

Treat a scene as the primary production unit. A scene can contain:

- Narration time range.
- One or more visual assets.
- Caption segment range.
- Transition in/out.
- Motion settings.
- Optional notes and AI suggestions.

Selecting a scene should select its related visual, narration range, captions, and markers together. This makes the relationship between spoken content and visuals visible without requiring users to manually hunt across tracks.

The Scene Inspector should show a compact summary:

```text
Scene 07 · 00:42.800–00:48.200
Narration: “...spoken segment...”
Visual coverage: Complete
Asset: archive_city_04.jpg
Motion: Slow push in
Transition: Cross dissolve · 12 frames
```

Include **Previous scene**, **Next scene**, **Duplicate scene**, **Replace visual**, and **Ask AI for alternatives** actions.

## 9. Captions and Text

The Captions workspace should be optimized for rapid review rather than styling alone.

### Caption review layout

- Center: video preview with caption safe-area guides.
- Bottom: caption timeline segments.
- Right: editable transcript table.

The transcript table should support inline editing, start/end time editing, search, and status indicators. Highlight the currently spoken segment during playback.

Caption styling should use reusable presets with a small number of clear controls:

- Font and weight.
- Size.
- Color and background.
- Position.
- Line length and maximum lines.
- Animation preset where supported.

Separate **content/timing** from **appearance** so users do not confuse a style change with a timing change.

## 10. AI Assistance Model

AI should appear at moments where it reduces work, not as a permanent chat surface competing with the editor.

### Contextual AI actions

- Generate or refine transcript.
- Split narration into scene beats.
- Suggest visual assets for a selected range.
- Suggest alternatives for a scene.
- Identify uncovered narration.
- Recommend motion or transition.
- Detect caption readability issues.
- Find repeated or visually redundant assets.

### Trust and review

Every AI suggestion should communicate:

- What will change.
- Which scenes or ranges are affected.
- Whether the action is reversible.
- A preview or before/after comparison.

Use a suggestion drawer with **Apply**, **Apply to selected**, **Preview**, and **Dismiss**. Never silently overwrite user edits.

## 11. Export Workspace

Export should be a dedicated workspace while remaining accessible from the global Export button.

### Layout

- **Left:** preset selection.
- **Center:** output summary and estimated file size/duration.
- **Right:** advanced settings.
- **Bottom:** validation messages and export action.

### Presets

Provide creator-oriented presets such as:

- YouTube 16:9.
- YouTube Shorts / Reels 9:16.
- Square social video 1:1.
- 4K cinematic master.
- Custom.

Advanced controls should include resolution, frame rate, aspect ratio, codec/container where supported, audio settings, quality, hardware acceleration, and output location.

Before export, run a validation pass for:

- Missing media.
- Uncovered narration.
- Caption overflow.
- Unsupported settings.
- Offline or inaccessible output path.

Errors should identify the exact scene or asset and provide a repair action.

## 12. Visual Design System

### Color

Use a dark neutral foundation optimized for long editing sessions:

- Background: near-black blue-gray.
- Elevated surfaces: slightly lighter charcoal.
- Borders: low-contrast cool gray.
- Primary accent: electric violet or blue-violet for active controls and AI-related actions.
- Narration accent: warm amber or coral, visually distinct from AI.
- Visual track accent: cool blue.
- Caption track accent: mint or cyan.
- Warning: amber.
- Error: restrained red.
- Success: green.

Color should never be the only indicator. Pair status colors with icons, labels, or patterns.

### Typography

Use a highly legible modern sans-serif with tabular numerals for timecodes. Establish a compact scale:

- 11–12 px: metadata and secondary labels.
- 13–14 px: controls and body text.
- 16 px: panel headings.
- 20–24 px: workspace headings and important empty states.

Use medium or semibold weight for labels, but avoid making every control bold.

### Density

Default to professional medium density. Let users choose compact or comfortable density in settings, but keep hit targets at least 28–32 px for common controls and larger for primary actions.

## 13. Interaction Patterns

- Prefer direct manipulation with visible drop previews.
- Use familiar keyboard shortcuts: spacebar playback, `S` split, `Delete` delete, `I/O` range markers, `Ctrl/Cmd + Z` undo.
- Show a tooltip after a short delay, including the shortcut.
- Make destructive actions undoable and clearly previewable.
- Use inline editing for names, caption text, and scene labels.
- Preserve selection and scroll position after edits.
- Avoid modal dialogs except for destructive operations, project recovery, or advanced configuration.
- Support context menus on clips, scenes, tracks, assets, and markers.

## 14. Empty, Loading, and Error States

Every major area should have a useful state, not merely a blank panel.

Examples:

- No project: **Create a project** / **Open project**.
- No narration: explain that narration establishes the project timeline and offer **Import narration**.
- No visuals: offer **Import media** and **Suggest visuals**.
- Missing media: identify the number of affected scenes and offer **Relink all**.
- Rendering: show progress, elapsed time, current stage, and cancel action.
- Render failure: show likely cause, affected settings, log access, and **Retry with fallback** where available.

## 15. Responsive Desktop Behavior

Although Windows desktop is the primary target, the layout should tolerate different window sizes.

At wide sizes, show Media, Preview, Inspector, and Timeline together. At narrower sizes:

- Collapse the left panel into an icon rail.
- Allow the Inspector to become a drawer.
- Keep the timeline visible because it is the primary editing surface.
- Never hide the current timecode or playback controls.

Support high-DPI scaling and keyboard-only navigation for core actions.

## 16. Recommended MVP Versus Future Opportunities

### Core interface to prioritize now

- Project shell and autosave state.
- Media import and library.
- Narration-first timeline.
- Scene selection and visual replacement.
- Preview playback.
- Basic caption review.
- Existing transitions and motion controls.
- FFmpeg export with progress and error states.
- Undo/redo for supported edits.

### Future opportunities

- AI visual matching and continuity scoring.
- Semantic scene search.
- Automatic B-roll replacement suggestions.
- Multi-version exports for different aspect ratios.
- Collaborative comments and review links.
- Brand kits and reusable caption templates.
- Audio ducking and intelligent music pacing.
- Advanced keyframes and compositing.

Future features should extend the same scene, timeline, and inspector model rather than introducing separate mental models.

## 17. Success Criteria

The design is successful if a new creator can:

1. Create or open a project.
2. Import narration and understand that it defines duration.
3. Add visuals and see exactly where coverage is complete or missing.
4. Preview the result without leaving the editing context.
5. Correct captions quickly.
6. Make manual changes without breaking narration timing.
7. Understand what AI will change before applying it.
8. Export a reliable finished video and recover from common errors.

For experienced users, the design should make frequent operations faster than a guided workflow while keeping the narration-first model visible and safe.

## Final Recommendation

Build RenderFlow around a **scene-centric, narration-anchored editing model** with three persistent concepts: the narration track is the timing authority, scenes are the production units, and the Inspector is the place where details are edited. Keep AI contextual and reviewable, keep the timeline visible, and make project health and render reliability first-class parts of the interface. This combination will differentiate RenderFlow from both rigid one-click video generators and complex traditional editors.
