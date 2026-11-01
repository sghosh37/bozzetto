// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// A small WebGL mesh viewer: drag to turn, scroll or pinch to zoom, double-click to reset.
// Shaded like modelling clay so the form reads clearly.

const VS = `
attribute vec3 aPos; attribute vec3 aNrm;
uniform mat4 uMVP; uniform mat3 uN;
varying vec3 vN;
void main() { vN = normalize(uN * aNrm); gl_Position = uMVP * vec4(aPos, 1.0); }`;
const FS = `
precision mediump float;
varying vec3 vN;
uniform vec3 uClay; uniform vec3 uSky; uniform vec3 uGround;
void main() {
  vec3 n = normalize(vN);
  vec3 key = normalize(vec3(-0.45, 0.75, 0.55));
  float d = max(dot(n, key), 0.0);
  float rim = pow(1.0 - max(n.z, 0.0), 2.5);
  vec3 hemi = mix(uGround, uSky, n.y * 0.5 + 0.5);
  vec3 c = uClay * (0.48 * hemi + 0.62 * d) + 0.08 * rim;
  gl_FragColor = vec4(c, 1.0);
}`;

function mul(a, b) {
  const o = new Float32Array(16);
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
    let s = 0;
    for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k];
    o[i * 4 + j] = s;
  }
  return o;
}
const rotX = (t) => { const c = Math.cos(t), s = Math.sin(t); return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]); };
const rotY = (t) => { const c = Math.cos(t), s = Math.sin(t); return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]); };
const trans = (x, y, z) => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]);
const persp = (fov, asp, n, f) => { const t = 1 / Math.tan(fov / 2); return new Float32Array([t / asp, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) / (n - f), -1, 0, 0, 2 * f * n / (n - f), 0]); };

