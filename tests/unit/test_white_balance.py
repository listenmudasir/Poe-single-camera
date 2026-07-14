# -*- coding: utf-8 -*-
import numpy as np
from poe_single_aravis.imaging.white_balance import WhiteBalanceController


def test_manual_gain_clamped():
    wb = WhiteBalanceController()
    wb.set_gains(5.0, 0.1, 1.0)   # out of [0.5, 2.0]
    assert wb.r_gain == 2.0 and wb.g_gain == 0.5 and wb.b_gain == 1.0


def test_presets_exist_and_apply():
    wb = WhiteBalanceController()
    assert "default" in WhiteBalanceController.preset_names()
    assert len(WhiteBalanceController.PRESETS) >= 5
    assert wb.set_preset("tungsten")
    assert not wb.set_preset("nope")


def test_apply_changes_channels():
    wb = WhiteBalanceController()
    wb.set_gains(2.0, 1.0, 0.5)
    img = np.full((4, 4, 3), 100, np.uint8)   # BGR all 100
    out = wb.apply(img)
    assert out[0, 0, 2] == 200            # R doubled
    assert out[0, 0, 0] == 50             # B halved
    assert out.dtype == np.uint8


def test_gray_world_neutralizes():
    wb = WhiteBalanceController()
    # Red-heavy image → gray-world should lower R gain relative to others
    img = np.zeros((10, 10, 3), np.uint8)
    img[:, :, 2] = 200; img[:, :, 1] = 100; img[:, :, 0] = 100
    wb.auto_gray_world(img)
    assert wb.r_gain < wb.g_gain


def test_reset():
    wb = WhiteBalanceController()
    wb.set_gains(2.0, 0.5, 1.5)
    wb.reset()
    assert (wb.r_gain, wb.g_gain, wb.b_gain) == (1.0, 1.0, 1.0)
