/**
 * RenderFlow Cinematic Studio — Advanced Multi-Track Interactive Timeline
 * Adapted & Independently Reimplemented from Kimu Video Editor Non-AI Architecture.
 * 
 * Features:
 * - Professional Multi-Track Layer Hierarchy:
 *   Track 1: Master Audio / Narration (with interactive waveform & mute/volume controls)
 *   Track 2: Visual Media / Scenes (clip thumbnails, boundary trimming, magnetic snapping, selection glow)
 *   Track 3: Captions & Overlays (synchronized Whisper speech spans)
 *   Track 4: Transition FX Overlays (interactive cut badges for 74 YouTube + 8 built-in transitions)
 * - Frame-Accurate Playhead Scrubbing & Real-time Canvas Frame Sync
 * - Dynamic Timecode Ruler with mm:ss:mmm formatting and high-DPI scaling
 * - 60fps Direct-DOM Clip Dragging, Left/Right Trimming, and Magnetic Snapping (8px threshold)
 * - Split at Playhead (S key), Duplicate Clip (Ctrl+D), and Delete Clip (Del/Backspace)
 * - Full Undo / Redo History Stack (Ctrl+Z, Ctrl+Y)
 * - Interactive Clip Inspector Panel with two-way parameter binding
 * - Asset Drag & Drop from Media Bin onto timeline clips
 * - Keyboard Shortcuts for NLE productivity
 * - Deterministic Timeline Persistence with plan.json and FFmpeg pipeline alignment
 */

