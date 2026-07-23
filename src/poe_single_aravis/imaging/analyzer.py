# -*- coding: utf-8 -*-
"""
imaging/analyzer.py
====================
Stateless image analysis – RGB, HSL, brightness statistics.
No Python pixel loops; uses vectorized numpy/OpenCV.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..domain.models import ImageStatistics


class ImageAnalyzer:
    """Analyzes a single BGR uint8 frame."""

    @staticmethod
    def analyze(frame: np.ndarray) -> ImageStatistics:
        """
        Compute RGB/HSL/brightness statistics.

        Args:
            frame: BGR uint8 ndarray.

        Returns:
            ImageStatistics.
        """
        if frame is None or frame.size == 0:
            return ImageStatistics(0, 0, 0, 0, 0, 0, 0, 0, 0)

        h, w = frame.shape[:2]

        # ── RGB means (frame is BGR) ─────────────────────────
        # cv2.mean averages each channel in one C call, avoiding the three
        # full-frame float32 temporaries the old per-channel .astype() path
        # created — a meaningful CPU saving on the Raspberry Pi.
        if frame.ndim == 3:
            m = cv2.mean(frame)                       # (B, G, R, A)
            mean_b, mean_g, mean_r = float(m[0]), float(m[1]), float(m[2])
            # BT.601 luminance of the mean == mean of the per-pixel luminance
            # (averaging is linear), so no per-pixel luminance pass is needed.
            brightness = 0.299 * mean_r + 0.587 * mean_g + 0.114 * mean_b
        else:
            gray_mean = float(cv2.mean(frame)[0])
            mean_r = mean_g = mean_b = gray_mean
            brightness = gray_mean

        # ── HSL via OpenCV HLS (order: H, L, S) ──────────────
        if frame.ndim == 3:
            hls = cv2.cvtColor(frame, cv2.COLOR_BGR2HLS)
            mh, ml, ms, _ = cv2.mean(hls)
            mean_h = float(mh)                        # 0–180
            mean_l = float(ml) / 255.0 * 100.0        # %
            mean_s = float(ms) / 255.0 * 100.0        # %
        else:
            mean_h = 0.0
            mean_l = brightness / 255.0 * 100.0
            mean_s = 0.0

        return ImageStatistics(
            mean_r=mean_r,
            mean_g=mean_g,
            mean_b=mean_b,
            mean_h=mean_h,
            mean_s=mean_s,
            mean_l=mean_l,
            brightness=brightness,
            width=w,
            height=h,
        )
