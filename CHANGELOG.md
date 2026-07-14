# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [1.0.0] — 2026-07-14

### Added
- Ground-up single-camera application on the **Aravis 0.10** backend.
- Camera discovery, connection, and an explicit camera **state machine**
  (`DISCONNECTED → CONNECTING → CONNECTED → STARTING → STREAMING → STOPPING`,
  plus `ERROR`).
- Aravis stream lifecycle with a reusable buffer pool; every completed buffer
  is requeued and every frame is copied into numpy-owned memory before requeue.
- Capability-aware feature adapter (exposure, gain, frame rate, ROI, pixel
  format, trigger) with high-level API → generic GenICam fallback, bounds
  clamping, and increment alignment.
- Pixel-format converter for Mono8, Mono16, RGB8, BGR8 and the four Bayer-8
  variants, with a clear error for unsupported formats.
- Image analysis (RGB/HSL/brightness), software white balance (manual, 5
  presets, gray-world), and resize (presets, custom width, linear/cubic/lanczos).
- Background-subtraction coverage pipeline (CPU + optional PyTorch CUDA with
  automatic CPU fallback), flashing coverage alerts.
- Per-minute CSV coverage logging keyed on the camera serial; 1–5 day history
  chart.
- Hardware monitor (CPU/RAM/GPU/VRAM) with graceful "N/A".
- PyQt5 UI: live view with letterboxing + difference PiP, double-click
  fullscreen, camera/analysis/coverage/hardware panels, Chinese/English i18n.
- Reconnect logic after camera/network loss with a bounded attempt count.
- `check_aravis`, `list_cameras`, and `run_fake_camera_test` scripts; `run.sh`
  launcher; unit + fake-camera integration tests.

### Fixed
- Brightness/luminance computation that raised on multi-pixel frames.
- `Settings` resolving `config/default.yaml` one directory too high.

### Changed / bootstrap
- `app.py` auto-locates a non-standard Aravis install and imports `gi` before
  PyQt5 to avoid a GLib load-order crash.
- Hikvision MVS SDK `LD_LIBRARY_PATH` entries (old Qt 5.6.3) are stripped by the
  launcher and by a one-time self-heal re-exec.

### Removed
- All Hikvision MVS SDK usage and every multi-camera concept (20 slots, grid,
  paging, start/stop-all, GPU batch processor, per-camera arrays, cross-camera
  sync/aggregation).
