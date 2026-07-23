# -*- coding: utf-8 -*-
import numpy as np
import cv2
from poe_single_aravis.imaging.analyzer import ImageAnalyzer


def _reference(frame):
    """Original (pre-optimization) statistics, used as a parity oracle."""
    b = frame[:, :, 0].astype(np.float32)
    g = frame[:, :, 1].astype(np.float32)
    r = frame[:, :, 2].astype(np.float32)
    mr, mg, mb = float(r.mean()), float(g.mean()), float(b.mean())
    brightness = float((0.299 * r + 0.587 * g + 0.114 * b).mean())
    hls = cv2.cvtColor(frame, cv2.COLOR_BGR2HLS)
    mh = float(hls[:, :, 0].mean())
    ml = float(hls[:, :, 1].mean() / 255.0 * 100.0)
    ms = float(hls[:, :, 2].mean() / 255.0 * 100.0)
    return mr, mg, mb, mh, ms, ml, brightness


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


def test_matches_reference_on_random_frames():
    """The optimized analyzer must stay numerically identical (to float
    rounding) to the original per-pixel implementation."""
    rng = np.random.default_rng(1234)
    for _ in range(15):
        frame = rng.integers(0, 256, (90, 120, 3), dtype=np.uint8)
        ref = _reference(frame)
        s = ImageAnalyzer.analyze(frame)
        got = (s.mean_r, s.mean_g, s.mean_b, s.mean_h,
               s.mean_s, s.mean_l, s.brightness)
        for a, b in zip(ref, got):
            assert abs(a - b) < 1e-3


def test_grayscale_frame_is_safe():
    gray = np.full((12, 12), 128, np.uint8)
    s = ImageAnalyzer.analyze(gray)
    assert abs(s.mean_r - 128) < 1e-6
    assert abs(s.brightness - 128) < 1e-6
    assert s.width == 12 and s.height == 12
