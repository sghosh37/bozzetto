// Bozzetto: photos to a rough 3D shape for sculpting
// Copyright (C) 2026 Suman Ghosh
// SPDX-License-Identifier: GPL-3.0-or-later
//
// Volume helpers: Gaussian softening (like scipy.ndimage.gaussian_filter) and the surface at a level.
// The desktop app uses scikit-image's marching cubes (Lewiner); this is a plain marching cubes whose
// case table is generated at load time. Volumes are flat arrays indexed [x][y][z] (z fastest).

/** Separable Gaussian, scipy defaults: truncate 4 sigma, mode 'reflect' (d c b a | a b c d). */
export function gaussian3d(vol, dims, sigma) {
  const radius = Math.trunc(4 * sigma + 0.5);
  const k = [];
  let sum = 0;
  for (let i = -radius; i <= radius; i++) { const v = Math.exp(-0.5 * i * i / (sigma * sigma)); k.push(v); sum += v; }
  for (let i = 0; i < k.length; i++) k[i] /= sum;
  const [nx, ny, nz] = dims;
  const strides = [ny * nz, nz, 1];
  let src = vol, dst = new Float32Array(vol.length);
  const reflect = (i, n) => {
    while (i < 0 || i >= n) i = i < 0 ? -i - 1 : 2 * n - i - 1;
    return i;
  };
  for (let axis = 0; axis < 3; axis++) {
    const n = dims[axis], s = strides[axis];
    const line = new Float32Array(n);
    // iterate over every line along this axis
    const others = [0, 1, 2].filter((a) => a !== axis);
    const [a1, a2] = others;
    for (let i1 = 0; i1 < dims[a1]; i1++) {
      for (let i2 = 0; i2 < dims[a2]; i2++) {
        const base = i1 * strides[a1] + i2 * strides[a2];
        for (let t = 0; t < n; t++) line[t] = src[base + t * s];
        for (let t = 0; t < n; t++) {
          let acc = 0;
          for (let j = -radius; j <= radius; j++) acc += k[j + radius] * line[reflect(t + j, n)];
          dst[base + t * s] = acc;
        }
      }
    }
    if (axis === 0) { src = dst; dst = new Float32Array(vol.length); }
    else { const tmp = src; src = dst; dst = tmp; }
  }
  return src;
}

// ---- marching cubes, with the case table built here rather than typed in ----
// Corners are numbered c = x*4 + y*2 + z (each 0 or 1). For every one of the 256 inside/outside
// patterns, the crossing edges are linked face by face into closed loops; a face with two diagonally
// opposite inside corners is always split so that each inside corner is cut off on its own. Two cells
// that share a face see the same pattern on it and make the same cut, so the surface is closed.

const EDGES = [];                       // [corner a, corner b] with a < b, differing in one axis
for (let a = 0; a < 8; a++) for (const bit of [4, 2, 1]) if (!(a & bit)) EDGES.push([a, a | bit]);
const edgeOf = (a, b) => EDGES.findIndex(([p, q]) => (p === a && q === b) || (p === b && q === a));
const FACES = [];                       // 4 corners in cyclic order
for (const bit of [4, 2, 1]) {
  const others = [4, 2, 1].filter((b) => b !== bit);
  for (const side of [0, bit]) {
    const [u, v] = others;
    FACES.push([side, side | u, side | u | v, side | v]);
  }
}

