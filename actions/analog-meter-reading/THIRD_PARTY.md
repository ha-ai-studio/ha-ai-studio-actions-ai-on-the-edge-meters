# Upstream project and attribution

## AI-on-the-edge-device

The planned meter-recognition implementation in this repository is based on the work of **jomjol and the AI-on-the-edge-device contributors**.

- Original project: https://github.com/jomjol/AI-on-the-edge-device
- Authors and contributors: https://github.com/jomjol/AI-on-the-edge-device/graphs/contributors
- Reviewed source revision: `708129ba779e233b6fe67ace663bada31888d2ad`
- Original license at that revision: https://github.com/jomjol/AI-on-the-edge-device/blob/708129ba779e233b6fe67ace663bada31888d2ad/Licence.md
- License: **Dual Use License for AI-on-the-Edge Device**, version 1.0, dated 2025-01-05. The unchanged text is included in [LICENSE.md](LICENSE.md).

Thank you to the original authors for their work on image alignment, digit and dial recognition, and meter-value post-processing.

This is an independent HA AI Studio Action project. Any ports or adaptations maintained here are modified versions, not official releases of the upstream project. No endorsement by the upstream authors is implied.

## Incorporated material and modifications

- `actions/analog-meter-reading/models/ana-cont_1500_s2_q.tflite` and `dig-cont_0900_s3_q.tflite`: unchanged upstream models from `sd-card/config/` at the revision above. SHA256 hashes are in `models/PROVENANCE.json`.
- `actions/analog-meter-reading/correction.py`: Python adaptation of `PointerEvalAnalogNew`, `PointerEvalHybridNew`, `PointerEvalAnalogToDigitNew` and readout assembly from `code/components/jomjol_flowcontroll/ClassFlowCNNGeneral.cpp`. ESP32-specific I/O and logging removed; explicit invalid-result handling added.
- `actions/analog-meter-reading/engine.py`: model output decoding adapted from the same upstream file and RGB input convention from `code/components/jomjol_tfliteclass/CTfLiteClass.cpp`. Uses desktop LiteRT, Pillow and OpenCV. Two-reference alignment is newly implemented using bounded template search and a rigid transform; it is not the original firmware's pixel-search implementation.
- `tests/test_analog_meter_reading.py`: selected numerical expected-value cases adapted from `code/test/components/jomjol-flowcontroll/test_flowpostprocessing.cpp`.
- The TypeScript/SCSS editor, Studio asset/preview interface and source access checks are new implementation work. No original web interface code is copied.

This is a modified independent derivative, not an upstream release. Copyright and licensing rights of jomjol and the upstream contributors are preserved. Adopting the license does not grant a commercial license to their work. HA AI Studio is separately licensed.

Python runtime dependencies are pinned with hashes in the Action lockfile. They retain their own licenses: Pillow (HPND), NumPy (BSD-3-Clause), OpenCV (Apache-2.0), LiteRT (Apache-2.0) and their transitive dependency notices. See installed distribution metadata for full notices. No external model/API service is contacted for inference.
