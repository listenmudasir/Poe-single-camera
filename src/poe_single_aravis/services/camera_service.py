# -*- coding: utf-8 -*-
"""
services/camera_service.py
===========================
Application service layer – the single orchestrator that the UI talks to.

It owns:
  * one CameraDiscovery
  * one CameraSession (the single camera)
  * one persistent ProcessingService (QThread)
  * one persistent HardwareMonitor  (QThread)
  * one CoverageLogger (per connected camera)
  * one SnapshotService
  * the imaging helpers (analyzer, white balance, resizer, coverage processor)

The UI NEVER touches Aravis or the imaging modules directly – it calls
methods here and connects to the Qt signals below.  Everything Aravis-related
is funnelled through CameraSession, keeping API compatibility localised.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import List, Optional

from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np

from ..domain.camera_state import CameraState
from ..domain.models import (
    CameraDescriptor, CameraCapabilities, ImageStatistics, CoverageResult,
)
from ..domain.errors import PoeError
from ..settings import Settings
from ..aravis_backend.discovery import CameraDiscovery
from ..aravis_backend.camera import CameraSession
from ..imaging.analyzer import ImageAnalyzer
from ..imaging.white_balance import WhiteBalanceController
from ..imaging.resizer import FrameResizer
from ..imaging.background_subtraction import make_processor
from .processing_service import ProcessingService
from .hardware_monitor import HardwareMonitor
from .coverage_logger import CoverageLogger
from .snapshot_service import SnapshotService

log = logging.getLogger(__name__)


class CameraService(QObject):
    """Single façade over the whole acquisition + processing stack."""

    # ── signals (all delivered to the Qt main thread) ─────────
    devices_updated   = pyqtSignal(list)                 # list[CameraDescriptor]
    state_changed     = pyqtSignal(object, object)       # (old CameraState, new CameraState)
    capabilities_ready = pyqtSignal(object)              # CameraCapabilities
    frame_ready       = pyqtSignal(np.ndarray, object, object)  # display_bgr, stats, coverage
    fps_updated       = pyqtSignal(float, float, float)  # acq, proc, display
    error_message     = pyqtSignal(str)
    info_message      = pyqtSignal(str)
    reconnecting      = pyqtSignal(int, int)             # attempt, max
    reconnected       = pyqtSignal()

    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self._settings = settings

        # backend
        self._discovery = CameraDiscovery()
        self._session = CameraSession(
            buffer_count=settings.buffer_count,
            frame_timeout_ms=settings.frame_timeout_ms,
            consecutive_failure_threshold=settings.consecutive_failure_threshold,
            on_state_change=self._on_state_change,
            on_error=self._on_backend_error,
        )

        # imaging helpers (shared, owned here)
        self.analyzer = ImageAnalyzer()
        self.white_balance = WhiteBalanceController()
        self.resizer = FrameResizer()
        self._processor = make_processor(
            settings.processing_mode,
            analysis_w=settings.analysis_width,
            analysis_h=settings.analysis_height,
            gaussian_kernel=settings.gaussian_kernel,
            morphology_kernel=settings.morphology_kernel,
            alert_threshold=settings.alert_threshold_percent,
        )
        self._proc_mode = settings.processing_mode

        # processing worker (persistent)
        self.processing = ProcessingService(
            processor=self._processor,
            resizer=self.resizer,
            wb=self.white_balance,
            analyzer=self.analyzer,
        )
        self.processing.set_processing_mode(settings.processing_mode)
        self.processing.set_threshold(settings.difference_threshold)
        self.processing.frame_processed.connect(self.frame_ready)
        self.processing.fps_updated.connect(self.fps_updated)
        self.processing.start()

        # hardware monitor (persistent)
        self.hardware = HardwareMonitor(settings.monitor_interval_seconds)

        # snapshot + logging
        self.snapshots = SnapshotService()
        self._logger: Optional[CoverageLogger] = None

        # reconnect state
        self._reconnect_thread: Optional[threading.Thread] = None
        self._reconnect_cancel = threading.Event()
        self._was_streaming_on_error = False

    # ── lifecycle ─────────────────────────────────────────────

    def start_background_services(self) -> None:
        self.hardware.start()

    def shutdown(self) -> None:
        """Orderly shutdown – no forced thread termination."""
        log.info("CameraService shutting down …")
        self._reconnect_cancel.set()
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            self._reconnect_thread.join(timeout=2.0)
        try:
            self.processing.stop()
        except Exception:
            pass
        try:
            self.hardware.stop()
        except Exception:
            pass
        try:
            self._session.disconnect()
        except Exception:
            pass
        log.info("CameraService shut down cleanly")

    # ── discovery ─────────────────────────────────────────────

    def refresh_devices(self) -> List[CameraDescriptor]:
        try:
            devs = self._discovery.refresh()
        except Exception as exc:
            log.error("Discovery failed: %s", exc)
            self.error_message.emit(f"裝置搜尋失敗 / Discovery failed: {exc}")
            devs = []
        self.devices_updated.emit(devs)
        return devs

    # ── connection ────────────────────────────────────────────

    @property
    def state(self) -> CameraState:
        return self._session.state

    @property
    def capabilities(self) -> Optional[CameraCapabilities]:
        return self._session.capabilities

    def connect(self, device_id: str) -> bool:
        # A manual connect supersedes any in-flight auto-reconnect.
        self._reconnect_cancel.set()
        try:
            caps = self._session.connect(device_id)
        except PoeError as exc:
            self.error_message.emit(f"連線失敗 / Connect failed: {exc}")
            return False
        except Exception as exc:
            self.error_message.emit(f"連線失敗 / Connect failed: {exc}")
            return False

        # per-camera coverage logger keyed on serial (or sanitised device id)
        cam_id = caps.serial_number or caps.device_id or device_id
        self._logger = CoverageLogger(
            camera_id=cam_id,
            log_dir=self._settings.log_directory,
            interval_seconds=self._settings.log_interval_seconds,
        )
        self._logger.set_enabled(self._settings.logging_enabled)
        self.processing.set_logger(self._logger)

        self.capabilities_ready.emit(caps)
        return True

    def disconnect(self) -> None:
        """User-initiated disconnect: release the camera AND immediately halt
        the analysis session (subtraction, alerts, background, logging).

        Note: the automatic ERROR→reconnect path deliberately does NOT call
        this — a network glitch must resume monitoring with the same
        background, so it releases only the session, not the analysis state.
        """
        self._reconnect_cancel.set()
        self.processing.set_source(None, None)
        # Halt analysis now — nothing may keep alerting after the operator
        # releases the camera, and a stale background must not survive into
        # the next connection (scene/ROI/format may all have changed).
        self.processing.set_do_subtraction(False)
        self.processing.reset_background()
        try:
            self._session.disconnect()
        except Exception as exc:
            log.warning("Disconnect error: %s", exc)

    # ── acquisition ───────────────────────────────────────────

    def start(self) -> bool:
        try:
            self._session.start_acquisition()
        except PoeError as exc:
            self.error_message.emit(f"取像啟動失敗 / Start failed: {exc}")
            return False
        # Attach the freshly-created stream slot to the processing worker
        self.processing.set_source(self._session.frame_slot, self._session.stream_stats)
        return True

    def stop(self) -> None:
        self.processing.set_source(None, None)
        try:
            self._session.stop_acquisition()
        except Exception as exc:
            log.warning("Stop error: %s", exc)

    def software_trigger(self) -> None:
        self._session.software_trigger()

    # ── camera controls (capability-aware handled by UI) ──────

    def set_exposure(self, us: float) -> None:
        self._guarded(lambda: self._session.set_exposure(us), "曝光 / exposure")

    def set_gain(self, db: float) -> None:
        self._guarded(lambda: self._session.set_gain(db), "增益 / gain")

    def set_frame_rate(self, fps: float) -> None:
        self._guarded(lambda: self._session.set_frame_rate(fps), "幀率 / frame rate")

    def set_trigger_mode(self, software: bool) -> None:
        self._guarded(lambda: self._session.set_trigger_mode(software), "觸發 / trigger")

    def set_region(self, x: int, y: int, w: int, h: int) -> None:
        """ROI change requires a stopped stream; caller must stop first."""
        was_streaming = self._session.state == CameraState.STREAMING
        if was_streaming:
            self.stop()
        self._guarded(lambda: self._session.set_region(x, y, w, h), "ROI")
        if was_streaming:
            self.start()

    def set_pixel_format(self, fmt: str) -> None:
        was_streaming = self._session.state == CameraState.STREAMING
        if was_streaming:
            self.stop()
        self._guarded(lambda: self._session.set_pixel_format(fmt), "像素格式 / pixel format")
        if was_streaming:
            self.start()

    def read_capabilities(self) -> Optional[CameraCapabilities]:
        return self._session.capabilities

    def read_current_params(self) -> dict:
        """Live read of exposure/gain/frame-rate/region (for 'Get Param')."""
        return self._session.read_current_params()

    def reset_region_to_max(self):
        """Reset ROI to full sensor (stops/restarts stream if needed)."""
        was_streaming = self._session.state == CameraState.STREAMING
        if was_streaming:
            self.stop()
        result = None
        try:
            result = self._session.reset_region_to_max()
        except Exception as exc:
            self.error_message.emit(f"ROI: {exc}")
        if was_streaming:
            self.start()
        return result

    def hardware_auto_white_balance(self) -> None:
        if not self._session.auto_white_balance():
            self.info_message.emit(
                "此相機不支援硬體白平衡 / Hardware white balance unsupported")
        else:
            self.info_message.emit("已執行單次自動白平衡 / Auto white balance done")

    # ── processing / coverage controls ────────────────────────

    def set_subtraction_enabled(self, enabled: bool) -> None:
        self.processing.set_do_subtraction(enabled)

    def set_threshold(self, t: int) -> None:
        self.processing.set_threshold(t)

    def set_alert_threshold(self, pct: float) -> None:
        try:
            self._processor.update_alert_threshold(pct)
        except Exception:
            pass

    def capture_background(self) -> None:
        self.processing.capture_background()

    def reset_background(self) -> None:
        self.processing.reset_background()

    def has_background(self) -> bool:
        return self.processing.has_background()

    def set_processing_mode(self, mode: str) -> str:
        """Switch CPU/CUDA. Returns the effective mode after fallback."""
        if mode == self._proc_mode:
            return self._proc_mode
        new_proc = make_processor(
            mode,
            analysis_w=self._settings.analysis_width,
            analysis_h=self._settings.analysis_height,
            gaussian_kernel=self._settings.gaussian_kernel,
            morphology_kernel=self._settings.morphology_kernel,
            alert_threshold=self._settings.alert_threshold_percent,
        )
        self._processor = new_proc
        self.processing.set_processor(new_proc)
        self.processing.set_processing_mode(mode)
        self._proc_mode = mode
        # Detect a silent CPU fallback so the UI can report it
        effective = mode
        if mode == "cuda" and getattr(new_proc, "_cpu_fallback", None) is not None:
            effective = "cpu"
            self.info_message.emit(
                "CUDA 不可用，已回退至 CPU / CUDA unavailable – fell back to CPU"
            )
        return effective

    # ── snapshot ──────────────────────────────────────────────

    def save_snapshot(self, frame: np.ndarray, ext: str = ".png") -> Optional[str]:
        if frame is None:
            self.error_message.emit("尚無影像可儲存 / No frame to save")
            return None
        try:
            path = self.snapshots.save(frame, ext=ext)
            self.info_message.emit(f"已儲存 / Saved: {os.path.basename(path)}")
            return path
        except Exception as exc:
            self.error_message.emit(f"儲存失敗 / Save failed: {exc}")
            return None

    # ── reconnection ──────────────────────────────────────────

    def cancel_reconnect(self) -> None:
        self._reconnect_cancel.set()

    def _begin_reconnect(self) -> None:
        if not self._settings.reconnect_enabled:
            return
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        device_id = self._session.device_id
        if not device_id:
            return
        self._reconnect_cancel.clear()
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            args=(device_id, self._was_streaming_on_error),
            name="camera-reconnect",
            daemon=True,
        )
        self._reconnect_thread.start()

    def _reconnect_loop(self, device_id: str, restart_stream: bool) -> None:
        max_attempts = self._settings.max_reconnect_attempts
        interval = self._settings.reconnect_interval_seconds
        for attempt in range(1, max_attempts + 1):
            if self._reconnect_cancel.wait(interval):
                log.info("Reconnect cancelled")
                return
            self.reconnecting.emit(attempt, max_attempts)
            try:
                # Release any half-open handles, then re-discover + reopen
                try:
                    self._session.disconnect()
                except Exception:
                    pass
                self._discovery.refresh()
                caps = self._session.connect(device_id)
                self._session.reapply_settings()
                if self._logger is None:
                    cam_id = caps.serial_number or caps.device_id or device_id
                    self._logger = CoverageLogger(
                        camera_id=cam_id,
                        log_dir=self._settings.log_directory,
                        interval_seconds=self._settings.log_interval_seconds,
                    )
                    self.processing.set_logger(self._logger)
                self.capabilities_ready.emit(caps)
                if restart_stream:
                    self._session.start_acquisition()
                    self.processing.set_source(
                        self._session.frame_slot, self._session.stream_stats
                    )
                self.reconnected.emit()
                self.info_message.emit(
                    f"已重新連線 / Reconnected (attempt {attempt})"
                )
                return
            except Exception as exc:
                log.warning("Reconnect attempt %d/%d failed: %s",
                            attempt, max_attempts, exc)
        self.error_message.emit(
            "重新連線失敗，已達最大次數 / Reconnect failed after max attempts"
        )

    # ── backend callbacks ─────────────────────────────────────

    def _on_state_change(self, old: CameraState, new: CameraState) -> None:
        self.state_changed.emit(old, new)

    def _on_backend_error(self, message: str) -> None:
        # Called from the acquisition thread on consecutive failures / errors.
        self._was_streaming_on_error = True
        self.processing.set_source(None, None)
        self.error_message.emit(message)
        self._begin_reconnect()

    # ── helpers ───────────────────────────────────────────────

    def _guarded(self, fn, label: str) -> None:
        try:
            fn()
        except PoeError as exc:
            self.error_message.emit(f"{label}: {exc}")
        except Exception as exc:
            self.error_message.emit(f"{label}: {exc}")
