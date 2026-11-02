// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Runs the scan off the page's main thread. Messages in: { type: 'run', files | frames, settings, name }.
// Messages out: progress, done (model arrays, OBJ text, GLB bytes, info), failed.
// The worker stays alive between builds, so the TripoSR model loads only once per visit.

import { run } from './core/pipeline.js';
import { glbBuffer, objText } from './core/export.js';
import { loadTripo } from './tripo-runtime.js';

async function decode(buffer, name, maxWidth) {
  const bmp = await createImageBitmap(new Blob([buffer]), { imageOrientation: 'from-image' });
  const s = Math.min(1, maxWidth / bmp.width);
  const w = Math.round(bmp.width * s), h = Math.round(bmp.height * s);
  const canvas = new OffscreenCanvas(w, h);
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(bmp, 0, 0, w, h);
  const originalWidth = bmp.width;
  bmp.close();
  const id = ctx.getImageData(0, 0, w, h);
  return { image: { width: w, height: h, data: id.data }, originalWidth };
}

self.onmessage = async (e) => {
  const msg = e.data;
  if (msg.type !== 'run') return;
  let last = 0;
  const progress = (stage, fraction, message) => {
    const now = performance.now();
    if (message || fraction === 1 || now - last > 80) { last = now; self.postMessage({ type: 'progress', stage, fraction, message }); }
  };
  try {
    const r = await run({ files: msg.files, frames: msg.frames, decode, settings: msg.settings, loadTripo }, progress);
    const obj = objText(r.model, msg.name, r.method);
    const glb = glbBuffer(r.model);
    const m = r.model;
    const transfer = [m.vertices.buffer, m.normals.buffer, m.faces.buffer, glb];
    if (m.colors) transfer.push(m.colors.buffer);
    self.postMessage({ type: 'done', method: r.method, vertices: m.vertices, normals: m.normals, faces: m.faces,
                       colors: m.colors, sizeMm: m.sizeMm, scaledToHeight: m.scaledToHeight, obj, glb, info: r.info }, transfer);
  } catch (err) {
    self.postMessage({ type: 'failed', code: err.code || 'ENGINE_CRASHED',
                       message: err.userMessage || (err.code ? err.message : `Something went wrong: ${err.message}`),
                       detail: err.detail || err.stack || '' });
  }
};