function cssColor(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  const m = /^#([0-9a-f]{6})$/i.exec(v);
  if (!m) return fallback;
  const n = parseInt(m[1], 16);
  return [(n >> 16) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export class MeshViewer {
  /** @param {HTMLCanvasElement} canvas */
  constructor(canvas, { spin = false } = {}) {
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { antialias: true }) || canvas.getContext('webgl', { antialias: true });
    if (!gl) throw new Error('WebGL is not available in this browser.');
    this.gl = gl;
    this.uint = (typeof WebGL2RenderingContext !== 'undefined' && gl instanceof WebGL2RenderingContext)
      || !!gl.getExtension('OES_element_index_uint');
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const p = gl.createProgram();
    gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    this.p = p;
    this.loc = { pos: gl.getAttribLocation(p, 'aPos'), nrm: gl.getAttribLocation(p, 'aNrm'), mvp: gl.getUniformLocation(p, 'uMVP'),
                 n: gl.getUniformLocation(p, 'uN'), clay: gl.getUniformLocation(p, 'uClay'),
                 sky: gl.getUniformLocation(p, 'uSky'), ground: gl.getUniformLocation(p, 'uGround') };
    this.yaw = 0.6; this.pitch = 0.32; this.zoom = 1; this.count = 0;
    this.spin = spin && !matchMedia('(prefers-reduced-motion: reduce)').matches;
    this._bind();
    new ResizeObserver(() => this.draw()).observe(canvas);
    matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => this.draw());
    if (this.spin) { const tick = () => { if (!this.dragging) { this.yaw += 0.004; this.draw(); } this.raf = requestAnimationFrame(tick); }; tick(); }
  }

  _bind() {
    const c = this.canvas;
    let last = null;
    const pts = new Map();
    c.addEventListener('pointerdown', (e) => { c.setPointerCapture(e.pointerId); pts.set(e.pointerId, [e.clientX, e.clientY]); last = [e.clientX, e.clientY]; this.dragging = true; });
    c.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId)) return;
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        const before = Math.hypot(a[0] - b[0], a[1] - b[1]);
        pts.set(e.pointerId, [e.clientX, e.clientY]);
        const [a2, b2] = [...pts.values()];
        const after = Math.hypot(a2[0] - b2[0], a2[1] - b2[1]);
        if (before > 0) this.zoom = Math.min(4, Math.max(0.4, this.zoom * after / before));
      } else {
        this.yaw += (e.clientX - last[0]) * 0.01;
        this.pitch = Math.max(-1.4, Math.min(1.4, this.pitch + (e.clientY - last[1]) * 0.01));
        pts.set(e.pointerId, [e.clientX, e.clientY]);
      }
      last = [e.clientX, e.clientY];
      this.draw();
    });
    const up = (e) => { pts.delete(e.pointerId); if (!pts.size) this.dragging = false; };
    c.addEventListener('pointerup', up); c.addEventListener('pointercancel', up);
    c.addEventListener('wheel', (e) => { e.preventDefault(); this.zoom = Math.min(4, Math.max(0.4, this.zoom * Math.exp(-e.deltaY * 0.001))); this.draw(); }, { passive: false });
    c.addEventListener('dblclick', () => { this.yaw = 0.6; this.pitch = 0.32; this.zoom = 1; this.draw(); });
    c.addEventListener('keydown', (e) => {
      const k = { ArrowLeft: [-0.15, 0], ArrowRight: [0.15, 0], ArrowUp: [0, -0.15], ArrowDown: [0, 0.15] }[e.key];
      if (k) { e.preventDefault(); this.yaw += k[0]; this.pitch = Math.max(-1.4, Math.min(1.4, this.pitch + k[1])); this.draw(); }
      if (e.key === '+' || e.key === '=') { this.zoom = Math.min(4, this.zoom * 1.15); this.draw(); }
      if (e.key === '-') { this.zoom = Math.max(0.4, this.zoom / 1.15); this.draw(); }
    });
  }

  /** vertices and normals: Float32Array xyz; faces: Uint32Array. Units don't matter (fitted to view). */
  setMesh(vertices, normals, faces) {
    const gl = this.gl;
    let min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < vertices.length; i += 3) for (let k = 0; k < 3; k++) { min[k] = Math.min(min[k], vertices[i + k]); max[k] = Math.max(max[k], vertices[i + k]); }
    this.centre = min.map((m, k) => (m + max[k]) / 2);
    this.radius = Math.hypot(max[0] - min[0], max[1] - min[1], max[2] - min[2]) / 2 || 1;
    const buf = (data, target) => { const b = gl.createBuffer(); gl.bindBuffer(target, b); gl.bufferData(target, data, gl.STATIC_DRAW); return b; };
    for (const b of [this.vb, this.nb, this.ib]) if (b) gl.deleteBuffer(b);
    this.vb = buf(vertices instanceof Float32Array ? vertices : Float32Array.from(vertices), gl.ARRAY_BUFFER);
    this.nb = buf(normals instanceof Float32Array ? normals : Float32Array.from(normals), gl.ARRAY_BUFFER);
    if (this.uint) { this.ib = buf(Uint32Array.from(faces), gl.ELEMENT_ARRAY_BUFFER); this.itype = gl.UNSIGNED_INT; }
    else { this.ib = buf(Uint16Array.from(faces), gl.ELEMENT_ARRAY_BUFFER); this.itype = gl.UNSIGNED_SHORT; }
    this.count = faces.length;
    this.draw();
  }

  clear() { this.count = 0; this.draw(); }

  /** Load a .glb made by Bozzetto (positions + normals + indices). */
  async loadGlb(url) {
    const ab = await (await fetch(url)).arrayBuffer();
    const dv = new DataView(ab);
    const jsLen = dv.getUint32(12, true);
    const gltf = JSON.parse(new TextDecoder().decode(new Uint8Array(ab, 20, jsLen)));
    const bin = 20 + jsLen + 8;
    const view = (acc, Type) => {
      const a = gltf.accessors[acc], bv = gltf.bufferViews[a.bufferView];
      const n = a.count * (a.type === 'VEC3' ? 3 : 1);
      return new Type(ab.slice(bin + (bv.byteOffset || 0), bin + (bv.byteOffset || 0) + n * Type.BYTES_PER_ELEMENT));
    };
    const prim = gltf.meshes[0].primitives[0];
    this.setMesh(view(prim.attributes.POSITION, Float32Array), view(prim.attributes.NORMAL, Float32Array), view(prim.indices, Uint32Array));
  }

  draw() {
    const gl = this.gl, c = this.canvas;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(c.clientWidth * dpr)), h = Math.max(1, Math.round(c.clientHeight * dpr));
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (!this.count) return;
    gl.enable(gl.DEPTH_TEST);
    gl.useProgram(this.p);
    const dist = this.radius * 3.6 / this.zoom;
    const model = mul(rotX(this.pitch), mul(rotY(this.yaw), trans(-this.centre[0], -this.centre[1], -this.centre[2])));
    const view = trans(0, 0, -dist);
    const proj = persp(0.7, w / h, dist * 0.05, dist * 4);
    const mv = mul(view, model);
    gl.uniformMatrix4fv(this.loc.mvp, false, mul(proj, mv));
    gl.uniformMatrix3fv(this.loc.n, false, new Float32Array([mv[0], mv[1], mv[2], mv[4], mv[5], mv[6], mv[8], mv[9], mv[10]]));
    gl.uniform3fv(this.loc.clay, cssColor(c, '--clay', [0.62, 0.66, 0.6]));
    gl.uniform3fv(this.loc.sky, cssColor(c, '--clay-sky', [1, 1, 1]));
    gl.uniform3fv(this.loc.ground, cssColor(c, '--clay-ground', [0.45, 0.42, 0.38]));
    gl.bindBuffer(gl.ARRAY_BUFFER, this.vb);
    gl.enableVertexAttribArray(this.loc.pos); gl.vertexAttribPointer(this.loc.pos, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.nb);
    gl.enableVertexAttribArray(this.loc.nrm); gl.vertexAttribPointer(this.loc.nrm, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.ib);
    gl.drawElements(gl.TRIANGLES, this.count, this.itype, 0);
  }
}
