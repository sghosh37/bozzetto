// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Photo checks before carving: exact copies, EXIF focal length and the turntable score.
// Port of the matching parts of bozzetto/core/inputs.py.

import { cutOut } from './masks.js';
import { resizeArea } from './image.js';

export const PHOTO_EXTS = ['.jpg', '.jpeg', '.png', '.heic', '.heif', '.tif', '.tiff', '.webp', '.bmp'];
export const VIDEO_EXTS = ['.mov', '.mp4', '.m4v', '.avi', '.mkv', '.webm'];

const ext = (name) => { const i = name.lastIndexOf('.'); return i < 0 ? '' : name.slice(i).toLowerCase(); };
export const isPhotoName = (name) => PHOTO_EXTS.includes(ext(name)) && !name.startsWith('.');
export const isVideoName = (name) => VIDEO_EXTS.includes(ext(name));

/** Sort by file name the way Python's sorted() does (by code point). */
export function byName(a, b) { return a.name < b.name ? -1 : a.name > b.name ? 1 : 0; }

async function sha256(buffer) {
  const d = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(d), (x) => x.toString(16).padStart(2, '0')).join('');
}

/** Split [{name, buffer}] into unique files and [copy, original] name pairs, by exact content. */
export async function findDuplicates(files) {
  const seen = new Map(), unique = [], dups = [];
  for (const f of files) {
    const key = await sha256(f.buffer);
    if (seen.has(key)) dups.push([f.name, seen.get(key)]);
    else { seen.set(key, f.name); unique.push(f); }
  }
  return { unique, dups };
}

/**
 * Focal length from a JPEG's EXIF: { focalMm, is35mm }. 35 mm equivalent (tag 0xA405) is preferred,
 * then the actual focal length (0x920A). Returns { focalMm: null } when absent.
 */
export function exifFocal(buffer) {
  const none = { focalMm: null, is35mm: false };
  try {
    const dv = new DataView(buffer);
    if (dv.getUint16(0) !== 0xFFD8) return none;
    let off = 2;
    while (off + 4 < dv.byteLength) {
      const marker = dv.getUint16(off);
      const len = dv.getUint16(off + 2);
      if (marker === 0xFFE1 && dv.getUint32(off + 4) === 0x45786966) {   // "Exif"
        return readTiff(dv, off + 10) ?? none;
      }
      if ((marker & 0xFF00) !== 0xFF00 || marker === 0xFFDA) break;
      off += 2 + len;
    }
  } catch { /* unreadable EXIF: no focal length */ }
  return none;
}

function readTiff(dv, t) {
  const le = dv.getUint16(t) === 0x4949;
  const u16 = (o) => dv.getUint16(t + o, le), u32 = (o) => dv.getUint32(t + o, le);
  const entries = (ifd) => {
    const n = u16(ifd), out = new Map();
    for (let i = 0; i < n; i++) {
      const e = ifd + 2 + 12 * i;
      out.set(u16(e), { type: u16(e + 2), count: u32(e + 4), at: e + 8 });
    }
    return out;
  };
  const ifd0 = entries(u32(4));
  const exifPtr = ifd0.get(0x8769);
  if (!exifPtr) return null;
  const sub = entries(u32(exifPtr.at));
  const f35 = sub.get(0xA405);
  if (f35) {
    const v = f35.type === 3 ? u16(f35.at) : u32(f35.at);
    if (v) return { focalMm: v, is35mm: true };
  }
  const f = sub.get(0x920A);
  if (f && f.type === 5) {
    const o = u32(f.at), num = u32(o), den = u32(o + 4);
    if (num && den) return { focalMm: num / den, is35mm: false };
  }
  return null;
}

const std = (a) => { const m = a.reduce((s, x) => s + x, 0) / a.length; return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length); };
const clip01 = (x) => Math.min(1, Math.max(0, x));

/** 0..1: same size, same backdrop colour, outline centred similarly, similar outline height. */
export function turntableScore(images, sample = 12) {
  if (images.length < 3) return 0;
  const m = Math.min(sample, images.length);
  const picks = [];
  for (let i = 0; i < m; i++) picks.push(images[Math.trunc(m === 1 ? 0 : i * (images.length - 1) / (m - 1))]);
  const sizes = new Set(), bgs = [], cxs = [], heights = [];
  for (const full of picks) {
    sizes.add(`${full.width}x${full.height}`);
    const img = resizeArea(full, 400);
    const co = cutOut(img);
    if (!co.ok) return 0;
    const [x, , w, h] = co.bbox;
    bgs.push(co.backgroundLab);
    cxs.push((x + w / 2) / img.width);
    heights.push(h / img.height);
  }
  const sSize = sizes.size === 1 ? 1 : 0;
  const bgSpread = Math.max(...[0, 1, 2].map((c) => std(bgs.map((b) => b[c]))));
  const sBg = clip01(1 - bgSpread / 12);
  const sCx = clip01(1 - std(cxs) / 0.08);
  const meanH = heights.reduce((s, x) => s + x, 0) / heights.length;
  const sH = clip01(1 - std(heights) / Math.max(meanH, 1e-6) / 0.15);
  return Math.round(1000 * (0.25 * sSize + 0.25 * sBg + 0.25 * sCx + 0.25 * sH)) / 1000;
}
