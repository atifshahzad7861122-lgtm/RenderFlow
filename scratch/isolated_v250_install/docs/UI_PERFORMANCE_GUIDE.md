# RenderFlow — UI Performance & Resource Allocation Guide
### Zero-Regression Architectural Principles · AI With Atif

---

## 1. Prime Directive: Rendering Stability Wins

In RenderFlow, the user interface exists to serve and monitor the rendering engine—never to compete with it. When a user executes a 4K 60FPS export, system resources (CPU cores, RAM bandwidth, GPU VRAM, and PCIe bus) must remain 100% dedicated to FFmpeg and NVENC/hardware encoders.

### Priority Hierarchy:
```
1. Video Frame Accuracy & Audio Sync   (P0 - Absolute)
2. Hardware Video Encoder Saturation    (P0 - Absolute)
3. Memory Safety (<60MB Python Core)    (P0 - Absolute)
4. Application Responsiveness (SSE/UI)  (P1 - Critical)
5. UI Usability & Workflow Navigation  (P1 - Critical)
6. Waveform & Timeline Visuals         (P2 - Standard)
7. 3D WebGL Telemetry & Motion Effects (P3 - Throttled)
```

---

## 2. Resource Budgets

| Metric | Target Budget | Hard Cap | Fallback Trigger |
| :--- | :--- | :--- | :--- |
| **Python Core Peak RSS** | $< 45\text{ MB}$ | $60\text{ MB}$ | Garbage collection pass |
| **Web UI Memory Footprint** | $< 65\text{ MB}$ | $90\text{ MB}$ | Auto-dispose WebGL textures |
| **UI Main Thread Latency** | $< 16.6\text{ ms}$ (60 FPS) | $33\text{ ms}$ (30 FPS) | Drop decorative animations |
| **GPU WebGL VRAM Overhead** | $< 25\text{ MB}$ | $40\text{ MB}$ | Downscale particle buffers |
| **3D Render Loop (Idle)** | $0\text{ ms}$ (Halted) | $1.2\text{ ms}$ | Pause via Visibility API |

---

## 3. WebGL & Three.js Throttling Strategies

### 3.1. Page Visibility Throttling
When the user minimizes the RenderFlow desktop window or switches to another browser tab:
```javascript
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    RenderFlow3D.pauseLoop();
    RenderFlowMotion.pauseCanvas();
  } else {
    RenderFlow3D.resumeLoop();
    RenderFlowMotion.resumeCanvas();
  }
});
```

### 3.2. Viewport-Aware Rendering (Intersection Observer)
The 3D Render-Core canvas only evaluates frames when its container is within the active viewport (e.g. Tab 2: Render & Hardware). If the user navigates to Tab 1 (Media & Timeline) or Tab 3 (Styles), the 3D requestAnimationFrame loop immediately enters a dormant sleep state, freeing 100% of GPU compute.

### 3.3. Device Pixel Ratio (DPR) Clamping
On 4K monitors (3840×2160) with Windows display scaling at 150% or 200%, default WebGL renderers create massive $4\text{K}\times4\text{K}$ framebuffers consuming hundreds of megabytes of VRAM. RenderFlow strictly clamps DPR:
- **Low / Medium Mode**: `Math.min(window.devicePixelRatio, 1.0)`
- **High Mode**: `Math.min(window.devicePixelRatio, 1.5)`
- **Eco Mode**: Pure 2D Canvas (0% WebGL framebuffer allocation)

---

## 4. UI Performance Profiles

RenderFlow links its UI animation subsystem directly to the user-selected **Performance Profile**:

### 1. Eco Profile
- Intended for: Budget quad-core CPUs, laptops on battery, systems with $\le 8\text{GB}$ RAM.
- WebGL 3D: **Disabled** (Replaced with lightweight 2D canvas).
- Backdrop Blur: Disabled (`backdrop-filter: none`, replaced with solid dark fills).
- Motion Physics: Simplified linear transitions ($0\text{ ms}$ delay).
- Audio Waveform: Static pre-computed peak envelope (zero animation loop).

### 2. Balanced Profile (Default)
- Intended for: Modern standard desktops and laptops.
- WebGL 3D: Medium fidelity (60 particles, wireframe core, DPR 1.0).
- Backdrop Blur: Moderate ($8\text{px}-16\text{px}$).
- Motion Physics: 30 FPS spring physics.
- Audio Waveform: Real-time playhead tracker.

### 3. Performance Profile
- Intended for: High-end workstations with dedicated GPUs (RTX 30/40/50 series, Radeon 6000/7000).
- WebGL 3D: High fidelity (120 particles, dynamic point lighting, DPR 1.5).
- Backdrop Blur: Full fidelity ($16\text{px}-24\text{px}$).
- Motion Physics: 60 FPS deterministic springs.
- Audio Waveform: 60 FPS anti-aliased waveform engine.

### 4. Max Quality Profile
- Intended for: Studio mastering environments prioritizing visual elegance and 4K preview precision.
- Full UI animation fidelity with native high-DPI scaling.

---

## 5. CSS & DOM Optimization Best Practices

1. **Composite-Only Properties**: Micro-interactions only animate `transform` and `opacity` to avoid browser layout and paint recalibration passes.
2. **CSS Containment**: High-frequency components (Timeline clips, Media grids, Progress rings) utilize `contain: content;` and `contain: layout style;` to isolate style invalidations.
3. **Passive Event Listeners**: All mouse wheel scrubbers and touch handlers register with `{ passive: true }` to guarantee non-blocking scroll and scrub responsiveness.
