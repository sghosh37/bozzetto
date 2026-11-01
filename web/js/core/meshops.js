// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Mesh helpers on flat arrays. Port of bozzetto/core/meshops.py.
// vertices: Float64Array (x, y, z per vertex); faces: Uint32Array (a, b, c per triangle).

function cross(v, a, b, c) {
  const ux = v[3 * b] - v[3 * a], uy = v[3 * b + 1] - v[3 * a + 1], uz = v[3 * b + 2] - v[3 * a + 2];
  const wx = v[3 * c] - v[3 * a], wy = v[3 * c + 1] - v[3 * a + 1], wz = v[3 * c + 2] - v[3 * a + 2];
  return [uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx];
}

/**
 * Drop triangles that repeat a vertex, and (when minArea > 0) near-zero-area ones. The browser's
 * marching tetrahedra makes thin slivers that are still part of a closed surface, so the export calls
 * this with minArea = 0: removing slivers would open holes.
 */
export function removeDegenerate(v, f, minArea = 1e-12) {
  const out = [];
  for (let i = 0; i < f.length; i += 3) {
    const a = f[i], b = f[i + 1], c = f[i + 2];
    if (a === b || b === c || a === c) continue;
    const n = cross(v, a, b, c);
    if (minArea <= 0 || Math.hypot(n[0], n[1], n[2]) > minArea) out.push(a, b, c);
  }
  return Uint32Array.from(out);
}

/** Keep only the biggest connected piece (by face count); re-index vertices. */
export function largestComponent(v, f) {
  const nv = v.length / 3;
  const parent = new Int32Array(nv);
  for (let i = 0; i < nv; i++) parent[i] = i;
  const find = (x) => { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; };
  const union = (a, b) => { a = find(a); b = find(b); if (a !== b) parent[a] = b; };
  for (let i = 0; i < f.length; i += 3) { union(f[i], f[i + 1]); union(f[i + 1], f[i + 2]); }
  const counts = new Map();
  for (let i = 0; i < f.length; i += 3) { const r = find(f[i]); counts.set(r, (counts.get(r) || 0) + 1); }
  let best = -1, bestN = -1;
  for (const [r, c] of counts) if (c > bestN) { best = r; bestN = c; }
  const remap = new Int32Array(nv).fill(-1);
  const keptV = [], keptF = [];
  for (let i = 0; i < f.length; i += 3) {
    if (find(f[i]) !== best) continue;
    for (let k = 0; k < 3; k++) {
      const o = f[i + k];
      if (remap[o] < 0) { remap[o] = keptV.length / 3; keptV.push(v[3 * o], v[3 * o + 1], v[3 * o + 2]); }
      keptF.push(remap[o]);
    }
  }
  return { vertices: Float64Array.from(keptV), faces: Uint32Array.from(keptF) };
}

/** Unique neighbours of every vertex, as CSR arrays. */
export function neighbours(nv, f) {
  const sets = Array.from({ length: nv }, () => new Set());
  for (let i = 0; i < f.length; i += 3) {
    const a = f[i], b = f[i + 1], c = f[i + 2];
    sets[a].add(b); sets[a].add(c); sets[b].add(a); sets[b].add(c); sets[c].add(a); sets[c].add(b);
  }
  const start = new Uint32Array(nv + 1);
  for (let i = 0; i < nv; i++) start[i + 1] = start[i] + sets[i].size;
  const list = new Uint32Array(start[nv]);
  for (let i = 0; i < nv; i++) { let k = start[i]; for (const j of sets[i]) list[k++] = j; }
  return { start, list };
}

/** Taubin smoothing: removes voxel steps and noise without shrinking the shape. */
export function taubin(v, f, iterations = 6, lam = 0.5, mu = -0.53) {
  if (iterations <= 0 || f.length === 0) return v;
  const nv = v.length / 3;
  const { start, list } = neighbours(nv, f);
  let cur = Float64Array.from(v);
  const step = (factor) => {
    const next = new Float64Array(cur.length);
    for (let i = 0; i < nv; i++) {
      const deg = start[i + 1] - start[i];
      for (let k = 0; k < 3; k++) {
        let avg = 0;
        for (let j = start[i]; j < start[i + 1]; j++) avg += cur[3 * list[j] + k];
        avg = deg ? avg / deg : 0;
        // vertices without neighbours: numpy version averages to 0 then moves toward it; none occur in closed meshes
        next[3 * i + k] = cur[3 * i + k] + factor * (avg - cur[3 * i + k]);
      }
    }
    cur = next;
  };
  for (let it = 0; it < iterations; it++) { step(lam); step(mu); }
  return cur;
}

export function signedVolume(v, f) {
  let s = 0;
  for (let i = 0; i < f.length; i += 3) {
    const a = 3 * f[i], b = 3 * f[i + 1], c = 3 * f[i + 2];
    s += v[a] * (v[b + 1] * v[c + 2] - v[b + 2] * v[c + 1])
       + v[a + 1] * (v[b + 2] * v[c] - v[b] * v[c + 2])
       + v[a + 2] * (v[b] * v[c + 1] - v[b + 1] * v[c]);
  }
  return s / 6;
}

/** Flip all faces if the closed mesh is inside-out (negative volume). */
export function orientOutward(v, f) {
  if (signedVolume(v, f) >= 0) return f;
  const g = new Uint32Array(f.length);
  for (let i = 0; i < f.length; i += 3) { g[i] = f[i + 2]; g[i + 1] = f[i + 1]; g[i + 2] = f[i]; }
  return g;
}

export function vertexNormals(v, f) {
  const n = new Float64Array(v.length);
  for (let i = 0; i < f.length; i += 3) {
    const fn = cross(v, f[i], f[i + 1], f[i + 2]);     // area-weighted
    for (let k = 0; k < 3; k++) { const o = 3 * f[i + k]; n[o] += fn[0]; n[o + 1] += fn[1]; n[o + 2] += fn[2]; }
  }
  const out = new Float32Array(v.length);
  for (let i = 0; i < v.length; i += 3) {
    const l = Math.hypot(n[i], n[i + 1], n[i + 2]) || 1;
    out[i] = n[i] / l; out[i + 1] = n[i + 1] / l; out[i + 2] = n[i + 2] / l;
  }
  return out;
}

/** Edges not shared by exactly two faces (0 = closed, manifold). */
export function badEdges(f) {
  const counts = new Map();
  for (let i = 0; i < f.length; i += 3) {
    for (let k = 0; k < 3; k++) {
      const a = f[i + k], b = f[i + (k + 1) % 3];
      const key = a < b ? a * 4294967296 + b : b * 4294967296 + a;
      counts.set(key, (counts.get(key) || 0) + 1);
    }
  }
  let bad = 0;
  for (const c of counts.values()) if (c !== 2) bad++;
  return bad;
}
