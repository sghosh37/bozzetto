// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// TripoSR in the browser: everything around the neural network. Port of bozzetto/engines/triposr.py
// and of the vendored TripoSR code it uses (MIT, Tripo AI & Stability AI):
//   photo choice and preparation  ->  triplane (network 1)  ->  density on a grid (network 2,
//   fed by bilinear samples of the three planes)  ->  marching cubes at density 25  ->  Y up.
// The two networks are passed in, so this file runs in a Web Worker and in Node tests alike.

import { cutOut } from './masks.js';
import { resizeArea, sharpness } from './image.js';
import { isosurface } from './volume.js';
import { ScanError, Cancelled } from './errors.js';

export const IMAGE_SIZE = 512;
export const FG_RATIO = 0.85;
export const RADIUS = 0.87;            // TripoSR renderer.radius
export const THRESHOLD = 25.0;         // TripoSR extract_mesh threshold on activated density
export const PLANES = 3, CHANNELS = 40, PLANE_RES = 64;
export const FEATURES = PLANES * CHANNELS;   // 120

/** Sharpest photo with a clean outline (checks up to 12 evenly spaced photos). */
export function bestPhoto(images) {
  if (images.length === 1) return 0;
  const m = Math.min(12, images.length);
  let best = -1, bestKey = null;
  for (let t = 0; t < m; t++) {
    const i = Math.trunc(m === 1 ? 0 : t * (images.length - 1) / (m - 1));
    const small = resizeArea(images[i], 800);
    const key = [cutOut(small).ok ? 1 : 0, sharpness(small)];
    if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) { best = i; bestKey = key; }
  }
  return best;
}

/**
 * Cut the product out and centre it on a square mid-grey canvas filling 85 %, 512 px: TripoSR's input.
 * @returns {Float32Array} NCHW [1, 3, 512, 512], RGB 0..1
 */
export function prepareImage(img) {
  const co = cutOut(img);
  if (!co.ok) {
    throw new ScanError('NO_OUTLINE', `Couldn’t separate the product from the background in ${img.name || 'the photo'}. ` +
      'Use a plain backdrop that contrasts with the product.');
  }
  const { width: W } = img;
  const [x, y, w, h] = co.bbox;
  // soften the mask edge: cv2.GaussianBlur(mask, (3, 3), 0) = [1 2 1] / 4 each way
  const H = img.height, m = co.mask.data;
  const at = (xx, yy) => {
    xx = xx < 0 ? -xx : xx >= W ? 2 * W - 2 - xx : xx;
    yy = yy < 0 ? -yy : yy >= H ? 2 * H - 2 - yy : yy;
    return m[yy * W + xx];
  };
  const side = Math.ceil(Math.max(w, h) / FG_RATIO);
  const oy = Math.floor((side - h) / 2), ox = Math.floor((side - w) / 2);
  const canvas = new Float32Array(side * side * 3).fill(0.5);
  const k = [1, 2, 1];
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      const sx = x + c, sy = y + r;
      let a = 0;
      for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) a += k[dy + 1] * k[dx + 1] * at(sx + dx, sy + dy);
      a = Math.round(a / 16) / 255;                    // OpenCV keeps the blurred mask as bytes
      const p = (sy * W + sx) * 4, q = ((oy + r) * side + ox + c) * 3;
      for (let ch = 0; ch < 3; ch++) canvas[q + ch] = (img.data[p + ch] / 255) * a + 0.5 * (1 - a);
    }
  }
  const small = resizeFloat3(canvas, side, IMAGE_SIZE);
  const out = new Float32Array(3 * IMAGE_SIZE * IMAGE_SIZE);
  const n = IMAGE_SIZE * IMAGE_SIZE;
  for (let i = 0; i < n; i++) { out[i] = small[3 * i]; out[n + i] = small[3 * i + 1]; out[2 * n + i] = small[3 * i + 2]; }
  return out;
}

