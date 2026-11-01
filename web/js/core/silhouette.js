// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Turntable silhouette engine ("visual hull"). Port of bozzetto/engines/silhouette.py.
// Keeps only the space that lies inside the product's outline in every photo. The camera is fixed,
// tilted down by tiltDeg, and the product turns by equal steps about a vertical axis.
// Scale is arbitrary (distance to the axis = 1); export scales to the real height.

import { cutOut } from './masks.js';
import { morph, pyRound } from './image.js';
import { gaussian3d, isosurface } from './volume.js';
import { ScanError, Cancelled } from './errors.js';

export const WORK_WIDTH = 1200;       // photos are reduced to this width for cut-out and carving
export const DEFAULT_HFOV_DEG = 50;   // used when EXIF has no focal length
export const MIN_PHOTOS = 6;
export const SMOOTH_ITERATIONS = 4;

const rad = (d) => d * Math.PI / 180;

export class Camera {
  constructor(fx, fy, cx, cy, tilt, distance = 1) {
    Object.assign(this, { fx, fy, cx, cy, tilt, distance });
    const s = Math.sin(tilt), c = Math.cos(tilt);
    this.R = [[1, 0, 0], [0, -c, s], [0, -s, -c]];          // rows: right, down, forward
    this.C = [0, distance * s, distance * c];
  }

  /** World height where the camera ray through image row v (centre column) meets the plane x-y. */
  rayYAtAxisPlane(v) {
    const d = [0, (v - this.cy) / this.fy, 1];
    const R = this.R;
    const dw = [0, 1, 2].map((k) => R[0][k] * d[0] + R[1][k] * d[1] + R[2][k] * d[2]);
    const t = Math.abs(dw[2]) > 1e-9 ? -this.C[2] / dw[2] : 0;
    return this.C[1] + t * dw[1];
  }
}

export function focalPx(width, focalMm, is35mm) {
  if (focalMm && is35mm) return focalMm / 36 * width;
  if (focalMm && focalMm > 0) return focalMm / 23.5 * width;   // no sensor size: assume 23.5 mm wide
  return (width / 2) / Math.tan(rad(DEFAULT_HFOV_DEG / 2));
}

/** Remove the wedge the carving leaves under the base. occ is indexed [x][y][z] flat. Returns layers removed. */
export function trimBaseWedge(occ, dims, voxel, tilt) {
  if (tilt <= rad(2)) return 0;
  const [nx, ny, nz] = dims;
  const area = new Float64Array(ny);
  for (let x = 0; x < nx; x++) for (let y = 0; y < ny; y++) {
    const o = (x * ny + y) * nz;
    for (let z = 0; z < nz; z++) area[y] += occ[o + z];
  }
  const filled = [];
  for (let y = 0; y < ny; y++) if (area[y] > 0) filled.push(y);
  if (filled.length < 6) return 0;
  const r = Array.from(area, (a) => Math.sqrt(a / Math.PI) * voxel);
  const wedgeSlope = 1 / Math.tan(tilt);
  const k = 2, lo = filled[0];
  const limit = lo + Math.trunc(filled.length * 0.3);
  let j = lo;
  while (j + k <= limit) {
    const slope = (r[j + k] - r[j]) / (k * voxel);
    if (slope < 0.45 * wedgeSlope) break;
    j++;
  }
  if (j > lo) {
    for (let x = 0; x < nx; x++) for (let y = 0; y < j; y++) occ.fill(0, (x * ny + y) * nz, (x * ny + y + 1) * nz);
  }
  return j - lo;
}

/**
 * Carve a mesh from turntable photos.
 * @param {Object} job
 * @param {Array<{name:string,width:number,height:number,data:Uint8ClampedArray}>} job.images  in turntable order, already at most WORK_WIDTH wide
 * @param {number} job.originalWidth  width of the photos as taken (for the EXIF focal length)
 * @param {?number} job.focalMm
 * @param {boolean} job.focal35mm
 * @param {number} job.tiltDeg
 * @param {boolean} job.clockwise
 * @param {'quick'|'accurate'} job.preset
 * @param {(stage:string, fraction:?number, message?:string)=>void} progress
 * @param {()=>boolean} cancelled
 * @returns {{vertices:Float64Array, faces:Uint32Array, log:string[]}}
 */
