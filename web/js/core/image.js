// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Image helpers on plain typed arrays, matching what the desktop app does with OpenCV.
// An image is { width, height, data } with RGBA bytes (the layout of the browser's ImageData).
// A mask is { width, height, data: Uint8Array } with 0 or 255 per pixel.

/** Python's round(): halves go to the even neighbour. */
export function pyRound(x) {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

/** OpenCV cvRound (also half to even), fast path for hot loops. */
export function cvRound(x) {
  let r = Math.floor(x + 0.5);
  if (r - x === 0.5 && (r & 1)) r--;
  return r;
}

function reflect101(i, n) {
  if (n === 1) return 0;
  while (i < 0 || i >= n) i = i < 0 ? -i : 2 * n - 2 - i;
  return i;
}

/** cv2.GaussianBlur(img, (5, 5), 0) on the RGB channels: kernel [1 4 6 4 1] / 16, result rounded to bytes. */
export function gaussianBlur5(img) {
  const { width: w, height: h, data } = img;
  const k0 = 1 / 16, k1 = 4 / 16, k2 = 6 / 16;
  const xi = (t) => Int32Array.from({ length: w }, (_, x) => reflect101(x + t, w));
  const yi = (t) => Int32Array.from({ length: h }, (_, y) => reflect101(y + t, h));
  const [xm2, xm1, xp1, xp2] = [xi(-2), xi(-1), xi(1), xi(2)];
  const [ym2, ym1, yp1, yp2] = [yi(-2), yi(-1), yi(1), yi(2)];
  const tmp = new Float32Array(w * h * 3);
  for (let y = 0; y < h; y++) {
    const ro = y * w;
    for (let x = 0; x < w; x++) {
      const a = (ro + xm2[x]) * 4, b = (ro + xm1[x]) * 4, c = (ro + x) * 4, d = (ro + xp1[x]) * 4, e = (ro + xp2[x]) * 4;
      const q = (ro + x) * 3;
      for (let ch = 0; ch < 3; ch++) {
        tmp[q + ch] = k0 * (data[a + ch] + data[e + ch]) + k1 * (data[b + ch] + data[d + ch]) + k2 * data[c + ch];
      }
    }
  }
  const out = new Uint8Array(w * h * 3);
  for (let y = 0; y < h; y++) {
    const a = ym2[y] * w, b = ym1[y] * w, c = y * w, d = yp1[y] * w, e = yp2[y] * w;
    for (let x = 0; x < w; x++) {
      const q = (c + x) * 3;
      for (let ch = 0; ch < 3; ch++) {
        const v = k0 * (tmp[(a + x) * 3 + ch] + tmp[(e + x) * 3 + ch]) + k1 * (tmp[(b + x) * 3 + ch] + tmp[(d + x) * 3 + ch])
                + k2 * tmp[q + ch];
        out[q + ch] = v <= 0 ? 0 : v >= 255 ? 255 : cvRound(v);
      }
    }
  }
  return out;
}

const SRGB = new Float64Array(256);
for (let i = 0; i < 256; i++) {
  const c = i / 255;
  SRGB[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
const labF = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);

/** 8-bit Lab like cv2.COLOR_RGB2LAB: L scaled to 0..255, a and b offset by 128. rgb: 3 bytes per pixel. */
const CACHE_BITS = 16;
const cacheKey = new Int32Array(1 << CACHE_BITS).fill(-1);
const cacheVal = new Int32Array(1 << CACHE_BITS);

export function rgbToLab8(rgb, n) {
  const out = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const key = (rgb[3 * i] << 16) | (rgb[3 * i + 1] << 8) | rgb[3 * i + 2];
    const slot = (Math.imul(key, 2654435761) >>> (32 - CACHE_BITS));
    if (cacheKey[slot] === key) {
      const v = cacheVal[slot];
      out[3 * i] = v >>> 16; out[3 * i + 1] = (v >>> 8) & 255; out[3 * i + 2] = v & 255;
      continue;
    }
    const r = SRGB[rgb[3 * i]], g = SRGB[rgb[3 * i + 1]], b = SRGB[rgb[3 * i + 2]];
    const X = (0.412453 * r + 0.357580 * g + 0.180423 * b) / 0.950456;
    const Y = 0.212671 * r + 0.715160 * g + 0.072169 * b;
    const Z = (0.019334 * r + 0.119193 * g + 0.950227 * b) / 1.088754;
    const fx = labF(X), fy = labF(Y), fz = labF(Z);
    const L = Y > 0.008856 ? 116 * fy - 16 : 903.3 * Y;
    out[3 * i] = Math.min(255, Math.max(0, cvRound(L * 255 / 100)));
    out[3 * i + 1] = Math.min(255, Math.max(0, cvRound(500 * (fx - fy) + 128)));
    out[3 * i + 2] = Math.min(255, Math.max(0, cvRound(200 * (fy - fz) + 128)));
    cacheKey[slot] = key;
    cacheVal[slot] = (out[3 * i] << 16) | (out[3 * i + 1] << 8) | out[3 * i + 2];
  }
  return out;
}

/** numpy-style percentile with linear interpolation. Sorts a copy. */
export function percentile(values, q) {
  const a = Float64Array.from(values).sort();
  if (a.length === 0) return 0;
  const pos = (a.length - 1) * q / 100, lo = Math.floor(pos), hi = Math.ceil(pos);
  return a[lo] + (a[hi] - a[lo]) * (pos - lo);
}

export const median = (values) => percentile(values, 50);

/** numpy median of integer values 0..255, by histogram (exact, no sort). */
export function medianBytes(values) {
  const hist = new Uint32Array(256);
  for (let i = 0; i < values.length; i++) hist[values[i]]++;
  const n = values.length;
  const kth = (k) => { let acc = 0; for (let v = 0; v < 256; v++) { acc += hist[v]; if (acc > k) return v; } return 255; };
  return n % 2 ? kth((n - 1) / 2) : (kth(n / 2 - 1) + kth(n / 2)) / 2;
}

/** cv2.threshold(..., THRESH_OTSU) on bytes: returns the threshold value. */
export function otsu(bytes) {
  const hist = new Float64Array(256);
  for (let i = 0; i < bytes.length; i++) hist[bytes[i]]++;
  const N = bytes.length;
  let mu = 0;
  for (let i = 0; i < 256; i++) mu += i * hist[i];
  mu /= N;
  let q1 = 0, mu1 = 0, maxSigma = 0, maxVal = 0;
  const EPS = 1.1920929e-7;
  for (let i = 0; i < 256; i++) {
    const p = hist[i] / N;
    mu1 *= q1;
    q1 += p;
    const q2 = 1 - q1;
    if (Math.min(q1, q2) < EPS || Math.max(q1, q2) > 1 - EPS) continue;
    mu1 = (mu1 + i * p) / q1;
    const mu2 = (mu - q1 * mu1) / q2;
    const sigma = q1 * q2 * (mu1 - mu2) * (mu1 - mu2);
    if (sigma > maxSigma) { maxSigma = sigma; maxVal = i; }
  }
  return maxVal;
}

/** Half-widths of each row of cv2.getStructuringElement(MORPH_ELLIPSE, (k, k)). */
export function ellipseRows(k) {
  const r = Math.floor(k / 2), c = Math.floor(k / 2);
  const inv = r ? 1 / (r * r) : 0;
  const rows = [];
  for (let i = 0; i < k; i++) {
    const dy = i - r;
    rows.push(Math.abs(dy) <= r ? cvRound(c * Math.sqrt((r * r - dy * dy) * inv)) : -1);
  }
  return rows;   // rows[i] = half-width for offset i - r (-1 = empty row)
}

/** Binary dilation (dilate=true) or erosion with an elliptical kernel; borders like OpenCV's defaults
 * (outside the image counts as "no change"). Each kernel row is a horizontal run, and only the
 * product's bounding box (plus the kernel radius) is processed: everything else stays empty. */
export function morph(m, k, dilate) {
  const { width: w, height: h, data } = m;
  const rows = ellipseRows(k), r = Math.floor(k / 2);
  const res = new Uint8Array(w * h);
  let bx0 = w, bx1 = -1, by0 = h, by1 = -1;
  for (let y = 0; y < h; y++) {
    const o = y * w;
    let first = -1, last = -1;
    for (let x = 0; x < w; x++) if (data[o + x]) { if (first < 0) first = x; last = x; }
    if (first < 0) continue;
    if (first < bx0) bx0 = first; if (last > bx1) bx1 = last;
    if (y < by0) by0 = y; by1 = y;
  }
  if (bx1 < 0) return { width: w, height: h, data: res };
  const X0 = Math.max(0, bx0 - r), X1 = Math.min(w - 1, bx1 + r);
  const Y0 = Math.max(0, by0 - r), Y1 = Math.min(h - 1, by1 + r);
  const ww = X1 - X0 + 1, hh = Y1 - Y0 + 1;
  // output region: the window for dilation, the box itself for erosion
  const ox0 = dilate ? X0 : bx0, ox1 = dilate ? X1 : bx1, oy0 = dilate ? Y0 : by0, oy1 = dilate ? Y1 : by1;

  const runs = new Map();
  const pre = new Int32Array(ww + 1);
  for (const hw of rows) {
    if (hw < 0 || runs.has(hw)) continue;
    const out = new Uint8Array(ww * hh);
    for (let y = Y0; y <= Y1; y++) {
      const o = y * w, ro = (y - Y0) * ww;
      let acc = 0;
      for (let x = X0; x <= X1; x++) { acc += data[o + x] ? 1 : 0; pre[x - X0 + 1] = acc; }
      for (let x = ox0; x <= ox1; x++) {
        const x0 = x - hw < 0 ? 0 : x - hw, x1 = x + hw >= w ? w - 1 : x + hw;       // image clip
        const c0 = x0 < X0 ? X0 : x0, c1 = x1 > X1 ? X1 : x1;                        // window clip (outside = empty)
        const cnt = pre[c1 - X0 + 1] - pre[c0 - X0];
        out[ro + x - X0] = dilate ? (cnt > 0 ? 1 : 0) : (cnt === x1 - x0 + 1 ? 1 : 0);
      }
    }
    runs.set(hw, out);
  }
  const acc = new Uint8Array(ww * hh).fill(dilate ? 0 : 1);
  for (let i = 0; i < rows.length; i++) {
    if (rows[i] < 0) continue;
    const src = runs.get(rows[i]), dy = i - r;
    for (let y = oy0; y <= oy1; y++) {
      const yy = y + dy;
      if (yy < 0 || yy >= h) continue;                 // outside the image: no change
      const o = (y - Y0) * ww;
      if (yy < Y0 || yy > Y1) { if (!dilate) acc.fill(0, o + ox0 - X0, o + ox1 - X0 + 1); continue; }
      const so = (yy - Y0) * ww;
      if (dilate) for (let x = ox0 - X0; x <= ox1 - X0; x++) acc[o + x] |= src[so + x];
      else for (let x = ox0 - X0; x <= ox1 - X0; x++) acc[o + x] &= src[so + x];
    }
  }
  for (let y = oy0; y <= oy1; y++) {
    const o = (y - Y0) * ww, d = y * w;
    for (let x = ox0; x <= ox1; x++) res[d + x] = acc[o + x - X0] ? 255 : 0;
  }
  return { width: w, height: h, data: res };
}

export function open(m, k) { return morph(morph(m, k, false), k, true); }

export function close(m, k, iterations = 1) {
  let r = m;
  for (let i = 0; i < iterations; i++) r = morph(r, k, true);
  for (let i = 0; i < iterations; i++) r = morph(r, k, false);
  return r;
}

/** Keep the largest 8-connected blob. Returns null when the mask is empty. */
export function largestBlob(m) {
  const { width: w, height: h, data } = m;
  const label = new Int32Array(w * h);
  const stack = new Int32Array(w * h);
  let best = 0, bestArea = 0, next = 0;
  for (let start = 0; start < w * h; start++) {
    if (!data[start] || label[start]) continue;
    next++;
    let top = 0, area = 0;
    stack[top++] = start; label[start] = next;
    while (top) {
      const p = stack[--top]; area++;
      const px = p % w, py = (p - px) / w;
      for (let dy = -1; dy <= 1; dy++) {
        const yy = py + dy;
        if (yy < 0 || yy >= h) continue;
        for (let dx = -1; dx <= 1; dx++) {
          const xx = px + dx;
          if (xx < 0 || xx >= w) continue;
          const q = yy * w + xx;
          if (data[q] && !label[q]) { label[q] = next; stack[top++] = q; }
        }
      }
    }
    if (area > bestArea) { bestArea = area; best = next; }
  }
  if (!best) return null;
  const out = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) out[i] = label[i] === best ? 255 : 0;
  return { width: w, height: h, data: out };
}

