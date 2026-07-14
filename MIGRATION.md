# Migration: POE 20-camera (Hikvision MVS) → poe_single_aravis (Aravis)

This document maps every retained feature from the original `POE_20camera`
application to its new module, and lists the multi-camera features that were
**removed**.

## 1. Backend replacement (MVS → Aravis)

| Old (Hikvision MVS)            | New (Aravis)                                             | Module |
| ----------------------------- | ------------------------------------------------------- | ------ |
| `MvCamera` enumerate devices  | `Aravis.update_device_list()` + device metadata         | `aravis_backend/discovery.py` |
| `MV_CC_CreateHandle`/open     | `Aravis.Camera.new(device_id)`                          | `aravis_backend/camera.py` |
| device control handle         | `camera.get_device()`                                   | `aravis_backend/feature_adapter.py` |
| `MV_CC_StartGrabbing`         | create stream → queue buffers → `start_acquisition()`   | `aravis_backend/stream.py` |
| `MV_CC_StopGrabbing`          | stop acquisition + clean worker shutdown                | `aravis_backend/stream.py` |
| `MV_CC_GetImageBuffer`        | `stream.timeout_pop_buffer()`                           | `aravis_backend/stream.py` |
| `MV_CC_FreeImageBuffer`       | `stream.push_buffer(buffer)` (same buffer requeued)     | `aravis_backend/stream.py` |
| payload size                  | `camera.get_payload()`                                  | `aravis_backend/stream.py` |
| exposure / gain / frame rate  | Aravis high-level API → generic GenICam fallback        | `aravis_backend/feature_adapter.py` |
| ROI                           | `camera.set_region()` → Width/Height/Offset fallback    | `aravis_backend/feature_adapter.py` |
| trigger mode / trigger once   | standard GenICam trigger nodes / `software_trigger()`   | `aravis_backend/feature_adapter.py` |
| pixel format                  | Aravis pixel-format API + GenICam enumeration           | `aravis_backend/feature_adapter.py`, `pixel_formats.py` |
| frame → numpy                 | copy payload into numpy-owned memory, then requeue      | `aravis_backend/pixel_formats.py` |
| save image                    | OpenCV encode of the converted BGR frame                | `services/snapshot_service.py` |
| device disconnect detection   | consecutive-failure threshold → `ERROR` state + reconnect | `aravis_backend/camera.py`, `services/camera_service.py` |

A grep for `MvCameraControl`, `MV_CC_`, `MV_FRAME_OUT`, `MvCamera` over `src/`
returns **no production matches**.

## 2. Retained camera-independent features → new module

| Original feature | New module |
| ---------------- | ---------- |
| Search / refresh cameras; show id/vendor/model/serial/transport | `aravis_backend/discovery.py`, `ui/main_window.py` (top bar) |
| Select one camera / optional auto-connect first | `ui/main_window.py`, `settings.py` (`auto_connect_first`) |
| Connect / disconnect, start / stop, continuous & software trigger | `services/camera_service.py`, `aravis_backend/camera.py` |
| Exposure / gain / FPS / ROI / pixel-format / current params display | `ui/camera_controls.py`, `aravis_backend/feature_adapter.py` |
| Frame timeout & connection-loss reporting; reconnect | `aravis_backend/stream.py`, `services/camera_service.py` |
| Snapshot PNG/JPEG/BMP | `services/snapshot_service.py` |
| Live display, aspect-ratio letterboxing, double-click fullscreen | `ui/video_widget.py`, `ui/fullscreen_dialog.py` |
| Difference-image picture-in-picture | `ui/video_widget.py` |
| Live/difference/chart toggle | `ui/main_window.py`, `ui/coverage_panel.py`, `ui/chart_widget.py` |
| Acquisition FPS / processing FPS / display FPS | `aravis_backend/stream.py`, `services/processing_service.py` |
| RGB / HSL / brightness (BT.601) / resolution | `imaging/analyzer.py`, `ui/analysis_panel.py` |
| Software white balance: manual gains, 5 presets, gray-world, reset | `imaging/white_balance.py`, `ui/analysis_panel.py` |
| Optional hardware auto-white-balance | `aravis_backend/feature_adapter.py` (`BalanceWhiteAuto`) |
| Resize presets / custom width / linear-cubic-lanczos | `imaging/resizer.py`, `ui/analysis_panel.py` |
| Background capture / reset | `imaging/background_subtraction.py`, `services/processing_service.py` |
| Difference, threshold, morphology, contours, coverage % | `imaging/background_subtraction.py` |
| CPU processing mode | `imaging/background_subtraction.py::CpuCoverageProcessor` |
| Optional CUDA mode + automatic CPU fallback | `imaging/background_subtraction.py::CudaCoverageProcessor` |
| Coverage alert threshold + flashing alert | `ui/coverage_panel.py` |
| Per-minute coverage logging | `services/coverage_logger.py` |
| Historical coverage chart (1–5 days) | `ui/chart_widget.py` |
| CPU / RAM / GPU / VRAM monitoring | `services/hardware_monitor.py`, `ui/hardware_panel.py` |
| Dark industrial UI, Chinese/English localization | `ui/*`, `ui/i18n.py` |
| Clear status / acquisition state / processing mode / error messages | `ui/main_window.py`, `ui/hardware_panel.py` |

## 3. Removed multi-camera features (deliberately not carried over)

* 20 camera slots, camera overview grid, camera pages, slot assignment
* Start-all / stop-all / connect-all cameras
* Multi-camera frame batching and the centralized **GPU batch processor**
  (`GPUBatchProcessor`)
* Per-camera worker arrays, 20 coverage charts, cross-camera synchronization
* Multi-camera aggregate statistics and configuration matrices

No dormant multi-camera code is retained behind flags. The internal data model
represents exactly one active camera session (`CameraSession`).

## 4. Behavioural notes / justified changes

* **Brightness bug fix.** The luminance computation now averages the luminance
  array (`(0.299R+0.587G+0.114B).mean()`) instead of attempting to cast the
  whole array to a scalar first — the original expression raised on multi-pixel
  frames.
* **Config path fix.** `Settings` now resolves `config/default.yaml` at the
  repository root instead of one directory too high.
* **Qt/MVS conflict handling** is new (no equivalent in the old app): the old
  MVS `LD_LIBRARY_PATH` entries ship a conflicting Qt and are stripped by
  `run.sh` and a one-time self-heal re-exec in `app.py`.
