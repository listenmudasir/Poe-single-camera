# -*- coding: utf-8 -*-
import numpy as np
from poe_single_aravis.imaging.analyzer import ImageAnalyzer


def test_solid_color_rgb_means():
    # BGR image, solid (b=10, g=20, r=30)
    img = np.zeros((40, 50, 3), np.uint8)
    img[:, :, 0] = 10; img[:, :, 1] = 20; img[:, :, 2] = 30
    s = ImageAnalyzer.analyze(img)
    assert s.mean_b == 10 and s.mean_g == 20 and s.mean_r == 30
    assert s.width == 50 and s.height == 40


def test_bt601_brightness():
    img = np.zeros((10, 10, 3), np.uint8)
    img[:, :, 0] = 100  # B
    img[:, :, 1] = 150  # G
    img[:, :, 2] = 200  # R
    s = ImageAnalyzer.analyze(img)
    expected = 0.299 * 200 + 0.587 * 150 + 0.114 * 100
    assert abs(s.brightness - expected) < 0.5


def test_white_frame_high_lightness():
    img = np.full((8, 8, 3), 255, np.uint8)
    s = ImageAnalyzer.analyze(img)
    assert s.mean_l > 95 and s.brightness > 250


def test_empty_frame_is_safe():
    s = ImageAnalyzer.analyze(np.zeros((0,), np.uint8))
    assert s.width == 0 and s.height == 0
