// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser pipeline: inspect the photos, choose the method, build the shape, normalise for export.
// Methods: the turntable silhouette engine (6+ photos) and TripoSR (one photo, guessed back).
// Works in a Web Worker or in Node (the test suite); image decoding and the TripoSR networks are passed in.

import { byName, exifFocal, findDuplicates, isPhotoName, turntableScore } from './inputs.js';
import { carve, MIN_PHOTOS, SMOOTH_ITERATIONS, WORK_WIDTH } from './silhouette.js';
import { normalise } from './export.js';
import { runTripo } from './tripo.js';
import { Cancelled, ScanError } from './errors.js';

export const TURNTABLE = 0.7;

/** Automatic choice, as the desktop rules give it for the methods the browser has. */
export function chooseMethod(count, requested = 'auto') {
  if (requested === 'silhouette' || requested === 'triposr') return requested;
  return count < MIN_PHOTOS ? 'triposr' : 'silhouette';
}

/**
 * @param {Object} input
 * @param {Array<{name:string, buffer:ArrayBuffer}>} [input.files]  photos as files
 * @param {Array<{name:string,width:number,height:number,data:Uint8ClampedArray}>} [input.frames]  or decoded video frames
 * @param {(buffer:ArrayBuffer, name:string, maxWidth:number)=>Promise<{image:Object, originalWidth:number}>} [input.decode]
 * @param {(progress:Function)=>Promise<{triplane:Function, decode:Function}>} [input.loadTripo]  loads the networks
 * @param {{heightMm:?number, tiltDeg:number, clockwise:boolean, preset:'quick'|'accurate', method:'auto'|'silhouette'|'triposr'}} input.settings
 */
export async function run(input, progress = () => {}, cancelled = () => false) {
  const started = Date.now();
  const s = input.settings;
  let images, originalWidth, focal = { focalMm: null, is35mm: false }, dups = [];

  if (input.frames) {
    images = input.frames;
    originalWidth = images.length ? images[0].originalWidth || images[0].width : 0;
  } else {
    const photos = (input.files || []).filter((f) => isPhotoName(f.name)).sort(byName);
    if (!photos.length) throw new ScanError('NO_INPUT', 'Add JPEG, PNG or WebP photos (or a video).');
    progress('Checking the photos', 0);
    const d = await findDuplicates(photos);
    dups = d.dups;
    focal = exifFocal(d.unique[0].buffer);
    images = [];
    for (let i = 0; i < d.unique.length; i++) {
      if (cancelled()) throw new Cancelled();
      const f = d.unique[i];
      let decoded;
      try { decoded = await input.decode(f.buffer, f.name, WORK_WIDTH); }
      catch (e) {
        throw new ScanError('NO_INPUT', `Couldn’t open ${f.name}. This browser may not read that format (HEIC opens only in Safari); try JPEG.`, String(e));
      }
      if (i === 0) originalWidth = decoded.originalWidth;
      images.push({ name: f.name, ...decoded.image });
      progress('Opening the photos', (i + 1) / d.unique.length);
    }
  }
  const method = chooseMethod(images.length, s.method);
  const warnings = [];
  if (dups.length) warnings.push(`${dups.length} exact copies ignored (copies add no new viewpoint).`);
  if (!s.heightMm) warnings.push('Enter the real height in mm for a true-to-size model.');
  let raw, score = null;

  if (method === 'triposr') {
    if (!input.loadTripo) throw new ScanError('UNSUPPORTED', 'The one-photo method isn’t available here.');
    warnings.push('Built from one photo: the sides the camera didn’t see are guessed.');
    const nets = await input.loadTripo(progress);
    raw = await runTripo({ images, preset: s.preset, resolution: s.resolution }, nets, progress, cancelled);
  } else {
    if (images.length < MIN_PHOTOS) {
      throw new ScanError('TOO_FEW_PHOTOS',
        `${images.length} photo(s)${dups.length ? ` (after ignoring ${dups.length} exact copies)` : ''}. ` +
        `The turntable method needs at least ${MIN_PHOTOS} photos all the way round. ` +
        'For fewer photos, choose the one-photo method.');
    }
    progress('Checking the photos', null, 'Measuring how turntable-like the photos are');
    score = turntableScore(images);
    if (score <= TURNTABLE) warnings.push('These photos don’t look like a turntable shoot; the shape may be rough.');
    raw = carve({ images, originalWidth, focalMm: focal.focalMm, focal35mm: focal.is35mm,
                  tiltDeg: s.tiltDeg, clockwise: s.clockwise, preset: s.preset, resolution: s.resolution }, progress, cancelled);
  }
  progress('Saving', 1);
  const model = normalise(raw, s.heightMm, method === 'silhouette' ? SMOOTH_ITERATIONS : 0);
  return {
    model,
    method,
    info: {
      method, photos: images.length, duplicates: dups, turntableScore: score, focal, warnings, log: raw.log,
      seconds: (Date.now() - started) / 1000, size: [images[0].width, images[0].height],
    },
  };
}
