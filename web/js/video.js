// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Frames from a video, like the desktop app: evenly spaced points in time, and around each point
// the sharpest of three nearby frames. Runs on the page (decoding video needs a <video> element).

import { sharpness } from './core/image.js';
import { ScanError } from './core/errors.js';

function once(el, event) {
  return new Promise((resolve, reject) => {
    const ok = () => { el.removeEventListener('error', bad); resolve(); };
    const bad = () => { el.removeEventListener(event, ok); reject(new Error(`video ${event} failed`)); };
    el.addEventListener(event, ok, { once: true });
    el.addEventListener('error', bad, { once: true });
  });
}

/**
 * @param {File} file
 * @returns {Promise<Array<{name:string,width:number,height:number,data:Uint8ClampedArray,originalWidth:number}>>}
 */
export async function extractFrames(file, { count = 40, candidates = 3, maxWidth = 1200, progress = () => {}, cancelled = () => false } = {}) {
  const url = URL.createObjectURL(file);
  const video = document.createElement('video');
  video.muted = true; video.playsInline = true; video.preload = 'auto';
  video.src = url;
  try {
    try { await once(video, 'loadeddata'); }
    catch { throw new ScanError('NO_INPUT', `This browser can’t play ${file.name}. Try an MP4 (H.264) video, or photos.`); }
    const duration = video.duration;
    if (!isFinite(duration) || duration < 0.5) {
      throw new ScanError('NO_INPUT', 'The video is too short. Film a slow 15–30 s circle around the object.');
    }
    const s = Math.min(1, maxWidth / video.videoWidth);
    const w = Math.round(video.videoWidth * s), h = Math.round(video.videoHeight * s);
    const canvas = document.createElement('canvas');
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const frames = [];
    const slot = duration / count;
    for (let i = 0; i < count; i++) {
      if (cancelled()) break;
      let best = null, bestS = -1;
      for (let k = 0; k < candidates; k++) {
        video.currentTime = Math.min(duration - 0.01, slot * (i + (k + 0.5) / candidates));
        await once(video, 'seeked');
        ctx.drawImage(video, 0, 0, w, h);
        const id = ctx.getImageData(0, 0, w, h);
        const sh = sharpness(id);
        if (sh > bestS) { best = id; bestS = sh; }
      }
      frames.push({ name: `frame_${String(i + 1).padStart(4, '0')}`, width: w, height: h, data: best.data, originalWidth: video.videoWidth });
      progress((i + 1) / count);
    }
    return frames;
  } finally {
    video.removeAttribute('src');
    video.load();
    URL.revokeObjectURL(url);
  }
}
