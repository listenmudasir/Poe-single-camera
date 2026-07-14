#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_fake_camera_test.py
=======================
Headless end-to-end smoke test against the Aravis fake camera:
discover → connect → stream → capture background → stop → restart →
disconnect.  Exits non-zero on failure.  Requires no display (uses the
Qt "offscreen" platform).

    python scripts/run_fake_camera_test.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ["ARV_FAKE_CAMERA_ENABLED"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def main() -> int:
    from poe_single_aravis.app import _sanitize_ld_library_path, _bootstrap_aravis
    _sanitize_ld_library_path()
    _bootstrap_aravis()

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QTimer
    from poe_single_aravis.settings import Settings
    from poe_single_aravis.services.camera_service import CameraService
    from poe_single_aravis.domain.camera_state import CameraState

    app = QApplication(sys.argv[:1])
    svc = CameraService(Settings())
    svc.start_background_services()

    frames = {"n": 0}
    svc.frame_ready.connect(lambda *a: frames.__setitem__("n", frames["n"] + 1))

    result = {"ok": False}

    def phase1():
        svc.refresh_devices()
        assert svc.connect("Fake_1"), "connect failed"
        assert svc.state == CameraState.CONNECTED
        assert svc.start(), "start failed"
        assert svc.state == CameraState.STREAMING
        svc.set_subtraction_enabled(True)
        QTimer.singleShot(400, svc.capture_background)

    def phase2():
        svc.stop()
        assert svc.state == CameraState.CONNECTED
        assert svc.start()

    def finish():
        n = frames["n"]
        svc.disconnect()
        svc.shutdown()
        ok = n > 5 and svc.state == CameraState.DISCONNECTED
        result["ok"] = ok
        print("frames processed: %d" % n)
        print("RESULT:", "PASS" if ok else "FAIL")
        app.quit()

    QTimer.singleShot(200, phase1)
    QTimer.singleShot(1500, phase2)
    QTimer.singleShot(2600, finish)
    app.exec_()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
