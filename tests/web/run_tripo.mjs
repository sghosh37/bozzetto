// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Runs the browser TripoSR code (web/js/core/tripo.js) in Node for tests/test_web_tripo.py,
// with stand-in networks instead of the real model.
//   node run_tripo.mjs prep   <rgba> <w> <h> <out.f32>        prepared 512×512 input (NCHW float32)
//   node run_tripo.mjs sample <triplane.f32> <pts.f32> <out.f32>  120 features per point
//   node run_tripo.mjs run    <manifest.json> <out.obj>          whole pipeline, prints a JSON summary
import { readFileSync, writeFileSync } from 'node:fs';
import { prepareImage, sampleFeatures, PLANE_RES, CHANNELS } from '../../web/js/core/tripo.js';
import { run } from '../../web/js/core/pipeline.js';
import { objText } from '../../web/js/core/export.js';
import { badEdges } from '../../web/js/core/meshops.js';

const f32 = (p) => { const b = readFileSync(p); return new Float32Array(b.buffer, b.byteOffset, b.byteLength / 4); };
const [mode, ...a] = process.argv.slice(2);

/** Stand-in networks: the triplane stores coordinates, the decoder turns them into an ellipsoid. */
function fakeNets(axes = [0.3, 0.2, 0.6]) {
  const triplane = new Float32Array(3 * CHANNELS * PLANE_RES * PLANE_RES);
  const centre = (i) => (2 * i + 1) / PLANE_RES - 1;
  for (let p = 0; p < 3; p++) for (let h = 0; h < PLANE_RES; h++) for (let w = 0; w < PLANE_RES; w++) {
    const base = (p * CHANNELS * PLANE_RES + h) * PLANE_RES + w;
    triplane[base] = centre(w);                               // channel 0: first coordinate of the pair
    triplane[base + PLANE_RES * PLANE_RES] = centre(h);       // channel 1: second coordinate
  }
  return {
    triplane: async (image) => {
      if (image.length !== 3 * 512 * 512) throw new Error('bad image size');
      return triplane;
    },
    decode: async (feats, n) => {
      const density = new Float32Array(n), color = new Float32Array(3 * n);
      for (let i = 0; i < n; i++) {
        const o = i * 3 * CHANNELS;
        const x = feats[o], y = feats[o + 1], z = feats[o + CHANNELS + 1];   // xy plane: x, y; xz plane: z
        const q = (x / axes[0]) ** 2 + (y / axes[1]) ** 2 + (z / axes[2]) ** 2;
        density[i] = 25 * Math.exp(-3 * (q - 1));
        color[3 * i] = 0.8; color[3 * i + 1] = 0.2; color[3 * i + 2] = 0.1;
      }
      return { density, color };
    },
  };
}

if (mode === 'prep') {
  const [raw, w, h, out] = a;
  const b = readFileSync(raw);
  const img = { name: 'photo', width: +w, height: +h, data: new Uint8ClampedArray(b.buffer, b.byteOffset, b.byteLength) };
  writeFileSync(out, Buffer.from(prepareImage(img).buffer));
} else if (mode === 'sample') {
  const [tp, pts, out] = a;
  const p = f32(pts);
  writeFileSync(out, Buffer.from(sampleFeatures(f32(tp), p, p.length / 3).buffer));
} else if (mode === 'run') {
  const [manifestPath, outPath] = a;
  const m = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const byName = new Map(m.photos.map((p) => [p.name, p]));
  const files = m.photos.map((p) => { const b = readFileSync(p.file); return { name: p.name, buffer: b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) }; });
  const decode = async (buffer, name) => {
    const p = byName.get(name), b = readFileSync(p.raw);
    return { image: { width: p.width, height: p.height, data: new Uint8ClampedArray(b.buffer, b.byteOffset, b.byteLength) }, originalWidth: p.width };
  };
  let loads = 0;
  const r = await run({ files, decode, settings: m.settings, loadTripo: async () => { loads++; return fakeNets(); } });
  writeFileSync(outPath, objText(r.model, 'web', r.method));
  console.log(JSON.stringify({ method: r.method, loads, size: r.model.sizeMm, triangles: r.model.faces.length / 3,
    badEdges: badEdges(r.model.faces), color: r.model.colors ? Array.from(r.model.colors.slice(0, 3)) : null,
    warnings: r.info.warnings, log: r.info.log }));
}
