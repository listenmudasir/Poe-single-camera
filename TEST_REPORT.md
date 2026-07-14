# Test Report — poe_single_aravis

**Date:** 2026-07-14
**Host:** Linux, conda env `poe` (Python 3.10), Aravis 0.10, PyQt5 5.15
**Camera under test:** GEV **FUE-S500C-PRO** (serial DA0321080), GigE Vision,
native ROI 2200×2048, pixel formats incl. RGB8Packed / BayerRG8.

## 1. Automated tests

Command:
```bash
env -u LD_LIBRARY_PATH PYTHONPATH=src QT_QPA_PLATFORM=offscreen \
    ~/miniconda3/envs/poe/bin/python -m pytest tests/ -q
```

Result: **48 passed, 1 skipped** (ROI test is opt-in — see below).

| Suite | Count | Status |
| ----- | ----- | ------ |
| Unit — camera state machine | 6 | ✅ |
| Unit — image analyzer (RGB/HSL/BT.601) | 4 | ✅ |
| Unit — white balance (manual/preset/gray-world) | 5 | ✅ |
| Unit — resizer (presets/custom/interp/letterbox) | 5 | ✅ |
| Unit — coverage (bg capture/clear, threshold, alert, CPU/GPU tolerance) | 7 | ✅ |
| Unit — pixel formats (Mono8/Mono16/RGB8/BGR8/Bayer, unsupported) | 7 | ✅ |
| Unit — settings validation | 3 | ✅ |
| Unit — latest-frame slot (stale-drop) | 3 | ✅ |
| Integration — discovery / connect / capabilities | 3 | ✅ (real camera) |
| Integration — stream frames + buffer requeue | 1 | ✅ (real camera) |
| Integration — frame owns memory | 1 | ✅ (real camera) |
| Integration — start/stop cycles | 1 | ✅ (real camera) |
| Integration — exposure control + bounds clamp | 1 | ✅ (real camera) |
| Integration — ROI register write/readback | 1 | ⏭ opt-in (`POE_TEST_ROI=1`) |

## 2. Full-stack end-to-end (real camera, headless)

Exercised the complete application stack via `CameraService` (discovery →
`CameraSession` → Aravis stream → Qt `ProcessingService` → analysis + coverage
→ hardware monitor), offscreen Qt:

| Check | Result |
| ----- | ------ |
| Discover + connect | ✅ CONNECTED |
| Start acquisition | ✅ STREAMING |
| Frames processed (real 2200×2048 RGB8 → BGR) | ✅ 24 frames, shape (2048, 2200, 3) |
| Background subtraction / coverage pipeline | ✅ ran on live frames |
| Hardware monitor (CPU/RAM/GPU) | ✅ emitting |
| Stop → restart | ✅ CONNECTED → STREAMING |
| Disconnect + orderly shutdown | ✅ DISCONNECTED, workers stopped |

Result: **PASS.**

## 3. Notes / anomalies

- The camera streams reliably in continuous mode at native ROI. Buffer
  requeue verified (finite 8-buffer pool, many frames flowed, 0 failed/0
  timeout in steady state).
- Camera-firmware quirks discovered and handled: `GevGVSPExtendedIDMode`
  default, ROI-change GVSP hang, and sensitivity to rapid connect/stream
  churn. See `KNOWN_LIMITATIONS.md`.
- Environment: the Hikvision MVS SDK on `LD_LIBRARY_PATH` ships an old Qt that
  crashes PyQt5; the app strips it via a self-heal re-exec (and `run.sh`).
  A stale instance of the **old** `multi_cam_stream.py` was found holding the
  camera and was stopped so the new app could acquire.

## 4. Outstanding (physical bench)

- 30-minute continuous-acquisition soak + memory/CPU/GPU resource regression
  (spec §19.4).
- Software-trigger single-frame validation on this model (trigger nodes are
  exposed; capability-aware controls are wired).
