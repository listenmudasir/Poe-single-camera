# Known Limitations

## Platform / environment
- **Linux only** is validated. Windows requires separately packaging Aravis,
  GLib, GObject-Introspection and PyGObject and is out of scope here.
- Requires **Aravis 0.10** with its GI typelib. The code pins
  `gi.require_version("Aravis", "0.10")`; a different major/minor needs the
  version string updated in `aravis_backend/*` (isolated there by design).
- If the **Hikvision MVS SDK** (`/opt/MVS/lib`) is on `LD_LIBRARY_PATH`, its
  bundled Qt collides with PyQt5. Handled by `run.sh` and a self-heal re-exec,
  but a residual environment with other conflicting Qt libraries could still
  interfere.

## Pixel formats
- Supported: `Mono8`, `Mono16` (down-shifted to 8-bit for display/analysis),
  `RGB8`, `BGR8`, and `BayerRG8 / BayerGR8 / BayerGB8 / BayerBG8`.
- **Not** supported: packed/compressed formats (e.g. `*Packed12`, JPEG),
  10/12-bit non-Mono formats. These raise a clear error naming the reported
  format rather than silently misinterpreting bytes. Switch the camera to a
  supported format.

## GPU / CUDA
- The CUDA coverage path requires `torch` with CUDA. On the reference `poe`
  conda env, `torch` is **absent**, so CUDA mode transparently falls back to
  CPU. The GPU mask uses a per-pixel threshold mean (no morphology), so its
  coverage value is *close to* but not bit-identical with the CPU path.

## Camera-specific GenICam features
- Manufacturer-private nodes have **no** guaranteed Aravis equivalent. Only
  standard GenICam nodes are used; unsupported features present as disabled
  controls with a tooltip. Record per-model gaps here as they are found:

  | Camera model | Observation | Handling |
  | ------------ | ----------- | -------- |
  | GEV FUE-S500C-PRO (DA0321080) | Powers up / factory-resets with `GevGVSPExtendedIDMode = On`; Aravis 0.10 then misparses GVSP → `PAYLOAD_NOT_SUPPORTED`, no usable frames. | App forces `GevGVSPExtendedIDMode = Off` at connect (`_apply_gige_tuning`). |
  | GEV FUE-S500C-PRO | An **ROI (Width/Height/Offset) change hangs the GVSP engine** until a `DeviceReset`; streaming afterwards yields all-timeouts. | ROI control still writes the register (validated); the ROI integration test is opt-in (`POE_TEST_ROI=1`) and never streams at a changed ROI. Avoid ROI changes on this model in production, or issue a DeviceReset afterwards. |
  | GEV FUE-S500C-PRO | Degrades under **very rapid connect / start-stop churn** (e.g. 10+ back-to-back stream cycles), eventually needing a DeviceReset. Normal use (one connect + continuous stream) is unaffected. | Integration cycling reduced to 3 with settle delays (`POE_TEST_CYCLES` to override). |
  | GEV FUE-S500C-PRO | Host NIC has no jumbo frames; `gv_auto_packet_size()` only reaches 1504. High-res frames (13.5 MB) rely on the stream's large socket buffer + packet-resend. | `AravisStream._tune_stream` sets `socket-buffer=AUTO`, `packet-resend=ALWAYS`. Configure jumbo frames on the NIC for best throughput. |

- **Recovery:** if this camera is stuck (streaming returns only timeouts),
  issue a device reset and wait ~40 s:
  `python -c "import gi; gi.require_version('Aravis','0.10'); from gi.repository import Aravis; Aravis.update_device_list(); Aravis.Camera.new(Aravis.get_device_id(0)).get_device().execute_command('DeviceReset')"`

## Reconnection
- Reconnect re-opens by the original **device id**. If the id changes after a
  network event (e.g. DHCP reassignment changing the GEV id), reconnection to
  that exact id may fail; re-run discovery and reconnect manually.

## Testing status
- Unit tests (42) pass headlessly with no camera.
- Integration tests (7) pass against the **real** GEV FUE-S500C-PRO camera;
  the app was validated end-to-end (discover → connect → stream real 2200×2048
  RGB → analysis + coverage → stop/restart → clean shutdown).  See
  `TEST_REPORT.md`.
- The 30-minute soak and long-run resource regression (spec §19.4) are the
  remaining physical-validation items and should be run on the target bench.
