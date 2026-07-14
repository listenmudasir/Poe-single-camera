# POE Single-Camera Monitor (Aravis)

A clean, single-camera PoE / GigE Vision monitoring application built on the
[Aravis](https://github.com/aravisproject/aravis) GenICam library. It is a
ground-up rebuild of the former 20-camera Hikvision-MVS application, keeping
all of the camera-independent functionality (live view, image analysis,
software white balance, background-subtraction coverage analysis, per-minute
logging, historical charts, hardware monitoring, bilingual UI) while removing
every multi-camera concept and the Hikvision MVS SDK dependency.

> **One camera, one session.** There are no camera grids, slots, paging, or
> start-all/stop-all operations anywhere in the data model.

> 📖 **New here? Start with the [USER GUIDE / 使用手冊](USER_GUIDE.md)** — 
> step-by-step installation, a tour of every control, typical workflows,
> and troubleshooting. This README covers the architecture and developer
> details.

---

## 1. Purpose

Continuously acquire from a single GenICam-compatible camera, display the live
image, analyse it (RGB/HSL/brightness, coverage vs a captured background),
raise alerts when coverage exceeds a threshold, log coverage once per minute,
and chart the history — all while staying responsive and shutting down cleanly.

## 2. Supported operating systems

* **Linux** (primary, validated) — Ubuntu 20.04+ / Debian equivalents.
* Windows is possible but the Aravis / GLib / PyGObject stack must be packaged
  separately; it is treated as a distinct deployment task and is **not**
  covered here.

## 3. System dependencies (Aravis + PyGObject)

These are **not** pip packages:

```bash
# Debian / Ubuntu
sudo apt install python3-gi gir1.2-glib-2.0 libglib2.0-0

# Aravis 0.10 (from your package manager if available, else build from source)
#   https://github.com/aravisproject/aravis
# After a source build under /usr/local, note the two search paths:
#   GI_TYPELIB_PATH -> <prefix>/lib/<arch>/girepository-1.0   (Aravis-0.10.typelib)
#   the shared lib  -> <prefix>/lib/<arch>/libaravis-0.10.so.0
```

This project targets the **Aravis 0.10** GObject-Introspection API. (The spec
was written against 0.8; 0.10 is API-compatible for everything used here and is
what is installed on the reference machine. All Aravis calls are isolated
behind `aravis_backend/`, so adjusting the required version is a one-line
change per module.)

The app locates a non-standard Aravis install automatically (it adds the
typelib dir to `GI_TYPELIB_PATH` and pre-loads the shared library via
`ctypes`). Override the location with `ARAVIS_TYPELIB_DIR` if your layout
differs.

## 4. Python environment

```bash
python3 -m venv .venv          # or use the provided conda env
source .venv/bin/activate
pip install -e .               # installs the Python deps from pyproject.toml
# optional GPU path:
pip install -e ".[gpu]"        # adds torch (CUDA background subtraction)
```

**Required Python packages:** PyQt5, numpy, opencv-python, psutil, matplotlib,
PyYAML. **Optional:** torch (GPU coverage processing).

> **Reference machine note.** `run.sh` prefers the `train310` conda env
> (`~/miniconda3/envs/train310/bin/python` — full stack **plus PyTorch/CUDA**,
> so GPU coverage mode is live) and falls back to the `poe` env (CPU-only).
> Override with `POE_PYTHON=/path/to/python`.

## 5. Verifying Aravis can see the camera

```bash
python scripts/check_aravis.py            # confirms the bindings load
python scripts/list_cameras.py            # lists real cameras (no stream opened)
python scripts/list_cameras.py --fake     # includes the Aravis fake camera
```

## 6. Running the application

```bash
./run.sh                 # real camera (recommended launcher)
./run.sh --fake          # Aravis fake camera, no hardware needed
```

Or directly:

```bash
python -m poe_single_aravis.app [--config PATH] [--fake] [--log-level INFO]
```

### ⚠️ Hikvision MVS SDK / Qt conflict (important)

If `/opt/MVS/lib/*` is on your `LD_LIBRARY_PATH`, the MVS SDK's bundled Qt
(5.6.3) will hijack PyQt5 and the app crashes with
*"Cannot mix incompatible Qt library"*. `run.sh` strips those entries, and the
app itself re-execs once with a cleaned `LD_LIBRARY_PATH` as a safety net.
Nothing is required from you, but this is why the app may restart itself once
on the first launch.

## 7. Continuous vs. software-trigger modes

* **Continuous** (default): the camera free-runs; frames arrive as fast as the
  frame-rate/exposure allow.
* **Software trigger**: select *Software Trigger* in the Camera Control panel.
  While streaming, the **Trigger Once** toolbar button becomes enabled — each
  click emits one software trigger and produces one frame.

## 8. Configuring exposure, gain, FPS, ROI, pixel format

All live in the **Camera Control** panel and are **capability-aware**: a
control is disabled (with an explanatory tooltip) if the camera doesn't expose
that feature, and numeric ranges come from the camera's reported bounds.
Values are clamped and increment-aligned before being written.

* **Exposure / Gain / Frame rate** apply immediately on edit.
* **Pixel format** and **ROI** change the payload size, so the app **stops the
  stream, applies the change, and restarts** automatically.

## 9. Capturing a background

In the **Coverage Analysis** panel: click **Capture Background** while
streaming — the next processed frame is frozen as the reference. **Reset
Background** clears it. Analysis shows *"Background: Not Set"* until a valid
background exists, and a resolution change invalidates it safely.

## 10. How coverage is calculated

For each frame (CPU path): grayscale → resize to the analysis size
(default 640×480) → Gaussian blur (default 21×21) → absolute difference vs the
stored background → binary threshold (default 5) → morphological close+open
(elliptical 5×5) → external contours → `coverage% = covered_area / total_area
× 100`. Contours and the percentage are drawn on the difference view. When
coverage ≥ the alert threshold, a flashing alert appears.

## 11. Enabling logging / where logs are stored

Logging is controlled by `config/default.yaml` → `logging.enabled` (default
`true`) and writes **one row per minute** while coverage analysis is running.
Files are CSV, one per camera, named by the camera serial number (or a
sanitised device id), under `logging.directory` (default `./data/coverage`).
Columns: `timestamp, camera_id, coverage_percent, acquisition_fps,
processing_fps, processing_mode, alert_active`. Writes happen off the UI
thread and never crash acquisition on disk/permission errors.

## 12. Historical charts

Toggle **Chart** in the Coverage panel to replace the live view with a
per-minute coverage chart. The day selector shows 1–5 days and handles missing
intervals.

## 13. Switching languages

Click the **EN / 中** button in the top-right. All labels re-translate at
runtime. Default language is set by `ui.language` (`zh` or `en`).

## 14. Diagnostics

**Camera not discovered**
* `python scripts/check_aravis.py` — do the bindings even load?
* `python scripts/list_cameras.py` — is the camera enumerated?
* Check power, cabling, and that the NIC is on the camera's subnet.
* For GigE, a larger packet size / jumbo frames may be required
  (`GevSCPSPacketSize`).

**Missing GenICam features**
* A disabled control with a *"not supported by this camera"* tooltip means the
  camera does not expose that GenICam node. This is expected for
  manufacturer-specific features; the standard nodes (ExposureTime, Gain,
  AcquisitionFrameRate, Width/Height/Offset, PixelFormat, TriggerMode …) are
  used where available.

**GPU mode does nothing / falls back**
* If `torch`/CUDA is unavailable, CUDA mode logs a warning and runs on the CPU
  path. This is by design — CPU mode has no GPU dependency.

## 15. Running the tests

```bash
pip install -e ".[dev]"
pytest                                   # unit tests (no camera needed)
python scripts/run_fake_camera_test.py   # headless fake-camera integration
```

The unit tests are pure Python/NumPy/OpenCV and do not require Aravis or a
display. The integration test uses the Aravis fake camera and the Qt
`offscreen` platform.

## 16. Known camera-specific limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## 17. Project layout

```
src/poe_single_aravis/
  app.py               entry point (+ Aravis/Qt bootstrap & self-heal)
  settings.py          YAML config loader with validated defaults
  domain/              models, camera state machine, errors
  aravis_backend/      the ONLY code that touches Aravis
  imaging/             analyzer, white balance, resizer, coverage (CPU+GPU)
  services/            camera_service (orchestrator), processing, logging,
                       hardware monitor, snapshots
  ui/                  modern flat-dark GUI (never calls Aravis directly)
    theme.py             design system (palette, cards, button styles)
    main_window.py       sidebar cards + live view + coverage bar
    video_widget.py      letterboxed video, diff PiP, flashing alert
    chart_widget.py      1–5 day coverage history chart
    fullscreen_dialog.py double-click fullscreen preview
    i18n.py              runtime Chinese/English strings
```

See [MIGRATION.md](MIGRATION.md) for the mapping from the old POE features to
these modules.
