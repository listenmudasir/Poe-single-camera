# -*- coding: utf-8 -*-
"""The bounded latest-frame exchange must drop stale frames (capacity 1)."""
import numpy as np
from poe_single_aravis.aravis_backend.stream import LatestFrameSlot
from poe_single_aravis.domain.models import Frame


def _frame(fid):
    return Frame(image=np.zeros((2, 2, 3), np.uint8), width=2, height=2,
                 pixel_format="Mono8", frame_id=fid, camera_timestamp_ns=None,
                 host_timestamp_ns=fid)


def test_only_latest_survives():
    slot = LatestFrameSlot()
    slot.put(_frame(1))
    slot.put(_frame(2))
    slot.put(_frame(3))
    got = slot.take()
    assert got.frame_id == 3          # stale 1 & 2 dropped
    assert slot.take() is None        # emptied after take


def test_wait_signals_on_put():
    slot = LatestFrameSlot()
    assert not slot.wait(0.01)        # nothing yet
    slot.put(_frame(7))
    assert slot.wait(0.01)


def test_clear_empties():
    slot = LatestFrameSlot()
    slot.put(_frame(9))
    slot.clear()
    assert slot.take() is None
