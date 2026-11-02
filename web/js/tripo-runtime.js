// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// The TripoSR networks in the browser: download once (checked against SHA-256, kept in the browser's
// cache), then run with ONNX Runtime Web on the graphics card (WebGPU), or on the processor when the
// browser has no WebGPU. The model is a community ONNX export of stabilityai/TripoSR (MIT) with the
// DINO ViT-B/16 encoder (Apache-2.0) inside; weights are int8.

export const MODEL_REPO = 'cgb/triposr-onnx-webgpu';
export const MODEL_REVISION = '048725e957f485cc6bc082a9d6a239fcf7d8880a';     // pinned: files never change under us
export const MODEL_PAGE = `https://huggingface.co/${MODEL_REPO}/tree/${MODEL_REVISION}`;
const BASE = `https://huggingface.co/${MODEL_REPO}/resolve/${MODEL_REVISION}/`;
export const MODEL_FILES = [
  { name: 'triplane_q8.onnx', sha256: '7721f5a45e79e02de8c6e909c21fb8e922fd0b594038a8fc1cfefa42c79ad6d5', size: 886_000 },
  { name: 'triplane_q8.onnx.data', sha256: '50bf9b1c1218dc2c7fb6051d0d2cb7a48a1c5f75cc86e67a9d0e09a931298e35', size: 484_000_000 },
  { name: 'decoder.onnx', sha256: '6ff43581f1d2b46aa61764c2729a8d33985b51cb6c8088cf36ffee3fd70355eb', size: 174_000 },
];
export const MODEL_BYTES = MODEL_FILES.reduce((s, f) => s + f.size, 0);
const CACHE_NAME = `bozzetto-triposr-${MODEL_REVISION.slice(0, 7)}`;

export const ORT_VERSION = '1.22.0';
const ORT_DIST = `https://cdn.jsdelivr.net/npm/onnxruntime-web@${ORT_VERSION}/dist/`;
const ORT_ENTRIES = ['ort.webgpu.bundle.min.mjs', 'ort.webgpu.min.mjs', 'ort.all.min.mjs'];

/** True when every model file is already in this browser's cache. */
export async function modelCached() {
  try {
    const cache = await caches.open(CACHE_NAME);
    for (const f of MODEL_FILES) if (!(await cache.match(BASE + f.name))) return false;
    return true;
  } catch { return false; }
}

/** Remove the downloaded model from this browser. */
export async function forgetModel() {
  try { await caches.delete(CACHE_NAME); } catch { /* nothing stored */ }
}

async function sha256(bytes) {
  const d = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(d), (x) => x.toString(16).padStart(2, '0')).join('');
}

async function getFile(file, onBytes) {
  const url = BASE + file.name;
  let cache = null;
  try { cache = await caches.open(CACHE_NAME); } catch { /* no cache storage (private window): download every time */ }
  const hit = cache && await cache.match(url);
  if (hit) { const b = new Uint8Array(await hit.arrayBuffer()); onBytes(b.length); return b; }

  let res;
  try { res = await fetch(url, { mode: 'cors' }); }
  catch (e) { throw Object.assign(new Error(`Couldn’t reach Hugging Face to download the TripoSR model. Check the internet connection. (${e.message})`), { code: 'DOWNLOAD_FAILED' }); }
  if (!res.ok) throw Object.assign(new Error(`Downloading ${file.name} failed (HTTP ${res.status}).`), { code: 'DOWNLOAD_FAILED' });
  const length = Number(res.headers.get('content-length')) || 0;
  const reader = res.body.getReader();
  let bytes;
  if (length) {
    bytes = new Uint8Array(length);
    let at = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes.set(value, at); at += value.length; onBytes(value.length);
    }
    if (at !== length) throw Object.assign(new Error(`The download of ${file.name} was cut short.`), { code: 'DOWNLOAD_FAILED' });
  } else {
    const parts = []; let total = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parts.push(value); total += value.length; onBytes(value.length);
    }
    bytes = new Uint8Array(total);
    let at = 0;
    for (const p of parts) { bytes.set(p, at); at += p.length; }
  }
  const sum = await sha256(bytes);
  if (sum !== file.sha256) {
    throw Object.assign(new Error(`${file.name} didn’t match its published checksum, so it wasn’t used.`), { code: 'DOWNLOAD_FAILED', detail: `expected ${file.sha256}\ngot      ${sum}` });
  }
  if (cache) {
    try { await cache.put(url, new Response(bytes, { headers: { 'content-type': 'application/octet-stream' } })); }
    catch { /* not enough storage: works now, downloads again next time */ }
  }
  return bytes;
}

