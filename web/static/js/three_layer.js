/**
 * RenderFlow by AI With Atif — Strategic 3D & WebGL Layer with High-End 2D Fallback
 * =================================================================================
 * Provides dynamic 3D Render-Core visualization for Dashboard and Render Monitor.
 * Reactive to application render states and theme tokens.
 * Features automated capability probing and seamless 2D Canvas + SVG fallback.
 */

class RenderFlow3DCore {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.options = options;
    this.state = 'idle'; // idle, preparing, syncing, rendering, complete, error
    this.theme = document.documentElement.getAttribute('data-theme') || 'glass';
    this.quality = localStorage.getItem('renderflow_3d_quality') || 'auto';
    this.isRunning = false;
    this.animId = null;
    this.rotX = 0.35;
    this.rotY = 0.0;
    this.pulse = 0;

    this.init();
  }

  init() {
    this.container.innerHTML = '';
    this.canvas = document.createElement('canvas');
    this.canvas.className = 'canvas-3d-canvas';
    this.canvas.style.width = '100%';
    this.canvas.style.height = '100%';
    this.canvas.style.display = 'block';
    this.container.appendChild(this.canvas);

    // Try WebGL, with seamless 2D Canvas high-fidelity fallback
    const hasWebGL = this.checkWebGLSupport();
    const isEcoMode = localStorage.getItem('renderflow_perf_mode') === 'eco';

    if (hasWebGL && this.quality !== 'disabled' && !isEcoMode) {
      try {
        this.gl = this.canvas.getContext('webgl', { alpha: true, antialias: true });
        if (this.gl) {
          this.setupWebGL();
          this.mode = 'webgl';
        } else {
          this.setup2D();
          this.mode = '2d';
        }
      } catch (e) {
        console.warn('[RenderFlow 3D] WebGL setup note, using 2D canvas engine.', e);
        this.setup2D();
        this.mode = '2d';
      }
    } else {
      this.setup2D();
      this.mode = '2d';
    }

    this.resize();
    window.addEventListener('resize', () => this.resize());
    
    // Immediate synchronous first paint
    if (this.mode === 'webgl' && this.gl) {
      this.renderWebGL(0, performance.now());
    } else {
      this.render2D(0, performance.now());
    }
    
    this.startLoop();
  }

  checkWebGLSupport() {
    try {
      const c = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && (c.getContext('webgl') || c.getContext('experimental-webgl')));
    } catch (e) {
      return false;
    }
  }

  setup2D() {
    this.ctx = this.canvas.getContext('2d');
  }

  setupWebGL() {
    const gl = this.gl;
    // Octahedron wireframe vertices
    this.vertices = new Float32Array([
      // Top pyramid edges
       0.0,  1.0,  0.0,   -0.8,  0.0,  0.8,
       0.0,  1.0,  0.0,    0.8,  0.0,  0.8,
       0.0,  1.0,  0.0,    0.8,  0.0, -0.8,
       0.0,  1.0,  0.0,   -0.8,  0.0, -0.8,
      // Base square
      -0.8,  0.0,  0.8,    0.8,  0.0,  0.8,
       0.8,  0.0,  0.8,    0.8,  0.0, -0.8,
       0.8,  0.0, -0.8,   -0.8,  0.0, -0.8,
      -0.8,  0.0, -0.8,   -0.8,  0.0,  0.8,
      // Bottom pyramid edges
       0.0, -1.0,  0.0,   -0.8,  0.0,  0.8,
       0.0, -1.0,  0.0,    0.8,  0.0,  0.8,
       0.0, -1.0,  0.0,    0.8,  0.0, -0.8,
       0.0, -1.0,  0.0,   -0.8,  0.0, -0.8,
    ]);

    this.vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
    gl.bufferData(gl.ARRAY_BUFFER, this.vertices, gl.STATIC_DRAW);

    const vsSource = `
      attribute vec3 aPos;
      uniform mat4 uMatrix;
      varying vec3 vPos;
      void main() {
        vPos = aPos;
        gl_Position = uMatrix * vec4(aPos * 0.75, 1.0);
      }
    `;

    const fsSource = `
      precision mediump float;
      uniform vec3 uColor;
      uniform float uPulse;
      varying vec3 vPos;
      void main() {
        float intensity = 0.6 + 0.4 * sin(vPos.y * 3.0 + uPulse);
        gl_FragColor = vec4(uColor * intensity, 0.9);
      }
    `;

    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, vsSource);
    gl.compileShader(vs);

    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, fsSource);
    gl.compileShader(fs);

    this.program = gl.createProgram();
    gl.attachShader(this.program, vs);
    gl.attachShader(this.program, fs);
    gl.linkProgram(this.program);

    this.aPosLoc = gl.getAttribLocation(this.program, 'aPos');
    this.uMatrixLoc = gl.getUniformLocation(this.program, 'uMatrix');
    this.uColorLoc = gl.getUniformLocation(this.program, 'uColor');
    this.uPulseLoc = gl.getUniformLocation(this.program, 'uPulse');
  }

  resize() {
    if (!this.container || !this.canvas) return;
    const rect = this.container.getBoundingClientRect();
    const w = rect.width > 0 ? rect.width : (this.container.clientWidth || 340);
    const h = rect.height > 0 ? rect.height : (this.container.clientHeight || 280);
    this.width = w;
    this.height = h;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    if (this.gl) {
      this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
      this.renderWebGL(0, performance.now());
    } else if (this.ctx) {
      this.render2D(0, performance.now());
    }
  }

  startLoop() {
    this.isRunning = true;
    let lastTime = performance.now();

    const loop = (now) => {
      if (!this.isRunning) return;
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      // Auto-recover size if tab just became visible
      if (this.container && this.container.clientWidth > 0) {
        const expectedW = Math.round(this.container.clientWidth * (window.devicePixelRatio || 1));
        if (Math.abs(this.canvas.width - expectedW) > 10) {
          this.resize();
        }
      }

      this.pulse += dt * 3.0;
      let speed = 0.8;
      if (this.state === 'rendering') speed = 2.4;
      else if (this.state === 'syncing') speed = 1.6;
      else if (this.state === 'error') speed = 0.2;

      this.rotY += speed * dt;
      this.rotX += speed * 0.3 * dt;

      if (this.mode === 'webgl' && this.gl) {
        this.renderWebGL(dt, now);
      } else {
        this.render2D(dt, now);
      }

      this.animId = requestAnimationFrame(loop);
    };
    this.animId = requestAnimationFrame(loop);
  }

  getThemeHex() {
    this.theme = document.documentElement.getAttribute('data-theme') || 'glass';
    if (this.state === 'error') return '#f43f5e';
    if (this.state === 'complete') return '#10b981';

    switch (this.theme) {
      case 'muddy': return '#d97706';
      case 'apple': return '#0071e3';
      case 'f1': return '#e10600';
      case 'glass':
      default: return '#00f0ff';
    }
  }

  getThemeColor() {
    this.theme = document.documentElement.getAttribute('data-theme') || 'glass';
    if (this.state === 'error') return [0.95, 0.25, 0.35];
    if (this.state === 'complete') return [0.06, 0.72, 0.5];

    switch (this.theme) {
      case 'muddy': return [0.85, 0.47, 0.02];
      case 'apple': return [0.0, 0.44, 0.89];
      case 'f1': return [0.88, 0.02, 0.0];
      case 'glass':
      default: return [0.0, 0.94, 1.0];
    }
  }

  renderWebGL(dt, now) {
    const gl = this.gl;
    if (!gl) return;

    gl.clearColor(0.0, 0.0, 0.0, 0.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);

    gl.useProgram(this.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vbo);
    gl.enableVertexAttribArray(this.aPosLoc);
    gl.vertexAttribPointer(this.aPosLoc, 3, gl.FLOAT, false, 0, 0);

    const aspect = (this.width || 320) / (this.height || 280);
    const matrix = this.createTransformMatrix(this.rotX, this.rotY, aspect);
    gl.uniformMatrix4fv(this.uMatrixLoc, false, matrix);

    const color = this.getThemeColor();
    gl.uniform3f(this.uColorLoc, color[0], color[1], color[2]);
    gl.uniform1f(this.uPulseLoc, now * 0.003);

    gl.drawArrays(gl.LINES, 0, 24);
  }

  render2D(dt, now) {
    const ctx = this.ctx;
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.width;
    const h = this.canvas.height;
    if (w === 0 || h === 0) return;

    ctx.clearRect(0, 0, w, h);

    const cx = w / 2;
    const cy = h / 2;
    const scale = Math.min(w, h) * 0.26;
    const color = this.getThemeHex();

    // 3D Octahedron vertices
    const rawNodes = [
      [ 0, -1.2,  0],  // top
      [ 0,  1.2,  0],  // bottom
      [-1,    0, -1],  // base 0
      [ 1,    0, -1],  // base 1
      [ 1,    0,  1],  // base 2
      [-1,    0,  1]   // base 3
    ];

    // Edges
    const edges = [
      [0,2], [0,3], [0,4], [0,5], // top to base
      [1,2], [1,3], [1,4], [1,5], // bottom to base
      [2,3], [3,4], [4,5], [5,2]  // base ring
    ];

    // Project 3D nodes
    const cosX = Math.cos(this.rotX), sinX = Math.sin(this.rotX);
    const cosY = Math.cos(this.rotY), sinY = Math.sin(this.rotY);

    const projected = rawNodes.map(pt => {
      // Y rotation
      let x1 = pt[0] * cosY - pt[2] * sinY;
      let y1 = pt[1];
      let z1 = pt[0] * sinY + pt[2] * cosY;

      // X rotation
      let y2 = y1 * cosX - z1 * sinX;
      let z2 = y1 * sinX + z1 * cosX;

      const fov = 3.2 / (3.2 + z2);
      return {
        x: cx + x1 * scale * fov,
        y: cy + y2 * scale * fov,
        z: z2
      };
    });

    // Draw Theme-Specific 3D Spatial Geometry & Lighting Signature
    const themeId = this.theme || document.documentElement.getAttribute('data-theme') || 'glass';
    
    if (themeId === 'f1') {
      // F1: Technical telemetry geometry — Crosshairs, racing red arcs & tachometer
      ctx.save();
      ctx.strokeStyle = 'rgba(225, 6, 0, 0.3)';
      ctx.lineWidth = 1 * dpr;
      ctx.beginPath();
      ctx.moveTo(cx - scale * 1.5, cy); ctx.lineTo(cx + scale * 1.5, cy);
      ctx.moveTo(cx, cy - scale * 1.3); ctx.lineTo(cx, cy + scale * 1.3);
      ctx.stroke();

      // Tachometer perimeter arc
      ctx.beginPath();
      ctx.arc(cx, cy, scale * 1.35, Math.PI * 0.7, Math.PI * 2.3);
      ctx.strokeStyle = '#e10600';
      ctx.lineWidth = 2 * dpr;
      ctx.setLineDash([4 * dpr, 5 * dpr]);
      ctx.stroke();
      ctx.restore();
    } else if (themeId === 'apple') {
      // Apple: Minimal spatial interface — Smooth concentric thin circles
      ctx.save();
      ctx.strokeStyle = 'rgba(0, 113, 227, 0.35)';
      ctx.lineWidth = 1 * dpr;
      ctx.beginPath();
      ctx.arc(cx, cy, scale * 1.3, 0, Math.PI * 2);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(cx, cy, scale * 0.75, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.stroke();
      ctx.restore();
    } else if (themeId === 'muddy') {
      // Muddy: Warm earthy lighting & organic amber orbital glow
      ctx.save();
      const grad = ctx.createRadialGradient(cx, cy, scale * 0.2, cx, cy, scale * 1.4);
      grad.addColorStop(0, 'rgba(217, 119, 6, 0.18)');
      grad.addColorStop(1, 'rgba(20, 17, 15, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, scale * 1.4, 0, Math.PI * 2);
      ctx.fill();

      ctx.beginPath();
      ctx.ellipse(cx, cy, scale * 1.35, scale * 0.5, this.rotY * 0.2, 0, Math.PI * 2);
      ctx.strokeStyle = '#d97706';
      ctx.lineWidth = 1.5 * dpr;
      ctx.globalAlpha = 0.35;
      ctx.stroke();
      ctx.restore();
    } else {
      // Glass: Cool luminous spatial core
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(cx, cy, scale * 1.35, scale * 0.45, this.rotY * 0.2, 0, Math.PI * 2);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1 * dpr;
      ctx.globalAlpha = 0.3;
      ctx.stroke();
      ctx.restore();
    }

    // Draw edges
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2 * dpr;
    ctx.shadowColor = color;
    ctx.shadowBlur = 12 * dpr;
    ctx.globalAlpha = 0.85;

    edges.forEach(([i, j]) => {
      ctx.beginPath();
      ctx.moveTo(projected[i].x, projected[i].y);
      ctx.lineTo(projected[j].x, projected[j].y);
      ctx.stroke();
    });
    ctx.restore();

    // Draw glowing nodes
    ctx.save();
    ctx.fillStyle = '#ffffff';
    ctx.shadowColor = color;
    ctx.shadowBlur = 10 * dpr;
    projected.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, (themeId === 'f1' ? 2.5 : 3) * dpr, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();

    // Telemetry label overlay at bottom of canvas
    ctx.save();
    ctx.font = `${Math.round(10 * dpr)}px 'JetBrains Mono', monospace`;
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.globalAlpha = 0.75;
    const stateLabel = this.state.toUpperCase();
    ctx.fillText(`RENDER-CORE • ${themeId.toUpperCase()} • ${stateLabel}`, cx, h - (16 * dpr));
    ctx.restore();
  }

  createTransformMatrix(rx, ry, aspect) {
    const cosX = Math.cos(rx), sinX = Math.sin(rx);
    const cosY = Math.cos(ry), sinY = Math.sin(ry);
    const fov = 1.5;

    return new Float32Array([
      cosY / aspect * fov,  sinX * sinY,          cosX * sinY,          0,
      0,                    cosX * fov,          -sinX,                 0,
     -sinY / aspect * fov,  sinX * cosY,          cosX * cosY,          0,
      0,                    0,                    0,                    1
    ]);
  }

  setState(newState) {
    this.state = newState;
  }

  setTheme(newTheme) {
    this.theme = newTheme;
    if (this.mode === 'webgl' && this.gl) {
      this.renderWebGL(0, performance.now());
    } else if (this.ctx) {
      this.render2D(0, performance.now());
    }
  }

  setQuality(newQuality) {
    this.quality = newQuality;
    localStorage.setItem('renderflow_3d_quality', newQuality);
    this.init();
  }

  destroy() {
    this.isRunning = false;
    if (this.animId) cancelAnimationFrame(this.animId);
  }
}

window.RenderFlow3DCore = RenderFlow3DCore;

