// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Separate the product from a plain background ("cut-out"). Port of bozzetto/core/masks.py.
// The colour along the photo's border is taken as the background, and every pixel is scored
// by how far its colour is from it.

import { close, fillHoles, gaussianBlur5, largestBlob, medianBytes, open, otsu, percentile, pyRound, rgbToLab8 } from './image.js';

/**
 * @typedef {Object} CutOut
 * @property {{width:number,height:number,data:Uint8Array}} mask  255 = product
 * @property {number} area          fraction of the image covered by the product
 * @property {number} borderTouch   fraction of the image border the product touches
 * @property {[number,number,number,number]} bbox  x, y, w, h
 * @property {[number,number,number]} backgroundLab
 * @property {boolean} ok
 */

function borderIndices(w, h, frac = 0.03) {
  const b = Math.max(2, pyRound(Math.min(h, w) * frac));
  const idx = [];
  for (let y = 0; y < b; y++) for (let x = 0; x < w; x++) idx.push(y * w + x);
  for (let y = h - b; y < h; y++) for (let x = 0; x < w; x++) idx.push(y * w + x);
  for (let y = 0; y < h; y++) for (let x = 0; x < b; x++) idx.push(y * w + x);
  for (let y = 0; y < h; y++) for (let x = w - b; x < w; x++) idx.push(y * w + x);
  return idx;
}

/** @returns {CutOut} */
export function cutOut(img) {
  const { width: w, height: h } = img;
  const n = w * h;
  const lab = rgbToLab8(gaussianBlur5(img), n);
  const border = borderIndices(w, h);
  const bg = [0, 1, 2].map((c) => medianBytes(border.map((i) => lab[3 * i + c])));

  // distance from the background colour (lightness counts a quarter, so soft shadows matter less)
  const dist = new Float32Array(n);
  let dmax = 0;
  for (let i = 0; i < n; i++) {
    const dl = lab[3 * i] - bg[0], da = lab[3 * i + 1] - bg[1], db = lab[3 * i + 2] - bg[2];
    const d = Math.sqrt(0.25 * dl * dl + da * da + db * db);
    dist[i] = d;
    if (d > dmax) dmax = d;
  }
  const noise = percentile(border.map((i) => dist[i]), 99) + 4.0;
  const d8 = new Uint8Array(n);
  const s = 255 / Math.max(dmax, 1e-6);
  for (let i = 0; i < n; i++) d8[i] = Math.min(255, Math.max(0, Math.trunc(dist[i] * s)));
  const thr = Math.max(noise, otsu(d8) / 255 * dmax * 0.6);
  let mask = { width: w, height: h, data: new Uint8Array(n) };
  for (let i = 0; i < n; i++) mask.data[i] = dist[i] > thr ? 255 : 0;

  const k = Math.max(3, pyRound(Math.min(h, w) * 0.006) | 1);
  mask = open(mask, k);
  mask = close(mask, k, 2);

  const blob = largestBlob(mask);
  if (!blob) {
    return { mask: { width: w, height: h, data: new Uint8Array(n) }, area: 0, borderTouch: 0,
             bbox: [0, 0, 0, 0], backgroundLab: bg, ok: false };
  }
  mask = fillHoles(blob);

  let x0 = w, y0 = h, x1 = -1, y1 = -1, count = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      if (!mask.data[y * w + x]) continue;
      count++;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
  }
  let edge = 0;
  for (let x = 0; x < w; x++) edge += (mask.data[x] ? 1 : 0) + (mask.data[(h - 1) * w + x] ? 1 : 0);
  for (let y = 0; y < h; y++) edge += (mask.data[y * w] ? 1 : 0) + (mask.data[y * w + w - 1] ? 1 : 0);
  const area = count / n, borderTouch = edge / (2 * w + 2 * h);
  return { mask, area, borderTouch, bbox: [x0, y0, x1 - x0 + 1, y1 - y0 + 1], backgroundLab: bg,
           ok: area > 0.005 && area < 0.9 && borderTouch < 0.35 };
}
