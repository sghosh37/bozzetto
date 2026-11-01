// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The browser app page: collect photos or a video, run the scan in a worker, show and download it.

import { MeshViewer } from './viewer.js';
import { extractFrames } from './video.js';
import { byName, isPhotoName, isVideoName } from './core/inputs.js';
import { MIN_PHOTOS } from './core/silhouette.js';

const $ = (id) => document.getElementById(id);
const store = {
  get(k, d) { try { const v = localStorage.getItem('bozzetto.' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('bozzetto.' + k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

// ---- theme ----
(() => {
  const btn = $('themeToggle');
  const saved = store.get('theme', null);
  if (saved) document.documentElement.dataset.theme = saved;
  btn.addEventListener('click', () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.dataset.theme = dark ? 'light' : 'dark';
    store.set('theme', document.documentElement.dataset.theme);
    viewer?.draw();
  });
})();

// ---- state ----
let input = null;        // { kind: 'photos', files: File[], name } | { kind: 'video', file: File, name }
let worker = null, running = false, cancelledFlag = false;
let urls = [];
let viewer = null;
try { viewer = new MeshViewer($('canvas')); }
catch (e) { $('empty').querySelector('div').textContent = 'This browser can’t show 3D (WebGL is off). You can still build and download the model.'; }

// remembered settings
$('tilt').value = store.get('tilt', 20);
document.querySelector(`input[name=dir][value=${store.get('clockwise', false) ? 'clock' : 'anti'}]`).checked = true;
document.querySelector(`input[name=preset][value=${store.get('preset', 'quick')}]`).checked = true;
$('frames').value = store.get('frames', 40);

function settings() {
  const h = parseFloat($('height').value);
  const tilt = parseFloat($('tilt').value);
  return {
    heightMm: h > 0 ? h : null,
    tiltDeg: isFinite(tilt) ? Math.min(60, Math.max(0, tilt)) : 20,
    clockwise: document.querySelector('input[name=dir]:checked').value === 'clock',
    preset: document.querySelector('input[name=preset]:checked').value,
  };
}
function remember() {
  const s = settings();
  store.set('tilt', s.tiltDeg); store.set('clockwise', s.clockwise); store.set('preset', s.preset);
  store.set('frames', parseInt($('frames').value, 10) || 40);
}

// ---- messages ----
function clearMessages() { $('messages').replaceChildren(); }
function message(kind, title, lines = [], detail = '') {
  const box = document.createElement('div');
  box.className = `msg ${kind}`;
  box.setAttribute('role', kind === 'bad' ? 'alert' : 'status');
  const b = document.createElement('b'); b.textContent = title; box.append(b);
  if (lines.length) {
    const ul = document.createElement('ul');
    for (const l of lines) { const li = document.createElement('li'); li.textContent = l; ul.append(li); }
    box.append(ul);
  }
  if (detail) {
    const d = document.createElement('details');
    const s = document.createElement('summary'); s.textContent = 'Details';
    const pre = document.createElement('pre'); pre.textContent = detail;
    d.append(s, pre); box.append(d);
  }
  $('messages').append(box);
}

// ---- choosing input ----
function folderName(files) {
  const p = files[0]?.webkitRelativePath;
  return p && p.includes('/') ? p.split('/')[0] : null;
}
const stem = (n) => n.replace(/\.[^.]+$/, '');
const safeName = (n) => (n || 'model').replace(/[^\w.-]+/g, '-').replace(/^-+|-+$/g, '') || 'model';

function setInput(fileList) {
  const files = [...fileList];
  clearMessages();
  const video = files.find((f) => isVideoName(f.name) || f.type.startsWith('video/'));
  const photos = files.filter((f) => isPhotoName(f.name)).sort(byName);
  if (video && !photos.length) input = { kind: 'video', file: video, name: safeName(stem(video.name)) };
  else if (photos.length) input = { kind: 'photos', files: photos, name: safeName(folderName(files) || 'bozzetto-model') };
  else {
    input = null;
    message('bad', 'No photos or video found there.', ['Use JPEG, PNG or WebP photos, or an MP4 or MOV video.']);
  }
  showSummary();
}

function showSummary() {
  urls.forEach(URL.revokeObjectURL); urls = [];
  const box = $('summary');
  $('framesField').hidden = input?.kind !== 'video';
  $('build').disabled = !input || running;
  if (!input) { box.hidden = true; return; }
  box.hidden = false;
  box.replaceChildren();
  const count = document.createElement('div');
  count.className = 'count';
  if (input.kind === 'video') {
    count.textContent = `Video: ${input.file.name}`;
    box.append(count);
    const p = document.createElement('div'); p.className = 'hint';
    p.textContent = 'The sharpest frames around evenly spaced moments are used.';
    box.append(p);
    return;
  }
  const n = input.files.length;
  count.textContent = `${n} photo${n === 1 ? '' : 's'}`;
  box.append(count);
  if (n < MIN_PHOTOS) {
    message('warn', `The browser version needs at least ${MIN_PHOTOS} photos all the way round.`,
            ['For one or two photos, use the desktop app: its TripoSR engine guesses the hidden sides.']);
  }
  const thumbs = document.createElement('div');
  thumbs.className = 'thumbs';
  for (const f of input.files.slice(0, 24)) {
    const img = document.createElement('img');
    const u = URL.createObjectURL(f); urls.push(u);
    img.src = u; img.alt = f.name; img.loading = 'lazy'; img.decoding = 'async';
    thumbs.append(img);
  }
  box.append(thumbs);
}

for (const id of ['pickPhotos', 'pickFolder', 'pickVideo']) {
  $(id).addEventListener('change', (e) => { if (e.target.files.length) setInput(e.target.files); e.target.value = ''; });
}
const drop = $('drop');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', async (e) => {
  e.preventDefault(); drop.classList.remove('over');
  const items = [...(e.dataTransfer.items || [])];
  const entries = items.map((i) => i.webkitGetAsEntry?.()).filter(Boolean);
  if (entries.some((en) => en.isDirectory)) {
    const files = [];
    const walk = (entry) => new Promise((resolve) => {
      if (entry.isFile) entry.file((f) => { files.push(f); resolve(); }, () => resolve());
      else {
        const reader = entry.createReader(), all = [];
        const more = () => reader.readEntries(async (batch) => {
          if (!batch.length) { for (const c of all) await walk(c); resolve(); }
          else { all.push(...batch); more(); }
        }, () => resolve());
        more();
      }
    });
    for (const en of entries) await walk(en);
    const dir = entries.find((en) => en.isDirectory);
    setInput(files);
    if (input && dir && input.kind === 'photos') input.name = safeName(dir.name);
  } else if (e.dataTransfer.files.length) setInput(e.dataTransfer.files);
});
// a drop anywhere else should not open the photo in the tab
window.addEventListener('dragover', (e) => e.preventDefault());
window.addEventListener('drop', (e) => e.preventDefault());

// ---- running ----
function setRunning(on) {
  running = on;
  $('build').disabled = on || !input;
  $('cancel').hidden = !on;
  $('progress').hidden = false;
  for (const el of document.querySelectorAll('.panel input')) el.disabled = on;
}
function showProgress(stage, fraction, msg) {
  if (stage) $('stage').textContent = stage + (fraction != null && fraction < 1 ? ` (${Math.round(fraction * 100)} %)` : '');
  const bar = $('bar');
  if (fraction == null) bar.classList.add('busy');
  else { bar.classList.remove('busy'); bar.firstElementChild.style.width = `${Math.round(fraction * 100)}%`; }
  if (msg) { const li = document.createElement('li'); li.textContent = msg; $('log').append(li); }
}

function stopWorker() { if (worker) { worker.terminate(); worker = null; } }

async function build() {
  if (!input || running) return;
  remember();
  clearMessages();
  $('log').replaceChildren();
  $('result').hidden = true;
  cancelledFlag = false;
  setRunning(true);
  const s = settings();
  const name = input.name;
  try {
    const msg = { type: 'run', settings: s, name };
    const transfer = [];
    if (input.kind === 'video') {
      showProgress('Reading the video', 0);
      const frames = await extractFrames(input.file, {
        count: Math.min(120, Math.max(6, parseInt($('frames').value, 10) || 40)),
        progress: (f) => showProgress('Reading the video', f), cancelled: () => cancelledFlag,
      });
      if (cancelledFlag) return;
      msg.frames = frames;
      transfer.push(...frames.map((f) => f.data.buffer));
    } else {
      showProgress('Reading the photos', null);
      msg.files = await Promise.all(input.files.map(async (f) => ({ name: f.name, buffer: await f.arrayBuffer() })));
      transfer.push(...msg.files.map((f) => f.buffer));
    }
    if (cancelledFlag) return;
    stopWorker();
    worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
    const result = await new Promise((resolve, reject) => {
      worker.onmessage = (e) => {
        const m = e.data;
        if (m.type === 'progress') showProgress(m.stage, m.fraction, m.message);
        else if (m.type === 'done') resolve(m);
        else if (m.type === 'failed') reject(m);
      };
      worker.onerror = (e) => reject({ message: 'The scan stopped unexpectedly.', detail: e.message || '' });
      worker.postMessage(msg, transfer);
    });
    showResult(result, name);
  } catch (err) {
    if (cancelledFlag) return;
    const m = err.userMessage || err.message || String(err);
    const lines = [];
    if (err.code === 'NO_MODEL') lines.push('Check the turntable direction and the camera tilt, and that the photos are in turning order.');
    if (err.code === 'NO_OUTLINE') lines.push('Shoot against a plain backdrop whose colour differs from the product.');
    message('bad', m, lines, err.detail || '');
    $('stage').textContent = 'Stopped.';
  } finally {
    stopWorker();
    setRunning(false);
    if (cancelledFlag) { $('stage').textContent = 'Cancelled.'; $('bar').classList.remove('busy'); }
  }
}

function showResult(r, name) {
  showProgress('Done', 1);
  $('stage').textContent = `Done: ${r.info.photos} ${input?.kind === 'video' ? 'frames' : 'photos'} used.`;
  if (r.info.warnings.length) message('warn', 'Worth knowing', r.info.warnings);
  if (viewer) { viewer.setMesh(r.vertices, r.normals, r.faces); $('empty').hidden = true; $('viewhelp').hidden = false; }
  else $('empty').hidden = true;
  const [w, h, d] = r.sizeMm;
  $('rSize').textContent = `${w.toFixed(1)} × ${h.toFixed(1)} × ${d.toFixed(1)} mm${r.scaledToHeight ? '' : ' (no height given)'}`;
  $('rTris').textContent = (r.faces.length / 3).toLocaleString();
  $('rTime').textContent = `${r.info.seconds.toFixed(1)} s`;
  for (const a of ['dlObj', 'dlGlb']) { const old = $(a).href; if (old) URL.revokeObjectURL(old); }
  $('dlObj').href = URL.createObjectURL(new Blob([r.obj], { type: 'model/obj' }));
  $('dlObj').download = `${name}.obj`;
  $('dlGlb').href = URL.createObjectURL(new Blob([r.glb], { type: 'model/gltf-binary' }));
  $('dlGlb').download = `${name}.glb`;
  $('result').hidden = false;
  if (matchMedia('(max-width: 860px)').matches) $('canvas').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('build').addEventListener('click', build);
$('cancel').addEventListener('click', () => { cancelledFlag = true; stopWorker(); setRunning(false); $('stage').textContent = 'Cancelled.'; $('bar').classList.remove('busy'); });

if (!window.Worker || !window.OffscreenCanvas || !window.createImageBitmap) {
  message('bad', 'This browser is too old for Bozzetto.', ['Use a current Chrome, Edge, Firefox or Safari (16.4 or newer).']);
  $('build').disabled = true;
}
