/**
 * RenderFlow by AI With Atif — Motion System & Remotion Primitives
 * ================================================================
 * Deterministic frame-based animation engine and motion composition primitives.
 * Provides spring physics, timeline interpolation, transition previews,
 * and adaptive motion budgets respecting user preferences and hardware tiers.
 */

class RenderFlowMotion {
  constructor() {
    this.fps = 30;
    this.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.performanceMode = localStorage.getItem('renderflow_perf_mode') || 'balanced';
    
    // Listen for reduced motion changes
    window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (e) => {
      this.reducedMotion = e.matches;
    });
  }

  /**
   * Evaluates a physical spring over discrete frames (Remotion spring physics model).
   */
  spring({ frame, fps = 30, config = {} }) {
    if (this.reducedMotion || this.performanceMode === 'eco') {
      return 1.0;
    }
    const { damping = 10, mass = 1, stiffness = 100 } = config;
    const t = frame / fps;
    const omega0 = Math.sqrt(stiffness / mass);
    const zeta = damping / (2 * Math.sqrt(stiffness * mass));

    if (zeta < 1) {
      // Under-damped oscillation
      const omegaD = omega0 * Math.sqrt(1 - zeta * zeta);
      const decay = Math.exp(-zeta * omega0 * t);
      return 1 - decay * (Math.cos(omegaD * t) + (zeta / Math.sqrt(1 - zeta * zeta)) * Math.sin(omegaD * t));
    } else {
      // Critically damped / Over-damped
      const decay = Math.exp(-omega0 * t);
      return 1 - decay * (1 + omega0 * t);
    }
  }

  /**
   * Deterministic linear & eased interpolation between input and output keyframe ranges.
   */
  interpolate(frame, inputRange, outputRange, options = {}) {
    if (this.reducedMotion) {
      return outputRange[outputRange.length - 1];
    }
    const { extrapolateLeft = 'clamp', extrapolateRight = 'clamp', easing } = options;
    const len = inputRange.length;

    if (frame <= inputRange[0]) {
      return extrapolateLeft === 'clamp' ? outputRange[0] : outputRange[0];
    }
    if (frame >= inputRange[len - 1]) {
      return extrapolateRight === 'clamp' ? outputRange[len - 1] : outputRange[len - 1];
    }

    // Find bounding segment
    let i = 0;
    while (i < len - 1 && inputRange[i + 1] < frame) {
      i++;
    }

    const t = (frame - inputRange[i]) / (inputRange[i + 1] - inputRange[i]);
    const easedT = easing ? easing(t) : t;
    return outputRange[i] + easedT * (outputRange[i + 1] - outputRange[i]);
  }

  /**
   * Staggers entrance animation across an array of DOM elements.
   */
  stagger(elements, options = {}) {
    if (!elements || elements.length === 0) return;
    if (this.reducedMotion || this.performanceMode === 'eco') {
      elements.forEach(el => {
        el.style.opacity = '1';
        el.style.transform = 'none';
      });
      return;
    }

    const { delayMs = 40, durationMs = 280 } = options;
    elements.forEach((el, idx) => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(10px)';
      el.style.transition = `opacity ${durationMs}ms cubic-bezier(0.16, 1, 0.3, 1), transform ${durationMs}ms cubic-bezier(0.16, 1, 0.3, 1)`;
      
      setTimeout(() => {
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
      }, idx * delayMs);
    });
  }

  /**
   * Renders an interactive waveform & beat visualization on a 2D Canvas.
   */
  renderTimelineCanvas(canvas, audioBuffer, scenes = [], playheadTime = 0, totalDuration = 1) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    // 1. Draw subtle background grid
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    for (let x = 0; x < width; x += 60) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, height);
      ctx.stroke();
    }

    // 2. Draw Scene blocks
    const totalDur = totalDuration > 0 ? totalDuration : 1;
    scenes.forEach((scene, idx) => {
      const startX = (scene.start / totalDur) * width;
      const endX = (scene.end / totalDur) * width;
      const blockWidth = Math.max(2, endX - startX);

      // Block background
      ctx.fillStyle = idx % 2 === 0 ? 'rgba(var(--accent-rgb, 0, 229, 255), 0.12)' : 'rgba(var(--accent-rgb, 0, 229, 255), 0.06)';
      ctx.fillRect(startX, 4, blockWidth, height - 8);

      // Cut boundary line
      ctx.strokeStyle = 'rgba(var(--accent-rgb, 0, 229, 255), 0.4)';
      ctx.beginPath();
      ctx.moveTo(startX, 4);
      ctx.lineTo(startX, height - 4);
      ctx.stroke();

      // Scene label
      if (blockWidth > 45) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
        ctx.font = '10px monospace';
        ctx.fillText(`SCENE ${idx + 1}`, startX + 6, 20);
      }
    });

    // 3. Draw simulated audio waveform bars
    ctx.fillStyle = 'rgba(var(--accent-rgb, 0, 229, 255), 0.35)';
    const barWidth = 2;
    const barGap = 2;
    const barCount = Math.floor(width / (barWidth + barGap));
    
    for (let i = 0; i < barCount; i++) {
      const x = i * (barWidth + barGap);
      // Pseudo-random deterministic amplitude derived from index
      const amp = Math.sin(i * 0.18) * 0.4 + Math.cos(i * 0.45) * 0.3 + 0.3;
      const barH = Math.max(4, amp * (height * 0.55));
      const y = (height - barH) / 2;
      ctx.fillRect(x, y, barWidth, barH);
    }

    // 4. Draw Interactive Playhead
    const playheadX = (playheadTime / totalDur) * width;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(playheadX, 0);
    ctx.lineTo(playheadX, height);
    ctx.stroke();

    // Playhead head marker
    ctx.fillStyle = 'var(--accent-primary, #00e5ff)';
    ctx.beginPath();
    ctx.arc(playheadX, 6, 5, 0, Math.PI * 2);
    ctx.fill();
  }

  /**
   * Deterministic transition preview composer.
   */
  drawTransitionPreview(canvas, progress = 0.5, type = 'dissolve') {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    if (type === 'dissolve' || type === 'cinematic_dissolve') {
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = `rgba(0, 229, 255, ${progress})`;
      ctx.fillRect(0, 0, w, h);
    } else if (type === 'soft_wipe') {
      const wipeX = w * progress;
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = '#1e293b';
      ctx.fillRect(0, 0, wipeX, h);
      ctx.strokeStyle = 'rgba(0, 229, 255, 0.8)';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.moveTo(wipeX, 0);
      ctx.lineTo(wipeX, h);
      ctx.stroke();
    } else {
      // Clean Cut
      ctx.fillStyle = progress < 0.5 ? '#0f172a' : '#1e293b';
      ctx.fillRect(0, 0, w, h);
    }
  }

  /**
   * Refreshes the audio waveform canvas on resize or tab switch.
   */
  refreshWaveform() {
    const canvas = document.getElementById('timelineWaveformCanvas');
    if (!canvas) return;
    const parentWidth = canvas.parentElement ? canvas.parentElement.clientWidth : 1200;
    if (parentWidth > 0) canvas.width = parentWidth;
    canvas.height = 48;
    this.renderTimelineCanvas(canvas, null, window.currentScenes || [], 0, 100);
  }
}

// Global Singleton Instance
window.renderflowMotion = new RenderFlowMotion();
window.RenderFlowMotion = window.renderflowMotion;

