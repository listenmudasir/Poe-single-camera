# -*- coding: utf-8 -*-
import numpy as np
import pytest
from poe_single_aravis.imaging.background_subtraction import (
    CpuCoverageProcessor, make_processor,
)


def _bg_frame(val=0):
    return np.full((480, 640, 3), val, np.uint8)


def test_background_not_set_reports_zero():
    p = CpuCoverageProcessor()
    r = p.process(_bg_frame(0), threshold=5)
    assert not r.background_set and r.coverage_percent == 0.0
    assert not p.has_background()


def test_capture_and_clear_background():
    p = CpuCoverageProcessor()
    p.set_background(_bg_frame(0))
    assert p.has_background()
    p.clear_background()
    assert not p.has_background()


def test_identical_frame_zero_coverage():
    p = CpuCoverageProcessor()
    p.set_background(_bg_frame(0))
    r = p.process(_bg_frame(0), threshold=5)
    assert r.background_set and r.coverage_percent < 0.5


def test_large_change_high_coverage_and_alert():
    p = CpuCoverageProcessor(alert_threshold=20.0)
    p.set_background(_bg_frame(0))
    # A big bright block over a dark background
    frame = _bg_frame(0)
    frame[100:400, 100:540] = 255
    r = p.process(frame, threshold=5)
    assert r.coverage_percent > 20.0
    assert r.alert_active
    assert r.diff_image.shape[2] == 3


def test_threshold_gates_small_differences():
    p = CpuCoverageProcessor()
    p.set_background(_bg_frame(50))
    frame = _bg_frame(58)                 # +8 everywhere
    low = p.process(frame, threshold=5).coverage_percent
    high = p.process(frame, threshold=100).coverage_percent
    assert low > high                     # higher threshold ⇒ less coverage


def test_alert_threshold_boundary():
    # Full-frame change gives ≈100% coverage (morphology trims a few edge px).
    p_lo = CpuCoverageProcessor(alert_threshold=90.0)
    p_hi = CpuCoverageProcessor(alert_threshold=100.0)
    for p in (p_lo, p_hi):
        p.set_background(_bg_frame(0))
    frame = _bg_frame(0); frame[:] = 255
    r_lo = p_lo.process(frame, threshold=5)
    r_hi = p_hi.process(frame, threshold=5)
    assert r_lo.coverage_percent > 95
    assert r_lo.alert_active            # ≥ 90 → alert
    assert not r_hi.alert_active        # ≈99.6 < 100 → no alert


def test_cpu_gpu_tolerance():
    """CUDA path falls back to CPU here (no torch); result must match CPU."""
    cpu = CpuCoverageProcessor()
    gpu = make_processor("cuda")          # → fallback or real GPU
    for proc in (cpu, gpu):
        proc.set_background(_bg_frame(0))
    frame = _bg_frame(0); frame[100:300, 100:300] = 200
    c = cpu.process(frame, 5).coverage_percent
    g = gpu.process(frame, 5).coverage_percent
    assert abs(c - g) < 5.0               # within tolerance
