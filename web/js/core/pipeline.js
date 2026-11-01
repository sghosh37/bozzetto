// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Browser pipeline: inspect the photos, carve with the silhouette engine, normalise for export.
// Works in a Web Worker or in Node (the test suite); image decoding is passed in.

import { byName, exifFocal, findDuplicates, isPhotoName, turntableScore } from './inputs.js';
import { carve, MIN_PHOTOS, SMOOTH_ITERATIONS, WORK_WIDTH } from './silhouette.js';
import { normalise } from './export.js';
import { Cancelled, ScanError } from './errors.js';

export const TURNTABLE = 0.7;

/**
 * @param {Object} input
 * @param {Array<{name:string, buffer:ArrayBuffer}>} [input.files]  photos as files
 * @param {Array<{name:string,width:number,height:number,data:Uint8ClampedArray}>} [input.frames]  or decoded video frames
 * @param {(buffer:ArrayBuffer, name:string, maxWidth:number)=>Promise<{image:Object, originalWidth:number}>} [input.decode]
 * @param {{heightMm:?number, tiltDeg:number, clockwise:boolean, preset:'quick'|'accurate'}} input.settings
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
  if (images.length < MIN_PHOTOS) {
    throw new ScanError('TOO_FEW_PHOTOS',
      `${images.length} photo(s)${dups.length ? ` (after ignoring ${dups.length} exact copies)` : ''}. ` +
      `The browser version needs at least ${MIN_PHOTOS} turntable photos all the way round. ` +
      'For one or two photos use the desktop app (TripoSR engine).');
  }

  progress('Checking the photos', null, 'Measuring how turntable-like the photos are');
  const score = turntableScore(images);
  const warnings = [];
  if (dups.length) warnings.push(`${dups.length} exact copies ignored (copies add no new viewpoint).`);
  if (!s.heightMm) warnings.push('Enter the real height in mm for a true-to-size model.');
  if (score <= TURNTABLE) warnings.push('These photos don’t look like a turntable shoot; the shape may be rough.');

  const raw = carve({ images, originalWidth, focalMm: focal.focalMm, focal35mm: focal.is35mm,
                      tiltDeg: s.tiltDeg, clockwise: s.clockwise, preset: s.preset, resolution: s.resolution }, progress, cancelled);
  progress('Saving', 1);
  const model = normalise(raw, s.heightMm, SMOOTH_ITERATIONS);
  return {
    model,
    info: {
      photos: images.length, duplicates: dups, turntableScore: score, focal, warnings, log: raw.log,
      seconds: (Date.now() - started) / 1000, size: [images[0].width, images[0].height],
    },
  };
}