export function carve(job, progress = () => {}, cancelled = () => false) {
  const images = job.images;
  const n = images.length;
  const log = [];
  if (n < MIN_PHOTOS) {
    throw new ScanError('TOO_FEW_PHOTOS', `The silhouette engine needs at least ${MIN_PHOTOS} photos all the way round.`);
  }

  // 1-2: cut out
  const masks = [], bad = [];
  for (let i = 0; i < n; i++) {
    if (cancelled()) throw new Cancelled();
    const co = cutOut(images[i]);
    if (!co.ok) bad.push(images[i].name);
    masks.push(co.mask);
    progress('Cutting out the product', 0.4 * (i + 1) / n);
  }
  if (bad.length > Math.floor(n / 4)) {
    throw new ScanError('NO_OUTLINE', `Couldn’t separate the product from the background in ${bad.length} of ${n} photos. ` +
      'Use a plain backdrop that contrasts with the product.', bad.slice(0, 10).join(', '));
  }
  if (bad.length) {
    const msg = `Outline unclear in ${bad.length} photo(s): ${bad.slice(0, 5).join(', ')}`;
    log.push(msg);
    progress('Cutting out the product', null, msg);
  }
  const { width: w, height: h } = masks[0];
  if (masks.some((m) => m.width !== w || m.height !== h)) {
    throw new ScanError('NO_OUTLINE', 'The photos are not all the same size, so they can’t be from one turntable shoot.');
  }

  // 3: camera
  const f = focalPx(w, job.focalMm, job.focal35mm) * (job.originalWidth ? w / job.originalWidth : 1);
  const extents = masks.map((m) => {
    let c0 = w, c1 = -1, r0 = h, r1 = -1;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (!m.data[y * w + x]) continue;
      if (x < c0) c0 = x; if (x > c1) c1 = x; if (y < r0) r0 = y; if (y > r1) r1 = y;
    }
    return c1 < 0 ? null : { c0, c1, r0, r1 };
  }).filter(Boolean);
  if (!extents.length) throw new ScanError('NO_OUTLINE', 'No product outline was found in any photo.');
  const sorted = extents.map((e) => (e.c0 + e.c1) / 2).sort((a, b) => a - b);
  const mid = sorted.length >> 1;
  const uAxis = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  const halfWidth = Math.max(...extents.map((e) => Math.max(uAxis - e.c0, e.c1 - uAxis)));
  const cam = new Camera(f, f, uAxis, h / 2, rad(job.tiltDeg ?? 20));
  const radius = halfWidth / f * cam.distance * 1.25;
  const yTop = cam.rayYAtAxisPlane(Math.min(...extents.map((e) => e.r0)));
  const yBot = cam.rayYAtAxisPlane(Math.max(...extents.map((e) => e.r1)));
  const lo = [-radius, Math.min(yTop, yBot) - 0.35 * radius, -radius];
  const hi = [radius, Math.max(yTop, yBot) + 0.35 * radius, radius];

  // 4: carve
  const res = job.resolution || (job.preset === 'accurate' ? 224 : 160);
  const voxel = Math.max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / res;
  const dims = [0, 1, 2].map((k) => Math.max(Math.ceil((hi[k] - lo[k]) / voxel), 2));
  const [nx, ny, nz] = dims;
  const total = nx * ny * nz;
  const cx = new Float64Array(nx), cy = new Float64Array(ny), cz = new Float64Array(nz);
  for (let i = 0; i < nx; i++) cx[i] = lo[0] + (i + 0.5) * voxel;
  for (let i = 0; i < ny; i++) cy[i] = lo[1] + (i + 0.5) * voxel;
  for (let i = 0; i < nz; i++) cz[i] = lo[2] + (i + 0.5) * voxel;
  let idx = new Uint32Array(total);
  for (let i = 0; i < total; i++) idx[i] = i;
  let count = total;
  const misses = new Uint8Array(total);
  const allowed = Math.floor(n / 36);              // with many photos, tolerate one bad outline
  const step = (job.clockwise ? -1 : 1) * 2 * Math.PI / n;
  const tol = Math.max(1, pyRound(w * 0.002));
  const R = cam.R, C = cam.C;
  for (let i = 0; i < n; i++) {
    if (cancelled()) throw new Cancelled();
    const mm = morph(masks[i], 2 * tol + 1, true).data;
    const a = i * step, ca = Math.cos(a), sa = Math.sin(a);
    let kept = 0;
    for (let t = 0; t < count; t++) {
      const g = idx[t];
      const iz = g % nz, rest = (g - iz) / nz, iy = rest % ny, ix = (rest - iy) / ny;
      const X = cx[ix], Y = cy[iy], Z = cz[iz];
      // turn the object by a about +Y, then into camera coordinates
      const px = ca * X + sa * Z - C[0], py = Y - C[1], pz = -sa * X + ca * Z - C[2];
      const xc = R[0][0] * px + R[0][1] * py + R[0][2] * pz;
      const yc = R[1][0] * px + R[1][1] * py + R[1][2] * pz;
      const zc = R[2][0] * px + R[2][1] * py + R[2][2] * pz;
      const zs = zc > 1e-6 ? zc : 1e-6;
      const ui = Math.round(cam.fx * xc / zs + cam.cx), vi = Math.round(cam.fy * yc / zs + cam.cy);
      const hit = zc > 0 && ui >= 0 && ui < w && vi >= 0 && vi < h && mm[vi * w + ui] > 0;
      if (!hit) misses[g]++;
      if (misses[g] <= allowed) idx[kept++] = g;
    }
    count = kept;
    progress('Carving the shape', 0.4 + 0.45 * (i + 1) / n);
    if (count === 0) break;
  }
  if (count < 50) {
    throw new ScanError('NO_MODEL', 'Nothing was left after carving. The turntable direction, camera tilt or photo order may be wrong.');
  }
  const occ = new Float32Array(total);
  for (let t = 0; t < count; t++) occ[idx[t]] = 1;
  const cut = trimBaseWedge(occ, dims, voxel, cam.tilt);
  if (cut) {
    const msg = `Trimmed ${cut} voxel layers of hidden-underside wedge`;
    log.push(msg);
    progress('Carving the shape', 0.86, msg);
  }

  // 5: mesh (pad by one voxel, soften, then the 0.5 surface)
  progress('Building the mesh', 0.9);
  const pdims = [nx + 2, ny + 2, nz + 2];
  const padded = new Float32Array(pdims[0] * pdims[1] * pdims[2]);
  for (let x = 0; x < nx; x++) for (let y = 0; y < ny; y++) {
    const src = (x * ny + y) * nz, dst = ((x + 1) * pdims[1] + (y + 1)) * pdims[2] + 1;
    padded.set(occ.subarray(src, src + nz), dst);
  }
  const field = gaussian3d(padded, pdims, 0.8);
  const mesh = isosurface(field, pdims, 0.5);
  const v = mesh.vertices;
  for (let i = 0; i < v.length; i += 3) {
    v[i] = v[i] * voxel + lo[0] - voxel;
    v[i + 1] = v[i + 1] * voxel + lo[1] - voxel;
    v[i + 2] = v[i + 2] * voxel + lo[2] - voxel;
  }
  const msg = `Carved ${nx}×${ny}×${nz} voxels, kept ${count.toLocaleString('en')}; ${(mesh.faces.length / 3).toLocaleString('en')} triangles`;
  log.push(msg);
  progress('Building the mesh', 1, msg);
  return { vertices: v, faces: mesh.faces, log };
}
