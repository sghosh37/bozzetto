// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Runs the browser engine (web/js/core) in Node for the parity test.
// usage: node run_core.mjs <manifest.json> <out.obj> [out.glb]
// The manifest lists photos: { name, file (the JPEG), raw (RGBA bytes decoded by OpenCV), width, height }
// and settings: { heightMm, tiltDeg, clockwise, preset }. Prints a JSON summary.
import { readFileSync, writeFileSync } from 'node:fs';
import { run } from '../../web/js/core/pipeline.js';
import { glbBuffer, objText } from '../../web/js/core/export.js';
import { badEdges } from '../../web/js/core/meshops.js';

const [manifestPath, outPath, glbPath] = process.argv.slice(2);
const m = JSON.parse(readFileSync(manifestPath, 'utf8'));
const byName = new Map(m.photos.map((p) => [p.name, p]));
const toAB = (b) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength);
const files = m.photos.map((p) => ({ name: p.name, buffer: toAB(readFileSync(p.file)) }));
const decode = async (buffer, name) => {
  const p = byName.get(name);
  return { image: { width: p.width, height: p.height, data: new Uint8ClampedArray(readFileSync(p.raw)) }, originalWidth: p.width };
};
const t0 = Date.now();
const r = await run({ files, decode, settings: m.settings });
writeFileSync(outPath, objText(r.model, 'web'));
if (glbPath) writeFileSync(glbPath, Buffer.from(glbBuffer(r.model)));
console.log(JSON.stringify({ size: r.model.sizeMm, triangles: r.model.faces.length / 3, badEdges: badEdges(r.model.faces),
  score: r.info.turntableScore, warnings: r.info.warnings, log: r.info.log, ms: Date.now() - t0 }));
