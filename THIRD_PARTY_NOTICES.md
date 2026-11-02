# Third-party notices

Bozzetto is licensed under the GNU General Public License v3.0 or later (see `LICENSE`).
It includes or uses the following third-party components. Each keeps its own licence.

## Included in this repository

### TripoSR (inference code) — MIT

- Source: https://github.com/VAST-AI-Research/TripoSR (commit in `bozzetto/engines/tsr/UPSTREAM_COMMIT`)
- Location: `bozzetto/engines/tsr/`
- Changes for Bozzetto: no trimesh/rembg/imageio imports; scikit-image marching cubes instead of
  torchmcubes; local tokenizer config; safe weight loading; plain-array mesh output. Marked
  with `Bozzetto:` comments.

```
MIT License

Copyright (c) 2024 Tripo AI & Stability AI

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Downloaded on first use (not shipped)

| Component | Licence | Source |
|---|---|---|
| TripoSR model weights (`stabilityai/TripoSR`) | MIT | https://huggingface.co/stabilityai/TripoSR |
| DINO ViT-B/16 configuration (`facebook/dino-vitb16`, config only) | Apache-2.0 | https://huggingface.co/facebook/dino-vitb16 |

## Python packages installed with Bozzetto

| Package | Licence | Source |
|---|---|---|
| PySide6 / Qt for Python | LGPL-3.0 | https://doc.qt.io/qtforpython/ |
| NumPy | BSD-3-Clause | https://numpy.org |
| OpenCV (opencv-python-headless) | Apache-2.0 (OpenCV), MIT (packaging) | https://github.com/opencv/opencv-python |
| scikit-image | BSD-3-Clause | https://scikit-image.org |
| SciPy | BSD-3-Clause | https://scipy.org |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| pillow-heif | BSD-3-Clause (libheif: LGPL-3.0) | https://github.com/bigcat88/pillow_heif |
| platformdirs | MIT | https://github.com/platformdirs/platformdirs |

Optional, for the TripoSR engine (`pip install "bozzetto[triposr]"`):

| Package | Licence | Source |
|---|---|---|
| PyTorch | BSD-3-Clause | https://pytorch.org |
| Transformers | Apache-2.0 | https://github.com/huggingface/transformers |
| OmegaConf | BSD-3-Clause | https://github.com/omry/omegaconf |
| einops | MIT | https://github.com/arogozhnikov/einops |
| huggingface_hub | Apache-2.0 | https://github.com/huggingface/huggingface_hub |

## Browser version (`web/`) and the web pages

The browser engine is Bozzetto's own code (a port of its Python engine, including the parts of the
TripoSR inference code it needs, MIT, see above). Nothing third-party is stored in this repository for
the browser; the pages load these at run time:

| Component | Licence | Source | When |
|---|---|---|---|
| ONNX Runtime Web 1.30.0 (Microsoft), from cdn.jsdelivr.net | MIT | https://github.com/microsoft/onnxruntime | One-photo method only |
| TripoSR ONNX export, int8 (`cgb/triposr-onnx-webgpu`, revision `048725e`), from huggingface.co | MIT (TripoSR, Tripo AI & Stability AI); Apache-2.0 (DINO ViT-B/16 encoder inside, Meta) | https://huggingface.co/cgb/triposr-onnx-webgpu | One-photo method only, after the visitor agrees; checked against SHA-256 |
| IBM Plex Sans and IBM Plex Sans Condensed fonts, served by Google Fonts | SIL Open Font License 1.1 | https://github.com/IBM/plex | Always (system fonts are used if they don't load) |

## Used through the operating system

- **Apple Object Capture** (RealityKit `PhotogrammetrySession`), part of macOS, used by the
  `macos/bozzetto-capture` helper (stage 3). Not redistributed.

## Planned (stage 4, downloaded on first use)

| Component | Licence | Source |
|---|---|---|
| COLMAP | BSD-3-Clause | https://github.com/colmap/colmap |
| OpenMVS | AGPL-3.0 | https://github.com/cdcseacave/openMVS |

When the release packages are built (stage 5), the full licence text of every bundled component is
added to the package.
