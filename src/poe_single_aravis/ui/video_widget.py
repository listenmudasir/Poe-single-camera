# -*- coding: utf-8 -*-
"""
ui/video_widget.py
==================
Live video display with:
  - Aspect-ratio-preserving letterbox rendering
  - Difference picture-in-picture overlay (bottom-right)
  - Acquisition / processing FPS pill overlay
  - Flashing red border when a coverage alert is active
  - Double-click to open fullscreen
"""

from __future__ import annotations

import time
from typing import Optional

import cv2
import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap, QFont
from PyQt5.QtWidgets import QLabel, QSizePolicy

from .i18n import tr
from .theme import C


class VideoWidget(QLabel):
    double_clicked = pyqtSignal()

    def __init__(self, parent=None, min_size=(480, 360), display_fps_cap: int = 0) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(int(min_size[0]), int(min_size[1]))
        self._base_style = (
            f"background: #05070c; border: 1px solid {C.BORDER};"
            f" border-radius: 14px; color: {C.TEXT_FAINT}; font-size: 15px;")
        self.setStyleSheet(self._base_style)
        self.setText(tr("waiting_conn"))
        self.setFont(QFont("Noto Sans CJK TC", 14))

        self._show_pip = True
        self._last_bgr: Optional[np.ndarray] = None
        self._last_diff: Optional[np.ndarray] = None
        self._acq_fps = 0.0
        self._proc_fps = 0.0
        # Keeps the numpy buffer backing the current QImage alive.
        self._rgb_buf: Optional[np.ndarray] = None

        # Display FPS cap: frames arriving faster than this are coalesced so the
        # Qt render (resize + colour convert + upload) never runs more often
        # than needed — the key display-side win on a low-power Pi.
        self._min_interval = (1.0 / display_fps_cap) if display_fps_cap > 0 else 0.0
        self._last_render_t = 0.0
        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.timeout.connect(self._flush_pending)

        self._alerting = False
        self._flash_on = False
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(450)
        self._flash_timer.timeout.connect(self._flash_tick)

    # ── public API ────────────────────────────────────────────

    def set_show_pip(self, v: bool) -> None:
        self._show_pip = v

    def set_display_fps_cap(self, cap: int) -> None:
        self._min_interval = (1.0 / cap) if cap > 0 else 0.0

    def set_alert(self, active: bool) -> None:
        if active == self._alerting:
            return
        self._alerting = active
        if active:
            self._flash_timer.start()
        else:
            self._flash_timer.stop()
            self.setStyleSheet(self._base_style)

    def update_frame(self, bgr: np.ndarray, diff: Optional[np.ndarray] = None,
                     acq_fps: float = 0.0, proc_fps: float = 0.0) -> None:
        self._last_bgr = bgr
        self._last_diff = diff
        self._acq_fps = acq_fps
        self._proc_fps = proc_fps

        # Frame-rate cap: if we painted too recently, keep only the latest frame
        # and arm a trailing render so no frame is lost when the stream pauses.
        if self._min_interval > 0.0:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_render_t)
            if wait > 0.0:
                if not self._flush_timer.isActive():
                    self._flush_timer.start(max(1, int(wait * 1000)))
                return
            self._last_render_t = now
        self._render()

    def _flush_pending(self) -> None:
        self._last_render_t = time.monotonic()
        self._render()

    def last_frame(self) -> Optional[np.ndarray]:
        return self._last_bgr

    def clear_view(self) -> None:
        self._last_bgr = None
        self._last_diff = None
        self.setPixmap(QPixmap())
        self.setText(tr("waiting_conn"))

    # ── internal ──────────────────────────────────────────────

    def _flash_tick(self) -> None:
        self._flash_on = not self._flash_on
        col = "#ff2b2b" if self._flash_on else "#5c0d0d"
        self.setStyleSheet(
            f"background: #05070c; border: 3px solid {col};"
            f" border-radius: 14px; color: {C.TEXT_FAINT}; font-size: 15px;")

    def _render(self) -> None:
        if self._last_bgr is None:
            return
        wv, hv = self.width(), self.height()
        if wv <= 0 or hv <= 0:
            return

        fh, fw = self._last_bgr.shape[:2]
        scale = min(wv / fw, hv / fh)
        dw, dh = max(1, int(fw * scale)), max(1, int(fh * scale))
        scaled = cv2.resize(self._last_bgr, (dw, dh), interpolation=cv2.INTER_LINEAR)

        # Difference PiP (bottom-right)
        if self._show_pip and self._last_diff is not None:
            pip_w = max(96, dw // 4)
            pip_h = max(72, int(pip_w * dh / max(1, dw)))
            pip = cv2.resize(self._last_diff, (pip_w, pip_h))
            x0, y0 = dw - pip_w - 8, dh - pip_h - 8
            if x0 > 0 and y0 > 0:
                cv2.rectangle(scaled, (x0 - 2, y0 - 2), (x0 + pip_w + 1, y0 + pip_h + 1),
                              (90, 70, 40), 2)
                scaled[y0:y0 + pip_h, x0:x0 + pip_w] = pip

        # FPS pill (top-left)
        txt = f"ACQ {self._acq_fps:4.1f}   PROC {self._proc_fps:4.1f} fps"
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(scaled, (8, 8), (8 + tw + 16, 8 + th + 14), (18, 22, 32), -1)
        cv2.putText(scaled, txt, (16, 8 + th + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 230, 255), 1, cv2.LINE_AA)

        rgb = np.ascontiguousarray(cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB))
        h, w, ch = rgb.shape
        # QPixmap.fromImage copies the pixels into the pixmap synchronously, so
        # a per-frame QImage.copy() is redundant; we only need to keep the numpy
        # buffer alive for the duration of that call (hence the reference).
        self._rgb_buf = rgb
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(qimg))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render()

    def mouseDoubleClickEvent(self, event) -> None:
        self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)