function buildCase(mask) {
  const inside = (c) => (mask >> c) & 1;
  const links = new Map();               // edge -> neighbouring edges in loops
  const link = (e1, e2) => {
    (links.get(e1) || links.set(e1, []).get(e1)).push(e2);
    (links.get(e2) || links.set(e2, []).get(e2)).push(e1);
  };
  for (const f of FACES) {
    const crossing = [];
    for (let i = 0; i < 4; i++) {
      const a = f[i], b = f[(i + 1) % 4];
      if (inside(a) !== inside(b)) crossing.push({ e: edgeOf(a, b), i });
    }
    if (crossing.length === 2) link(crossing[0].e, crossing[1].e);
    else if (crossing.length === 4) {
      // diagonal case: pair the two edges around each inside corner
      for (let i = 0; i < 4; i++) {
        if (!inside(f[i])) continue;
        link(edgeOf(f[(i + 3) % 4], f[i]), edgeOf(f[i], f[(i + 1) % 4]));
      }
    }
  }
  const loops = [], seen = new Set();
  for (const start of links.keys()) {
    if (seen.has(start)) continue;
    const loop = [start];
    seen.add(start);
    let prev = -1, cur = start;
    for (;;) {
      const nb = links.get(cur);
      const next = nb[0] !== prev ? nb[0] : nb[1];
      if (next === start || next === undefined) break;
      loop.push(next); seen.add(next); prev = cur; cur = next;
    }
    loops.push(loop);
  }
  return loops;
}
const CASES = Array.from({ length: 256 }, (_, m) => buildCase(m));

/**
 * Closed triangle surface where the field crosses `level` (inside = above level).
 * Returns vertices in grid-index units (Float64Array, xyz) and faces (Uint32Array), wound outward.
 */
export function isosurface(field, dims, level) {
  const [nx, ny, nz] = dims;
  const sx = ny * nz, sy = nz;
  const cornerOff = [];
  for (let c = 0; c < 8; c++) cornerOff.push((c >> 2) * sx + ((c >> 1) & 1) * sy + (c & 1));
  const verts = [], faces = [];
  const edgeIndex = new Map();
  const val = new Float64Array(8);

  for (let x = 0; x < nx - 1; x++) {
    for (let y = 0; y < ny - 1; y++) {
      for (let z = 0; z < nz - 1; z++) {
        const base = x * sx + y * sy + z;
        let mask = 0;
        for (let c = 0; c < 8; c++) { val[c] = field[base + cornerOff[c]]; if (val[c] > level) mask |= 1 << c; }
        if (mask === 0 || mask === 255) continue;
        // field gradient at the cell centre (trilinear): the surface faces down the gradient
        const gx = (val[4] + val[5] + val[6] + val[7]) - (val[0] + val[1] + val[2] + val[3]);
        const gy = (val[2] + val[3] + val[6] + val[7]) - (val[0] + val[1] + val[4] + val[5]);
        const gz = (val[1] + val[3] + val[5] + val[7]) - (val[0] + val[2] + val[4] + val[6]);
        for (const loop of CASES[mask]) {
          const ids = loop.map((e) => {
            const [a, b] = EDGES[e];
            const key = (base + cornerOff[a]) * 8 + (a ^ b);       // lower grid point + axis
            let id = edgeIndex.get(key);
            if (id === undefined) {
              const t = (level - val[a]) / (val[b] - val[a]);
              id = verts.length / 3;
              verts.push(x + (a >> 2) + t * ((b >> 2) - (a >> 2)),
                         y + ((a >> 1) & 1) + t * (((b >> 1) & 1) - ((a >> 1) & 1)),
                         z + (a & 1) + t * ((b & 1) - (a & 1)));
              edgeIndex.set(key, id);
            }
            return id;
          });
          // loop orientation from its area vector (Newell), compared with the outward direction -gradient
          let ax = 0, ay = 0, az = 0;
          for (let i = 0; i < ids.length; i++) {
            const p = 3 * ids[i], q = 3 * ids[(i + 1) % ids.length];
            ax += (verts[p + 1] - verts[q + 1]) * (verts[p + 2] + verts[q + 2]);
            ay += (verts[p + 2] - verts[q + 2]) * (verts[p] + verts[q]);
            az += (verts[p] - verts[q]) * (verts[p + 1] + verts[q + 1]);
          }
          const flip = ax * -gx + ay * -gy + az * -gz < 0;
          for (let i = 1; i + 1 < ids.length; i++) {
            if (flip) faces.push(ids[0], ids[i + 1], ids[i]);
            else faces.push(ids[0], ids[i], ids[i + 1]);
          }
        }
      }
    }
  }
  return { vertices: Float64Array.from(verts), faces: Uint32Array.from(faces) };
}
