# Third-party components

Лицедей's MIT license covers its own code and documentation. It does not replace the licenses below. Third-party files retain their original notices; no endorsement by their authors is implied.

| Component | Included files | License and source |
|---|---|---|
| Universal Modder | `vendor/um/common.py`, `comfy.py`, `__init__.py` | [MIT](vendor/LICENSE-universal-modder); Copyright (c) 2026 Rehan and universal-modder contributors. [Source commit](https://github.com/rehan-remade/universal-modder/tree/2c2201437ca676fb4e5f06a18fff6e8db99eef0f). Files are unchanged; Лицедей uses the ComfyUI graph helpers and supplies its own error callback. |
| MediaPipe Tasks Vision 1.1.0 | `web/vendor/mediapipe/vision_bundle.*`, `wasm/*`, package metadata | [Apache-2.0](web/vendor/mediapipe/LICENSE). [Official npm package](https://www.npmjs.com/package/@mediapipe/tasks-vision/v/1.1.0), [upstream source](https://github.com/google-ai-edge/mediapipe). Distributed JavaScript and WASM match the npm archive; no modifications. |
| MediaPipe Face Landmarker | `web/vendor/mediapipe/face_landmarker.task` | Apache-2.0; Google. [Official task documentation](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker), [Face Mesh model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf), [Blendshape model card](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf). Exact download and hash in `web/vendor/mediapipe/SOURCE.json`. Unmodified. |
| Inter | `web/fonts/InterVariable.woff2` | [SIL Open Font License 1.1](web/fonts/LICENSE.txt); Copyright (c) 2016 The Inter Project Authors. [Source](https://github.com/rsms/inter). Unmodified font. |

Python dependencies are installed separately using `requirements.txt`: [Pillow](https://github.com/python-pillow/Pillow), [NumPy](https://github.com/numpy/numpy), and [psd-tools](https://github.com/psd-tools/psd-tools), plus their transitive dependencies. Their distributions include their own license files. Python, Node.js, ComfyUI and AI-provider models are not included in this repository.

Machine-readable hashes for redistributed files are in `vendor-manifest.json`. Compatibility fields and file extensions in exported JSON are retained as required by the data schemas; they do not rebrand third-party software or claim ownership of it.
