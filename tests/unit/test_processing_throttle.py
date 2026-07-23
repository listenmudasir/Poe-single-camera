# -*- coding: utf-8 -*-
"""Analysis-rate cap and stream-change reset in ProcessingService.

ProcessingService subclasses QThread, so these tests need PyQt5; they are
skipped automatically where Qt is unavailable (e.g. a headless dev box) and
run on the target/CI where PyQt5 is installed.
"""
import pytest

pytest.importorskip("PyQt5")

from poe_single_aravis.services.processing_service import ProcessingService
from poe_single_aravis.imaging.analyzer import ImageAnalyzer
from poe_single_aravis.imaging.resizer import FrameResizer
from poe_single_aravis.imaging.white_balance import WhiteBalanceController
from poe_single_aravis.imaging.background_subtraction import make_processor


def _service():
    return ProcessingService(
        processor=make_processor("cpu"),
        resizer=FrameResizer(),
        wb=WhiteBalanceController(),
        analyzer=ImageAnalyzer(),
    )


def test_analysis_fps_maps_to_interval():
    svc = _service()
    svc.set_analysis_fps(0)
    assert svc._analysis_min_interval == 0.0          # 0 = every frame
    svc.set_analysis_fps(8)
    assert abs(svc._analysis_min_interval - 0.125) < 1e-9
    svc.set_analysis_fps(4)
    assert abs(svc._analysis_min_interval - 0.25) < 1e-9


def test_set_source_resets_cached_stats():
    svc = _service()
    svc._last_stats = object()
    svc._last_analysis_t = 123.0
    svc.set_source(None, None)
    assert svc._last_stats is None
    assert svc._last_analysis_t == 0.0
