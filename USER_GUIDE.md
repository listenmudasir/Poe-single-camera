# User Guide — POE Single-Camera Monitor (Aravis)
# 使用手冊 — POE 單相機監控系統

A complete guide to installing, launching, and operating the single-camera
monitoring application. For developer/architecture details see
[README.md](README.md); for camera-specific quirks see
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

---

## 目錄 / Contents

1. [快速入門 Quick Start](#1-快速入門--quick-start)
2. [Installation from scratch](#2-installation-from-scratch)
3. [Launching the application](#3-launching-the-application)
4. [UI tour — every control explained](#4-ui-tour--every-control-explained)
5. [Typical workflows](#5-typical-workflows)
6. [Data, logs and snapshots](#6-data-logs-and-snapshots)
7. [Configuration reference](#7-configuration-reference)
8. [Troubleshooting](#8-troubleshooting)
9. [FAQ](#9-faq)

---

## 1. 快速入門 / Quick Start

已安裝好環境的機器（例如本開發機）只需三步：

```bash
cd poe_single_aravis
./run.sh          # 啟動程式（自動選擇 conda 環境、設定 Aravis 路徑）
```

1. **連線** — 上方下拉選單選擇相機，按「連線」。
2. **開始取像** — 按「▶ 開始取像」，即時畫面出現。
3. **覆蓋率監控** — 下方按「影像相減」開啟、按「拍攝背景」凍結背景，
   之後畫面變化的覆蓋率會即時顯示，超過警示閾值會閃紅框警示。

On an already-provisioned machine (like this bench), that is all you need.
For a fresh machine, continue to section 2.

---

## 2. Installation from scratch

### 2.1 Supported platform

* **Linux** (validated on Ubuntu 22.04). Windows requires separately packaging
  Aravis/GLib/PyGObject and is not covered here.
* A GigE Vision / GenICam camera reachable on the local network (PoE or
  otherwise). USB3 Vision cameras supported by Aravis should also work.

### 2.2 System packages

```bash
sudo apt update
sudo apt install -y \
    python3-gi gir1.2-glib-2.0 libglib2.0-dev \
    gobject-introspection libgirepository1.0-dev \
    meson ninja-build cmake pkg-config \
    libxml2-dev zlib1g-dev
```

### 2.3 Install Aravis 0.10

If your distribution ships `libaravis-0.10` + `gir1.2-aravis-0.10`, install
those. Otherwise build from source (what this machine uses — installed under
`/usr/local`):

```bash
git clone https://github.com/AravisProject/aravis.git
cd aravis
git checkout 0.8.30   # or any 0.10.x release tag, e.g. ARAVIS_0_8_30 / main
meson setup build --prefix=/usr/local
ninja -C build
sudo ninja -C build install
sudo ldconfig
```

After a `/usr/local` install, note these two paths (the app auto-detects them,
but they matter for manual runs):

| What | Path |
| ---- | ---- |
| GI typelib | `/usr/local/lib/x86_64-linux-gnu/girepository-1.0/Aravis-0.10.typelib` |
| Shared library | `/usr/local/lib/x86_64-linux-gnu/libaravis-0.10.so.0` |

If your layout differs, set `ARAVIS_TYPELIB_DIR=/path/to/girepository-1.0`.

### 2.4 Python environment

Any Python ≥ 3.8 with these packages:

```bash
# option A: fresh virtualenv (needs PyGObject built via pip)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .              # PyQt5, numpy, opencv-python, psutil, matplotlib, PyYAML
pip install PyGObject         # gi bindings (needs libgirepository1.0-dev)

# option B (GPU coverage processing): also install torch with CUDA
pip install -e ".[gpu]"
```

> **This machine:** two ready conda envs exist. `run.sh` prefers
> **`train310`** (has PyTorch + CUDA → GPU coverage mode available) and falls
> back to **`poe`** (CPU-only). Override with `POE_PYTHON=/path/to/python`.

### 2.5 Verify the installation

```bash
python scripts/check_aravis.py          # bindings load? prints Aravis version
python scripts/list_cameras.py          # camera discovered? prints ID/vendor/model/serial
python scripts/list_cameras.py --fake   # no hardware? test with the fake camera
python -m pytest tests/unit -q          # 42 unit tests, no camera needed
python scripts/run_fake_camera_test.py  # headless end-to-end pipeline check
```

---

## 3. Launching the application

```bash
./run.sh                # normal launch (real camera)
./run.sh --fake         # adds the Aravis fake camera (demo without hardware)
./run.sh --config my.yaml --log-level DEBUG
```

`run.sh` does three things you would otherwise do manually:

1. **Strips `/opt/MVS` from `LD_LIBRARY_PATH`** — the Hikvision MVS SDK ships
   an old Qt 5.6 that crashes PyQt5 ("Cannot mix incompatible Qt library").
   The app also self-heals (re-execs once) if launched without `run.sh`.
2. Sets `GI_TYPELIB_PATH` so the Aravis bindings load.
3. Picks the interpreter (`train310` → `poe` → `python3`, or `$POE_PYTHON`).

Environment variables:

| Variable | Purpose |
| -------- | ------- |
| `POE_PYTHON` | Force a specific Python interpreter |
| `ARAVIS_TYPELIB_DIR` | Non-standard Aravis typelib directory |
| `ARV_FAKE_CAMERA_ENABLED=1` | Same as `--fake` |

---

## 4. UI tour — every control explained

### 4.1 Top bar 上方工具列

| Control | 中文 | Function |
| ------- | ---- | -------- |
| Camera dropdown | 相機選單 | Discovered cameras (vendor, model, serial). Locked while connected. |
| 🔍 Refresh | 刷新 | Re-scan the network for cameras. Only when disconnected. |
| Connect / Disconnect | 連線／斷線 | Open or release the selected camera. Turns red while connected. |
| ▶ Start / ■ Stop | 開始取像／停止 | Start/stop continuous acquisition. |
| 📸 Trigger | 單次觸發 | Fire one software trigger. Enabled **only** in software-trigger mode while streaming. |
| 💾 Snapshot | 擷圖 | Save the current displayed frame as PNG to `./snapshots/`. |
| Status pill | 狀態 | Grey=disconnected, amber=transition, cyan=connected, green=streaming, red=error. |
| 🌐 EN/中 | 語言 | Toggle the whole UI between Chinese and English instantly. |

### 4.2 Sidebar cards 左側面板

**🖥 Hardware Monitor 硬體監控** — live CPU %, RAM %, and (with an NVIDIA
GPU) GPU utilisation + VRAM. Shows N/A when unavailable. Updates every ~1.5 s.

**📷 Camera Control 相機控制** — compute mode for the coverage pipeline:
* **CPU** — pure OpenCV, works everywhere.
* **CUDA (GPU)** — PyTorch on the GPU; greyed out if CUDA is unavailable, and
  silently falls back to CPU (with a message) if GPU init fails at runtime.

**⚙ Camera Parameters 相機參數**
* **Exposure (µs) / Gain (dB) / Frame rate (FPS)** — ranges come from the
  camera itself; out-of-range values are clamped.
* **Pixel format 像素格式** — every format the camera advertises. Changing it
  stops and restarts the stream automatically.
* **Trigger mode 觸發模式** — Continuous (free-run) or Software trigger.
* **📥 Get 讀取參數** — read the *current* values back from the camera.
* **📤 Apply 套用參數** — write exposure/gain/frame-rate to the camera.

**🔲 ROI 感興趣區域** — hardware sensor crop (Offset X/Y, Width/Height).
* **Apply ROI 套用 ROI** — stops the stream, writes the region, restarts.
* **Reset Full 重置全圖** — restore the full sensor area.
* ⚠ On the FUE-S500C-PRO see the ROI caveat in
  [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) — if streaming stops after an
  ROI change, use the DeviceReset recovery in §8.3.

**⚖ White Balance 白平衡**
* **Auto White Balance 單次自動白平衡** — one-shot *hardware* white balance
  (writes `BalanceWhiteAuto=Once` to the camera).
* **Software preset 軟體預設** — display-side gain presets (daylight, cloudy,
  tungsten, fluorescent, shade); never touches camera registers.
* **Gray-World 灰世界** — automatic software balance from the current frame.
* **Reset 重設** — neutral software gains.

**📊 Image Analysis 影像分析** — live per-frame statistics:
RGB means, HSL means, intensity (L), BT.601 brightness, current resolution,
and acquisition/processing FPS.

### 4.3 Center view 中央畫面

* **Live video** with letterboxed aspect-correct scaling.
* **FPS overlay** (top-left): acquisition and processing rates.
* **Difference PiP** (bottom-right): the binary difference image with contours
  and coverage % — visible while subtraction is enabled.
* **Flashing red border** when coverage ≥ alert threshold.
* **Double-click 雙擊** → fullscreen preview. **Esc** or double-click closes it.
* **🎥 Live / 📈 Chart** buttons swap the view between live video and the
  coverage history chart (selectable 1–5 days).

### 4.4 Coverage bar 底部覆蓋率列

| Control | 中文 | Function |
| ------- | ---- | -------- |
| Subtraction (toggle) | 影像相減 | Enable/disable the background-difference pipeline. |
| Capture BG | 拍攝背景 | Freeze the *next* frame as the reference background. |
| Reset BG | 重設背景 | Clear the background (status dot turns amber = not set). |
| Sensitivity 1–100 | 相減靈敏度 | Binary threshold on the difference image (default 5; lower = more sensitive). |
| Alert threshold % | 警示閾值 | Coverage % at which the alert triggers (default 20%). |
| Coverage readout | 覆蓋率 | Large live percentage; green normally, red + ⚠ badge during an alert. |

**How coverage is computed:** grayscale → resize to 640×480 → Gaussian blur
21×21 → absolute difference vs the background → threshold → morphological
close+open (5×5 ellipse) → external contours → covered area / total area × 100.

---

## 5. Typical workflows

### 5.1 Basic live monitoring
1. `./run.sh` → select camera → **Connect** → **Start**.
2. Watch the live view; adjust **Exposure/Gain** in Camera Parameters and
   press **Apply** if the image is too dark/bright (or use hardware
   auto white balance for colour).

### 5.2 Coverage alerting (the main use case)
1. Start streaming with the scene in its *empty/reference* state.
2. Enable **Subtraction**, press **Capture BG**.
3. Set **Sensitivity** (start at 5) and **Alert threshold** (e.g. 20%).
4. Anything that changes versus the background now shows in the PiP and the
   coverage %; alerts flash the video border red and show the ⚠ badge.
5. Coverage is logged automatically once per minute — view history via
   **📈 Chart** (1–5 days).
6. If lighting changes permanently, press **Capture BG** again.

### 5.3 Software-triggered capture
1. In Camera Parameters select **Software** trigger, press **Apply** if you
   also changed exposure etc.
2. **Start** the stream — the camera now waits for triggers.
3. Each press of **📸 Trigger** produces exactly one frame.
4. Switch back to **Continuous** for free-running video.

### 5.4 Cropping to a region (ROI)
1. Enter Offset X/Y and Width/Height (values are aligned/clamped by the
   camera, typically to multiples of 4).
2. **Apply ROI** — the stream restarts at the new size; analysis and
   background are reset automatically.
3. **Reset Full** restores the whole sensor.

---

## 6. Data, logs and snapshots

| What | Where | Format |
| ---- | ----- | ------ |
| Coverage log | `./data/coverage/<camera-serial>.csv` | One row per minute: `timestamp, camera_id, coverage_percent, acquisition_fps, processing_fps, processing_mode, alert_active` |
| Snapshots | `./snapshots/snapshot_YYYYMMDD_HHMMSS*.png` | PNG (BGR frame as displayed) |
| History chart | in-app (📈) | reads the CSV; handles gaps/missing minutes |

Paths are relative to the directory you launch from; the log directory is
configurable (`logging.directory`). Logging never runs on the UI thread and a
full disk or permission error will not crash acquisition.

---

## 7. Configuration reference

`config/default.yaml` (all keys optional — invalid values fall back to the
documented defaults):

```yaml
camera:
  auto_connect_first: false   # true = connect+stream first camera on startup
  buffer_count: 24            # Aravis buffer pool size
  frame_timeout_ms: 500       # per-frame wait before counting a timeout
  reconnect_enabled: true     # auto-reconnect after camera/network loss
  reconnect_interval_seconds: 3
  max_reconnect_attempts: 10
  consecutive_failure_threshold: 5   # failures before declaring the link lost

processing:
  mode: cpu                   # "cpu" or "cuda" (falls back to cpu if no CUDA)
  analysis_width: 640         # coverage analysis resolution
  analysis_height: 480
  difference_threshold: 5     # default sensitivity (UI slider)
  gaussian_kernel: 21         # blur kernel (odd)
  morphology_kernel: 5        # ellipse kernel for close/open
  alert_threshold_percent: 20.0
  analysis_fps: 8             # max RGB/HSL/brightness recomputes/sec (0 = every frame)

logging:
  enabled: true
  interval_seconds: 60        # one row per minute
  directory: "./data/coverage"

monitoring:
  interval_seconds: 1.5       # hardware monitor refresh

ui:
  language: "zh"              # "zh" or "en" (runtime-switchable)
  show_difference_pip: true   # difference picture-in-picture overlay
  compact: "auto"             # small-screen layout: "auto" | true | false
  display_fps_cap: 30         # cap UI repaint rate (fps); 0 = uncapped
  card_shadows: "auto"        # card drop shadows: "auto" | true | false
```

Use a custom file with `./run.sh --config /path/to/file.yaml`.

### Running on a Raspberry Pi

On a small display (e.g. the official 7" 800×480 touchscreen) the window
switches to a **compact layout** automatically — tighter margins, a smaller
video minimum, and a window sized to fit the screen. You can force it either
way with `ui.compact: true` / `false`.

Two display-performance settings help the Pi's modest GPU/CPU:

* `display_fps_cap` decouples the UI repaint from the acquisition rate. The
  camera keeps streaming and coverage analysis still runs on every frame, but
  the costly Qt render (resize + colour-convert + upload) never runs faster
  than the cap. Lower it (e.g. `15`) on a Pi 3; raise or set `0` to uncap.
* `card_shadows` turns off the per-card drop shadows (soft shadows are drawn
  in software and are surprisingly expensive on the Pi's composited display).
  `"auto"` disables them whenever the compact layout is active.

The `processing.analysis_fps` setting caps how often the RGB/HSL/brightness
read-outs are recomputed (default 8/sec). The live video keeps updating every
frame — only the statistics pass is rate-limited — so lowering it (e.g. `4`)
frees CPU on a Pi without making the video choppy. Set `0` to analyse every
frame as before. Coverage/background-subtraction analysis is separate and runs
only while subtraction is enabled.

The divider between the left panel and the video can be **dragged** to give
either side more room.

---

## 8. Troubleshooting

### 8.1 No camera in the dropdown
* `python scripts/list_cameras.py` — is it enumerated at all?
* Camera powered (PoE budget!) and on the same subnet as the NIC.
* Firewalls can block GVCP discovery (UDP 3956).
* **Another program may be holding the camera** — notably a leftover instance
  of the old 20-camera app: `ps aux | grep multi_cam` → `kill <pid>`.

### 8.2 App crashes at startup with "Cannot mix incompatible Qt library"
The Hikvision MVS SDK's Qt is on `LD_LIBRARY_PATH`. Launch via `./run.sh`
(strips it) — the app also self-heals once by re-executing with a clean path.

### 8.3 Connected, but no frames (timeouts) / stopped after an ROI change
This camera model's GVSP engine can stall (see KNOWN_LIMITATIONS.md). Recover
with a device reset, then wait ~40 s and reconnect:

```bash
python - <<'EOF'
import gi; gi.require_version('Aravis','0.10')
from gi.repository import Aravis
Aravis.update_device_list()
cam = Aravis.Camera.new(Aravis.get_device_id(0))
cam.get_device().execute_command('DeviceReset')
print("reset issued — wait ~40 s")
EOF
```

(Run through `run.sh`'s environment or with `GI_TYPELIB_PATH` set.)

### 8.4 "Unsupported pixel format"
Supported: Mono 8/10/12/16, RGB8, BGR8, Bayer RG/GR/GB/BG at 8/10/12/16-bit,
YUV422 (YUYV/UYVY). *Packed* 10/12-bit variants (e.g. `BayerRG12Packed`,
`Mono12p`) are not — switch the camera to a plain variant in the pixel-format
selector.

### 8.5 CUDA option greyed out / falls back to CPU
The selected Python has no CUDA-enabled PyTorch. Use the `train310` env (the
`run.sh` default) or `pip install -e ".[gpu]"`. A runtime GPU failure
automatically drops to CPU and reports it — processing continues.

### 8.6 Choppy stream / dropped frames at full resolution
The bench NIC has no jumbo frames (packet size ≈1504). The app compensates
(large socket buffer + packet resend), but for best throughput enable jumbo
frames: `sudo ip link set <nic> mtu 9000`, then reconnect (packet size is
re-negotiated automatically).

### 8.7 Feature is greyed out with a tooltip
The camera does not expose that GenICam node — this is per-model, not an app
error. See the capability matrix in KNOWN_LIMITATIONS.md.

---

## 9. FAQ

**Q: 介面可以換語言嗎？** — 可以，右上角 🌐 按鈕即時切換中英文；預設語言在
`config/default.yaml` 的 `ui.language` 設定。

**Q: Does software white balance change my camera settings?**
No. Presets/gray-world/manual gains affect only display & analysis. Only
**單次自動白平衡 (Auto White Balance)** writes to the camera
(`BalanceWhiteAuto=Once`).

**Q: What happens if the network cable is pulled?**
After 5 consecutive frame failures the app enters ERROR, keeps the UI alive,
and retries every 3 s (up to 10 attempts), restoring your exposure/gain/ROI/
trigger settings and restarting the stream if it was running.

**Q: Can I run it without any camera?**
Yes — `./run.sh --fake` adds Aravis's simulated camera (`Fake_1`), useful for
demos and UI testing.

**Q: Where did the 20-camera grid go?**
This application is the single-camera successor. All analysis/monitoring
features were kept; multi-camera slots, paging and batch processing were
removed by design (see [MIGRATION.md](MIGRATION.md)).
