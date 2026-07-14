# -*- coding: utf-8 -*-
"""
imaging/background_subtraction.py
===================================
CPU and GPU coverage processors implementing the CoverageProcessor protocol.

CPU sequence (matches V4.0.1 behaviour):
  1. Grayscale conversion
  2. Resize to analysis size
  3. Gaussian blur
  4. Absolute difference vs frozen background
  5. Binary threshold
  6. Morphological close + open (ellipse kernel)
  7. External contour detection
  8. Coverage = sum(contour areas) / total pixels × 100
  9. Draw contours + label on colour diff image

GPU sequence (PyTorch):
  Same steps on GPU tensors; result is numerically close to CPU path.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

import cv2
import numpy as np

from ..domain.models import CoverageResult
from ..domain.errors import GpuError

log = logging.getLogger(__name__)


@runtime_checkable
class CoverageProcessor(Protocol):
    def set_background(self, frame: np.ndarray) -> None: ...
    def clear_background(self) -> None: ...
    def process(self, frame: np.ndarray, threshold: int) -> CoverageResult: ...
    def has_background(self) -> bool: ...


class CpuCoverageProcessor:
    """
    Pure OpenCV/NumPy implementation.
    Works without any GPU dependency.
    """

    def __init__(
        self,
        analysis_w: int = 640,
        analysis_h: int = 480,
        gaussian_kernel: int = 21,
        morphology_kernel: int = 5,
        alert_threshold: float = 20.0,
    ) -> None:
        self._aw   = analysis_w
        self._ah   = analysis_h
        self._gk   = gaussian_kernel if gaussian_kernel % 2 == 1 else gaussian_kernel + 1
        self._mk   = morphology_kernel
        self._alert = alert_threshold

        self._bg: Optional[np.ndarray] = None   # blurred grayscale background
        self._morph_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (self._mk, self._mk)
        )

    # ── protocol ──────────────────────────────────────────────

    def set_background(self, frame: np.ndarray) -> None:
        gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small  = cv2.resize(gray, (self._aw, self._ah))
        self._bg = cv2.GaussianBlur(small, (self._gk, self._gk), 0).copy()
        log.debug("Background captured: %s", self._bg.shape)

    def clear_background(self) -> None:
        self._bg = None

    def has_background(self) -> bool:
        return self._bg is not None

    def process(self, frame: np.ndarray, threshold: int) -> CoverageResult:
        if self._bg is None:
            blank = np.zeros((self._ah, self._aw, 3), dtype=np.uint8)
            cv2.putText(blank, "Background not set",
                        (10, self._ah // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (80, 80, 80), 2)
            return CoverageResult(
                coverage_percent=0.0,
                diff_image=blank,
                alert_active=False,
                background_set=False,
            )

        # 1. Grayscale + resize + blur
        gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small  = cv2.resize(gray, (self._aw, self._ah))
        blurred = cv2.GaussianBlur(small, (self._gk, self._gk), 0)

        # Safety: re-capture if shapes diverge
        if blurred.shape != self._bg.shape:
            log.warning("Background shape mismatch – resetting background")
            self._bg = blurred.copy()

        # 2. Absolute difference + threshold
        diff = cv2.absdiff(self._bg, blurred)
        _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

        # 3. Morphology
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, self._morph_kernel)
        cleaned = cv2.morphologyEx(closed, cv2.MORPH_OPEN,  self._morph_kernel)

        # 4. Contours + coverage
        contours, _ = cv2.findContours(
            cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        total_px   = cleaned.size
        covered_px = sum(cv2.contourArea(c) for c in contours)
        coverage   = (covered_px / total_px * 100.0) if total_px > 0 else 0.0

        # 5. Visualisation
        diff_bgr = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)
        cv2.drawContours(diff_bgr, contours, -1, (0, 255, 100), 2)
        cv2.putText(
            diff_bgr,
            f"Coverage: {coverage:.1f}%",
            (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 255), 2,
        )

        return CoverageResult(
            coverage_percent=coverage,
            diff_image=diff_bgr,
            alert_active=coverage >= self._alert,
            background_set=True,
        )

    def update_alert_threshold(self, pct: float) -> None:
        self._alert = pct


# ── GPU implementation (optional) ─────────────────────────────

_HAS_TORCH = False
try:
    import torch
    import torch.nn.functional as F
    _HAS_TORCH = True
except ImportError:
    pass


def _make_gaussian_kernel_torch(ksize: int, device):
    sigma = 0.3 * ((ksize - 1) * 0.5 - 1) + 0.8
    import torch
    ax = torch.arange(ksize, dtype=torch.float32, device=device) - (ksize - 1) / 2.0
    g1d = torch.exp(-(ax ** 2) / (2.0 * sigma * sigma))
    g1d = g1d / g1d.sum()
    return torch.outer(g1d, g1d).reshape(1, 1, ksize, ksize)


class CudaCoverageProcessor:
    """
    GPU-accelerated background subtraction using PyTorch.
    Falls back to CpuCoverageProcessor on init failure.
    """

    def __init__(
        self,
        analysis_w: int = 640,
        analysis_h: int = 480,
        gaussian_kernel: int = 21,
        morphology_kernel: int = 5,
        alert_threshold: float = 20.0,
    ) -> None:
        self._cpu_fallback: Optional[CpuCoverageProcessor] = None
        self._aw  = analysis_w
        self._ah  = analysis_h
        self._gk  = gaussian_kernel
        self._mk  = morphology_kernel
        self._alert = alert_threshold
        self._device = None
        self._gauss_kernel = None
        self._bg_tensor = None

        if not _HAS_TORCH:
            log.warning("PyTorch not available – falling back to CPU processor")
            self._init_fallback()
            return

        try:
            import torch
            if not torch.cuda.is_available():
                raise GpuError("CUDA not available")
            self._device = torch.device("cuda")
            self._gauss_kernel = _make_gaussian_kernel_torch(self._gk, self._device)
            log.info("CUDA coverage processor initialised on %s", self._device)
        except Exception as exc:
            log.warning("GPU init failed (%s) – falling back to CPU", exc)
            self._init_fallback()

    def _init_fallback(self) -> None:
        self._cpu_fallback = CpuCoverageProcessor(
            self._aw, self._ah, self._gk, self._mk, self._alert
        )

    def set_background(self, frame: np.ndarray) -> None:
        if self._cpu_fallback:
            return self._cpu_fallback.set_background(frame)
        try:
            import torch
            import torch.nn.functional as F
            gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, (self._aw, self._ah)).astype(np.float32) / 255.0
            t = torch.from_numpy(small).unsqueeze(0).unsqueeze(0).to(self._device)
            pad = self._gk // 2
            blurred = F.conv2d(t, self._gauss_kernel, padding=pad)
            self._bg_tensor = blurred.detach()
        except Exception as exc:
            log.warning("GPU set_background failed: %s – falling back", exc)
            self._init_fallback()
            self._cpu_fallback.set_background(frame)

    def clear_background(self) -> None:
        if self._cpu_fallback:
            return self._cpu_fallback.clear_background()
        self._bg_tensor = None

    def has_background(self) -> bool:
        if self._cpu_fallback:
            return self._cpu_fallback.has_background()
        return self._bg_tensor is not None

    def process(self, frame: np.ndarray, threshold: int) -> CoverageResult:
        if self._cpu_fallback:
            return self._cpu_fallback.process(frame, threshold)
        if self._bg_tensor is None:
            blank = np.zeros((self._ah, self._aw, 3), dtype=np.uint8)
            cv2.putText(blank, "Background not set",
                        (10, self._ah // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (80, 80, 80), 2)
            return CoverageResult(0.0, blank, False, False)
        try:
            import torch
            import torch.nn.functional as F
            gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small  = cv2.resize(gray, (self._aw, self._ah)).astype(np.float32) / 255.0
            t      = torch.from_numpy(small).unsqueeze(0).unsqueeze(0).to(self._device)
            pad    = self._gk // 2
            blurred = F.conv2d(t, self._gauss_kernel, padding=pad)
            diff   = torch.abs(blurred - self._bg_tensor)
            thr    = threshold / 255.0
            binary = (diff > thr).float()
            coverage = float(binary.mean().item()) * 100.0

            # Convert back for visualisation using CPU
            mask_np = (binary.squeeze().cpu().numpy() * 255).astype(np.uint8)
            diff_bgr = cv2.cvtColor(mask_np, cv2.COLOR_GRAY2BGR)
            contours, _ = cv2.findContours(mask_np, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(diff_bgr, contours, -1, (0, 255, 100), 2)
            cv2.putText(diff_bgr, f"Coverage: {coverage:.1f}%",
                        (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 255), 2)
            return CoverageResult(
                coverage_percent=coverage,
                diff_image=diff_bgr,
                alert_active=coverage >= self._alert,
                background_set=True,
            )
        except Exception as exc:
            log.warning("GPU process failed: %s – falling back to CPU", exc)
            self._init_fallback()
            if self._bg_tensor is not None:
                # Try to recover background on CPU
                self._cpu_fallback.set_background(frame)
            return self._cpu_fallback.process(frame, threshold)

    def update_alert_threshold(self, pct: float) -> None:
        self._alert = pct
        if self._cpu_fallback:
            self._cpu_fallback.update_alert_threshold(pct)


def make_processor(
    mode: str,
    analysis_w: int = 640,
    analysis_h: int = 480,
    gaussian_kernel: int = 21,
    morphology_kernel: int = 5,
    alert_threshold: float = 20.0,
) -> CoverageProcessor:
    """Factory: create CPU or GPU processor (with automatic fallback)."""
    kwargs = dict(
        analysis_w=analysis_w,
        analysis_h=analysis_h,
        gaussian_kernel=gaussian_kernel,
        morphology_kernel=morphology_kernel,
        alert_threshold=alert_threshold,
    )
    if mode == "cuda":
        return CudaCoverageProcessor(**kwargs)
    return CpuCoverageProcessor(**kwargs)
