# -*- coding: utf-8 -*-
"""
services/processing_service.py
================================
Processing worker – consumes frames from the LatestFrameSlot,
runs analysis + background subtraction, emits results to the Qt thread.

Runs in a dedicated QThread.  Never touches Aravis buffers.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal
import numpy as np

from ..domain.models import Frame, ImageStatistics, CoverageResult, StreamStatistics
from ..imaging.analyzer import ImageAnalyzer
from ..imaging.white_balance import WhiteBalanceController
from ..imaging.resizer import FrameResizer
from ..imaging.background_subtraction import CoverageProcessor

log = logging.getLogger(__name__)


class ProcessingService(QThread):
    """
    Frame processing pipeline worker.

    Signals (all emitted on the Qt main thread via the signal/slot mechanism):
        frame_processed(bgr_image, stats, coverage_result)
        fps_updated(acq_fps, proc_fps, display_fps)
    """

    frame_processed = pyqtSignal(np.ndarray, object, object)
    # (bgr_frame, ImageStatistics | None, CoverageResult | None)

    fps_updated = pyqtSignal(float, float, float)
    # (acquisition_fps, processing_fps, display_fps)

    def __init__(
        self,
        processor: CoverageProcessor,
        resizer: FrameResizer,
        wb: WhiteBalanceController,
        analyzer: ImageAnalyzer,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._slot      = None    # LatestFrameSlot – set per stream via set_source()
        self._ss        = None    # StreamStatistics – set per stream
        self._processor = processor
        self._resizer   = resizer
        self._wb        = wb
        self._analyzer  = analyzer
        self._logger    = None    # CoverageLogger – optional

        self._running  = True
        self._do_analysis   = True
        self._do_subtraction = False
        self._threshold = 5
        self._proc_mode = "cpu"
        self._lock      = threading.Lock()

        # Pending background-capture request (captured from next frame)
        self._capture_bg_pending = False

        # FPS tracking
        self._proc_count  = 0
        self._fps_t0      = time.monotonic()
        self._proc_fps    = 0.0
        self._display_fps = 0.0

    # ── control ───────────────────────────────────────────────

    def set_source(self, frame_slot, stream_stats: Optional[StreamStatistics]) -> None:
        """Attach the current stream's frame slot + stats (or None to pause)."""
        with self._lock:
            self._slot = frame_slot
            self._ss   = stream_stats

    def set_logger(self, logger) -> None:
        self._logger = logger

    def set_do_analysis(self, v: bool) -> None:
        self._do_analysis = v

    def set_do_subtraction(self, v: bool) -> None:
        self._do_subtraction = v

    def set_threshold(self, t: int) -> None:
        self._threshold = t

    def set_processing_mode(self, mode: str) -> None:
        self._proc_mode = mode

    def set_processor(self, processor: CoverageProcessor) -> None:
        """Swap the coverage processor (e.g. CPU↔CUDA). Background is reset."""
        self._processor = processor

    def capture_background(self, frame: Optional[np.ndarray] = None) -> None:
        """Capture background now (if frame given) or from the next processed frame."""
        if frame is not None:
            self._processor.set_background(frame)
        else:
            self._capture_bg_pending = True

    def reset_background(self) -> None:
        self._processor.clear_background()

    def has_background(self) -> bool:
        try:
            return self._processor.has_background()
        except Exception:
            return False

    # ── QThread.run ───────────────────────────────────────────

    def run(self) -> None:
        while self._running:
            with self._lock:
                slot = self._slot
                ss   = self._ss
            if slot is None:
                time.sleep(0.05)
                continue

            if not slot.wait(0.05):
                continue

            frame: Optional[Frame] = slot.take()
            if frame is None:
                continue

            bgr = frame.image.copy()  # processing-side copy

            # White balance
            if self._wb.r_gain != 1.0 or self._wb.g_gain != 1.0 or self._wb.b_gain != 1.0:
                bgr = self._wb.apply(bgr)

            # Pending background capture (from full white-balanced frame)
            if self._capture_bg_pending:
                self._capture_bg_pending = False
                try:
                    self._processor.set_background(bgr)
                except Exception as exc:
                    log.warning("Background capture failed: %s", exc)

            # Resize for display
            display_frame = self._resizer.resize(bgr)

            # Image statistics
            stats: Optional[ImageStatistics] = None
            if self._do_analysis:
                try:
                    stats = self._analyzer.analyze(bgr)
                except Exception as exc:
                    log.warning("Analysis failed: %s", exc)

            # Coverage
            coverage: Optional[CoverageResult] = None
            if self._do_subtraction:
                try:
                    # Processor internally resizes to analysis size
                    coverage = self._processor.process(bgr, self._threshold)
                except Exception as exc:
                    log.warning("Coverage processing failed: %s", exc)

            # FPS
            acq_fps = ss.acquisition_fps if ss else 0.0
            self._proc_count += 1
            now = time.monotonic()
            elapsed = now - self._fps_t0
            if elapsed >= 1.0:
                self._proc_fps = self._proc_count / elapsed
                self._proc_count = 0
                self._fps_t0 = now
                if ss:
                    ss.processing_fps = self._proc_fps
                self.fps_updated.emit(acq_fps, self._proc_fps, self._display_fps)

            # Per-interval coverage logging (writes off this thread, never on UI)
            if coverage is not None and coverage.background_set and self._logger is not None:
                try:
                    self._logger.try_log(
                        coverage_percent=coverage.coverage_percent,
                        acquisition_fps=acq_fps,
                        processing_fps=self._proc_fps,
                        processing_mode=self._proc_mode,
                        alert_active=coverage.alert_active,
                    )
                except Exception as exc:
                    log.warning("Coverage logging failed: %s", exc)

            self.frame_processed.emit(display_frame, stats, coverage)

    def stop(self) -> None:
        self._running = False
        self.wait(3000)
