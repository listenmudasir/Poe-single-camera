# -*- coding: utf-8 -*-
import numpy as np
from poe_single_aravis.imaging.resizer import FrameResizer


def test_presets():
    rz = FrameResizer()
    img = np.zeros((200, 400, 3), np.uint8)
    rz.set_preset("50%")
    out = rz.resize(img)
    assert out.shape[:2] == (100, 200)


def test_custom_width_keeps_aspect():
    rz = FrameResizer()
    img = np.zeros((200, 400, 3), np.uint8)   # 2:1
    rz.set_custom_width(100)
    out = rz.resize(img)
    assert out.shape[1] == 100 and out.shape[0] == 50


def test_interpolation_names():
    rz = FrameResizer()
    assert rz.set_interpolation("lanczos")
    assert rz.set_interpolation("cubic")
    assert not rz.set_interpolation("bogus")


def test_fit_to_widget_letterbox():
    img = np.zeros((100, 100, 3), np.uint8)
    out = FrameResizer.fit_to_widget(img, 50, 200)   # width-constrained
    assert out.shape[1] == 50 and out.shape[0] == 50


def test_no_resize_at_100pct():
    rz = FrameResizer()
    img = np.zeros((30, 40, 3), np.uint8)
    rz.set_preset("100%")
    assert rz.resize(img).shape == img.shape