/** Area-average resize of a square float RGB image (side -> size). */
function resizeFloat3(src, side, size) {
  if (side === size) return src;
  const out = new Float32Array(size * size * 3);
  if (side < size) {
    // OpenCV's INTER_AREA enlarges with plain bilinear interpolation
    const sc = side / size;
    for (let oy = 0; oy < size; oy++) {
      let fy = (oy + 0.5) * sc - 0.5; if (fy < 0) fy = 0;
      const y0 = Math.min(side - 1, Math.floor(fy)), y1 = Math.min(side - 1, y0 + 1), ty = fy - y0;
      for (let ox = 0; ox < size; ox++) {
        let fx = (ox + 0.5) * sc - 0.5; if (fx < 0) fx = 0;
        const x0 = Math.min(side - 1, Math.floor(fx)), x1 = Math.min(side - 1, x0 + 1), tx = fx - x0;
        for (let ch = 0; ch < 3; ch++) {
          const a = src[(y0 * side + x0) * 3 + ch], b = src[(y0 * side + x1) * 3 + ch];
          const c = src[(y1 * side + x0) * 3 + ch], d = src[(y1 * side + x1) * 3 + ch];
          out[(oy * size + ox) * 3 + ch] = (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty;
        }
      }
    }
    return out;
  }
  const s = side / size;
  for (let oy = 0; oy < size; oy++) {
    const y0 = oy * s, y1 = y0 + s;
    for (let ox = 0; ox < size; ox++) {
      const x0 = ox * s, x1 = x0 + s;
      let r = 0, g = 0, b = 0, wsum = 0;
      for (let y = Math.floor(y0); y < Math.min(side, Math.ceil(y1)); y++) {
        const wy = Math.min(y + 1, y1) - Math.max(y, y0);
        for (let x = Math.floor(x0); x < Math.min(side, Math.ceil(x1)); x++) {
          const ww = wy * (Math.min(x + 1, x1) - Math.max(x, x0));
          const p = (y * side + x) * 3;
          r += ww * src[p]; g += ww * src[p + 1]; b += ww * src[p + 2]; wsum += ww;
        }
      }
      const q = (oy * size + ox) * 3;
      out[q] = r / wsum; out[q + 1] = g / wsum; out[q + 2] = b / wsum;
    }
  }
  return out;
}

// ---- sampling the triplane (torch grid_sample, bilinear, align_corners=False, zero padding) ----

/** Two taps and weights along one plane axis for a coordinate in -1..1. */
function taps(u) {
  const f = ((u + 1) * PLANE_RES - 1) / 2;
  const i0 = Math.floor(f), t = f - i0;
  return [i0, 1 - t, i0 + 1, t];
}

/**
 * 40 features of plane p at (a, b): a runs along the plane's width, b along its height.
 * triplane: Float32Array [1, 3, 40, 64, 64].
 */
export function samplePlane(triplane, p, a, b, out, offset) {
  const [x0, wx0, x1, wx1] = taps(a), [y0, wy0, y1, wy1] = taps(b);
  const corners = [[x0, y0, wx0 * wy0], [x1, y0, wx1 * wy0], [x0, y1, wx0 * wy1], [x1, y1, wx1 * wy1]];
  for (let c = 0; c < CHANNELS; c++) out[offset + c] = 0;
  for (const [xx, yy, wgt] of corners) {
    if (xx < 0 || yy < 0 || xx >= PLANE_RES || yy >= PLANE_RES || wgt === 0) continue;
    const base = (p * CHANNELS * PLANE_RES + yy) * PLANE_RES + xx;
    for (let c = 0; c < CHANNELS; c++) out[offset + c] += wgt * triplane[base + c * PLANE_RES * PLANE_RES];
  }
}

/** 120 features at normalised points (xyz in -1..1): planes (x,y), (x,z), (y,z), concatenated. */
export function sampleFeatures(triplane, pts, n) {
  const out = new Float32Array(n * FEATURES);
  for (let i = 0; i < n; i++) {
    const x = pts[3 * i], y = pts[3 * i + 1], z = pts[3 * i + 2];
    samplePlane(triplane, 0, x, y, out, i * FEATURES);
    samplePlane(triplane, 1, x, z, out, i * FEATURES + CHANNELS);
    samplePlane(triplane, 2, y, z, out, i * FEATURES + 2 * CHANNELS);
  }
  return out;
}

/**
 * Density on an R³ grid over -radius..radius (TripoSR's marching-cubes grid). Each plane is sampled
 * once per grid line pair, so a point's features are three copies of precomputed rows.
 * @param {(features: Float32Array, n: number) => Promise<{density: Float32Array}>} decode
 */
export async function densityGrid(triplane, R, decode, { chunk = 65536, progress = () => {}, cancelled = () => false } = {}) {
  const coord = new Float32Array(R);
  for (let i = 0; i < R; i++) coord[i] = -1 + 2 * i / (R - 1);
  const table = (p) => {
    const t = new Float32Array(R * R * CHANNELS);
    for (let i = 0; i < R; i++) for (let j = 0; j < R; j++) samplePlane(triplane, p, coord[i], coord[j], t, (i * R + j) * CHANNELS);
    return t;
  };
  const xy = table(0), xz = table(1), yz = table(2);
  const total = R * R * R;
  const density = new Float32Array(total);
  const feats = new Float32Array(chunk * FEATURES);
  for (let start = 0; start < total; start += chunk) {
    if (cancelled()) throw new Cancelled();
    const n = Math.min(chunk, total - start);
    for (let t = 0; t < n; t++) {
      const g = start + t;
      const k = g % R, r = (g - k) / R, j = r % R, i = (r - j) / R;
      const o = t * FEATURES;
      feats.set(xy.subarray((i * R + j) * CHANNELS, (i * R + j + 1) * CHANNELS), o);
      feats.set(xz.subarray((i * R + k) * CHANNELS, (i * R + k + 1) * CHANNELS), o + CHANNELS);
      feats.set(yz.subarray((j * R + k) * CHANNELS, (j * R + k + 1) * CHANNELS), o + 2 * CHANNELS);
    }
    const res = await decode(n === chunk ? feats : feats.subarray(0, n * FEATURES), n);
    density.set(res.density.subarray(0, n), start);
    progress((start + n) / total);
  }
  return density;
}

/**
 * Whole TripoSR run.
 * @param {Object} job  { images: decoded photos, preset: 'quick'|'accurate' }
 * @param {Object} nets { triplane(image: Float32Array) => Promise<Float32Array>, decode(features, n) => Promise<{density, color}> }
 * @returns {{vertices: Float64Array, faces: Uint32Array, colors: Uint8Array, log: string[]}}
 */
export async function runTripo(job, nets, progress = () => {}, cancelled = () => false) {
  const log = [];
  const pick = bestPhoto(job.images);
  const photo = job.images[pick];
  log.push(`Using ${photo.name}`);
  progress('Preparing the photo', 0.02, `Using ${photo.name}`);
  const image = prepareImage(photo);
  if (cancelled()) throw new Cancelled();

  progress('Reading the shape from the photo', null);
  const triplane = await nets.triplane(image);
  if (triplane.length !== PLANES * CHANNELS * PLANE_RES * PLANE_RES) {
    throw new ScanError('ENGINE_CRASHED', 'The TripoSR model gave an unexpected result.', `triplane length ${triplane.length}`);
  }

  const R = job.resolution || (job.preset === 'accurate' ? 192 : 128);
  const density = await densityGrid(triplane, R, nets.decode, {
    progress: (f) => progress('Measuring the shape', 0.1 + 0.75 * f), cancelled,
  });
  progress('Building the mesh', 0.87, `Marching cubes at ${R}³`);
  const mesh = isosurface(density, [R, R, R], THRESHOLD);
  if (!mesh.faces.length) throw new ScanError('NO_MODEL', 'TripoSR couldn’t find a shape in this photo. Try a clearer photo of the object on a plain backdrop.');

  // grid index -> -1..1 (normalised) for colour lookup; world = normalised × radius
  const v = mesh.vertices, nv = v.length / 3;
  const norm = new Float32Array(v.length);
  for (let i = 0; i < v.length; i++) norm[i] = -1 + 2 * v[i] / (R - 1);
  progress('Colouring the mesh', 0.93);
  const colors = new Uint8Array(nv * 3);
  const chunk = 65536;
  for (let s = 0; s < nv; s += chunk) {
    const n = Math.min(chunk, nv - s);
    const res = await nets.decode(sampleFeatures(triplane, norm.subarray(3 * s, 3 * (s + n)), n), n);
    for (let i = 0; i < 3 * n; i++) colors[3 * s + i] = Math.max(0, Math.min(255, Math.trunc(res.color[i] * 255)));   // as the desktop (astype uint8)
  }
  // TripoSR is Z up; turn to Y up facing the viewer, as on the desktop: (x, y, z) -> (-y, z, -x)
  const out = new Float64Array(v.length);
  for (let i = 0; i < nv; i++) {
    const x = norm[3 * i] * RADIUS, y = norm[3 * i + 1] * RADIUS, z = norm[3 * i + 2] * RADIUS;
    out[3 * i] = -y; out[3 * i + 1] = z; out[3 * i + 2] = -x;
  }
  const msg = `${(mesh.faces.length / 3).toLocaleString('en')} triangles`;
  log.push(`Marching cubes at ${R}³; ${msg}`);
  progress('Building the mesh', 0.98, msg);
  return { vertices: out, faces: mesh.faces, colors, log };
}