/** Fill holes: background not 4-connected to the image border becomes product. */
export function fillHoles(m) {
  const { width: w, height: h, data } = m;
  const outside = new Uint8Array(w * h);
  const stack = new Int32Array(w * h);
  let top = 0;
  const push = (q) => { if (!data[q] && !outside[q]) { outside[q] = 1; stack[top++] = q; } };
  for (let x = 0; x < w; x++) { push(x); push((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { push(y * w); push(y * w + w - 1); }
  while (top) {
    const p = stack[--top];
    const px = p % w, py = (p - px) / w;
    if (px > 0) push(p - 1);
    if (px < w - 1) push(p + 1);
    if (py > 0) push(p - w);
    if (py < h - 1) push(p + w);
  }
  const out = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) out[i] = outside[i] ? 0 : 255;
  return { width: w, height: h, data: out };
}

/** Area-average downscale (like cv2.INTER_AREA when shrinking). */
export function resizeArea(img, newW) {
  const { width: w, height: h, data } = img;
  if (newW >= w) return img;
  const newH = pyRound(h * newW / w);
  const sx = w / newW, sy = h / newH;
  const out = new Uint8ClampedArray(newW * newH * 4);
  for (let oy = 0; oy < newH; oy++) {
    const y0 = oy * sy, y1 = y0 + sy;
    for (let ox = 0; ox < newW; ox++) {
      const x0 = ox * sx, x1 = x0 + sx;
      let r = 0, g = 0, b = 0, a = 0, wsum = 0;
      for (let y = Math.floor(y0); y < Math.min(h, Math.ceil(y1)); y++) {
        const wy = Math.min(y + 1, y1) - Math.max(y, y0);
        for (let x = Math.floor(x0); x < Math.min(w, Math.ceil(x1)); x++) {
          const wx = Math.min(x + 1, x1) - Math.max(x, x0);
          const ww = wx * wy, p = (y * w + x) * 4;
          r += ww * data[p]; g += ww * data[p + 1]; b += ww * data[p + 2]; a += ww * data[p + 3]; wsum += ww;
        }
      }
      const q = (oy * newW + ox) * 4;
      out[q] = r / wsum; out[q + 1] = g / wsum; out[q + 2] = b / wsum; out[q + 3] = a / wsum;
    }
  }
  return { width: newW, height: newH, data: out };
}

/** Variance of the Laplacian on a grey copy at most 320 px wide (photo sharpness, like the desktop app). */
export function sharpness(img) {
  const small = resizeArea(img, 320);
  const { width: w, height: h, data } = small;
  const g = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) g[i] = 0.299 * data[4 * i] + 0.587 * data[4 * i + 1] + 0.114 * data[4 * i + 2];
  let sum = 0, sum2 = 0;
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const at = (xx, yy) => g[reflect101(yy, h) * w + reflect101(xx, w)];
      const l = at(x - 1, y) + at(x + 1, y) + at(x, y - 1) + at(x, y + 1) - 4 * g[y * w + x];
      sum += l; sum2 += l * l;
    }
  }
  const n = w * h, mean = sum / n;
  return sum2 / n - mean * mean;
}
