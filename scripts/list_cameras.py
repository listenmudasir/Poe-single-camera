#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
list_cameras.py
===============
Enumerate all cameras Aravis can discover and print their metadata.
Does NOT open a stream.  Use --fake to include the Aravis fake camera.

    python scripts/list_cameras.py [--fake]
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main() -> int:
    if "--fake" in sys.argv:
        os.environ["ARV_FAKE_CAMERA_ENABLED"] = "1"

    from poe_single_aravis.app import _bootstrap_aravis
    _bootstrap_aravis()

    from poe_single_aravis.aravis_backend.discovery import CameraDiscovery

    devices = CameraDiscovery().refresh()
    if not devices:
        print("No cameras discovered.")
        print("  • Check the camera is powered and on the same subnet.")
        print("  • Try:  python scripts/list_cameras.py --fake")
        return 1

    print("Discovered %d camera(s):\n" % len(devices))
    for i, d in enumerate(devices):
        print("  [%d] %s" % (i, d.device_id))
        print("      vendor    : %s" % (d.vendor or "?"))
        print("      model     : %s" % (d.model or "?"))
        print("      serial    : %s" % (d.serial_number or "?"))
        print("      transport : %s\n" % (d.transport or "?"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
