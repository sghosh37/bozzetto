// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Normalise a mesh and write it: millimetres, Y up, base on y = 0, centred on x/z.
// Port of bozzetto/core/export.py (no textures or vertex colours: the silhouette engine has none).

import { largestComponent, orientOutward, removeDegenerate, taubin, vertexNormals } from './meshops.js';
import { ScanError } from './errors.js';

export const DEFAULT_HEIGHT_MM = 100;

/**
 * @param {{vertices:Float64Array, faces:Uint32Array, colors?:Uint8Array}} mesh  Y up, arbitrary units
 * @param {?number} heightMm
 * @returns {{vertices:Float32Array, faces:Uint32Array, normals:Float32Array, colors:?Uint8Array, sizeMm:number[], scaledToHeight:boolean}}
 */
export function normalise(mesh, heightMm, smooth = 0) {
  if (!mesh.vertices.length || !mesh.faces.length) throw new ScanError('NO_MODEL', 'The engine produced an empty mesh.');
  let f = removeDegenerate(mesh.vertices, mesh.faces, 0);
  const lc = largestComponent(mesh.vertices, f, mesh.colors || null);
  let v = lc.vertices;
  f = orientOutward(v, lc.faces);
  if (smooth) v = taubin(v, f, smooth);

  let minY = Infinity, maxY = -Infinity, minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
  for (let i = 0; i < v.length; i += 3) {
    minX = Math.min(minX, v[i]); maxX = Math.max(maxX, v[i]);
    minY = Math.min(minY, v[i + 1]); maxY = Math.max(maxY, v[i + 1]);
    minZ = Math.min(minZ, v[i + 2]); maxZ = Math.max(maxZ, v[i + 2]);
  }
  const height = maxY - minY;
  if (!(height > 0)) throw new ScanError('NO_MODEL', 'The engine produced a flat mesh.');
  const scaled = !!(heightMm && heightMm > 0);
  const scale = scaled ? heightMm / height : DEFAULT_HEIGHT_MM / height;
  const c = [(maxX + minX) / 2, minY, (maxZ + minZ) / 2];
  const out = new Float32Array(v.length);
  for (let i = 0; i < v.length; i += 3) {
    out[i] = (v[i] - c[0]) * scale; out[i + 1] = (v[i + 1] - c[1]) * scale; out[i + 2] = (v[i + 2] - c[2]) * scale;
  }
  const sizeMm = [(maxX - minX) * scale, height * scale, (maxZ - minZ) * scale];
  return { vertices: out, faces: f, normals: vertexNormals(out, f), colors: lc.colors, sizeMm, scaledToHeight: scaled };
}

/** OBJ text in the desktop app's layout (positions, normals, faces with normal indices). */
export function objText(m, name, engineId = 'silhouette') {  // vertex colours, when present, as `v x y z r g b`
  const { vertices: v, faces: f, normals: n, colors: col, sizeMm, scaledToHeight } = m;
  const note = scaledToHeight ? 'scaled to the real height you entered'
                              : `no real height given: scaled to ${DEFAULT_HEIGHT_MM} mm high`;
  const lines = [
    '# Bozzetto export', `# engine: ${engineId} (browser)`, `# units: mm (1 unit = 1 mm), ${note}`,
    `# size (W x H x D): ${sizeMm.map((x) => x.toFixed(2)).join(' x ')} mm`,
    `# vertices: ${v.length / 3}, triangles: ${f.length / 3}`, '# Y is up; the base of the object sits at y = 0',
    `o ${name}`,
  ];
  for (let i = 0; i < v.length; i += 3) {
    let line = `v ${v[i].toFixed(3)} ${v[i + 1].toFixed(3)} ${v[i + 2].toFixed(3)}`;
    if (col) line += ` ${(col[i] / 255).toFixed(4)} ${(col[i + 1] / 255).toFixed(4)} ${(col[i + 2] / 255).toFixed(4)}`;
    lines.push(line);
  }
  for (let i = 0; i < n.length; i += 3) lines.push(`vn ${n[i].toFixed(4)} ${n[i + 1].toFixed(4)} ${n[i + 2].toFixed(4)}`);
  for (let i = 0; i < f.length; i += 3) {
    const a = f[i] + 1, b = f[i + 1] + 1, c = f[i + 2] + 1;
    lines.push(`f ${a}//${a} ${b}//${b} ${c}//${c}`);
  }
  return lines.join('\n') + '\n';
}

/** Minimal binary glTF 2.0 (positions in metres, as glTF expects). Returns an ArrayBuffer. */
export function glbBuffer(m) {
  const pos = new Float32Array(m.vertices.length);
  for (let i = 0; i < pos.length; i++) pos[i] = m.vertices[i] / 1000;
  const blobs = [new Uint8Array(pos.buffer), new Uint8Array(Float32Array.from(m.normals).buffer)];
  if (m.colors) blobs.push(new Uint8Array(Float32Array.from(m.colors, (c) => c / 255).buffer));
  blobs.push(new Uint8Array(Uint32Array.from(m.faces).buffer));
  const pad4 = (x) => (4 - (x % 4)) % 4;
  const views = [];
  let offset = 0;
  blobs.forEach((b, i) => {
    views.push({ buffer: 0, byteOffset: offset, byteLength: b.length, target: i === blobs.length - 1 ? 34963 : 34962 });
    offset += b.length + pad4(b.length);
  });
  const min = [Infinity, Infinity, Infinity], max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < pos.length; i += 3) for (let k = 0; k < 3; k++) { min[k] = Math.min(min[k], pos[i + k]); max[k] = Math.max(max[k], pos[i + k]); }
  const gltf = {
    asset: { version: '2.0', generator: 'Bozzetto (browser)' }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: m.colors ? { POSITION: 0, NORMAL: 1, COLOR_0: 2 } : { POSITION: 0, NORMAL: 1 },
                              indices: blobs.length - 1 }] }],
    buffers: [{ byteLength: offset }], bufferViews: views,
    accessors: [
      { bufferView: 0, componentType: 5126, count: pos.length / 3, type: 'VEC3', min, max },
      { bufferView: 1, componentType: 5126, count: pos.length / 3, type: 'VEC3' },
      ...(m.colors ? [{ bufferView: 2, componentType: 5126, count: pos.length / 3, type: 'VEC3' }] : []),
      { bufferView: blobs.length - 1, componentType: 5125, count: m.faces.length, type: 'SCALAR' },
    ],
  };
  let js = new TextEncoder().encode(JSON.stringify(gltf));
  const jsLen = js.length + pad4(js.length);
  const total = 12 + 8 + jsLen + 8 + offset;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, 0x46546C67, true); dv.setUint32(4, 2, true); dv.setUint32(8, total, true);
  dv.setUint32(12, jsLen, true); dv.setUint32(16, 0x4E4F534A, true);
  out.set(js, 20);
  out.fill(0x20, 20 + js.length, 20 + jsLen);
  let p = 20 + jsLen;
  dv.setUint32(p, offset, true); dv.setUint32(p + 4, 0x004E4942, true);
  p += 8;
  for (let i = 0; i < blobs.length; i++) { out.set(blobs[i], p + views[i].byteOffset); }
  return out.buffer;
}