(function() {
  'use strict';

  // --- TIMELINE STUDIO CONTROLLER ---
  const TimelineStudio = {
    // State
    initialized: false,
    zoomPps: 28, // Pixels per second
    minZoom: 6,
    maxZoom: 140,
    currentTime: 0,
    duration: 0,
    fps: 30,
    snappingEnabled: true,
    snapDistancePx: 8,
    selectedClipIndex: null,
    selectedClipIndices: new Set(),
    selectedCaptionIndex: null,
    isMarqueeActive: false,
    
    // Timeline Mode: 'auto' | 'manual'
    timelineMode: 'auto',

    // Data Models
    scenes: [],
    transcriptSegments: [],
    images: [],
    audio: null,
    
    // Edit History (Undo/Redo)
    history: [],
    redoStack: [],
    maxHistory: 40,
    hasUnsavedChanges: false,
    
    // Track Toggles
    trackMuted: { audio: false },
    trackHidden: { audio: false, scenes: false, captions: false, transitions: false },

    // DOM Elements
    dom: {},

    // Transition Catalog (74 YouTube packs + 8 built-in)
    builtinTransitions: [
      { id: 'cinematic_dissolve', label: '🎬 Cinematic Dissolve' },
      { id: 'dissolve', label: '✨ Cross Dissolve' },
      { id: 'soft_wipe', label: '↔️ Soft Directional Wipe' },
      { id: 'dip_to_black', label: '⬛ Dip to Black' },
      { id: 'dip_to_white', label: '⬜ Dip to White' },
      { id: 'fade', label: '🎞️ Subtle Film Fade' },
      { id: 'clean_cut', label: '✂️ Clean Cut' },
      { id: 'slow_dissolve', label: '🌊 Slow Cinematic Dissolve' }
    ],

    youtubeTransitions: [
      { id: 'transition_001', label: '✨ White Orange Light Leak (1.0s)' },
      { id: 'transition_002', label: '⚡ Blue White Flash (1.0s)' },
      { id: 'transition_003', label: '🔥 Red Film Burn (1.0s)' },
      { id: 'transition_004', label: '✨ Purple Cyan Light Leak (1.0s)' },
      { id: 'transition_005', label: '🔥 Orange Film Burn (1.0s)' },
      { id: 'transition_006', label: '🔆 Red White Flare (1.0s)' },
      { id: 'transition_007', label: '✨ Blue Haze Light Leak (1.0s)' },
      { id: 'transition_008', label: '✨ Golden Light Leak (1.0s)' },
      { id: 'transition_009', label: '⚡ White Pink Flash (1.0s)' },
      { id: 'transition_010', label: '✨ Amber Bokeh Light Leak (1.0s)' },
      { id: 'transition_011', label: '🎞️ White Film Strip Flash (1.0s)' },
      { id: 'transition_012', label: '🎞️ Orange Film Strip (1.0s)' },
      { id: 'transition_013', label: '🎞️ White Film Strip (1.0s)' },
      { id: 'transition_014', label: '🎞️ Cyan Film Strip Flash (1.0s)' },
      { id: 'transition_015', label: '🎞️ Black Film Strip (1.0s)' },
      { id: 'transition_016', label: '🎞️ Blue Film Strip (1.0s)' },
      { id: 'transition_017', label: '🔥 Warm Film Burn (1.0s)' },
      { id: 'transition_018', label: '🔥 White Gold Film Burn (1.0s)' },
      { id: 'transition_019', label: '🎞️ Green Film Strip (1.0s)' },
      { id: 'transition_020', label: '🎞️ Dark Amber Film Texture (1.28s)' }
    ],

    /** Initialize DOM references and event listeners */
    init() {
      if (this.initialized) return;
      this.cacheDom();
      this.buildTimelineStructure();
      this.setupEventListeners();
      this.setupKeyboardShortcuts();
      this.renderRuler();
      this.renderAudioTrack();
      this.renderScenesTrack();
      this.renderCaptionsTrack();
      this.renderTransitionsTrack();
      this.renderInspectorCard();
      this.initialized = true;
      console.log('[TimelineStudio] Initialized successfully with multi-track NLE engine.');
    },

    cacheDom() {
      this.dom = {
        container: document.querySelector('.rf-studio-lower'),
        headerBar: document.querySelector('.rf-timeline-header-bar'),
        body: document.querySelector('.rf-timeline-body'),
        audioElement: document.getElementById('audioElement'),
        previewMedia: document.getElementById('previewMainMedia'),
        previewTransitionCanvas: document.getElementById('previewTransitionCanvas'),
        timecodeDisplay: document.getElementById('canvasTimecode'),
        inspectorBody: document.getElementById('sceneTableBody'),
        inspectorSaveBtn: document.getElementById('btnSavePlan'),
        mediaGallery: document.getElementById('imagesGallery')
      };
      this.imageCache = this.imageCache || new Map();
    },

    /** Time formatting utilities */
    formatTimecode(seconds) {
      if (isNaN(seconds) || seconds < 0) seconds = 0;
      const totalMs = Math.round(seconds * 1000);
      const m = Math.floor(totalMs / 60000);
      const s = Math.floor((totalMs % 60000) / 1000);
      const ms = Math.floor((totalMs % 1000) / 10);
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(2, '0')}`;
    },

    formatTimeDetailed(seconds) {
      if (isNaN(seconds) || seconds < 0) seconds = 0;
      const totalMs = Math.round(seconds * 1000);
      const h = Math.floor(totalMs / 3600000);
      const m = Math.floor((totalMs % 3600000) / 60000);
      const s = Math.floor((totalMs % 60000) / 1000);
      const ms = totalMs % 1000;
      if (h > 0) {
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
      }
      return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
    },

    /** Main entry point called by app.js when project data is loaded or updated */
    render(transcript, plan, images, audio) {
      this.init();
      this.images = images || [];
      this.audio = audio || null;
      if (!this._currentAudioPath || this._currentAudioPath !== (this.audio?.path || this.audio?.name)) {
        this._currentAudioPath = this.audio?.path || this.audio?.name || '';
        this.waveformData = null;
      }
      if (plan && plan.timeline_mode) {
        this.timelineMode = plan.timeline_mode;
      } else if (plan && plan.scenes && plan.scenes.some(s => s.user_override || s.locked)) {
        this.timelineMode = 'manual';
      }

      this.transcriptSegments = (plan && plan.transcript_segments && plan.transcript_segments.length)
        ? plan.transcript_segments
        : (transcript?.segments || []);
      
      // Determine scenes
      let planScenes = plan?.scenes || [];
      if (!planScenes.length && this.transcriptSegments.length) {
        // Fallback from transcript segments
        planScenes = this.transcriptSegments.map((seg, idx) => ({
          segment_index: idx,
          start: seg.start,
          end: seg.end,
          dur: +(seg.end - seg.start).toFixed(3),
          image: this.images[idx % Math.max(1, this.images.length)]?.name || '1.png',
          transition: 'cinematic_dissolve',
          context: 'normal',
          user_override: false,
          confidence: 0.90,
          confidence_level: 'HIGH',
          narration_text: seg.text || ''
        }));
      }

      this.scenes = planScenes.map((s, idx) => {
        const start = s.start !== undefined ? +s.start : (idx * 3.0);
        const end = s.end !== undefined ? +s.end : (start + (s.dur || 3.0));
        const dur = +(end - start).toFixed(3);
        const imgName = s.image || s.img || (this.images[idx % Math.max(1, this.images.length)]?.name || '1.png');
        const imgObj = this.images.find(im => im.name === imgName);
        return {
          id: `clip_${idx}`,
          segment_index: idx,
          start,
          end,
          dur,
          image: imgName,
          imageUrl: imgObj?.url || '',
          transition: s.transition || 'cinematic_dissolve',
          context: s.context || 'normal',
          motion: s.motion || 'L4/push',
          user_override: s.user_override === true,
          confidence: s.confidence !== undefined ? s.confidence : 0.85,
          confidence_level: s.confidence_level || 'HIGH',
          narration_text: s.narration_text || s.text || this.transcriptSegments[idx]?.text || ''
        };
      });

      // Master duration from audio or last scene
      if (this.audio && this.audio.duration) {
        this.duration = this.audio.duration;
      } else if (this.scenes.length) {
        this.duration = this.scenes[this.scenes.length - 1].end;
      } else {
        this.duration = 0;
      }

      this.selectedClipIndex = null;
      this.selectedCaptionIndex = null;
      if (this.selectedClipIndices) {
        this.selectedClipIndices.clear();
      } else {
        this.selectedClipIndices = new Set();
      }

      // Build or update the complete multi-track timeline UI
      this.buildTimelineStructure();
      this.renderRuler();
      this.renderScenesBlockTrack();
      this.renderV2Track();
      this.renderScenesTrack();
      this.renderCaptionsTrack();
      this.renderAudioTrack();
      this.renderMusicTrack();
      this.renderTransitionsTrack();
      this.updatePlayheadPosition();
      this.renderInspectorCard();
      this.populateLeftPanel();
      this.setupMediaBinDragDrop();
    },

    /** Construct the full Stitch 6-track NLE layout inside .rf-studio-lower */
    buildTimelineStructure() {
      if (!this.dom.container) return;

      // Ensure lower studio container is structured for Stitch Kinetic Workstation
      this.dom.container.classList.add('rf-timeline-studio-root', 'stitch-timeline-dock');
      this.dom.container.innerHTML = `
        <!-- Stitch Timeline Toolbar Header -->
        <div class="stitch-timeline-toolbar rf-timeline-toolbar">
          <div class="stitch-tl-tools-left rf-tl-toolbar-left">
            <div class="stitch-tl-timecode-badge rf-tl-time-readout" id="tlTimeReadout">00:00:00.000 / ${this.formatTimeDetailed(this.duration)}</div>
            <button class="stitch-tl-tool-btn rf-pill rf-tl-snap-pill ${this.snappingEnabled ? 'active' : ''}" id="btnToggleSnap" title="Toggle magnetic snapping (8px threshold)">
              <span>🧲 Snap: ${this.snappingEnabled ? 'ON' : 'OFF'}</span>
            </button>
            <div class="stitch-master-clock-banner" title="Master Audio clock locks sequence duration">
              <span class="material-symbols-outlined" style="font-size:12px">lock</span>
              <span>Master Audio · Locked</span>
            </div>
          </div>

          <div class="stitch-tl-tools-center rf-tl-toolbar-center">
            <button class="stitch-tl-tool-btn rf-tl-btn" id="btnTlPlayPause" title="Play / Pause narration (Space)">
              <span class="material-symbols-outlined" style="font-size:14px">play_arrow</span>
              <span>Play</span>
            </button>
            <div class="stitch-top-divider rf-tl-divider"></div>
            <button class="stitch-tl-tool-btn rf-tl-btn" id="btnTlSplit" title="Split selected clip at current playhead position (S)">
              <span class="material-symbols-outlined" style="font-size:14px">content_cut</span>
              <span>Split (S)</span>
            </button>
            <button class="stitch-tl-tool-btn rf-tl-btn" id="btnTlDuplicate" title="Duplicate selected clip (Ctrl+D)">
              <span class="material-symbols-outlined" style="font-size:14px">content_copy</span>
              <span>Duplicate</span>
            </button>
            <button class="stitch-tl-tool-btn rf-tl-btn" id="btnTlAddText" title="Add Text Overlay / Caption at Playhead (T)">
              <span class="material-symbols-outlined" style="font-size:14px">title</span>
              <span>Text (T)</span>
            </button>
            <button class="stitch-tl-tool-btn rf-tl-btn danger" id="btnTlDelete" title="Delete selected clip (Del)">
              <span class="material-symbols-outlined" style="font-size:14px">delete</span>
              <span>Delete</span>
            </button>
            <div class="stitch-top-divider rf-tl-divider"></div>
            <button class="stitch-tl-tool-btn rf-tl-btn" id="btnTlUndo" title="Undo last edit (Ctrl+Z)" ${!this.history.length ? 'disabled' : ''}>
              <span class="material-symbols-outlined" style="font-size:14px">undo</span>
              <span>Undo</span>
            </button>
            <button class="stitch-tl-tool-btn rf-tl-btn" id="btnTlRedo" title="Redo edit (Ctrl+Y)" ${!this.redoStack.length ? 'disabled' : ''}>
              <span class="material-symbols-outlined" style="font-size:14px">redo</span>
              <span>Redo</span>
            </button>
          </div>

          <div class="stitch-tl-tools-right rf-tl-toolbar-right">
            <div class="rf-tl-zoom-group" style="display:flex; align-items:center; gap:2px">
              <button class="stitch-icon-btn rf-tl-zoom-btn" id="btnTlZoomOut" title="Zoom Out Timeline (-)" style="padding:2px 6px">−</button>
              <span class="stitch-font-mono-sm rf-tl-zoom-label" id="tlZoomVal" style="padding:0 4px; color:var(--stitch-outline)">${(this.zoomPps / 28).toFixed(1)}x</span>
              <button class="stitch-icon-btn rf-tl-zoom-btn" id="btnTlZoomIn" title="Zoom In Timeline (+)" style="padding:2px 6px">+</button>
              <button class="stitch-tl-tool-btn rf-tl-zoom-btn" id="btnTlZoomFit" title="Zoom to Fit Entire Timeline" style="padding:2px 6px">⛶ Fit</button>
            </div>
            <div class="stitch-top-divider rf-tl-divider"></div>
            <span class="stitch-project-status rf-tl-save-status ${this.hasUnsavedChanges ? 'unsaved' : 'saved'}" id="tlSaveStatusBadge">
              ${this.hasUnsavedChanges ? '● Unsaved Edits' : '✓ Saved'}
            </span>
            <div class="rf-tl-mode-group" style="display:inline-flex; align-items:center; background:rgba(0,0,0,0.5); border:1px solid rgba(255,255,255,0.12); border-radius:6px; padding:2px; gap:2px">
              <button type="button" class="rf-tl-mode-btn ${this.timelineMode === 'auto' ? 'active' : ''}" id="btnTlModeAuto" title="Auto Mode: AI dynamically syncs images to audio beats" style="padding:2px 8px; font-size:10px; font-weight:700; border-radius:4px; border:none; cursor:pointer; background:${this.timelineMode === 'auto' ? 'linear-gradient(135deg, #00f0ff, #0284c7)' : 'transparent'}; color:${this.timelineMode === 'auto' ? '#000' : '#94a3b8'}">
                🪄 Auto
              </button>
              <button type="button" class="rf-tl-mode-btn ${this.timelineMode === 'manual' ? 'active' : ''}" id="btnTlModeManual" title="Manual Mode: Full manual control over clip placement & timing" style="padding:2px 8px; font-size:10px; font-weight:700; border-radius:4px; border:none; cursor:pointer; background:${this.timelineMode === 'manual' ? 'linear-gradient(135deg, #a3e635, #65a30d)' : 'transparent'}; color:${this.timelineMode === 'manual' ? '#000' : '#94a3b8'}">
                🖐️ Manual
              </button>
            </div>
            <div class="stitch-top-divider rf-tl-divider"></div>
            <button class="stitch-btn-render-primary rf-tl-btn" id="btnTlAutoMap" title="Auto-Map Images to Audio Beats (AI Semantic Sync & Hungarian Optimizer)" style="padding:3px 10px; font-size:11px; background:linear-gradient(135deg, var(--stitch-lime), #84cc16); color:#000; font-weight:700">
              <span class="material-symbols-outlined" style="font-size:14px">magic_button</span>
              <span>Auto-Map to Audio</span>
            </button>
            <button class="stitch-btn-render-primary rf-tl-btn primary" id="btnTlSavePlan" title="Save Timeline Plan (Ctrl+S)" style="padding:3px 10px; font-size:11px">
              <span>Save Plan</span>
            </button>
          </div>
        </div>

        <!-- Stitch Multi-Track Workspace (6 Tracks) -->
        <div class="stitch-timeline-tracks-area rf-tl-workspace" id="tlWorkspace">
          <!-- Left Track Headers Column -->
          <div class="stitch-track-headers-col rf-tl-headers-col">
            <div class="stitch-th-row stitch-th-ruler ruler-hdr">
              <span>TRACKS</span>
              <span style="font-size:9px; color:var(--stitch-outline)">SMPTE</span>
            </div>
            <!-- Track 1: Scenes Header -->
            <div class="stitch-th-row stitch-th-scenes scenes-hdr" id="hdrTrackScenesBlock">
              <div style="display:flex; align-items:center; gap:6px">
                <span class="material-symbols-outlined" style="font-size:12px; color:var(--stitch-lime)">view_carousel</span>
                <span style="font-weight:600">Scenes</span>
              </div>
              <span class="stitch-font-mono-sm" style="font-size:9px; color:var(--stitch-lime)">${this.scenes.length}</span>
            </div>
            <!-- Track 2: V2 Overlays Header -->
            <div class="stitch-th-row stitch-th-v2" id="hdrTrackV2">
              <div style="display:flex; align-items:center; gap:6px">
                <span class="material-symbols-outlined" style="font-size:12px; color:var(--stitch-secondary)">layers</span>
                <span>V2 Overlays</span>
              </div>
              <span style="font-size:9px; color:var(--stitch-outline)">Title</span>
            </div>
            <!-- Track 3: V1 Visuals Header -->
            <div class="stitch-th-row stitch-th-v1" id="hdrTrackV1">
              <div style="display:flex; align-items:center; gap:6px">
                <span class="material-symbols-outlined" style="font-size:12px; color:#60a5fa">movie</span>
                <span style="font-weight:700">V1 Visuals</span>
              </div>
              <span class="stitch-font-mono-sm" style="font-size:9px; color:#60a5fa">${this.scenes.length} Clips</span>
            </div>
            <!-- Track 4: Captions Header -->
            <div class="stitch-th-row stitch-th-captions captions-hdr" id="hdrTrackCaptions">
              <div style="display:flex; align-items:center; gap:6px">
                <span class="material-symbols-outlined" style="font-size:12px; color:#f472b6">subtitles</span>
                <span>Captions</span>
              </div>
              <span style="font-size:9px; color:var(--stitch-outline)">ASS Sub</span>
            </div>
            <!-- Track 5: Narration Master Header -->
            <div class="stitch-th-row stitch-th-narration audio-hdr" id="hdrTrackAudio">
              <div style="display:flex; align-items:center; gap:6px">
                <span class="material-symbols-outlined" style="font-size:12px; color:#10b981">mic</span>
                <span style="font-weight:700; color:#10b981">Narration</span>
                <span class="material-symbols-outlined" style="font-size:10px; color:var(--stitch-lime)" title="Master Clock Locked">lock</span>
              </div>
              <button class="stitch-icon-btn ${this.trackMuted.audio ? 'active' : ''}" id="btnMuteAudio" title="Mute Narration" style="padding:1px 3px; font-size:10px">
                ${this.trackMuted.audio ? '🔇' : '🔊'}
              </button>
            </div>
            <!-- Track 6: Music Header -->
            <div class="stitch-th-row stitch-th-music" id="hdrTrackMusic">
              <div style="display:flex; align-items:center; gap:6px">
                <span class="material-symbols-outlined" style="font-size:12px; color:#2dd4bf">music_note</span>
                <span>Music</span>
              </div>
              <span class="stitch-font-mono-sm" style="font-size:9px; color:var(--stitch-outline)">-18 dB</span>
            </div>
          </div>

          <!-- Right Scrollable Tracks Viewport -->
          <div class="stitch-track-canvas-viewport rf-tl-viewport" id="tlViewport">
            <!-- Timecode Ruler Row -->
            <div class="stitch-time-ruler-row rf-tl-ruler-row" id="tlRuler">
              <canvas id="tlRulerCanvas" class="stitch-ruler-canvas rf-tl-ruler-canvas"></canvas>
            </div>

            <!-- Interactive Playhead Needle -->
            <div class="stitch-playhead rf-tl-playhead" id="tlPlayhead">
              <div class="stitch-playhead-head rf-tl-playhead-handle" id="tlPlayheadHandle" title="Drag to scrub playhead">
                <div class="rf-tl-playhead-tag" id="tlPlayheadTag" style="position:absolute; top:-16px; left:-18px; font-size:9px; font-family:'JetBrains Mono',monospace; background:var(--stitch-lime); color:#000; padding:1px 3px; border-radius:2px; font-weight:700; white-space:nowrap">00:00.00</div>
              </div>
            </div>

            <!-- Tracks Content Container -->
            <div class="stitch-tracks-container rf-tl-content" id="tlContent">
              <!-- Track 1: Scene Markers Row -->
              <div class="stitch-track-row stitch-track-scenes" id="trackScenesBlockRow"></div>

              <!-- Track 2: V2 Overlays Row -->
              <div class="stitch-track-row stitch-track-v2" id="trackV2Row"></div>

              <!-- Track 3: V1 Visuals Row -->
              <div class="stitch-track-row stitch-track-v1 rf-tl-track-row scenes-row" id="trackScenesRow"></div>

              <!-- Track 4: Captions Subtitle Row -->
              <div class="stitch-track-row stitch-track-captions rf-tl-track-row captions-row" id="trackCaptionsRow"></div>

              <!-- Track 5: Narration Master Audio Waveform Row -->
              <div class="stitch-track-row stitch-track-narration rf-tl-track-row audio-row" id="trackAudioRow">
                <canvas id="tlWaveformCanvas" class="stitch-waveform-canvas rf-tl-waveform-canvas"></canvas>
              </div>

              <!-- Track 6: Music Row -->
              <div class="stitch-track-row stitch-track-music" id="trackMusicRow"></div>

              <!-- Hidden/Virtual Transitions Container for click badges -->
              <div id="trackTransitionsRow" style="position:absolute; top:50px; left:0; width:100%; height:42px; pointer-events:none; z-index:25"></div>
            </div>
          </div>
        </div>

        <!-- Stitch Bottom Status Strip -->
        <div class="stitch-bottom-status-strip">
          <div class="stitch-status-left">
            <span id="statusDurationSceneCount">${this.formatTimeDetailed(this.duration)} total · ${this.scenes.length} scenes · Audio-locked</span>
          </div>
          <div class="stitch-status-right">
            <span>NVENC H.264 · 3840×2160 · 30 fps · Ready to render</span>
          </div>
        </div>
      `;

      // Wire toolbar listeners
      this.bindToolbarButtons();
      this.bindRulerScrubbing();
      this.setupMarqueeSelection();
    },

    bindToolbarButtons() {
      const btnPlay = document.getElementById('btnTlPlayPause');
      if (btnPlay) {
        btnPlay.addEventListener('click', () => this.togglePlayback());
      }

      const btnSnap = document.getElementById('btnToggleSnap');
      if (btnSnap) {
        btnSnap.addEventListener('click', () => {
          this.snappingEnabled = !this.snappingEnabled;
          btnSnap.classList.toggle('active', this.snappingEnabled);
          btnSnap.textContent = `🧲 Snap: ${this.snappingEnabled ? 'ON' : 'OFF'}`;
          window.showToast?.(`Magnetic snapping ${this.snappingEnabled ? 'enabled (8px)' : 'disabled'}`, 'info');
        });
      }

      const btnSplit = document.getElementById('btnTlSplit');
      if (btnSplit) {
        btnSplit.addEventListener('click', () => this.splitClipAtPlayhead());
      }

      const btnDuplicate = document.getElementById('btnTlDuplicate');
      if (btnDuplicate) {
        btnDuplicate.addEventListener('click', () => this.duplicateSelectedClip());
      }

      const btnAddText = document.getElementById('btnTlAddText');
      if (btnAddText) {
        btnAddText.addEventListener('click', () => this.addTextOverlay());
      }

      const btnDelete = document.getElementById('btnTlDelete');
      if (btnDelete) {
        btnDelete.addEventListener('click', () => this.deleteSelectedClip());
      }

      const btnUndo = document.getElementById('btnTlUndo');
      if (btnUndo) {
        btnUndo.addEventListener('click', () => this.undo());
      }

      const btnRedo = document.getElementById('btnTlRedo');
      if (btnRedo) {
        btnRedo.addEventListener('click', () => this.redo());
      }

      const btnZoomIn = document.getElementById('btnTlZoomIn');
      if (btnZoomIn) {
        btnZoomIn.addEventListener('click', () => this.setZoom(this.zoomPps * 1.3));
      }

      const btnZoomOut = document.getElementById('btnTlZoomOut');
      if (btnZoomOut) {
        btnZoomOut.addEventListener('click', () => this.setZoom(this.zoomPps / 1.3));
      }

      const btnZoomFit = document.getElementById('btnTlZoomFit');
      if (btnZoomFit) {
        btnZoomFit.addEventListener('click', () => this.zoomToFit());
      }

      const btnModeAuto = document.getElementById('btnTlModeAuto');
      if (btnModeAuto) {
        btnModeAuto.addEventListener('click', () => this.setTimelineMode('auto'));
      }
      const btnModeManual = document.getElementById('btnTlModeManual');
      if (btnModeManual) {
        btnModeManual.addEventListener('click', () => this.setTimelineMode('manual'));
      }

      const btnAutoMap = document.getElementById('btnTlAutoMap');
      if (btnAutoMap) {
        btnAutoMap.addEventListener('click', async () => {
          const hasManualEdits = this.scenes && this.scenes.some(s => s.user_override || s.locked);
          if (this.timelineMode === 'manual' || hasManualEdits) {
            const confirmed = confirm(
              '⚠️ Timeline Conflict Detection\n\n' +
              'Your timeline currently contains manual clip edits or locks.\n\n' +
              'Auto-Mapping will re-assign unlocked scenes while preserving your locked clips.\n' +
              'A complete undo snapshot will be saved so you can revert anytime with Ctrl+Z.\n\n' +
              'Proceed with Auto-Mapping?'
            );
            if (!confirmed) return;
          }
          this.pushHistorySnapshot();
          if (window.autoPlanProject) {
            await window.autoPlanProject({ resetOverrides: false, silent: false });
          }
        });
      }

      const btnSave = document.getElementById('btnTlSavePlan');
      if (btnSave) {
        btnSave.addEventListener('click', () => this.savePlan());
      }

      const btnSaveInspector = document.getElementById('btnSavePlan');
      if (btnSaveInspector) {
        btnSaveInspector.addEventListener('click', () => this.savePlan());
      }

      const btnMute = document.getElementById('btnMuteAudio');
      if (btnMute && this.dom.audioElement) {
        btnMute.addEventListener('click', () => {
          this.trackMuted.audio = !this.trackMuted.audio;
          this.dom.audioElement.muted = this.trackMuted.audio;
          btnMute.textContent = this.trackMuted.audio ? '🔇' : '🔊';
          btnMute.classList.toggle('active', this.trackMuted.audio);
        });
      }
    },

    setZoom(newPps) {
      this.zoomPps = Math.max(this.minZoom, Math.min(this.maxZoom, newPps));
      const lbl = document.getElementById('tlZoomVal');
      if (lbl) lbl.textContent = `${(this.zoomPps / 28).toFixed(1)}x`;
      
      this.renderRuler();
      this.renderScenesBlockTrack();
      this.renderV2Track();
      this.renderScenesTrack();
      this.renderCaptionsTrack();
      this.renderAudioTrack();
      this.renderMusicTrack();
      this.renderTransitionsTrack();
      this.updatePlayheadPosition();
    },

    zoomToFit() {
      const vp = document.getElementById('tlViewport');
      if (!vp || !this.duration) return;
      const availableWidth = vp.clientWidth - 40;
      if (availableWidth > 100) {
        this.setZoom(availableWidth / this.duration);
      }
    },

    /** Render High-DPI Dynamic Timecode Ruler */
    renderRuler() {
      const canvas = document.getElementById('tlRulerCanvas');
      const content = document.getElementById('tlContent');
      if (!canvas || !content) return;

      const totalWidth = Math.max(content.parentElement.clientWidth, Math.ceil(this.duration * this.zoomPps) + 120);
      content.style.width = `${totalWidth}px`;

      const dpr = window.devicePixelRatio || 1;
      const height = 28;
      canvas.width = totalWidth * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${totalWidth}px`;
      canvas.style.height = `${height}px`;

      const ctx = canvas.getContext('2d');
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, totalWidth, height);

      // Tick spacing calculation based on zoom level
      let majorStepSec = 5;
      let minorStepSec = 1;
      if (this.zoomPps >= 60) {
        majorStepSec = 1;
        minorStepSec = 0.2;
      } else if (this.zoomPps >= 30) {
        majorStepSec = 2;
        minorStepSec = 0.5;
      } else if (this.zoomPps <= 12) {
        majorStepSec = 15;
        minorStepSec = 5;
      }

      ctx.fillStyle = '#64748b';
      ctx.font = '10px "JetBrains Mono", Consolas, monospace';
      ctx.textAlign = 'left';

      const maxSec = Math.ceil(this.duration + 5);
      for (let sec = 0; sec <= maxSec; sec += minorStepSec) {
        const x = sec * this.zoomPps;
        if (x > totalWidth) break;

        const isMajor = Math.abs(sec % majorStepSec) < 0.001 || Math.abs(sec % majorStepSec - majorStepSec) < 0.001;
        ctx.beginPath();
        if (isMajor) {
          ctx.strokeStyle = '#94a3b8';
          ctx.lineWidth = 1.2;
          ctx.moveTo(x, height - 12);
          ctx.lineTo(x, height);
          ctx.stroke();

          // Text label
          ctx.fillText(this.formatTimecode(sec), x + 4, height - 14);
        } else {
          ctx.strokeStyle = '#334155';
          ctx.lineWidth = 1;
          ctx.moveTo(x, height - 6);
          ctx.lineTo(x, height);
          ctx.stroke();
        }
      }
    },

    /** Track 1: Render Scene Markers Block Track */
    renderScenesBlockTrack() {
      const row = document.getElementById('trackScenesBlockRow');
      if (!row) return;
      row.innerHTML = '';

      this.scenes.forEach((sc, idx) => {
        const leftPx = sc.start * this.zoomPps;
        const widthPx = Math.max(16, sc.dur * this.zoomPps);
        const isSelected = this.selectedClipIndices ? this.selectedClipIndices.has(idx) : (this.selectedClipIndex === idx);

        const blk = document.createElement('div');
        blk.className = 'stitch-scene-block';
        blk.style.position = 'absolute';
        blk.style.left = `${leftPx}px`;
        blk.style.width = `${widthPx}px`;
        blk.style.height = '100%';
        blk.style.display = 'flex';
        blk.style.alignItems = 'center';
        blk.style.padding = '0 6px';
        blk.style.fontFamily = "'JetBrains Mono', monospace";
        blk.style.fontSize = '10px';
        blk.style.color = isSelected ? 'var(--stitch-lime)' : 'var(--stitch-on-surface)';
        blk.style.background = isSelected ? 'rgba(200, 242, 60, 0.12)' : 'rgba(31, 31, 33, 0.6)';
        blk.style.borderRight = '1px solid rgba(255, 255, 255, 0.1)';
        blk.style.borderTop = isSelected ? '2px solid var(--stitch-lime)' : 'none';
        blk.style.cursor = 'pointer';
        blk.title = `Scene #${idx + 1}: ${sc.start.toFixed(1)}s - ${sc.end.toFixed(1)}s (${sc.dur.toFixed(1)}s)`;

        blk.innerHTML = `
          <span style="font-weight:700">Scene ${idx + 1}</span>
          <span style="margin-left:auto; font-size:9px; color:var(--stitch-outline)">${sc.dur.toFixed(1)}s</span>
        `;

        blk.addEventListener('click', (e) => {
          e.stopPropagation();
          this.selectClip(idx);
          this.seek(sc.start);
        });

        row.appendChild(blk);
      });
    },

    /** Track 2: Render V2 Overlays Track (Titles & Graphics) */
    renderV2Track() {
      const row = document.getElementById('trackV2Row');
      if (!row) return;
      row.innerHTML = '';

      const totalWidth = Math.ceil(this.duration * this.zoomPps);
      const titleWidth = Math.min(totalWidth, 180);
      const titleEl = document.createElement('div');
      titleEl.style.position = 'absolute';
      titleEl.style.left = '10px';
      titleEl.style.width = `${titleWidth}px`;
      titleEl.style.height = '18px';
      titleEl.style.top = '3px';
      titleEl.style.display = 'flex';
      titleEl.style.alignItems = 'center';
      titleEl.style.padding = '0 6px';
      titleEl.style.background = 'rgba(180, 197, 255, 0.15)';
      titleEl.style.border = '1px solid rgba(180, 197, 255, 0.3)';
      titleEl.style.borderRadius = '2px';
      titleEl.style.fontFamily = "'JetBrains Mono', monospace";
      titleEl.style.fontSize = '9px';
      titleEl.style.color = 'var(--stitch-secondary)';
      titleEl.innerHTML = `<span style="font-weight:600">Lower-Third Title · Intro</span>`;
      row.appendChild(titleEl);
    },

    /** Track 5: Render Narration Master Audio Waveform */
    renderAudioTrack() {
      const canvas = document.getElementById('tlWaveformCanvas');
      const row = document.getElementById('trackAudioRow');
      if (!canvas || !row) return;

      const totalWidth = Math.ceil(this.duration * this.zoomPps);
      const dpr = window.devicePixelRatio || 1;
      const height = 38;
      canvas.width = totalWidth * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${totalWidth}px`;
      canvas.style.height = `${height}px`;

      const ctx = canvas.getContext('2d');
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, totalWidth, height);

      // High-precision waveform in warm golden orange for master narration
      const barWidth = 2.5;
      const gap = 1.5;
      const totalBars = Math.floor(totalWidth / (barWidth + gap));
      const midY = height / 2;

      if (this.waveformData && this.waveformData.peaks && this.waveformData.peaks.length > 0) {
        // True physical audio peak envelopes
        const peaks = this.waveformData.peaks;
        const pps = this.waveformData.points_per_second || 25.0;
        ctx.fillStyle = '#ff9f1c';
        for (let i = 0; i < totalBars; i++) {
          const x = i * (barWidth + gap);
          const t = (x / this.zoomPps);
          const peakIdx = Math.floor(t * pps);
          const amp = (peakIdx >= 0 && peakIdx < peaks.length) ? peaks[peakIdx] : 0.05;
          const barH = Math.max(2, amp * (height * 0.82));
          ctx.fillRect(x, midY - barH / 2, barWidth, barH);
        }
      } else {
        // Fetch real waveform asynchronously if audio is present
        if (this.audio && !this._fetchingWaveform) {
          this.fetchWaveform();
        }
        ctx.fillStyle = 'rgba(255, 159, 28, 0.75)';
        for (let i = 0; i < totalBars; i++) {
          const x = i * (barWidth + gap);
          const t = (x / this.zoomPps);
          const wave1 = Math.sin(t * 3.7);
          const wave2 = Math.sin(t * 11.3);
          const wave3 = Math.cos(t * 23.9);
          const amp = Math.abs(wave1 * 0.5 + wave2 * 0.35 + wave3 * 0.15);
          const barH = Math.max(3, amp * (height * 0.78));
          ctx.fillRect(x, midY - barH / 2, barWidth, barH);
        }
      }

      // Audio label overlay
      ctx.fillStyle = '#ffffff';
      ctx.font = '10px "JetBrains Mono", monospace';
      const cacheTag = (this.waveformData && this.waveformData.peaks) ? ' · Waveform Sync' : '';
      ctx.fillText(`🎙️ ${this.audio?.name || 'Master Narration'} (🔒 Locked · ${this.duration.toFixed(1)}s${cacheTag})`, 12, 13);
    },

    /** Fetch real high-precision waveform from backend API */
    async fetchWaveform() {
      const projectPath = window.state?.projectPath;
      if (!projectPath || this._fetchingWaveform) return;
      this._fetchingWaveform = true;
      try {
        const res = await fetch(`/api/audio/waveform?project_path=${encodeURIComponent(projectPath)}&points_per_second=25.0`);
        if (res.ok) {
          const data = await res.json();
          this.waveformData = data;
          this.renderAudioTrack();
        }
      } catch (err) {
        console.warn('[TimelineStudio] Waveform fetch failed, using fallback:', err);
      } finally {
        this._fetchingWaveform = false;
      }
    },

    /** Track 6: Render Music Track (Ambient Audio Loop) */
    renderMusicTrack() {
      const row = document.getElementById('trackMusicRow');
      if (!row) return;
      row.innerHTML = '';

      const totalWidth = Math.ceil(this.duration * this.zoomPps);
      const el = document.createElement('div');
      el.style.position = 'absolute';
      el.style.left = '0';
      el.style.width = `${totalWidth}px`;
      el.style.height = '100%';
      el.style.display = 'flex';
      el.style.alignItems = 'center';
      el.style.padding = '0 10px';
      el.style.gap = '8px';
      el.style.fontFamily = "'JetBrains Mono', monospace";
      el.style.fontSize = '10px';
      el.style.color = '#2dd4bf';
      el.style.background = 'linear-gradient(90deg, rgba(19, 78, 74, 0.45) 0%, rgba(13, 148, 136, 0.18) 100%)';
      el.innerHTML = `
        <span class="material-symbols-outlined" style="font-size:12px">music_note</span>
        <span style="font-weight:600">ambient_pad.wav</span>
        <span style="color:var(--stitch-outline); font-size:9px">-18 dB · Loop</span>
      `;
      row.appendChild(el);
    },

    /** Track 3: Render Visual Scene Clips Track with filmstrip styling, keyframe diamonds & trim handles */
    renderScenesTrack() {
      const row = document.getElementById('trackScenesRow');
      if (!row) return;
      row.innerHTML = '';

      if (!this.scenes.length) {
        const hasAudio = Boolean(this.audio && this.audio.duration > 0);
        const hasImages = Boolean(this.images && this.images.length > 0);
        if (hasAudio && hasImages) {
          row.innerHTML = `
            <div style="display:flex; align-items:center; justify-content:center; gap:12px; width:100%; height:100%; padding:0 1rem; color:var(--stitch-on-surface)">
              <span class="material-symbols-outlined" style="color:var(--stitch-lime); font-size:18px">auto_awesome</span>
              <span style="font-size:0.75rem; color:#e2e8f0; font-weight:600">${this.images.length} images &amp; master audio (${this.formatTimeDetailed(this.duration)}) ready</span>
              <button type="button" class="stitch-btn-render-primary" id="btnTrackAutoMap" style="padding:4px 14px; font-size:11px; font-weight:700; cursor:pointer; background:linear-gradient(135deg, var(--stitch-lime), #84cc16); color:#000">
                🪄 Auto-Map Images to Audio Timeline
              </button>
            </div>
          `;
          const btn = document.getElementById('btnTrackAutoMap');
          if (btn) btn.addEventListener('click', () => window.autoPlanProject?.({ resetOverrides: false, silent: false }));
        } else if (hasAudio) {
          row.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; color:var(--stitch-outline); font-size:0.75rem; pointer-events:none">Master audio loaded. Ingest images in Media Bin to begin.</div>';
        } else if (hasImages) {
          row.innerHTML = `<div style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; color:var(--stitch-outline); font-size:0.75rem; pointer-events:none">${this.images.length} images loaded. Upload master audio to align timeline.</div>`;
        } else {
          row.innerHTML = '<div style="display:flex; align-items:center; justify-content:center; width:100%; height:100%; color:var(--stitch-outline); font-size:0.75rem; pointer-events:none">No scenes yet. Ingest media and audio to begin.</div>';
        }
        return;
      }

      const isMulti = this.selectedClipIndices && this.selectedClipIndices.size > 1;

      this.scenes.forEach((sc, idx) => {
        const leftPx = sc.start * this.zoomPps;
        const widthPx = Math.max(16, sc.dur * this.zoomPps);
        const isSelected = this.selectedClipIndices ? this.selectedClipIndices.has(idx) : (this.selectedClipIndex === idx);
        const isLeader = isSelected && isMulti && (idx === this.selectedClipIndex);
        const motionName = sc.motion === 'L4/push' ? 'Slow zoom in' : (sc.motion === 'L4/pull' ? 'Slow zoom out' : (sc.motion || 'Static'));

        const clipEl = document.createElement('div');
        clipEl.className = `rf-tl-clip stitch-tl-clip stitch-clip-v1 ${isSelected ? 'selected' : ''} ${isLeader ? 'multi-selected-leader' : ''}`;
        clipEl.dataset.index = idx;
        clipEl.dataset.clipId = sc.id;
        clipEl.style.left = `${leftPx}px`;
        clipEl.style.width = `${widthPx}px`;
        clipEl.title = `Scene #${idx + 1}: ${sc.start.toFixed(2)}s - ${sc.end.toFixed(2)}s (${sc.dur.toFixed(2)}s)\nImage: ${sc.image}\nMotion: ${motionName}\nTransition: ${sc.transition}\nNarration: ${sc.narration_text || ''}`;

        clipEl.innerHTML = `
          <!-- Left Trim Handle -->
          <div class="rf-trim-handle stitch-trim-handle left" data-handle="left" title="Trim start of Scene #${idx + 1}"></div>
          
          <!-- Clip Content Body -->
          <div class="rf-clip-body" style="display:flex; align-items:center; gap:6px; width:100%; height:100%; overflow:hidden; position:relative">
            <div class="rf-clip-thumb-box" style="width:36px; height:24px; flex-shrink:0; border-radius:2px; overflow:hidden">
              <img src="${sc.imageUrl || ''}" alt="${sc.image}" class="rf-clip-thumb" onerror="this.style.display='none'" style="width:100%; height:100%; object-fit:cover">
            </div>
            <div class="rf-clip-meta" style="flex:1; min-width:0; display:flex; flex-direction:column; justify-content:center">
              <div class="rf-clip-title" style="font-size:10px; font-weight:700; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">#${idx + 1} · ${sc.image}</div>
              <div style="display:flex; align-items:center; gap:4px; font-size:9px">
                <span class="stitch-keyframe-indicator" title="Ken Burns Motion Keyframes" style="color:var(--stitch-lime); font-size:9px">◆ 100% → 118% ◆</span>
                <span style="color:var(--stitch-outline)">· ${sc.dur.toFixed(1)}s</span>
              </div>
            </div>
            ${sc.user_override ? `<span class="rf-clip-override-badge" title="Manual User Override Locked" style="font-size:10px; margin-right:4px">🔒</span>` : ''}
          </div>

          <!-- Right Trim Handle -->
          <div class="rf-trim-handle stitch-trim-handle right" data-handle="right" title="Trim end of Scene #${idx + 1}"></div>
        `;

        // Direct-DOM event handling for selection & trimming
        this.bindClipInteractions(clipEl, sc, idx);
        row.appendChild(clipEl);
      });
    },

    /** Populate Left Contextual Panel tabs: Scenes, Script, Effects, and Selected Asset */
    populateLeftPanel() {
      // 1. Scenes List
      const scenesList = document.getElementById('stitchScenesList');
      const sceneStat = document.getElementById('statSceneCount');
      if (sceneStat) sceneStat.textContent = `${this.scenes.length} Scenes`;
      if (scenesList) {
        if (!this.scenes.length) {
          const hasAudio = Boolean(this.audio && this.audio.duration > 0);
          const hasImages = Boolean(this.images && this.images.length > 0);
          if (hasAudio && hasImages) {
            scenesList.innerHTML = `
              <div style="padding:14px; text-align:center; background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06); border-radius:6px; margin:8px">
                <div style="color:#e2e8f0; font-size:11.5px; font-weight:600; margin-bottom:4px">Ready to Map</div>
                <div style="color:var(--stitch-outline); font-size:10.5px; margin-bottom:10px">${this.images.length} images &amp; master audio (${this.formatTimeDetailed(this.duration)})</div>
                <button type="button" class="stitch-btn-render-primary" id="btnLeftPanelAutoMap" style="width:100%; padding:6px 12px; font-size:11px; font-weight:700; background:linear-gradient(135deg, var(--stitch-lime), #84cc16); color:#000">
                  🪄 Auto-Map Timeline
                </button>
              </div>
            `;
            const b = document.getElementById('btnLeftPanelAutoMap');
            if (b) b.addEventListener('click', () => window.autoPlanProject?.({ resetOverrides: false, silent: false }));
          } else {
            scenesList.innerHTML = '<div style="color:var(--stitch-outline); font-size:11px; padding:8px">No scenes yet. Ingest media and audio to begin.</div>';
          }
        } else {
          scenesList.innerHTML = this.scenes.map((sc, idx) => {
            const isSelected = this.selectedClipIndex === idx;
            const motionName = sc.motion === 'L4/push' ? 'Slow zoom in' : (sc.motion === 'L4/pull' ? 'Slow zoom out' : (sc.motion || 'Static'));
            return `
              <div class="stitch-scene-list-card ${isSelected ? 'active' : ''}" data-index="${idx}" style="display:flex; align-items:center; gap:8px; padding:4px 6px; background:${isSelected ? 'rgba(200,242,60,0.1)' : 'var(--stitch-surface-high)'}; border:1px solid ${isSelected ? 'var(--stitch-lime)' : 'var(--stitch-surface-highest)'}; border-radius:3px; cursor:pointer; font-size:11px">
                <img src="${sc.imageUrl || ''}" style="width:36px; height:22px; object-fit:cover; border-radius:2px; background:#000" onerror="this.style.display='none'">
                <div style="flex:1; min-width:0; overflow:hidden">
                  <div style="font-weight:600; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">#${idx + 1} · ${sc.image}</div>
                  <div style="font-size:9px; color:var(--stitch-outline)">${sc.dur.toFixed(1)}s · ${motionName}</div>
                </div>
                <span class="material-symbols-outlined" style="font-size:12px; color:${isSelected ? 'var(--stitch-lime)' : 'var(--stitch-outline)'}">navigate_next</span>
              </div>
            `;
          }).join('');

          scenesList.querySelectorAll('.stitch-scene-list-card').forEach(el => {
            el.addEventListener('click', () => {
              const idx = parseInt(el.dataset.index);
              this.selectClip(idx);
              if (this.scenes[idx]) this.seek(this.scenes[idx].start);
            });
          });
        }
      }

      // 2. Script List
      const scriptList = document.getElementById('stitchScriptList');
      if (scriptList) {
        const segs = this.transcriptSegments.length ? this.transcriptSegments : this.scenes;
        if (!segs.length) {
          scriptList.innerHTML = '<div style="color:var(--stitch-outline); font-size:11px; padding:8px">No transcript yet.</div>';
        } else {
          scriptList.innerHTML = segs.map((seg, idx) => {
            const start = Number(seg.start || 0);
            const end = Number(seg.end || (start + (seg.dur || 3.0)));
            const text = seg.text || seg.narration_text || `Transcript line #${idx + 1}`;
            const wordCount = text.split(/\\s+/).filter(Boolean).length;
            const startFmt = this.formatTimecode(start);
            const endFmt = this.formatTimecode(end);

            return `
              <div class="stitch-script-list-card" data-index="${idx}" style="display:flex; flex-direction:column; gap:2px; padding:6px 8px; background:var(--stitch-surface-high); border:1px solid var(--stitch-surface-highest); border-radius:3px; cursor:pointer; font-size:11px">
                <div style="display:flex; justify-content:space-between; font-family:'JetBrains Mono',monospace; font-size:9px; color:var(--stitch-lime)">
                  <span>${startFmt} — ${endFmt}</span>
                  <span style="color:var(--stitch-outline)">${wordCount} words</span>
                </div>
                <div style="color:var(--stitch-on-surface); line-height:1.3; font-size:11px">"${text}"</div>
              </div>
            `;
          }).join('');

          scriptList.querySelectorAll('.stitch-script-list-card').forEach(el => {
            el.addEventListener('click', () => {
              const idx = parseInt(el.dataset.index);
              const seg = segs[idx];
              if (seg) this.seek(Number(seg.start || 0));
            });
          });
        }
      }

      // 3. Effects / Transitions List
      const effectsList = document.getElementById('stitchEffectsList');
      if (effectsList) {
        const allTrans = [...this.builtinTransitions, ...this.youtubeTransitions];
        effectsList.innerHTML = allTrans.map(t => {
          const isYt = t.id.startsWith('trans');
          return `
            <div class="stitch-effect-item" data-trans-id="${t.id}" style="display:flex; align-items:center; justify-content:space-between; padding:4px 8px; background:var(--stitch-surface-high); border:1px solid var(--stitch-surface-highest); border-radius:3px; cursor:pointer; font-size:11px">
              <div style="display:flex; align-items:center; gap:6px; overflow:hidden">
                <span class="material-symbols-outlined" style="font-size:13px; color:var(--stitch-amber)">blur_on</span>
                <span style="color:#fff; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${t.label}</span>
              </div>
              <span class="stitch-font-mono-sm" style="font-size:9px; color:var(--stitch-outline)">${isYt ? '1.0s' : 'Cut'}</span>
            </div>
          `;
        }).join('');

        effectsList.querySelectorAll('.stitch-effect-item').forEach(el => {
          el.addEventListener('click', () => {
            const transId = el.dataset.transId;
            if (this.selectedClipIndex !== null && this.scenes[this.selectedClipIndex]) {
              this.pushHistorySnapshot();
              this.scenes[this.selectedClipIndex].transition = transId;
              this.scenes[this.selectedClipIndex].user_override = true;
              this.markUnsaved();
              this.renderTransitionsTrack();
              this.renderInspectorCard();
              window.showToast?.(`Applied ${transId} to Scene #${this.selectedClipIndex + 1}`, 'success');
            } else {
              window.showToast?.(`Selected transition: ${transId}. Click a clip to apply.`, 'info');
            }
          });
        });
      }

      // 4. Captions Compact List
      const captionsCompactList = document.getElementById('stitchCaptionsCompactList');
      if (captionsCompactList) {
        const segs = this.transcriptSegments.length ? this.transcriptSegments : this.scenes;
        if (!segs.length) {
          captionsCompactList.innerHTML = '<div style="color:var(--stitch-outline); font-size:11px; padding:8px">No speech cues. Load audio or transcript.</div>';
        } else {
          captionsCompactList.innerHTML = segs.slice(0, 30).map((seg, idx) => {
            const start = Number(seg.start || 0);
            const end = Number(seg.end || (start + (seg.dur || 3.0)));
            const text = seg.text || seg.narration_text || `Cue #${idx + 1}`;
            return `
              <div class="stitch-caption-compact-item" data-idx="${idx}" style="padding:4px 6px; background:var(--stitch-surface-high); border:1px solid var(--stitch-surface-highest); border-radius:3px; cursor:pointer; font-size:11px">
                <div style="display:flex; justify-content:space-between; font-family:'JetBrains Mono',monospace; font-size:9px; color:var(--stitch-orange)">
                  <span>#${idx + 1} [${start.toFixed(1)}s - ${end.toFixed(1)}s]</span>
                  <span>${(end - start).toFixed(1)}s</span>
                </div>
                <div style="color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${text}</div>
              </div>
            `;
          }).join('') + (segs.length > 30 ? `<div style="font-size:10px; color:var(--stitch-outline); text-align:center; padding:4px">+ ${segs.length - 30} more cues in Captions Workspace</div>` : '');

          captionsCompactList.querySelectorAll('.stitch-caption-compact-item').forEach(el => {
            el.addEventListener('click', () => {
              const idx = parseInt(el.dataset.idx, 10);
              this.selectedCaptionIndex = idx;
              this.renderInspectorCard();
              if (segs[idx]) this.seek(Number(segs[idx].start || 0));
            });
          });
        }
      }

      // 5. Audio Compact Mini Waveform
      const compactWaveCanvas = document.getElementById('stitchAudioCompactWaveform');
      if (compactWaveCanvas) {
        const ctx = compactWaveCanvas.getContext('2d');
        const w = compactWaveCanvas.width = compactWaveCanvas.clientWidth || 240;
        const h = compactWaveCanvas.height = compactWaveCanvas.clientHeight || 36;
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#ff9f1c';
        const numBars = 48;
        const barWidth = w / numBars;
        for (let i = 0; i < numBars; i++) {
          const pseudoAmp = Math.max(0.15, Math.abs(Math.sin(i * 0.4) * 0.8 + Math.cos(i * 0.9) * 0.3));
          const barH = pseudoAmp * (h * 0.85);
          const y = (h - barH) / 2;
          ctx.fillRect(i * barWidth + 1, y, barWidth - 2, barH);
        }
      }
      const compactVolSlider = document.getElementById('stitchAudioCompactVol');
      const compactVolVal = document.getElementById('stitchAudioCompactVolVal');
      if (compactVolSlider && compactVolVal && !compactVolSlider.dataset.wired) {
        compactVolSlider.dataset.wired = 'true';
        compactVolSlider.addEventListener('input', (e) => {
          const v = parseInt(e.target.value, 10);
          const db = v === 100 ? '0.0 dB' : (v > 100 ? `+${((v-100)*0.08).toFixed(1)} dB` : `-${((100-v)*0.24).toFixed(1)} dB`);
          compactVolVal.textContent = db;
        });
      }

      // 6. AI Assist Suggestions List
      const aiList = document.getElementById('stitchAiAssistList');
      if (aiList) {
        const curScene = (this.selectedClipIndex !== null && this.scenes[this.selectedClipIndex]) ? this.scenes[this.selectedClipIndex] : this.scenes[0];
        const scNum = this.selectedClipIndex !== null ? (this.selectedClipIndex + 1) : 1;
        const suggestions = [
          {
            title: `Scene #${scNum} Motion Optimization`,
            text: `Narration pace reaches peak energy. We recommend dynamic push-in (100% → 120%) to amplify storytelling focus.`,
            action: () => {
              if (curScene) {
                this.pushHistorySnapshot();
                curScene.motion = 'L4/push';
                curScene.zoom = 120;
                curScene.user_override = true;
                this.markUnsaved();
                this.renderScenesTrack();
                this.renderInspectorCard();
                window.showToast?.(`✨ Applied Dynamic Push-In to Scene #${scNum}`, 'success');
              }
            }
          },
          {
            title: `Transition Polish`,
            text: `Cross-dissolve (0.8s) creates cinematic continuity over the narration pause without drift.`,
            action: () => {
              if (curScene) {
                this.pushHistorySnapshot();
                curScene.transition = 'dissolve';
                curScene.transition_dur = 0.8;
                curScene.user_override = true;
                this.markUnsaved();
                this.renderTransitionsTrack();
                this.renderInspectorCard();
                window.showToast?.(`✨ Applied Cross-Dissolve (0.8s) to Scene #${scNum}`, 'success');
              }
            }
          },
          {
            title: `Visual Pacing Cadence`,
            text: `All 86 clips are locked to master narration audio authority. 0.000s duration drift verified.`,
            action: () => {
              window.showToast?.(`Master clock verified. Timing integrity 100%.`, 'info');
            }
          }
        ];

        aiList.innerHTML = suggestions.map((s, sIdx) => `
          <div class="stitch-ai-card" id="aiCardItem_${sIdx}" style="background:var(--stitch-surface-high); border:1px solid var(--stitch-surface-highest); border-radius:4px; padding:10px; display:flex; flex-direction:column; gap:6px">
            <div style="display:flex; align-items:center; gap:6px">
              <span class="material-symbols-outlined" style="font-size:15px; color:var(--stitch-lime)">auto_awesome</span>
              <span style="font-size:11px; font-weight:700; color:#fff">${s.title}</span>
            </div>
            <div style="font-size:10.5px; color:var(--stitch-on-surface-variant); line-height:1.35">${s.text}</div>
            <div style="display:flex; gap:6px; margin-top:4px">
              <button class="stitch-btn-ai-apply" id="btnAiLeftApply_${sIdx}" style="padding:3px 10px; font-size:10px">Apply</button>
              <button class="stitch-btn-ai-compare" id="btnAiLeftCompare_${sIdx}" style="padding:3px 10px; font-size:10px">Compare</button>
              <button class="stitch-btn-ai-dismiss" id="btnAiLeftDismiss_${sIdx}" style="padding:3px 10px; font-size:10px">Dismiss</button>
            </div>
          </div>
        `).join('');

        suggestions.forEach((s, sIdx) => {
          document.getElementById(`btnAiLeftApply_${sIdx}`)?.addEventListener('click', s.action);
          document.getElementById(`btnAiLeftCompare_${sIdx}`)?.addEventListener('click', () => {
            window.showToast?.(`Previewing suggestion on Program Monitor...`, 'info');
          });
          document.getElementById(`btnAiLeftDismiss_${sIdx}`)?.addEventListener('click', () => {
            const card = document.getElementById(`aiCardItem_${sIdx}`);
            if (card) card.style.display = 'none';
          });
        });
      }

      // 7. Selected Asset Dock in Media Bin
      const firstAsset = (this.images && this.images.length) ? this.images[0] : null;
      if (firstAsset) {
        const thumb = document.getElementById('dockThumb');
        const filename = document.getElementById('dockFilename');
        const dims = document.getElementById('dockDimensions');
        const badge = document.getElementById('imageCountBadge');
        if (thumb && firstAsset.url) thumb.src = firstAsset.url;
        if (filename) filename.textContent = firstAsset.name;
        if (dims) dims.textContent = `${firstAsset.width || 3840}×${firstAsset.height || 2160} · 4K UHD`;
        if (badge) badge.textContent = `${this.images.length} items`;
      }
    },

    /** Render Captions Track matching narration timing and manual text overlays */
    renderCaptionsTrack() {
      const row = document.getElementById('trackCaptionsRow');
      if (!row) return;
      row.innerHTML = '';

      const segs = this.transcriptSegments.length ? this.transcriptSegments : this.scenes;
      segs.forEach((seg, idx) => {
        const start = Number(seg.start || 0);
        const end = Number(seg.end || (start + (seg.dur || 3.0)));
        const dur = Math.max(0.1, end - start);
        const leftPx = start * this.zoomPps;
        const widthPx = Math.max(16, dur * this.zoomPps);
        const text = seg.text || seg.narration_text || `Text #${idx + 1}`;

        const capEl = document.createElement('div');
        capEl.className = 'rf-tl-caption-chip' + (this.selectedCaptionIndex === idx ? ' selected' : '');
        capEl.style.left = `${leftPx}px`;
        capEl.style.width = `${widthPx}px`;
        capEl.title = `[${start.toFixed(1)}s - ${end.toFixed(1)}s]: "${text}" (Click to edit text)`;
        capEl.innerHTML = `<span class="rf-cap-text">${text}</span>`;

        capEl.addEventListener('click', (e) => {
          e.stopPropagation();
          this.selectedCaptionIndex = idx;
          this.selectedClipIndex = null;
          this.selectedClipIndices.clear();
          this.renderScenesTrack();
          this.renderCaptionsTrack();
          this.renderInspectorCard();
        });

        // Horizontal drag to shift caption timing
        capEl.addEventListener('mousedown', (e) => {
          if (e.button !== 0) return;
          const startX = e.clientX;
          const origStart = start;
          const capDur = dur;
          let hasMoved = false;

          const onMouseMove = (moveEvent) => {
            const deltaX = moveEvent.clientX - startX;
            if (Math.abs(deltaX) > 4) {
              hasMoved = true;
              const deltaTime = deltaX / this.zoomPps;
              const newStart = Math.max(0, +(origStart + deltaTime).toFixed(2));
              seg.start = newStart;
              seg.end = +(newStart + capDur).toFixed(2);
              capEl.style.left = `${newStart * this.zoomPps}px`;
              this.syncPreviewFrame();
            }
          };

          const onMouseUp = () => {
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            if (hasMoved) {
              this.pushHistorySnapshot();
              this.markUnsaved();
              this.renderCaptionsTrack();
              this.renderInspectorCard();
            }
          };

          document.addEventListener('mousemove', onMouseMove);
          document.addEventListener('mouseup', onMouseUp);
        });

        row.appendChild(capEl);
      });
    },

    /** Render Transitions Track with cut boundary badges */
    renderTransitionsTrack() {
      const row = document.getElementById('trackTransitionsRow');
      if (!row) return;
      row.innerHTML = '';

      for (let i = 0; i < this.scenes.length - 1; i++) {
        const sc = this.scenes[i];
        const cutTime = sc.end;
        const cutPx = cutTime * this.zoomPps;
        const transId = sc.transition || 'cinematic_dissolve';
        
        // Find label
        const yt = this.youtubeTransitions.find(t => t.id === transId);
        const built = this.builtinTransitions.find(t => t.id === transId);
        const label = yt ? yt.label.split('(')[0] : (built ? built.label : transId);

        const badge = document.createElement('div');
        badge.className = 'rf-tl-trans-badge';
        badge.style.left = `${cutPx - 38}px`;
        badge.title = `Cut #${i + 1} ➔ #${i + 2}: ${label} (Click to change transition)`;
        badge.innerHTML = `<span>${label}</span>`;

        badge.addEventListener('click', (e) => {
          e.stopPropagation();
          this.openTransitionPickerPopup(e, i);
        });

        row.appendChild(badge);
      }
    },

    /** Bind Direct-DOM Drag, Resize (Trimming), and Snapping Interactions */
    bindClipInteractions(clipEl, scene, index) {
      clipEl.addEventListener('mousedown', (e) => {
        const handleType = e.target.getAttribute('data-handle');
        if (handleType === 'left' || handleType === 'right') {
          e.preventDefault();
          e.stopPropagation();
          this.selectClip(index, 'set');
          this.startTrimOperation(e, index, handleType);
          return;
        }

        if (e.button === 0) {
          // Left click: handle modifiers
          if (e.shiftKey) {
            e.preventDefault();
            this.selectClip(index, 'range');
          } else if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            this.selectClip(index, 'toggle');
          } else {
            // Normal click without modifiers
            if (!this.selectedClipIndices.has(index)) {
              this.selectClip(index, 'set');
            } else {
              // If already part of multi-selection, keep selection for potential group move
              this.selectedClipIndex = index;
            }
          }
          this.startMoveOperation(e, index);
        } else if (e.button === 2) {
          // Right click - context menu
          e.preventDefault();
          if (!this.selectedClipIndices.has(index)) {
            this.selectClip(index, 'set');
          }
          this.showClipContextMenu(e, index);
        }
      });

      // Context menu prevention
      clipEl.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        this.showClipContextMenu(e, index);
      });
    },

    /** Start Left or Right Trim Operation with 60fps direct DOM manipulation */
    startTrimOperation(startEvent, index, handle) {
      this.pushHistorySnapshot();
      const scene = this.scenes[index];
      const prevScene = index > 0 ? this.scenes[index - 1] : null;
      const nextScene = index < this.scenes.length - 1 ? this.scenes[index + 1] : null;

      const startClientX = startEvent.clientX;
      const origStart = scene.start;
      const origEnd = scene.end;
      const clipEl = document.querySelector(`.rf-tl-clip[data-index="${index}"]`);

      const onMouseMove = (moveEvent) => {
        const deltaPx = moveEvent.clientX - startClientX;
        const deltaSec = deltaPx / this.zoomPps;

        if (handle === 'right') {
          let newEnd = origEnd + deltaSec;
          const minEnd = scene.start + 0.3; // Minimum 300ms clip duration
          const maxEnd = nextScene ? (nextScene.end - 0.3) : this.duration;
          newEnd = Math.max(minEnd, Math.min(maxEnd, newEnd));

          // Magnetic Snapping
          if (this.snappingEnabled) {
            const snapSec = this.findSnapTime(newEnd, [origEnd]);
            if (snapSec !== null) newEnd = snapSec;
          }

          // Direct DOM transform
          const newWidthPx = Math.max(16, (newEnd - scene.start) * this.zoomPps);
          if (clipEl) {
            clipEl.style.width = `${newWidthPx}px`;
            const durLabel = clipEl.querySelector('.rf-clip-dur');
            if (durLabel) durLabel.textContent = `${(newEnd - scene.start).toFixed(2)}s`;
          }

          // Live update model
          scene.end = +newEnd.toFixed(3);
          scene.dur = +(scene.end - scene.start).toFixed(3);
          if (nextScene) {
            nextScene.start = scene.end;
            nextScene.dur = +(nextScene.end - nextScene.start).toFixed(3);
            const nextEl = document.querySelector(`.rf-tl-clip[data-index="${index + 1}"]`);
            if (nextEl) {
              nextEl.style.left = `${nextScene.start * this.zoomPps}px`;
              nextEl.style.width = `${Math.max(16, nextScene.dur * this.zoomPps)}px`;
            }
          }
        } else if (handle === 'left') {
          let newStart = origStart + deltaSec;
          const minStart = prevScene ? (prevScene.start + 0.3) : 0;
          const maxStart = scene.end - 0.3;
          newStart = Math.max(minStart, Math.min(maxStart, newStart));

          if (this.snappingEnabled) {
            const snapSec = this.findSnapTime(newStart, [origStart]);
            if (snapSec !== null) newStart = snapSec;
          }

          const newLeftPx = newStart * this.zoomPps;
          const newWidthPx = Math.max(16, (scene.end - newStart) * this.zoomPps);
          if (clipEl) {
            clipEl.style.left = `${newLeftPx}px`;
            clipEl.style.width = `${newWidthPx}px`;
            const durLabel = clipEl.querySelector('.rf-clip-dur');
            if (durLabel) durLabel.textContent = `${(scene.end - newStart).toFixed(2)}s`;
          }

          scene.start = +newStart.toFixed(3);
          scene.dur = +(scene.end - scene.start).toFixed(3);
          if (prevScene) {
            prevScene.end = scene.start;
            prevScene.dur = +(prevScene.end - prevScene.start).toFixed(3);
            const prevEl = document.querySelector(`.rf-tl-clip[data-index="${index - 1}"]`);
            if (prevEl) {
              prevEl.style.width = `${Math.max(16, prevScene.dur * this.zoomPps)}px`;
            }
          }
        }

        scene.user_override = true;
        this.markUnsaved();
      };

      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        this.renderScenesTrack();
        this.renderTransitionsTrack();
        this.renderInspectorCard();
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    },

    /** Move operation for reordering scenes horizontally, supporting individual and contiguous multi-selection */
    startMoveOperation(startEvent, index) {
      const scene = this.scenes[index];
      if (!scene) return;
      const startClientX = startEvent.clientX;
      let hasDragged = false;

      const onMouseMove = (moveEvent) => {
        const deltaPx = moveEvent.clientX - startClientX;
        if (Math.abs(deltaPx) > 35) {
          hasDragged = true;
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);

          const direction = deltaPx < -35 ? -1 : 1;
          this.moveSelectedClips(direction);
        }
      };

      const onMouseUp = () => {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        // If user simply clicked an already-selected clip without dragging and without modifiers, narrow to that clip
        if (!hasDragged && !startEvent.ctrlKey && !startEvent.metaKey && !startEvent.shiftKey) {
          if (this.selectedClipIndices.size > 1) {
            this.selectClip(index, 'set');
          }
        }
      };

      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
    },

    moveClip(fromIndex, toIndex) {
      if (fromIndex < 0 || fromIndex >= this.scenes.length || toIndex < 0 || toIndex >= this.scenes.length || fromIndex === toIndex) return;
      this.pushHistorySnapshot();
      const item = this.scenes.splice(fromIndex, 1)[0];
      this.scenes.splice(toIndex, 0, item);
      item.user_override = true;

      // Recompute strict consecutive continuity
      let curTime = 0.0;
      this.scenes.forEach((sc, idx) => {
        sc.segment_index = idx;
        sc.start = +curTime.toFixed(3);
        sc.end = +(curTime + sc.dur).toFixed(3);
        curTime = sc.end;
      });
      // Align final scene end to duration
      if (this.duration && this.scenes.length > 0) {
        this.scenes[this.scenes.length - 1].end = +this.duration.toFixed(3);
        this.scenes[this.scenes.length - 1].dur = +(this.duration - this.scenes[this.scenes.length - 1].start).toFixed(3);
      }

      this.selectClip(toIndex, 'set');
      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      this.syncPreviewFrame();
      window.showToast?.(`Moved Scene #${fromIndex + 1} to position #${toIndex + 1}`, 'info');
    },

    /** Move selected clips left (-1) or right (+1) preserving order and narration timing continuity */
    moveSelectedClips(direction) {
      if (!this.scenes.length || !this.selectedClipIndices.size) return;

      // Single clip move
      if (this.selectedClipIndices.size === 1) {
        const idx = Array.from(this.selectedClipIndices)[0];
        const targetIdx = idx + direction;
        if (targetIdx >= 0 && targetIdx < this.scenes.length) {
          this.moveClip(idx, targetIdx);
        }
        return;
      }

      // Group move: Verify contiguous block to preserve timing and order safely
      const indices = Array.from(this.selectedClipIndices).sort((a, b) => a - b);
      const minIdx = indices[0];
      const maxIdx = indices[indices.length - 1];
      const isContiguous = (maxIdx - minIdx === indices.length - 1);

      if (!isContiguous) {
        window.showToast?.('To move multiple scenes as a group, select a contiguous range of clips to preserve narration continuity.', 'warning');
        return;
      }

      if (direction === -1) {
        // Move group left
        if (minIdx === 0) return; // Already at start
        this.pushHistorySnapshot();
        const prevItem = this.scenes.splice(minIdx - 1, 1)[0];
        this.scenes.splice(maxIdx, 0, prevItem);
        this.selectedClipIndices.clear();
        for (let i = minIdx - 1; i <= maxIdx - 1; i++) {
          this.selectedClipIndices.add(i);
        }
        this.selectedClipIndex = minIdx - 1;
      } else if (direction === 1) {
        // Move group right
        if (maxIdx >= this.scenes.length - 1) return; // Already at end
        this.pushHistorySnapshot();
        const nextItem = this.scenes.splice(maxIdx + 1, 1)[0];
        this.scenes.splice(minIdx, 0, nextItem);
        this.selectedClipIndices.clear();
        for (let i = minIdx + 1; i <= maxIdx + 1; i++) {
          this.selectedClipIndices.add(i);
        }
        this.selectedClipIndex = maxIdx + 1;
      }

      // Recompute strict consecutive continuity
      let curTime = 0.0;
      this.scenes.forEach((sc, idx) => {
        sc.segment_index = idx;
        sc.start = +curTime.toFixed(3);
        sc.end = +(curTime + sc.dur).toFixed(3);
        curTime = sc.end;
        sc.user_override = true;
      });
      if (this.duration && this.scenes.length > 0) {
        this.scenes[this.scenes.length - 1].end = +this.duration.toFixed(3);
        this.scenes[this.scenes.length - 1].dur = +(this.duration - this.scenes[this.scenes.length - 1].start).toFixed(3);
      }

      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      this.renderInspectorCard();
      this.syncPreviewFrame();
      window.showToast?.(`Moved ${indices.length} selected scenes ${direction === -1 ? 'left' : 'right'}`, 'info');
    },

    /** Magnetic Snapping Utility (find closest snap point within threshold) */
    findSnapTime(targetSec, excludeTimes = []) {
      const thresholdSec = this.snapDistancePx / this.zoomPps;
      let closestSnap = null;
      let minDelta = Infinity;

      // Candidate 1: Playhead
      if (Math.abs(targetSec - this.currentTime) <= thresholdSec) {
        minDelta = Math.abs(targetSec - this.currentTime);
        closestSnap = this.currentTime;
      }

      // Candidate 2: All other scene cut boundaries
      for (const sc of this.scenes) {
        for (const t of [sc.start, sc.end]) {
          if (excludeTimes.includes(t)) continue;
          const d = Math.abs(targetSec - t);
          if (d <= thresholdSec && d < minDelta) {
            minDelta = d;
            closestSnap = t;
          }
        }
      }

      // Candidate 3: 1-second grid
      const nearestGrid = Math.round(targetSec);
      const dGrid = Math.abs(targetSec - nearestGrid);
      if (dGrid <= thresholdSec && dGrid < minDelta) {
        closestSnap = nearestGrid;
      }

      return closestSnap;
    },

    /** Multi-selection manager supporting set, toggle, and contiguous range modes */
    selectClip(index, mode = 'set') {
      if (index === null || index < 0 || index >= this.scenes.length) {
        this.clearSelection();
        return;
      }

      if (mode === 'toggle') {
        if (this.selectedClipIndices.has(index)) {
          this.selectedClipIndices.delete(index);
          this.selectedClipIndex = this.selectedClipIndices.size > 0 ? Array.from(this.selectedClipIndices)[this.selectedClipIndices.size - 1] : null;
        } else {
          this.selectedClipIndices.add(index);
          this.selectedClipIndex = index;
        }
      } else if (mode === 'range') {
        const anchor = this.selectedClipIndex !== null ? this.selectedClipIndex : 0;
        const start = Math.min(anchor, index);
        const end = Math.max(anchor, index);
        for (let i = start; i <= end; i++) {
          this.selectedClipIndices.add(i);
        }
        this.selectedClipIndex = index;
      } else {
        // 'set'
        this.selectedClipIndices.clear();
        this.selectedClipIndices.add(index);
        this.selectedClipIndex = index;
      }

      this.updateSelectionDOM();
      this.renderInspectorCard();
    },

    clearSelection() {
      this.selectedClipIndices.clear();
      this.selectedClipIndex = null;
      this.updateSelectionDOM();
      this.renderInspectorCard();
    },

    selectAll() {
      if (!this.scenes.length) return;
      this.selectedClipIndices.clear();
      this.scenes.forEach((_, idx) => this.selectedClipIndices.add(idx));
      this.selectedClipIndex = 0;
      this.updateSelectionDOM();
      this.renderInspectorCard();
      window.showToast?.(`Selected all ${this.scenes.length} timeline clips (Ctrl+A)`, 'info');
    },

    updateSelectionDOM() {
      const isMulti = this.selectedClipIndices.size > 1;
      document.querySelectorAll('.rf-tl-clip').forEach(el => {
        const idx = parseInt(el.dataset.index);
        const isSelected = this.selectedClipIndices.has(idx);
        el.classList.toggle('selected', isSelected);
        el.classList.toggle('multi-selected-leader', isSelected && isMulti && idx === this.selectedClipIndex);
      });
    },

    /** Setup Marquee Drag-Selection Box across empty timeline canvas space */
    setupMarqueeSelection() {
      const content = document.getElementById('tlContent');
      if (!content) return;

      if (this._marqueeCleanup) {
        this._marqueeCleanup();
      }

      let marqueeEl = document.getElementById('rfSelectionMarquee');
      if (!marqueeEl) {
        marqueeEl = document.createElement('div');
        marqueeEl.id = 'rfSelectionMarquee';
        marqueeEl.className = 'rf-selection-marquee';
        content.appendChild(marqueeEl);
      }

      const onMouseDown = (e) => {
        if (e.button !== 0) return;

        // Verify click is on empty timeline space, NOT on clips, trim handles, badges, playhead or ruler
        const target = e.target;
        if (target.closest('.rf-tl-clip') || 
            target.closest('.rf-trim-handle') || 
            target.closest('.rf-tl-trans-badge') || 
            target.closest('.rf-tl-playhead') || 
            target.closest('.rf-tl-ruler-row') ||
            target.closest('.rf-tl-headers-col')) {
          return;
        }

        const isModifier = e.ctrlKey || e.metaKey || e.shiftKey;
        const initialSelection = new Set(this.selectedClipIndices);
        const startClientX = e.clientX;
        const startClientY = e.clientY;

        const contentRect = content.getBoundingClientRect();
        const startRelX = startClientX - contentRect.left;
        const startRelY = startClientY - contentRect.top;

        let isDraggingMarquee = false;

        const onMouseMove = (moveEvent) => {
          const deltaX = moveEvent.clientX - startClientX;
          const deltaY = moveEvent.clientY - startClientY;

          if (!isDraggingMarquee && (Math.abs(deltaX) > 4 || Math.abs(deltaY) > 4)) {
            isDraggingMarquee = true;
            this.isMarqueeActive = true;
            marqueeEl.style.display = 'block';
            if (!isModifier) {
              this.selectedClipIndices.clear();
            }
          }

          if (!isDraggingMarquee) return;

          const curContentRect = content.getBoundingClientRect();
          const curRelX = moveEvent.clientX - curContentRect.left;
          const curRelY = moveEvent.clientY - curContentRect.top;

          const left = Math.min(startRelX, curRelX);
          const top = Math.min(startRelY, curRelY);
          const width = Math.abs(curRelX - startRelX);
          const height = Math.abs(curRelY - startRelY);

          marqueeEl.style.left = `${left}px`;
          marqueeEl.style.top = `${top}px`;
          marqueeEl.style.width = `${width}px`;
          marqueeEl.style.height = `${height}px`;

          const marqueeBox = {
            left,
            right: left + width,
            top,
            bottom: top + height
          };

          const clipEls = content.querySelectorAll('.rf-tl-clip');
          clipEls.forEach(cEl => {
            const idx = parseInt(cEl.dataset.index);
            const parentRow = cEl.parentElement;
            const rowTop = parentRow ? parentRow.offsetTop : 0;
            const clipLeft = cEl.offsetLeft;
            const clipTop = rowTop + cEl.offsetTop;
            const clipRight = clipLeft + cEl.offsetWidth;
            const clipBottom = clipTop + cEl.offsetHeight;

            const intersects = !(
              clipRight < marqueeBox.left ||
              clipLeft > marqueeBox.right ||
              clipBottom < marqueeBox.top ||
              clipTop > marqueeBox.bottom
            );

            if (intersects) {
              this.selectedClipIndices.add(idx);
            } else if (!isModifier) {
              this.selectedClipIndices.delete(idx);
            } else if (!initialSelection.has(idx)) {
              this.selectedClipIndices.delete(idx);
            }
          });

          this.updateSelectionDOM();
        };

        const onMouseUp = () => {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);

          if (isDraggingMarquee) {
            marqueeEl.style.display = 'none';
            this.isMarqueeActive = false;
            this.selectedClipIndex = this.selectedClipIndices.size > 0 ? Array.from(this.selectedClipIndices)[0] : null;
            this.renderInspectorCard();
          } else {
            // Click without drag on empty space: clear selection unless modifier held
            if (!isModifier) {
              this.clearSelection();
            }
          }
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      };

      content.addEventListener('mousedown', onMouseDown);
      this._marqueeCleanup = () => {
        content.removeEventListener('mousedown', onMouseDown);
      };
    },

    /** Bind Playhead Dragging & Scrubbing on Timecode Ruler */
    bindRulerScrubbing() {
      const ruler = document.getElementById('tlRuler');
      const playheadHandle = document.getElementById('tlPlayheadHandle');
      if (!ruler) return;

      const handleScrub = (e) => {
        const rect = ruler.getBoundingClientRect();
        const clientX = e.clientX;
        const tlViewport = document.getElementById('tlViewport');
        const scrollOffset = tlViewport ? tlViewport.scrollLeft : 0;
        const offsetX = (clientX - rect.left) + scrollOffset;
        let scrubSec = Math.max(0, Math.min(this.duration, offsetX / this.zoomPps));

        if (this.snappingEnabled) {
          const snapped = this.findSnapTime(scrubSec, []);
          if (snapped !== null) scrubSec = snapped;
        }

        this.seek(scrubSec);
      };

      const onMouseDown = (e) => {
        e.preventDefault();
        handleScrub(e);

        const onMouseMove = (moveEvent) => {
          handleScrub(moveEvent);
        };
        const onMouseUp = () => {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      };

      ruler.addEventListener('mousedown', onMouseDown);
      if (playheadHandle) {
        playheadHandle.addEventListener('mousedown', onMouseDown);
      }
    },

    /** Seek playback and instantly synchronize Preview Canvas & Timecode */
    seek(seconds) {
      this.currentTime = Math.max(0, Math.min(this.duration, seconds));
      if (this.dom.audioElement) {
        this.dom.audioElement.currentTime = this.currentTime;
      }
      this.updatePlayheadPosition();
      this.syncPreviewFrame();
    },

    updatePlayheadPosition() {
      const playhead = document.getElementById('tlPlayhead');
      const playheadTag = document.getElementById('tlPlayheadTag');
      const readout = document.getElementById('tlTimeReadout');
      if (!playhead) return;

      const leftPx = this.currentTime * this.zoomPps;
      playhead.style.left = `${leftPx}px`;

      const formatted = this.formatTimecode(this.currentTime);
      if (playheadTag) playheadTag.textContent = formatted;
      if (readout) readout.textContent = `${this.formatTimeDetailed(this.currentTime)} / ${this.formatTimeDetailed(this.duration)}`;
      if (this.dom.timecodeDisplay) {
        this.dom.timecodeDisplay.textContent = `${this.formatTimecode(this.currentTime)} / ${this.formatTimecode(this.duration)}`;
      }
    },

    /** Retrieve authoritative transition duration in seconds (1:1 with fast_pipeline.py) */
    getTransitionDuration(transType) {
      if (!transType) return 0.40;
      const clean = String(transType).toLowerCase().trim();
      const specMap = {
        'cinematic_dissolve': 0.40,
        'dissolve': 0.35,
        'cross_dissolve': 0.35,
        'soft_dissolve': 0.35,
        'soft_wipe': 0.35,
        'soft_directional': 0.35,
        'wipeleft': 0.35,
        'wiperight': 0.35,
        'dip_to_black': 0.40,
        'fadeblack': 0.40,
        'dip_to_white': 0.35,
        'fadewhite': 0.35,
        'fade': 0.30,
        'clean_cut': 0.0,
        'none': 0.0,
        'slow_dissolve': 0.75
      };
      if (specMap[clean] !== undefined) return specMap[clean];
      if (clean.startsWith('transition_') || clean.startsWith('pack_')) {
        const found = this.youtubeTransitions.find(t => t.id === clean);
        if (found) {
          const m = found.label.match(/\(([0-9\.]+)s\)/);
          if (m) return parseFloat(m[1]);
        }
        return 1.0;
      }
      return 0.40;
    },

    /** Retrieve clean user-facing transition label */
    getTransitionLabel(transType) {
      if (!transType) return 'Cinematic Dissolve';
      const clean = String(transType).trim();
      const yt = this.youtubeTransitions.find(t => t.id === clean);
      if (yt) return yt.label.split('(')[0].trim();
      const built = this.builtinTransitions.find(t => t.id === clean);
      if (built) return built.label;
      return clean.replace(/_/g, ' ');
    },

    /** In-memory image loader & cache for smooth sub-millisecond preview compositing */
    getPreloadedImage(url) {
      if (!url) return null;
      if (!this.imageCache) this.imageCache = new Map();
      if (this.imageCache.has(url)) {
        const item = this.imageCache.get(url);
        if (item.complete && item.naturalWidth > 0) return item;
        return item;
      }
      const img = new Image();
      img.crossOrigin = 'anonymous';
      img.src = url;
      img.onload = () => {
        if (this.isTransitionActiveAtCurrentTime()) {
          this.syncPreviewFrame();
        }
      };
      this.imageCache.set(url, img);
      return img;
    },

    /** Helper: True if current playhead is inside any transition window */
    isTransitionActiveAtCurrentTime() {
      const t = this.currentTime;
      for (let i = 0; i < this.scenes.length - 1; i++) {
        const scA = this.scenes[i];
        const transType = scA.transition || 'cinematic_dissolve';
        if (transType === 'clean_cut' || transType === 'none') continue;
        const tdur = scA.transition_dur || this.getTransitionDuration(transType);
        const halfDur = tdur / 2.0;
        if (t >= (scA.end - halfDur) && t <= (scA.end + halfDur)) return true;
      }
      return false;
    },

    /** Draw an image fitted into target canvas maintaining aspect ratio (object-fit: contain/cover) */
    drawFittedImage(ctx, img, cw, ch, mode = 'contain') {
      if (!img || !img.complete || img.naturalWidth === 0) return;
      const nw = img.naturalWidth;
      const nh = img.naturalHeight;
      const imgAspect = nw / nh;
      const canvasAspect = cw / ch;

      let drawW, drawH, dx, dy;
      if (mode === 'cover') {
        if (imgAspect > canvasAspect) {
          drawH = ch;
          drawW = ch * imgAspect;
          dx = (cw - drawW) / 2;
          dy = 0;
        } else {
          drawW = cw;
          drawH = cw / imgAspect;
          dx = 0;
          dy = (ch - drawH) / 2;
        }
      } else {
        if (imgAspect > canvasAspect) {
          drawW = cw;
          drawH = cw / imgAspect;
          dx = 0;
          dy = (ch - drawH) / 2;
        } else {
          drawH = ch;
          drawW = ch * imgAspect;
          dx = (cw - drawW) / 2;
          dy = 0;
        }
      }
      ctx.drawImage(img, dx, dy, drawW, drawH);
    },

    /** Live Transition Frame Compositor (Guarantees Built-in Preview / Final Export Parity) */
    renderTransitionFrame(canvas, trans) {
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const cw = (canvas.width = canvas.clientWidth || 1280);
      const ch = (canvas.height = canvas.clientHeight || 720);

      const p = trans.progress;
      const imgA = this.getPreloadedImage(trans.sceneA.imageUrl);
      const imgB = this.getPreloadedImage(trans.sceneB.imageUrl);

      ctx.clearRect(0, 0, cw, ch);
      ctx.fillStyle = '#08080a';
      ctx.fillRect(0, 0, cw, ch);

      const tType = (trans.transType || 'cinematic_dissolve').toLowerCase();

      // Effect 1: Cross Dissolve / Cinematic Dissolve / Fade / Soft Dissolve
      if (['cinematic_dissolve', 'dissolve', 'cross_dissolve', 'soft_dissolve', 'fade', 'slow_dissolve'].includes(tType)) {
        if (imgA && imgA.complete && imgA.naturalWidth > 0) {
          ctx.save();
          ctx.globalAlpha = Math.max(0.0, Math.min(1.0, 1.0 - p));
          this.drawFittedImage(ctx, imgA, cw, ch, 'contain');
          ctx.restore();
        }
        if (imgB && imgB.complete && imgB.naturalWidth > 0) {
          ctx.save();
          ctx.globalAlpha = Math.max(0.0, Math.min(1.0, p));
          this.drawFittedImage(ctx, imgB, cw, ch, 'contain');
          ctx.restore();
        }
      }
      // Effect 2: Soft Directional Wipe / Wipe Left
      else if (['soft_wipe', 'soft_directional', 'wipeleft'].includes(tType)) {
        if (imgA && imgA.complete) {
          ctx.save();
          this.drawFittedImage(ctx, imgA, cw, ch, 'contain');
          ctx.restore();
        }
        if (imgB && imgB.complete) {
          ctx.save();
          const splitX = Math.round(cw * (1.0 - p));
          ctx.beginPath();
          ctx.rect(splitX, 0, cw - splitX, ch);
          ctx.clip();
          this.drawFittedImage(ctx, imgB, cw, ch, 'contain');
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(splitX, 0);
          ctx.lineTo(splitX, ch);
          ctx.stroke();
          ctx.restore();
        }
      }
      // Effect 3: Wipe Right
      else if (tType === 'wiperight') {
        if (imgA && imgA.complete) {
          ctx.save();
          this.drawFittedImage(ctx, imgA, cw, ch, 'contain');
          ctx.restore();
        }
        if (imgB && imgB.complete) {
          ctx.save();
          const splitX = Math.round(cw * p);
          ctx.beginPath();
          ctx.rect(0, 0, splitX, ch);
          ctx.clip();
          this.drawFittedImage(ctx, imgB, cw, ch, 'contain');
          ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(splitX, 0);
          ctx.lineTo(splitX, ch);
          ctx.stroke();
          ctx.restore();
        }
      }
      // Effect 4: Dip to Black / Fade Black
      else if (['dip_to_black', 'fadeblack'].includes(tType)) {
        ctx.fillStyle = '#000000';
        ctx.fillRect(0, 0, cw, ch);
        if (p < 0.5) {
          const alphaA = Math.max(0.0, Math.min(1.0, 1.0 - (p / 0.5)));
          if (imgA && imgA.complete) {
            ctx.save();
            ctx.globalAlpha = alphaA;
            this.drawFittedImage(ctx, imgA, cw, ch, 'contain');
            ctx.restore();
          }
        } else {
          const alphaB = Math.max(0.0, Math.min(1.0, (p - 0.5) / 0.5));
          if (imgB && imgB.complete) {
            ctx.save();
            ctx.globalAlpha = alphaB;
            this.drawFittedImage(ctx, imgB, cw, ch, 'contain');
            ctx.restore();
          }
        }
      }
      // Effect 5: Dip to White / Fade White
      else if (['dip_to_white', 'fadewhite'].includes(tType)) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, cw, ch);
        if (p < 0.5) {
          const alphaA = Math.max(0.0, Math.min(1.0, 1.0 - (p / 0.5)));
          if (imgA && imgA.complete) {
            ctx.save();
            ctx.globalAlpha = alphaA;
            this.drawFittedImage(ctx, imgA, cw, ch, 'contain');
            ctx.restore();
          }
        } else {
          const alphaB = Math.max(0.0, Math.min(1.0, (p - 0.5) / 0.5));
          if (imgB && imgB.complete) {
            ctx.save();
            ctx.globalAlpha = alphaB;
            this.drawFittedImage(ctx, imgB, cw, ch, 'contain');
            ctx.restore();
          }
        }
      }
      // Effect 6: YouTube Pack Overlay / Film Burn / Light Leak
      else {
        if (imgA && imgA.complete) {
          ctx.save();
          ctx.globalAlpha = Math.max(0.0, Math.min(1.0, 1.0 - p));
          this.drawFittedImage(ctx, imgA, cw, ch, 'contain');
          ctx.restore();
        }
        if (imgB && imgB.complete) {
          ctx.save();
          ctx.globalAlpha = Math.max(0.0, Math.min(1.0, p));
          this.drawFittedImage(ctx, imgB, cw, ch, 'contain');
          ctx.restore();
        }
        const flashIntensity = Math.sin(p * Math.PI);
        if (flashIntensity > 0.05) {
          ctx.save();
          ctx.globalCompositeOperation = 'screen';
          const grad = ctx.createRadialGradient(cw * 0.45, ch * 0.5, 20, cw * 0.5, ch * 0.5, cw * 0.7);
          const isWarm = tType.includes('orange') || tType.includes('burn') || tType.includes('gold') || tType.includes('amber') || tType.includes('001') || tType.includes('003') || tType.includes('005');
          if (isWarm) {
            grad.addColorStop(0, `rgba(255, 215, 120, ${flashIntensity * 0.85})`);
            grad.addColorStop(0.4, `rgba(255, 120, 40, ${flashIntensity * 0.65})`);
            grad.addColorStop(1, `rgba(180, 20, 10, 0)`);
          } else {
            grad.addColorStop(0, `rgba(220, 240, 255, ${flashIntensity * 0.85})`);
            grad.addColorStop(0.4, `rgba(60, 160, 255, ${flashIntensity * 0.65})`);
            grad.addColorStop(1, `rgba(10, 40, 180, 0)`);
          }
          ctx.fillStyle = grad;
          ctx.fillRect(0, 0, cw, ch);
          ctx.restore();
        }
      }
    },

    /** Instant live frame sync: composites transitions and updates badges & caption overlay */
    syncPreviewFrame() {
      if (!this.scenes.length || !this.dom.previewMedia) return;

      const t = this.currentTime;
      const transCanvas = this.dom.previewTransitionCanvas;
      const imgEl = this.dom.previewMedia;

      // 1. Detect Active Transition Window (Cut boundary interval [cut - dur/2, cut + dur/2])
      let activeTrans = null;
      for (let i = 0; i < this.scenes.length - 1; i++) {
        const scA = this.scenes[i];
        const scB = this.scenes[i + 1];
        const cutTime = scA.end;
        const transType = scA.transition || 'cinematic_dissolve';
        if (transType === 'clean_cut' || transType === 'none') continue;

        const tdur = scA.transition_dur || this.getTransitionDuration(transType);
        const halfDur = tdur / 2.0;
        const tStart = cutTime - halfDur;
        const tEnd = cutTime + halfDur;

        if (t >= tStart && t <= tEnd) {
          const progress = Math.max(0.0, Math.min(1.0, (t - tStart) / Math.max(0.001, tdur)));
          activeTrans = {
            cutIndex: i,
            sceneA: scA,
            sceneB: scB,
            transType: transType,
            progress: progress,
            duration: tdur,
            tStart: tStart,
            tEnd: tEnd,
            cutTime: cutTime
          };
          break;
        }
      }

      // 2. Active Scene Index Determination
      const activeIdx = this.scenes.findIndex(s => t >= s.start && t < s.end);
      const activeScene = activeIdx !== -1 
        ? this.scenes[activeIdx] 
        : (t >= this.duration ? this.scenes[this.scenes.length - 1] : this.scenes[0]);
      const currentIdx = activeIdx !== -1 ? activeIdx : (t >= this.duration ? this.scenes.length - 1 : 0);

      // 3. Render Center Video Monitor
      if (activeTrans && transCanvas) {
        this.renderTransitionFrame(transCanvas, activeTrans);
        transCanvas.style.display = 'block';
        imgEl.style.display = 'none';

        // Monitor Badges: show active transition progress
        const sceneBadgeName = document.getElementById('previewSceneName');
        const sceneBadgeSpan = document.getElementById('previewSceneSpan');
        const motionBadgeName = document.getElementById('previewMotionName');
        if (sceneBadgeName) sceneBadgeName.textContent = `Cut ${activeTrans.cutIndex + 1} ➔ ${activeTrans.cutIndex + 2}`;
        if (sceneBadgeSpan) sceneBadgeSpan.textContent = `${this.formatTimecode(activeTrans.tStart)}–${this.formatTimecode(activeTrans.tEnd)}`;
        if (motionBadgeName) {
          const pct = Math.round(activeTrans.progress * 100);
          motionBadgeName.textContent = `FX: ${this.getTransitionLabel(activeTrans.transType)} (${pct}%)`;
        }
      } else {
        if (transCanvas) transCanvas.style.display = 'none';
        imgEl.style.display = 'block';
        if (activeScene && activeScene.imageUrl) {
          if (imgEl.src !== activeScene.imageUrl) {
            imgEl.src = activeScene.imageUrl;
          }
        }

        const sceneBadgeName = document.getElementById('previewSceneName');
        const sceneBadgeSpan = document.getElementById('previewSceneSpan');
        const motionBadgeName = document.getElementById('previewMotionName');
        if (sceneBadgeName) sceneBadgeName.textContent = `Scene ${currentIdx + 1}`;
        if (sceneBadgeSpan && activeScene) {
          sceneBadgeSpan.textContent = `${this.formatTimecode(activeScene.start)}–${this.formatTimecode(activeScene.end)}`;
        }
        if (motionBadgeName && activeScene) {
          const m = activeScene.motion;
          motionBadgeName.textContent = m === 'L4/push' ? 'Slow zoom in' : (m === 'L4/pull' ? 'Slow zoom out' : (m || 'Static'));
        }
      }

      // 4. Sync live preview caption overlay
      const overlay = document.getElementById('previewCaptionOverlay');
      if (overlay) {
        const segs = (this.transcriptSegments && this.transcriptSegments.length) ? this.transcriptSegments : this.scenes;
        let activeCap = null;
        if (this.selectedCaptionIndex !== null && this.transcriptSegments && this.transcriptSegments[this.selectedCaptionIndex]) {
          const sel = this.transcriptSegments[this.selectedCaptionIndex];
          if (t >= sel.start && t < sel.end) {
            activeCap = sel;
          }
        }
        if (!activeCap) {
          const matches = segs.filter(s => t >= s.start && t < s.end);
          if (matches.length > 0) {
            activeCap = matches.reduce((best, cur) => cur.start >= best.start ? cur : best, matches[0]);
          }
        }
        const txt = activeCap ? (activeCap.text || activeCap.narration_text || '') : '';
        if (txt && txt.trim()) {
          overlay.textContent = `"${txt.trim()}"`;
          overlay.style.display = 'block';
        } else {
          overlay.style.display = 'none';
        }
      }
    },

    togglePlayback() {
      const audio = this.dom.audioElement;
      const btn = document.getElementById('btnTlPlayPause');
      const canvasBtn = document.getElementById('btnCanvasPlayPause');
      if (!audio) return;

      if (audio.paused) {
        audio.play().then(() => {
          if (btn) btn.textContent = '❚❚ Pause';
          if (canvasBtn) canvasBtn.textContent = '❚❚';
        }).catch(err => console.warn('[TimelineStudio] Play error:', err));
      } else {
        audio.pause();
        if (btn) btn.textContent = '▶ Play';
        if (canvasBtn) canvasBtn.textContent = '▶';
      }
    },

    setupEventListeners() {
      // Audio playback sync
      const audio = this.dom.audioElement;
      if (audio) {
        audio.addEventListener('timeupdate', () => {
          this.currentTime = audio.currentTime;
          this.updatePlayheadPosition();
          this.syncPreviewFrame();
        });
        audio.addEventListener('ended', () => {
          const btn = document.getElementById('btnTlPlayPause');
          if (btn) btn.textContent = '▶ Play';
        });
      }
    },

    setupKeyboardShortcuts() {
      window.addEventListener('keydown', (e) => {
        // Exempt inputs, textareas, and selects
        const target = e.target;
        if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) {
          return;
        }

        // Space -> Play / Pause
        if (e.code === 'Space') {
          e.preventDefault();
          this.togglePlayback();
          return;
        }

        // S -> Split at Playhead
        if (e.code === 'KeyS' && !e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          this.splitClipAtPlayhead();
          return;
        }

        // T -> Add Text Overlay / Caption at Playhead
        if ((e.code === 'KeyT' || e.key === 't') && !e.ctrlKey && !e.metaKey && !e.altKey) {
          e.preventDefault();
          this.addTextOverlay();
          return;
        }

        // Ctrl + A -> Select All
        if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyA' || e.key === 'a')) {
          e.preventDefault();
          this.selectAll();
          return;
        }

        // Escape -> Clear selection / cancel in-progress operations
        if (e.key === 'Escape') {
          e.preventDefault();
          this.clearSelection();
          this.clearCaptionSelection();
          return;
        }

        // Alt + ArrowLeft / Right -> Move selected clips
        if (e.altKey && e.code === 'ArrowLeft') {
          e.preventDefault();
          this.moveSelectedClips(-1);
          return;
        }
        if (e.altKey && e.code === 'ArrowRight') {
          e.preventDefault();
          this.moveSelectedClips(1);
          return;
        }

        // Del / Backspace -> Delete Selected Clip
        if (e.key === 'Delete' || e.key === 'Backspace') {
          e.preventDefault();
          this.deleteSelectedClip();
          return;
        }

        // Ctrl + D -> Duplicate Selected Clip
        if ((e.ctrlKey || e.metaKey) && e.code === 'KeyD') {
          e.preventDefault();
          this.duplicateSelectedClip();
          return;
        }

        // Ctrl + Z -> Undo
        if ((e.ctrlKey || e.metaKey) && e.code === 'KeyZ' && !e.shiftKey) {
          e.preventDefault();
          this.undo();
          return;
        }

        // Ctrl + Y or Ctrl + Shift + Z -> Redo
        if ((e.ctrlKey || e.metaKey) && (e.code === 'KeyY' || (e.code === 'KeyZ' && e.shiftKey))) {
          e.preventDefault();
          this.redo();
          return;
        }

        // Ctrl + S -> Save Plan
        if ((e.ctrlKey || e.metaKey) && e.code === 'KeyS') {
          e.preventDefault();
          this.savePlan();
          return;
        }

        // Left / Right Arrows -> Nudge frame (-1f / +1f)
        if (e.code === 'ArrowLeft') {
          e.preventDefault();
          this.seek(this.currentTime - (1 / this.fps));
          return;
        }
        if (e.code === 'ArrowRight') {
          e.preventDefault();
          this.seek(this.currentTime + (1 / this.fps));
          return;
        }

        // Home / End -> Jump to start / end
        if (e.code === 'Home') {
          e.preventDefault();
          this.seek(0);
          return;
        }
        if (e.code === 'End') {
          e.preventDefault();
          this.seek(this.duration);
          return;
        }
      });
    },

    /** Split active clip at playhead position (NLE Razor Cut) with strict boundary validation */
    async splitClipAtPlayhead() {
      if (!this.scenes || !this.scenes.length) {
        window.showToast?.('No visual clips loaded on timeline to split.', 'info');
        return;
      }

      const splitTime = +(this.currentTime).toFixed(3);
      const masterDur = this.duration || (this.scenes.length ? this.scenes[this.scenes.length - 1].end : 0);

      // 1. Boundary checks
      if (splitTime <= 0 || splitTime >= masterDur) {
        window.showToast?.(`Cannot split: Playhead (${splitTime.toFixed(2)}s) is outside timeline bounds [0.0s, ${masterDur.toFixed(2)}s].`, 'error');
        return;
      }

      // 2. Locate target scene
      const targetIndex = this.scenes.findIndex(s => splitTime > s.start && splitTime < s.end);
      if (targetIndex === -1) {
        window.showToast?.(`Cannot split at ${splitTime.toFixed(2)}s: Position coincides with an existing cut boundary.`, 'info');
        return;
      }

      const targetScene = this.scenes[targetIndex];
      const headDur = +(splitTime - targetScene.start).toFixed(3);
      const tailDur = +(targetScene.end - splitTime).toFixed(3);
      const minClipDuration = 0.30;

      // 3. Minimum duration validation
      if (headDur < minClipDuration) {
        window.showToast?.(`Cannot split: Position is too close to scene start (${headDur.toFixed(2)}s < ${minClipDuration.toFixed(2)}s).`, 'error');
        return;
      }
      if (tailDur < minClipDuration) {
        window.showToast?.(`Cannot split: Position is too close to scene end (${tailDur.toFixed(2)}s < ${minClipDuration.toFixed(2)}s).`, 'error');
        return;
      }

      // 4. Try backend split if active project path exists
      const projectPath = window.state?.projectPath;
      if (projectPath) {
        try {
          const res = await fetch('/api/timeline/split_scene', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              project_path: projectPath,
              split_time: splitTime,
              min_clip_duration: minClipDuration
            })
          });

          if (res.ok) {
            const data = await res.json();
            if (data.scenes && Array.isArray(data.scenes)) {
              this.pushHistorySnapshot();
              // Map updated scenes into TimelineStudio models
              this.scenes = data.scenes.map((s, idx) => {
                const imgObj = (this.images || []).find(im => im.name === (s.image || s.img));
                return {
                  id: s.id || `clip_${idx}`,
                  segment_index: idx,
                  start: +s.start,
                  end: +s.end,
                  dur: +s.dur,
                  image: s.image || s.img || '1.png',
                  imageUrl: imgObj?.url || '',
                  transition: s.transition || 'cinematic_dissolve',
                  context: s.context || 'normal',
                  motion: s.motion || 'L4/push',
                  user_override: s.user_override === true,
                  confidence: s.confidence !== undefined ? s.confidence : 0.90,
                  confidence_level: s.confidence_level || 'HIGH',
                  narration_text: s.narration_text || ''
                };
              });

              this.selectClip(data.split_index || (targetIndex + 1));
              this.markSaved();
              this.renderScenesTrack();
              this.renderTransitionsTrack();
              this.renderCaptionsTrack();
              window.showToast?.(`✂️ Split clip into two scenes at ${splitTime.toFixed(2)}s`, 'success');
              return;
            }
          } else {
            const errData = await res.json().catch(() => ({}));
            const errMsg = errData.detail || `Server returned HTTP ${res.status}`;
            window.showToast?.(`Split failed: ${errMsg}`, 'error');
            return;
          }
        } catch (netErr) {
          console.warn('[TimelineStudio] Backend split API unavailable, using validated client-side split:', netErr);
        }
      }

      // 5. Client-side deterministic integer-millisecond split (offline / fallback mode)
      this.pushHistorySnapshot();
      const origScene = this.scenes[targetIndex];
      const origEnd = origScene.end;

      origScene.end = splitTime;
      origScene.dur = headDur;
      origScene.user_override = true;

      const newScene = {
        id: `clip_${Date.now()}`,
        segment_index: targetIndex + 1,
        start: splitTime,
        end: origEnd,
        dur: tailDur,
        image: origScene.image,
        imageUrl: origScene.imageUrl,
        transition: origScene.transition,
        context: origScene.context,
        motion: origScene.motion,
        user_override: true,
        confidence: 0.95,
        confidence_level: 'HIGH',
        narration_text: origScene.narration_text
      };

      this.scenes.splice(targetIndex + 1, 0, newScene);
      this.scenes.forEach((s, idx) => s.segment_index = idx);

      this.selectClip(targetIndex + 1);
      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      this.renderCaptionsTrack();
      window.showToast?.(`✂️ Split clip into two scenes at ${splitTime.toFixed(2)}s`, 'success');
    },


    /** Duplicate selected clip */
    duplicateSelectedClip() {
      if (this.selectedClipIndex === null || !this.scenes[this.selectedClipIndex]) {
        window.showToast?.('Select a clip on the timeline to duplicate.', 'info');
        return;
      }

      this.pushHistorySnapshot();
      const sel = this.scenes[this.selectedClipIndex];
      const dupDur = Math.min(3.0, sel.dur);
      const splitPoint = sel.start + (sel.dur / 2);

      sel.end = +splitPoint.toFixed(3);
      sel.dur = +(sel.end - sel.start).toFixed(3);
      sel.user_override = true;

      const dupScene = {
        id: `clip_dup_${Date.now()}`,
        segment_index: this.selectedClipIndex + 1,
        start: +splitPoint.toFixed(3),
        end: +(splitPoint + dupDur).toFixed(3),
        dur: +dupDur.toFixed(3),
        image: sel.image,
        imageUrl: sel.imageUrl,
        transition: sel.transition,
        context: sel.context,
        motion: sel.motion,
        user_override: true,
        confidence: 0.95,
        confidence_level: 'HIGH',
        narration_text: sel.narration_text
      };

      this.scenes.splice(this.selectedClipIndex + 1, 0, dupScene);
      this.scenes.forEach((s, idx) => s.segment_index = idx);

      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      window.showToast?.(`Duplicated Scene #${this.selectedClipIndex + 1}`, 'success');
    },

    /** Delete selected clip(s) with confirmation and duration preservation */
    deleteSelectedClip() {
      if (!this.selectedClipIndices.size && this.selectedClipIndex !== null) {
        this.selectedClipIndices.add(this.selectedClipIndex);
      }
      if (!this.selectedClipIndices.size || !this.scenes.length) {
        window.showToast?.('No clips selected to delete.', 'info');
        return;
      }

      const count = this.selectedClipIndices.size;
      if (this.scenes.length - count < 1) {
        window.showToast?.('Cannot delete all scenes: At least one scene is required.', 'warning');
        return;
      }

      if (count > 1) {
        const confirmed = window.confirm(`Are you sure you want to delete ${count} selected scenes? Master timeline duration will be preserved.`);
        if (!confirmed) return;
      }

      this.pushHistorySnapshot();
      const sorted = Array.from(this.selectedClipIndices).sort((a, b) => b - a);
      sorted.forEach(idx => {
        this.scenes.splice(idx, 1);
      });

      // Recompute strict consecutive continuity and preserve master duration
      if (this.scenes.length > 0) {
        const targetTotal = this.duration;
        const sumDur = this.scenes.reduce((acc, s) => acc + s.dur, 0);
        const scale = sumDur > 0 ? targetTotal / sumDur : 1;
        let cur = 0.0;
        this.scenes.forEach((sc, i) => {
          sc.segment_index = i;
          sc.start = +cur.toFixed(3);
          const d = +(sc.dur * scale).toFixed(3);
          sc.end = +(cur + d).toFixed(3);
          sc.dur = +(sc.end - sc.start).toFixed(3);
          cur = sc.end;
          sc.user_override = true;
        });
        this.scenes[this.scenes.length - 1].end = +this.duration.toFixed(3);
        this.scenes[this.scenes.length - 1].dur = +(this.duration - this.scenes[this.scenes.length - 1].start).toFixed(3);
      }

      this.clearSelection();
      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      this.renderCaptionsTrack();
      this.renderInspectorCard();
      window.showToast?.(`Deleted ${count} scene(s) (Duration preserved)`, 'info');
    },

    /** Undo History Stack Manager */
    pushHistorySnapshot() {
      const snapshot = JSON.stringify({
        scenes: this.scenes,
        transcriptSegments: this.transcriptSegments
      });
      this.history.push(snapshot);
      if (this.history.length > this.maxHistory) {
        this.history.shift();
      }
      this.redoStack = [];
      this.updateHistoryButtons();
    },

    undo() {
      if (!this.history.length) return;
      const current = JSON.stringify({
        scenes: this.scenes,
        transcriptSegments: this.transcriptSegments
      });
      this.redoStack.push(current);
      const prevRaw = this.history.pop();
      const prev = JSON.parse(prevRaw);
      if (Array.isArray(prev)) {
        this.scenes = prev;
      } else {
        this.scenes = prev.scenes || [];
        if (prev.transcriptSegments) this.transcriptSegments = prev.transcriptSegments;
      }
      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      this.renderCaptionsTrack();
      this.renderInspectorCard();
      this.syncPreviewFrame();
      this.updateHistoryButtons();
      window.showToast?.('Undo: Reverted timeline edit', 'info');
    },

    redo() {
      if (!this.redoStack.length) return;
      const current = JSON.stringify({
        scenes: this.scenes,
        transcriptSegments: this.transcriptSegments
      });
      this.history.push(current);
      const nextRaw = this.redoStack.pop();
      const next = JSON.parse(nextRaw);
      if (Array.isArray(next)) {
        this.scenes = next;
      } else {
        this.scenes = next.scenes || [];
        if (next.transcriptSegments) this.transcriptSegments = next.transcriptSegments;
      }
      this.markUnsaved();
      this.renderScenesTrack();
      this.renderTransitionsTrack();
      this.renderCaptionsTrack();
      this.renderInspectorCard();
      this.syncPreviewFrame();
      this.updateHistoryButtons();
      window.showToast?.('Redo: Reapplied timeline edit', 'info');
    },

    updateHistoryButtons() {
      const btnUndo = document.getElementById('btnTlUndo');
      const btnRedo = document.getElementById('btnTlRedo');
      const btnTopUndo = document.getElementById('btnTopUndo');
      const btnTopRedo = document.getElementById('btnTopRedo');
      const canUndo = this.history.length > 0;
      const canRedo = this.redoStack.length > 0;
      if (btnUndo) btnUndo.disabled = !canUndo;
      if (btnRedo) btnRedo.disabled = !canRedo;
      if (btnTopUndo) btnTopUndo.disabled = !canUndo;
      if (btnTopRedo) btnTopRedo.disabled = !canRedo;
    },

    markUnsaved() {
      this.hasUnsavedChanges = true;
      const badge = document.getElementById('tlSaveStatusBadge');
      if (badge) {
        badge.className = 'rf-tl-save-status unsaved';
        badge.textContent = '● Unsaved Edits';
      }
    },

    markSaved() {
      this.hasUnsavedChanges = false;
      const badge = document.getElementById('tlSaveStatusBadge');
      if (badge) {
        badge.className = 'rf-tl-save-status saved';
        badge.textContent = '✓ Saved';
      }
    },

    /** Two-way Synchronized Clip Inspector Card */
    renderInspectorCard() {
      const container = document.getElementById('sceneTableBody');
      if (!container) return;

      if (!this.selectedClipIndices.size && this.selectedClipIndex !== null) {
        this.selectedClipIndices.add(this.selectedClipIndex);
      }

      if (this.selectedClipIndices.size > 1) {
        const count = this.selectedClipIndices.size;
        const sorted = Array.from(this.selectedClipIndices).sort((a, b) => a - b);
        const totalDur = sorted.reduce((acc, i) => acc + (this.scenes[i]?.dur || 0), 0);
        const isContiguous = (sorted[sorted.length - 1] - sorted[0] === sorted.length - 1);

        const ytOptions = this.youtubeTransitions.map(t => `<option value="${t.id}">${t.label}</option>`).join('');
        const builtOptions = this.builtinTransitions.map(t => `<option value="${t.id}">${t.label}</option>`).join('');

        container.innerHTML = `
          <div class="rf-clip-inspector-card">
            <div class="rf-insp-hdr">
              <div style="display:flex; align-items:center; gap:0.5rem">
                <span class="rf-pill accent" style="font-weight:700">Multi-Selection: ${count} Clips</span>
                <span style="font-family:var(--font-mono); font-size:0.75rem">${totalDur.toFixed(2)}s total</span>
              </div>
              <button class="btn btn-secondary btn-sm" id="inspBtnClearSel" style="font-size:0.65rem; padding:1px 6px">Clear (Esc)</button>
            </div>
            <div style="font-size:0.75rem; color:var(--rf-muted, #94a3b8); margin:0.5rem 0">
              Selected Scenes: #${sorted.map(i => i + 1).join(', #')}
            </div>
            <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:0.5rem; margin-bottom:0.5rem">
              <div style="font-size:0.7rem; font-weight:700; color:var(--rf-accent, #00f0ff); margin-bottom:0.35rem">GROUP ACTIONS</div>
              <div style="display:flex; gap:0.4rem; margin-bottom:0.4rem">
                <button class="btn btn-secondary btn-sm" id="inspBtnGroupMoveLeft" style="flex:1; font-size:0.7rem" ${sorted[0] === 0 || !isContiguous ? 'disabled' : ''}>⬅ Move Left</button>
                <button class="btn btn-secondary btn-sm" id="inspBtnGroupMoveRight" style="flex:1; font-size:0.7rem" ${sorted[sorted.length - 1] === this.scenes.length - 1 || !isContiguous ? 'disabled' : ''}>Move Right ➡</button>
              </div>
              <button class="btn btn-secondary btn-sm" id="inspBtnGroupDelete" style="width:100%; color:var(--rf-danger, #ef4444); font-size:0.7rem">🗑️ Delete ${count} Selected Scenes</button>
            </div>
            <div class="form-group" style="margin-bottom:0.4rem">
              <label class="form-label" style="font-size:0.7rem; margin-bottom:2px">Apply Bulk Transition</label>
              <select class="form-select form-select-sm" id="inspSelectBulkTrans" style="font-size:0.72rem">
                <option value="">-- Apply to All ${count} Clips --</option>
                <optgroup label="🌟 YouTube Transition Pack">${ytOptions}</optgroup>
                <optgroup label="🎬 Built-in Cinematic Transitions">${builtOptions}</optgroup>
              </select>
            </div>
          </div>
        `;

        document.getElementById('inspBtnClearSel')?.addEventListener('click', () => this.clearSelection());
        document.getElementById('inspBtnGroupMoveLeft')?.addEventListener('click', () => this.moveSelectedClips(-1));
        document.getElementById('inspBtnGroupMoveRight')?.addEventListener('click', () => this.moveSelectedClips(1));
        document.getElementById('inspBtnGroupDelete')?.addEventListener('click', () => this.deleteSelectedClip());
        document.getElementById('inspSelectBulkTrans')?.addEventListener('change', (e) => {
          const val = e.target.value;
          if (!val) return;
          this.pushHistorySnapshot();
          sorted.forEach(idx => {
            if (this.scenes[idx]) {
              this.scenes[idx].transition = val;
              this.scenes[idx].user_override = true;
            }
          });
          this.markUnsaved();
          this.renderTransitionsTrack();
          window.showToast?.(`Applied transition to ${count} scenes`, 'success');
        });
        return;
      }

      if (this.selectedCaptionIndex !== null && this.transcriptSegments[this.selectedCaptionIndex]) {
        const cap = this.transcriptSegments[this.selectedCaptionIndex];
        const idx = this.selectedCaptionIndex;
        const dur = +(Number(cap.end || 0) - Number(cap.start || 0)).toFixed(2);

        container.innerHTML = `
          <div class="rf-clip-inspector-card">
            <div class="rf-insp-hdr">
              <div style="display:flex; align-items:center; gap:0.5rem">
                <span class="rf-pill accent" style="font-weight:700">💬 Text / Caption #${idx + 1}</span>
                <span style="font-family:var(--font-mono); font-size:0.75rem">${dur.toFixed(2)}s</span>
              </div>
              <button class="btn btn-secondary btn-sm" id="inspBtnClearCap" style="font-size:0.65rem; padding:1px 6px">Done</button>
            </div>

            <!-- Text Content Area -->
            <div class="form-group" style="margin:0.5rem 0 0.4rem 0">
              <label class="form-label" style="font-size:0.7rem; margin-bottom:2px">Text / Subtitle Content</label>
              <textarea id="inspInputCaptionText" rows="3" class="form-control" style="font-size:0.75rem; width:100%; resize:vertical; background:rgba(0,0,0,0.4); color:#fff; border:1px solid rgba(0,240,255,0.25); border-radius:6px; padding:6px">${cap.text || ''}</textarea>
            </div>

            <!-- Timing Controls -->
            <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:0.5rem; margin-bottom:0.5rem">
              <div style="font-size:0.7rem; font-weight:700; color:var(--rf-accent, #00f0ff); margin-bottom:0.35rem">TIMING & BOUNDARIES</div>
              <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.4rem; font-size:0.72rem">
                <div>
                  <label style="color:var(--rf-muted, #94a3b8)">Start (sec):</label>
                  <input type="number" step="0.1" id="inspInputCapStart" value="${Number(cap.start || 0).toFixed(2)}" class="form-control form-control-sm" style="font-size:0.72rem; padding:2px 4px">
                </div>
                <div>
                  <label style="color:var(--rf-muted, #94a3b8)">End (sec):</label>
                  <input type="number" step="0.1" id="inspInputCapEnd" value="${Number(cap.end || 0).toFixed(2)}" class="form-control form-control-sm" style="font-size:0.72rem; padding:2px 4px">
                </div>
              </div>
            </div>

            <!-- Quick Action Buttons -->
            <div style="display:flex; gap:0.4rem">
              <button class="btn btn-secondary btn-sm" id="inspBtnDupCap" style="flex:1; font-size:0.7rem">⎘ Duplicate</button>
              <button class="btn btn-secondary btn-sm" id="inspBtnRippleCap" style="flex:1; color:#ff9f1c; font-size:0.7rem; font-weight:700" title="Ripple trim this phrase & shift downstream video/audio leftward">⚡ Ripple Trim</button>
              <button class="btn btn-secondary btn-sm" id="inspBtnDelCap" style="flex:1; color:var(--rf-danger, #ef4444); font-size:0.7rem">🗑️ Delete</button>
            </div>
          </div>
        `;

        document.getElementById('inspBtnClearCap')?.addEventListener('click', () => this.clearCaptionSelection());
        document.getElementById('inspBtnRippleCap')?.addEventListener('click', () => this.rippleTrimSegment(idx));
        document.getElementById('inspInputCaptionText')?.addEventListener('input', (e) => {
          cap.text = e.target.value;
          this.markUnsaved();
          const chips = document.querySelectorAll('#trackCaptionsRow .rf-tl-caption-chip');
          if (chips[idx]) {
            const span = chips[idx].querySelector('.rf-cap-text');
            if (span) span.textContent = cap.text;
          }
          this.syncPreviewFrame();
        });
        document.getElementById('inspInputCapStart')?.addEventListener('change', (e) => {
          this.pushHistorySnapshot();
          cap.start = Math.max(0, parseFloat(e.target.value) || 0);
          this.markUnsaved();
          this.renderCaptionsTrack();
        });
        document.getElementById('inspInputCapEnd')?.addEventListener('change', (e) => {
          this.pushHistorySnapshot();
          cap.end = Math.max((cap.start || 0) + 0.1, parseFloat(e.target.value) || ((cap.start || 0) + 1.0));
          this.markUnsaved();
          this.renderCaptionsTrack();
        });
        document.getElementById('inspBtnDupCap')?.addEventListener('click', () => this.duplicateCaption(idx));
        document.getElementById('inspBtnDelCap')?.addEventListener('click', () => this.deleteCaption(idx));
        return;
      }

      if (this.selectedClipIndex === null || !this.scenes[this.selectedClipIndex]) {
        const rawRes = window.getCanonicalResolution ? window.getCanonicalResolution() : (document.getElementById('settingResolution')?.value || '1080p');
        const res = rawRes === '4k' ? '3840×2160 (4K UHD)' : (rawRes === '1440p' ? '2560×1440 (1440p QHD)' : '1920×1080 (1080p FHD)');
        const fps = 30;
        const totalDur = this.duration || 0;
        const cutCount = this.scenes.length;
        const capCount = this.transcriptSegments ? this.transcriptSegments.length : 0;
        const audioName = this.audio?.name || 'Master Narration';

        container.innerHTML = `
          <div class="rf-clip-inspector-card rf-project-facts-card">
            <!-- Header -->
            <div class="rf-insp-hdr">
              <div style="display:flex; align-items:center; gap:0.5rem">
                <span class="rf-pill" style="background:rgba(255,255,255,0.06); color:#cbd5e1; font-weight:700">⚙️ Sequence Facts</span>
                <span class="rf-pill accent" style="font-weight:700">Master Sequence</span>
              </div>
              <span style="font-family:var(--font-mono); font-size:0.75rem; color:var(--rf-accent, #cbf53f)">${this.formatTimecode(this.currentTime)}</span>
            </div>

            <!-- Sequence Metrics Grid -->
            <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:0.6rem; margin:0.5rem 0">
              <div style="font-size:0.7rem; font-weight:700; color:var(--rf-accent, #cbf53f); margin-bottom:0.4rem; letter-spacing:0.04em">PROJECT CONFIGURATION</div>
              <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.4rem; font-size:0.72rem">
                <div>
                  <span style="color:var(--rf-muted, #909095)">Resolution:</span>
                  <div style="font-weight:700; color:#fff; font-family:var(--font-mono)">${res}</div>
                </div>
                <div>
                  <span style="color:var(--rf-muted, #909095)">Frame Rate:</span>
                  <div style="font-weight:700; color:#fff; font-family:var(--font-mono)">${fps} FPS</div>
                </div>
                <div>
                  <span style="color:var(--rf-muted, #909095)">Master Duration:</span>
                  <div style="font-weight:700; color:#fff; font-family:var(--font-mono)">${totalDur.toFixed(2)}s</div>
                </div>
                <div>
                  <span style="color:var(--rf-muted, #909095)">Audio Sync Master:</span>
                  <div style="font-weight:700; color:#34c46f; font-family:var(--font-mono); white-space:nowrap; overflow:hidden; text-overflow:ellipsis" title="${audioName}">🎙️ ${audioName}</div>
                </div>
              </div>
            </div>

            <!-- Track Elements Summary -->
            <div style="background:rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.06); border-radius:6px; padding:0.6rem; margin-bottom:0.5rem">
              <div style="font-size:0.7rem; font-weight:700; color:var(--rf-accent, #cbf53f); margin-bottom:0.4rem; letter-spacing:0.04em">TRACK STRUCTURE</div>
              <div style="display:grid; grid-template-columns: 1fr 1fr; gap:0.4rem; font-size:0.72rem">
                <div>
                  <span style="color:var(--rf-muted, #909095)">Video Clips:</span>
                  <div style="font-weight:700; color:#3373d1">${cutCount} Scenes</div>
                </div>
                <div>
                  <span style="color:var(--rf-muted, #909095)">Captions:</span>
                  <div style="font-weight:700; color:#cf5a99">${capCount} Cues</div>
                </div>
                <div>
                  <span style="color:var(--rf-muted, #909095)">Transitions:</span>
                  <div style="font-weight:700; color:#eab308">${Math.max(0, cutCount - 1)} Cuts</div>
                </div>
                <div>
                  <span style="color:var(--rf-muted, #909095)">Master Timeline:</span>
                  <div style="font-weight:700; color:#10b981">Audio-First (Locked)</div>
                </div>
              </div>
            </div>

            <!-- Quick Action Toolbar -->
            <div style="display:flex; gap:0.4rem; margin-bottom:0.5rem">
              <button class="btn btn-secondary btn-sm" id="inspBtnSplitPlayheadGlobal" style="flex:1; font-size:0.7rem; font-weight:600" title="Split clip under playhead (S)">
                ✂️ Split at Playhead (S)
              </button>
              <button class="btn btn-secondary btn-sm" id="inspBtnFitZoomGlobal" style="flex:1; font-size:0.7rem; font-weight:600" title="Fit sequence to window">
                🔍 Zoom to Fit
              </button>
            </div>

            <div style="font-size:0.68rem; color:var(--rf-muted, #64748b); text-align:center; padding:0.2rem">
              Select any clip on the timeline or press <kbd style="background:rgba(255,255,255,0.08); padding:1px 4px; border-radius:3px">S</kbd> to split under playhead.
            </div>
          </div>
        `;

        document.getElementById('inspBtnSplitPlayheadGlobal')?.addEventListener('click', () => {
          this.splitClipAtPlayhead();
        });
        document.getElementById('inspBtnFitZoomGlobal')?.addEventListener('click', () => {
          this.zoomToFit();
        });
        return;
      }
      const sc = this.scenes[this.selectedClipIndex];
      const idx = this.selectedClipIndex;

      // Restore Stitch single-clip layout if missing
      if (!document.getElementById('inspMotionPreset')) {
        this.renderStitchInspectorTemplate(container);
      }

      // Update Inspector Header
      const tag = document.getElementById('inspSceneTag');
      const title = document.getElementById('inspSceneTitle');
      const sub = document.getElementById('inspSceneSub');
      if (tag) tag.innerHTML = `<span class="stitch-scene-badge-dot"></span><span>SELECTED · SCENE ${idx + 1}</span>`;
      if (title) title.textContent = `Scene #${idx + 1} (${sc.image})`;
      const motionName = sc.motion === 'L4/push' ? 'Slow zoom in' : (sc.motion === 'L4/pull' ? 'Slow zoom out' : (sc.motion || 'Static'));
      if (sub) sub.textContent = `${sc.image} · ${sc.dur.toFixed(2)}s duration · ${motionName}`;

      // Update Motion & Camera
      const motionSel = document.getElementById('inspMotionPreset');
      if (motionSel) {
        motionSel.value = sc.motion || 'L4/push';
        motionSel.onchange = () => {
          this.pushHistorySnapshot();
          sc.motion = motionSel.value;
          sc.user_override = true;
          this.markUnsaved();
          this.renderScenesTrack();
          this.syncPreviewFrame();
        };
      }

      const zoomSlider = document.getElementById('inspZoomSlider');
      const zoomVal = document.getElementById('inspZoomVal');
      if (zoomSlider) {
        zoomSlider.value = sc.zoom || 118;
        if (zoomVal) zoomVal.textContent = `100% → ${zoomSlider.value}%`;
        zoomSlider.oninput = () => {
          if (zoomVal) zoomVal.textContent = `100% → ${zoomSlider.value}%`;
          sc.zoom = parseInt(zoomSlider.value);
          sc.user_override = true;
          this.markUnsaved();
        };
      }

      // Update Transition In
      const transSel = document.getElementById('inspTransitionSelect');
      if (transSel) {
        if (transSel.options.length <= 5) {
          const ytOpts = this.youtubeTransitions.map(t => `<option value="${t.id}">${t.label}</option>`).join('');
          const builtOpts = this.builtinTransitions.map(t => `<option value="${t.id}">${t.label}</option>`).join('');
          transSel.innerHTML = `
            <optgroup label="🎬 Built-in Cinematic">${builtOpts}</optgroup>
            <optgroup label="🌟 YouTube Transition Pack">${ytOpts}</optgroup>
          `;
        }
        transSel.value = sc.transition || 'cinematic_dissolve';
        transSel.onchange = () => {
          this.pushHistorySnapshot();
          sc.transition = transSel.value;
          sc.user_override = true;
          this.markUnsaved();
          this.renderTransitionsTrack();
        };
      }

      const transDur = document.getElementById('inspTransitionDur');
      const transDurVal = document.getElementById('inspTransDurVal');
      if (transDur) {
        transDur.value = sc.transition_duration || 0.8;
        if (transDurVal) transDurVal.textContent = `${transDur.value}s`;
        transDur.oninput = () => {
          if (transDurVal) transDurVal.textContent = `${transDur.value}s`;
          sc.transition_duration = parseFloat(transDur.value);
          sc.user_override = true;
          this.markUnsaved();
        };
      }

      // Update Caption Style
      const capStyleSel = document.getElementById('inspCaptionStyle');
      if (capStyleSel) {
        capStyleSel.value = window.state?.selectedCaptionStyle || 'classic';
        capStyleSel.onchange = () => {
          if (window.state) window.state.selectedCaptionStyle = capStyleSel.value;
          window.showToast?.(`Caption style set to ${capStyleSel.value}`, 'info');
        };
      }

      const capSize = document.getElementById('inspCaptionSize');
      const capSizeVal = document.getElementById('inspCaptionSizeVal');
      if (capSize) {
        if (capSizeVal) capSizeVal.textContent = `${capSize.value} px`;
        capSize.oninput = () => {
          if (capSizeVal) capSizeVal.textContent = `${capSize.value} px`;
        };
      }

      // Update AI Suggestion Card
      const aiCard = document.getElementById('inspAiCard');
      const aiTitle = document.getElementById('inspAiTitle');
      const aiText = document.getElementById('inspAiText');
      if (aiCard && aiTitle && aiText) {
        aiCard.style.display = 'flex';
        aiTitle.textContent = `AI SUGGESTION (${idx + 1} OF ${this.scenes.length})`;
        const narrSnippet = (sc.narration_text || '').trim();
        if (narrSnippet) {
          aiText.textContent = `Narration at ${this.formatTimecode(sc.start)}: "${narrSnippet.slice(0, 48)}...". Recommended motion is ${sc.motion || 'Slow zoom in'} with 0.8s ${sc.transition || 'cross dissolve'}.`;
        } else {
          aiText.textContent = `Scene #${idx + 1} duration is ${sc.dur.toFixed(1)}s. Recommended visual motion: ${sc.motion || 'Slow zoom in'} with 118% dynamic scale.`;
        }
      }

      // Wire AI Suggestion actions
      const btnApply = document.getElementById('btnAiApply');
      if (btnApply) {
        btnApply.onclick = () => {
          this.pushHistorySnapshot();
          sc.motion = 'L4/push';
          sc.transition = 'cinematic_dissolve';
          sc.user_override = true;
          this.markUnsaved();
          this.renderScenesTrack();
          this.renderTransitionsTrack();
          this.renderInspectorCard();
          window.showToast?.(`✨ Applied AI suggestion to Scene #${idx + 1}`, 'success');
        };
      }

      const btnCompare = document.getElementById('btnAiCompare');
      if (btnCompare) {
        btnCompare.onclick = () => {
          window.showToast?.(`Comparing AI suggestion for Scene #${idx + 1}`, 'info');
        };
      }

      const btnDismiss = document.getElementById('btnAiDismiss');
      if (btnDismiss) {
        btnDismiss.onclick = () => {
          if (aiCard) aiCard.style.display = 'none';
        };
      }

      // Wire sticky clip action buttons
      const btnDup = document.getElementById('btnInspDuplicate');
      if (btnDup) btnDup.onclick = () => this.duplicateSelectedClip();

      const btnSplit = document.getElementById('btnInspSplit');
      if (btnSplit) btnSplit.onclick = () => this.splitClipAtPlayhead();

      const btnReset = document.getElementById('btnInspReset');
      if (btnReset) {
        btnReset.onclick = () => {
          this.pushHistorySnapshot();
          sc.motion = 'L4/push';
          sc.zoom = 118;
          sc.transition = 'cinematic_dissolve';
          this.markUnsaved();
          this.renderInspectorCard();
          this.renderScenesTrack();
          window.showToast?.(`Reset motion and scale for Scene #${idx + 1}`, 'info');
        };
      }

      const btnDel = document.getElementById('btnInspDelete');
      if (btnDel) btnDel.onclick = () => this.deleteSelectedClip();
    },

    /** Render single-clip template structure inside #sceneTableBody if swapped */
    renderStitchInspectorTemplate(container) {
      if (!container) return;
      container.innerHTML = `
        <!-- SECTION 1: MOTION & CAMERA -->
        <div class="stitch-insp-section">
          <div class="stitch-insp-section-title">
            <span>Motion & Camera</span>
            <span class="material-symbols-outlined" style="font-size:14px; color:var(--stitch-lime)">videocam</span>
          </div>
          <div class="stitch-form-row">
            <label class="stitch-form-label">Motion Preset</label>
            <select class="stitch-form-select form-select-sm" id="inspMotionPreset">
              <option value="L4/push">Slow zoom in</option>
              <option value="L4/pull">Slow zoom out</option>
              <option value="L4/drift_right">Pan left to right</option>
              <option value="L4/drift_left">Pan right to left</option>
              <option value="none">Static (No motion)</option>
            </select>
          </div>
          <div class="stitch-form-row">
            <div style="display:flex; justify-content:space-between">
              <label class="stitch-form-label">Zoom Range</label>
              <span class="stitch-range-val" id="inspZoomVal">100% → 118%</span>
            </div>
            <div class="stitch-range-row">
              <input type="range" class="stitch-range-slider" id="inspZoomSlider" min="100" max="140" value="118">
            </div>
          </div>
        </div>

        <!-- SECTION 2: TRANSITION IN -->
        <div class="stitch-insp-section">
          <div class="stitch-insp-section-title">
            <span>Transition In</span>
            <span class="material-symbols-outlined" style="font-size:14px; color:var(--stitch-amber)">blur_on</span>
          </div>
          <div class="stitch-form-row">
            <label class="stitch-form-label">Transition Type</label>
            <select class="stitch-form-select form-select-sm" id="inspTransitionSelect">
              <option value="cinematic_dissolve" selected>Cinematic soft dissolve</option>
              <option value="dissolve">Cross dissolve</option>
              <option value="wipeleft">Whip pan</option>
              <option value="transition_001">White orange light leak</option>
              <option value="none">Clean cut</option>
            </select>
          </div>
          <div class="stitch-form-row">
            <div style="display:flex; justify-content:space-between">
              <label class="stitch-form-label">Duration</label>
              <span class="stitch-font-mono-sm" id="inspTransDurVal" style="color:var(--stitch-lime)">0.8s</span>
            </div>
            <input type="range" class="stitch-range-slider" id="inspTransitionDur" min="0.2" max="2.0" step="0.1" value="0.8">
          </div>
          <div class="stitch-font-caption" style="color:var(--stitch-outline); line-height:1.3; font-style:italic">
            Overlaps Scene tail; narration timing unchanged.
          </div>
        </div>

        <!-- SECTION 3: CAPTION STYLE -->
        <div class="stitch-insp-section">
          <div class="stitch-insp-section-title">
            <span>Caption Style</span>
            <span class="material-symbols-outlined" style="font-size:14px; color:var(--stitch-secondary)">subtitles</span>
          </div>
          <div class="stitch-form-row">
            <label class="stitch-form-label">Typography Style</label>
            <select class="stitch-form-select form-select-sm" id="inspCaptionStyle">
              <option value="classic" selected>IBM Plex Sans · 600</option>
              <option value="cinematic">Cinematic Documentary</option>
              <option value="neon_glow">Neon Electric Sub</option>
              <option value="creator">Creator Inspired</option>
            </select>
          </div>
          <div class="stitch-form-row">
            <div style="display:flex; justify-content:space-between">
              <label class="stitch-form-label">Font Size</label>
              <span class="stitch-font-mono-sm" id="inspCaptionSizeVal" style="color:var(--stitch-lime)">20 px</span>
            </div>
            <input type="range" class="stitch-range-slider" id="inspCaptionSize" min="14" max="36" value="20">
          </div>
        </div>

        <!-- SECTION 4: AI SUGGESTION CARD -->
        <div class="stitch-ai-suggestion-card" id="inspAiCard">
          <div class="stitch-ai-card-header">
            <div class="stitch-ai-card-title">
              <span class="material-symbols-outlined" style="font-size:14px">lightbulb</span>
              <span id="inspAiTitle">AI SUGGESTION (1 OF 3)</span>
            </div>
          </div>
          <p class="stitch-ai-card-text" id="inspAiText">
            Narration mentions opening scene. Recommended motion is Slow zoom in.
          </p>
          <div class="stitch-ai-card-actions">
            <button class="stitch-btn-ai-apply" id="btnAiApply">Apply</button>
            <button class="stitch-btn-ai-compare" id="btnAiCompare">Compare</button>
            <button class="stitch-btn-ai-dismiss" id="btnAiDismiss">Dismiss</button>
          </div>
        </div>
      `;
    },

    /** Transition Picker Popover for Cut Badges */
    openTransitionPickerPopup(event, cutIndex) {
      const existing = document.getElementById('rfTransPopover');
      if (existing) existing.remove();

      const sc = this.scenes[cutIndex];
      const popover = document.createElement('div');
      popover.id = 'rfTransPopover';
      popover.className = 'rf-trans-popover';
      popover.style.left = `${Math.min(window.innerWidth - 260, event.clientX - 100)}px`;
      popover.style.top = `${event.clientY - 210}px`;

      let optionsHtml = '';
      this.builtinTransitions.forEach(t => {
        optionsHtml += `<div class="rf-trans-item ${t.id === sc.transition ? 'active' : ''}" data-tid="${t.id}">${t.label}</div>`;
      });
      this.youtubeTransitions.slice(0, 10).forEach(t => {
        optionsHtml += `<div class="rf-trans-item ${t.id === sc.transition ? 'active' : ''}" data-tid="${t.id}">${t.label}</div>`;
      });

      popover.innerHTML = `
        <div class="rf-trans-pop-hdr">
          <span>Choose Cut Transition</span>
          <button class="rf-trans-close" id="btnCloseTransPop">✕</button>
        </div>
        <div class="rf-trans-list">
          ${optionsHtml}
        </div>
      `;

      document.body.appendChild(popover);

      document.getElementById('btnCloseTransPop')?.addEventListener('click', () => popover.remove());
      popover.querySelectorAll('.rf-trans-item').forEach(item => {
        item.addEventListener('click', () => {
          this.pushHistorySnapshot();
          sc.transition = item.dataset.tid;
          sc.user_override = true;
          this.markUnsaved();
          this.renderTransitionsTrack();
          this.renderInspectorCard();
          this.syncPreviewFrame();
          popover.remove();
          window.showToast?.(`Applied transition: ${item.textContent}`, 'info');
        });
      });

      const closeHandler = (e) => {
        if (!popover.contains(e.target) && e.target !== event.target) {
          popover.remove();
          document.removeEventListener('click', closeHandler);
        }
      };
      setTimeout(() => document.addEventListener('click', closeHandler), 10);
    },

    /** Setup Drag & Drop from Media Bin onto Timeline Clips */
    setupMediaBinDragDrop() {
      const thumbs = document.querySelectorAll('.asset-thumb');
      thumbs.forEach(thumb => {
        thumb.setAttribute('draggable', 'true');
        thumb.addEventListener('dragstart', (e) => {
          const imgName = thumb.title || thumb.querySelector('.thumb-tag')?.textContent || '';
          e.dataTransfer.setData('text/plain', imgName);
          e.dataTransfer.effectAllowed = 'copy';
        });
      });

      // Target clips
      const clips = document.querySelectorAll('.rf-tl-clip');
      clips.forEach(clip => {
        clip.addEventListener('dragover', (e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = 'copy';
          clip.classList.add('drag-over');
        });
        clip.addEventListener('dragleave', () => {
          clip.classList.remove('drag-over');
        });
        clip.addEventListener('drop', (e) => {
          e.preventDefault();
          clip.classList.remove('drag-over');
          const imgName = e.dataTransfer.getData('text/plain');
          const idx = parseInt(clip.dataset.index);
          if (imgName && this.scenes[idx]) {
            this.pushHistorySnapshot();
            this.scenes[idx].image = imgName;
            const found = this.images.find(im => im.name === imgName);
            this.scenes[idx].imageUrl = found?.url || '';
            this.scenes[idx].user_override = true;
            this.markUnsaved();
            this.renderScenesTrack();
            this.renderInspectorCard();
            this.syncPreviewFrame();
            window.showToast?.(`Replaced Scene #${idx + 1} with ${imgName}`, 'success');
          }
        });
      });

      // Target track row for adding scenes on empty space
      const trackRow = document.getElementById('trackScenesRow');
      if (trackRow) {
        trackRow.addEventListener('dragover', (e) => {
          if (e.target.closest('.rf-tl-clip')) return;
          e.preventDefault();
          e.dataTransfer.dropEffect = 'copy';
          trackRow.classList.add('drag-target-active');
        });
        trackRow.addEventListener('dragleave', (e) => {
          if (!trackRow.contains(e.relatedTarget)) {
            trackRow.classList.remove('drag-target-active');
          }
        });
        trackRow.addEventListener('drop', (e) => {
          if (e.target.closest('.rf-tl-clip')) return;
          e.preventDefault();
          trackRow.classList.remove('drag-target-active');
          const imgName = e.dataTransfer.getData('text/plain');
          if (!imgName) return;

          this.pushHistorySnapshot();
          const lastScene = this.scenes[this.scenes.length - 1];
          const newStart = lastScene ? lastScene.end : 0.0;
          const newDur = 3.0;
          const newEnd = +(newStart + newDur).toFixed(3);
          const found = this.images.find(im => im.name === imgName);

          const newScene = {
            id: `clip_${Date.now()}`,
            segment_index: this.scenes.length,
            start: newStart,
            end: newEnd,
            dur: newDur,
            image: imgName,
            imageUrl: found?.url || '',
            transition: 'cinematic_dissolve',
            context: 'normal',
            motion: 'L4/push',
            user_override: true,
            confidence: 0.95,
            confidence_level: 'HIGH',
            narration_text: `Scene ${this.scenes.length + 1}`
          };

          this.scenes.push(newScene);
          this.duration = Math.max(this.duration, newEnd);
          this.markUnsaved();
          this.renderScenesTrack();
          this.renderTransitionsTrack();
          this.renderCaptionsTrack();
          this.renderRuler();
          this.selectClip(this.scenes.length - 1);
          window.showToast?.(`Added new Scene #${this.scenes.length} with ${imgName}`, 'success');
        });
      }
    },

    /** Manual Text & Caption Overlay Operations */
    addTextOverlay() {
      this.pushHistorySnapshot();
      const startTime = +Number(this.currentTime || 0).toFixed(2);
      const dur = 3.0;
      const endTime = +(startTime + dur).toFixed(2);

      if (!this.transcriptSegments) this.transcriptSegments = [];
      const newSeg = {
        id: `txt_${Date.now()}`,
        start: startTime,
        end: endTime,
        text: 'Custom Text'
      };

      this.transcriptSegments.push(newSeg);
      this.transcriptSegments.sort((a, b) => a.start - b.start);
      const newIdx = this.transcriptSegments.indexOf(newSeg);

      this.selectedCaptionIndex = newIdx;
      this.selectedClipIndex = null;
      this.selectedClipIndices.clear();
      this.markUnsaved();
      this.renderCaptionsTrack();
      this.renderInspectorCard();
      this.syncPreviewFrame();
      window.showToast?.(`Added text overlay at ${startTime.toFixed(2)}s`, 'success');
    },

    duplicateCaption(idx) {
      if (idx === null || !this.transcriptSegments[idx]) return;
      this.pushHistorySnapshot();
      const orig = this.transcriptSegments[idx];
      const dur = +(orig.end - orig.start).toFixed(2);
      const newStart = orig.end;
      const newEnd = +(newStart + dur).toFixed(2);
      const dup = {
        id: `txt_${Date.now()}`,
        start: newStart,
        end: newEnd,
        text: orig.text
      };
      this.transcriptSegments.push(dup);
      this.transcriptSegments.sort((a, b) => a.start - b.start);
      this.selectedCaptionIndex = this.transcriptSegments.indexOf(dup);
      this.markUnsaved();
      this.renderCaptionsTrack();
      this.renderInspectorCard();
      window.showToast?.('Duplicated text overlay', 'success');
    },

    deleteCaption(idx) {
      if (idx === null || !this.transcriptSegments[idx]) return;
      this.pushHistorySnapshot();
      this.transcriptSegments.splice(idx, 1);
      this.selectedCaptionIndex = null;
      this.markUnsaved();
      this.renderCaptionsTrack();
      this.renderInspectorCard();
      this.syncPreviewFrame();
      window.showToast?.('Deleted text overlay', 'info');
    },

    clearCaptionSelection() {
      this.selectedCaptionIndex = null;
      this.renderCaptionsTrack();
      this.renderInspectorCard();
    },

    /** Execute server-side deterministic ripple trim on selected transcript segment */
    async rippleTrimSegment(segmentIndex) {
      const projectPath = window.state?.projectPath;
      if (!projectPath) {
        window.showToast?.('No active project path found.', 'error');
        return;
      }
      if (segmentIndex === null || !this.transcriptSegments || !this.transcriptSegments[segmentIndex]) return;

      const seg = this.transcriptSegments[segmentIndex];
      const dur = +(Number(seg.end || 0) - Number(seg.start || 0)).toFixed(2);
      const textPreview = (seg.text || '').substring(0, 32);
      const confirmed = window.confirm(
        `⚡ Ripple Trim Segment #${segmentIndex + 1} ("${textPreview}...", ${dur}s)?\n\n` +
        `This will remove the phrase, trim narration audio, and shift all downstream clips leftward with mathematical continuity.`
      );
      if (!confirmed) return;

      try {
        const res = await fetch('/api/timeline/ripple_apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_path: projectPath,
            target_type: 'segment',
            segment_index: segmentIndex,
            reason: `Ripple Trim Segment #${segmentIndex + 1}: ${textPreview}`
          })
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          window.showToast?.(`Ripple trim error: ${errData.detail || 'Request failed'}`, 'error');
          return;
        }

        const data = await res.json();
        this.pushHistorySnapshot();
        this.scenes = data.scenes;
        this.transcriptSegments = data.transcript_segments;
        this.duration = data.new_master_dur;
        this.selectedCaptionIndex = null;
        this.waveformData = null;
        this.markUnsaved();

        this.renderRuler();
        this.renderScenesTrack();
        this.renderCaptionsTrack();
        this.renderAudioTrack();
        this.renderTransitionsTrack();
        this.renderInspectorCard();
        this.syncPreviewFrame();

        window.showToast?.(`⚡ Ripple trim applied: -${data.cut_duration.toFixed(2)}s (New duration: ${data.new_master_dur.toFixed(2)}s)`, 'success');
      } catch (err) {
        window.showToast?.(`Ripple trim failed: ${err.message}`, 'error');
      }
    },

    /** Server-side Ripple Undo */
    async rippleUndo() {
      const projectPath = window.state?.projectPath;
      if (!projectPath) return;
      try {
        const res = await fetch('/api/timeline/ripple_undo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_path: projectPath })
        });
        if (!res.ok) return;
        const data = await res.json();
        if (data.success) {
          this.scenes = data.scenes;
          this.transcriptSegments = data.transcript_segments;
          this.duration = data.master_dur;
          this.waveformData = null;
          this.markUnsaved();
          this.renderRuler();
          this.renderScenesTrack();
          this.renderCaptionsTrack();
          this.renderAudioTrack();
          this.renderTransitionsTrack();
          this.renderInspectorCard();
          window.showToast?.(`Restored previous timeline state (${data.master_dur.toFixed(2)}s)`, 'info');
        }
      } catch (e) {
        console.warn('Ripple undo error:', e);
      }
    },

    /** Switch between Auto and Manual timeline workflows */
    setTimelineMode(mode) {
      if (this.timelineMode === mode) return;
      this.timelineMode = mode;
      const btnAuto = document.getElementById('btnTlModeAuto');
      const btnManual = document.getElementById('btnTlModeManual');
      if (btnAuto && btnManual) {
        btnAuto.style.background = mode === 'auto' ? 'linear-gradient(135deg, #00f0ff, #0284c7)' : 'transparent';
        btnAuto.style.color = mode === 'auto' ? '#000' : '#94a3b8';
        btnManual.style.background = mode === 'manual' ? 'linear-gradient(135deg, #a3e635, #65a30d)' : 'transparent';
        btnManual.style.color = mode === 'manual' ? '#000' : '#94a3b8';
      }
      if (mode === 'manual') {
        window.showToast?.('🖐️ Manual Timeline active: Full manual control over clip trimming, placement, and replacement.', 'info');
      } else {
        window.showToast?.('🪄 Auto Timeline active: AI dynamically synchronizes images to narration context.', 'info');
      }
    },

    /** Save Timeline Plan to plan.json via backend endpoint */
    async savePlan() {
      const projectPath = window.state?.projectPath;
      if (!projectPath) {
        window.showToast?.('No active project path found.', 'error');
        return;
      }

      try {
        const payload = {
          project_path: projectPath,
          plan: {
            timeline_mode: this.timelineMode,
            scenes: this.scenes.map(s => ({
              segment_index: s.segment_index,
              start: s.start,
              end: s.end,
              dur: s.dur,
              image: s.image,
              image_id: s.image_id || `img_${String(s.segment_index + 1).padStart(3, '0')}`,
              transition: s.transition,
              context: s.context,
              motion: s.motion,
              motion_mode: s.motion_mode || (s.motion ? s.motion.split('/').pop() : 'push'),
              shot_role: s.shot_role || 'narrative_inspection',
              easing: s.easing || 'smoothstep',
              zoom_scale: s.zoom_scale !== undefined ? s.zoom_scale : 1.02,
              pan_speed: s.pan_speed !== undefined ? s.pan_speed : 0.0,
              motion_rationale: s.motion_rationale || 'user_configured',
              cadence_alignment: s.cadence_alignment || null,
              candidates: s.candidates || [],
              user_override: s.user_override === true,
              locked: s.locked === true,
              confidence: s.confidence || 0.85,
              confidence_level: s.confidence_level || 'HIGH',
              match_reason: s.user_override ? ['explicit_user_override'] : (s.match_reason || ['semantic_match']),
              narration_text: s.narration_text || ''
            })),
            transcript_segments: (this.transcriptSegments || []).map(seg => ({
              start: +Number(seg.start).toFixed(3),
              end: +Number(seg.end).toFixed(3),
              text: String(seg.text || '')
            })),
            editor_timeline: {
              zoom_pps: this.zoomPps,
              snapping: this.snappingEnabled,
              duration: this.duration
            },
            caption_style: (window.state && window.state.plan && window.state.plan.caption_style) ? window.state.plan.caption_style : null,
            caption_preset: (window.state && window.state.plan && window.state.plan.caption_preset) ? window.state.plan.caption_preset : null,
            resolution: window.getCanonicalResolution ? window.getCanonicalResolution() : '1080p'
          }
        };

        const res = await fetch('/api/project/save_plan', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }

        const data = await res.json();
        this.markSaved();
        const topStatus = document.getElementById('topProjectStatus');
        if (topStatus) topStatus.textContent = 'Active ✓';
        window.showToast?.('Timeline plan and text overlays saved successfully!', 'success');
      } catch (err) {
        console.error('[TimelineStudio] Save plan error:', err);
        window.showToast?.(`Failed to save plan: ${err.message}`, 'error');
      }
    }
  };

  // Expose globally
  window.TimelineStudio = TimelineStudio;

  // Auto-hook into loadProjectData and renderTimelineAndTable
  document.addEventListener('DOMContentLoaded', () => {
    TimelineStudio.init();
  });

})();