async function loadOrt() {
  let lastErr;
  for (const entry of ORT_ENTRIES) {
    try {
      const ort = await import(/* @vite-ignore */ ORT_DIST + entry);
      const o = ort.default && ort.default.InferenceSession ? ort.default : ort;
      o.env.wasm.wasmPaths = ORT_DIST;
      o.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 1) : 1;
      return o;
    } catch (e) { lastErr = e; }
  }
  throw Object.assign(new Error('Couldn’t load ONNX Runtime Web, which runs the TripoSR model. Check the internet connection.'),
                      { code: 'DOWNLOAD_FAILED', detail: String(lastErr) });
}

let loaded = null;

/**
 * Download (first time), then start both networks. progress(stage, fraction, message).
 * @returns {Promise<{device:string, triplane:(img:Float32Array)=>Promise<Float32Array>, decode:(f:Float32Array,n:number)=>Promise<{density:Float32Array,color:Float32Array}>}>}
 */
export async function loadTripo(progress = () => {}) {
  if (loaded) return loaded;
  const ort = await loadOrt();
  const cached = await modelCached();
  const stage = cached ? 'Loading the TripoSR model' : 'Downloading the TripoSR model (once)';
  let got = 0, last = 0;
  const onBytes = (n) => {
    got += n;
    const now = Date.now();
    if (now - last > 150) { last = now; progress(stage, Math.min(1, got / MODEL_BYTES), null); }
  };
  progress(stage, 0, cached ? 'Model found in this browser' : `Downloading ${Math.round(MODEL_BYTES / 1e6)} MB from huggingface.co/${MODEL_REPO}`);
  const bytes = [];
  for (const f of MODEL_FILES) bytes.push(await getFile(f, onBytes));

  let gpu = false;
  try { gpu = !!(navigator.gpu && await navigator.gpu.requestAdapter()); } catch { gpu = false; }
  const eps = gpu ? ['webgpu', 'wasm'] : ['wasm'];
  progress('Starting the TripoSR model', null, gpu ? 'Running on the graphics card (WebGPU)' : 'No WebGPU in this browser: running on the processor, which is slower');
  let triplaneSession, decoderSession;
  try {
    triplaneSession = await ort.InferenceSession.create(bytes[0], {
      executionProviders: eps, graphOptimizationLevel: 'all',
      externalData: [{ path: MODEL_FILES[1].name, data: bytes[1] }],
    });
    decoderSession = await ort.InferenceSession.create(bytes[2], { executionProviders: eps });
  } catch (e) {
    throw Object.assign(new Error('The TripoSR model couldn’t start in this browser. It needs about 1.5 GB of free memory; close other tabs or try Chrome or Edge.'),
                        { code: 'ENGINE_CRASHED', detail: String(e && e.stack || e) });
  }
  bytes.length = 0;     // let the downloaded copies go

  const outputs = decoderSession.outputNames;
  const densityName = outputs.find((n) => /dens/i.test(n)) || outputs[0];
  const colorName = outputs.find((n) => /col|rgb/i.test(n)) || outputs[1];
  const read = async (t) => (t.location && t.location !== 'cpu' ? await t.getData() : t.data);

  loaded = {
    device: gpu ? 'WebGPU' : 'CPU',
    async triplane(image) {
      const feeds = { [triplaneSession.inputNames[0]]: new ort.Tensor('float32', image, [1, 3, 512, 512]) };
      const out = await triplaneSession.run(feeds);
      return Float32Array.from(await read(out[triplaneSession.outputNames[0]]));
    },
    async decode(features, n) {
      const feeds = { [decoderSession.inputNames[0]]: new ort.Tensor('float32', features, [n, 120]) };
      const out = await decoderSession.run(feeds);
      return { density: await read(out[densityName]), color: await read(out[colorName]) };
    },
  };
  return loaded;
}
