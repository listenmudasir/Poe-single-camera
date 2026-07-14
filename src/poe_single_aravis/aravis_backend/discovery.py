# -*- coding: utf-8 -*-
"""
aravis_backend/discovery.py
===========================
Camera discovery using Aravis 0.10 GObject Introspection API.
Keeps discovery separate from camera connection so enumeration
never automatically opens every camera.
"""

from __future__ import annotations

import logging
import os
from typing import List

import gi
gi.require_version("Aravis", "0.10")
from gi.repository import Aravis

from ..domain.models import CameraDescriptor

log = logging.getLogger(__name__)

# Allow the Aravis fake camera in tests / demo mode
_FAKE_ENABLED = os.environ.get("ARV_FAKE_CAMERA_ENABLED", "0") == "1"


def _ensure_fake_interface() -> None:
    """Enable the Aravis fake-camera interface if requested."""
    if _FAKE_ENABLED:
        try:
            Aravis.enable_interface("Fake")
        except Exception:
            pass


class CameraDiscovery:
    """
    Discovers GenICam-compatible cameras via Aravis.

    refresh() never opens a camera connection; it only reads
    the device-list metadata already obtained by Aravis.
    """

    def refresh(self) -> List[CameraDescriptor]:
        """
        Update the Aravis device list and return all discovered cameras.

        Returns:
            List of CameraDescriptor.  May be empty.
        """
        _ensure_fake_interface()
        try:
            Aravis.update_device_list()
        except Exception as exc:
            log.error("Aravis device enumeration failed: %s", exc)
            return []

        count = Aravis.get_n_devices()
        descriptors: List[CameraDescriptor] = []

        for i in range(count):
            try:
                device_id = Aravis.get_device_id(i)
            except Exception:
                continue

            vendor   = _safe_str(lambda: Aravis.get_device_vendor(i))
            model    = _safe_str(lambda: Aravis.get_device_model(i))
            serial   = _safe_str(lambda: Aravis.get_device_serial_nbr(i))
            protocol = _safe_str(lambda: Aravis.get_device_protocol(i))

            descriptors.append(CameraDescriptor(
                device_id=device_id,
                vendor=vendor,
                model=model,
                serial_number=serial,
                transport=protocol,
            ))
            log.debug("Discovered: %s (vendor=%s model=%s sn=%s transport=%s)",
                      device_id, vendor, model, serial, protocol)

        log.info("Discovery complete: %d camera(s) found", len(descriptors))
        return descriptors


def _safe_str(fn) -> str | None:
    try:
        v = fn()
        return str(v).strip() if v else None
    except Exception:
        return None
