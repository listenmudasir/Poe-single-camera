# -*- coding: utf-8 -*-
"""
domain/models.py
================
Core data models for the single-camera POE application.
All are immutable frozen dataclasses for thread-safety.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass(frozen=True)
class CameraDescriptor:
    """Immutable description of a discovered camera."""
    device_id: str
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    transport: Optional[str] = None

    def display_name(self) -> str:
        parts = []
        if self.vendor:
            parts.append(self.vendor)
        if self.model:
            parts.append(self.model)
        if self.serial_number:
            parts.append(f"[{self.serial_number}]")
        return " ".join(parts) if parts else self.device_id

    def __str__(self) -> str:
        return f"{self.display_name()} ({self.device_id})"


@dataclass(frozen=True)
class Frame:
    """
    A single acquired frame with its own NumPy-owned memory.
    The image is always a BGR uint8 ndarray after conversion.
    """
    image: np.ndarray          # BGR uint8, shape (H, W, 3) or (H, W) for mono
    width: int
    height: int
    pixel_format: str
    frame_id: Optional[int]
    camera_timestamp_ns: Optional[int]
    host_timestamp_ns: int = field(default_factory=lambda: time.time_ns())

    def is_color(self) -> bool:
        return self.image.ndim == 3 and self.image.shape[2] == 3

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Frame):
            return NotImplemented
        return self.frame_id == other.frame_id and self.host_timestamp_ns == other.host_timestamp_ns


@dataclass(frozen=True)
class CameraCapabilities:
    """
    Camera capabilities read at connection time.
    Controls which UI elements are enabled.
    """
    has_exposure: bool = False
    exposure_min: float = 0.0
    exposure_max: float = 0.0
    exposure_current: float = 0.0

    has_gain: bool = False
    gain_min: float = 0.0
    gain_max: float = 0.0
    gain_current: float = 0.0

    has_frame_rate: bool = False
    fps_min: float = 0.0
    fps_max: float = 0.0
    fps_current: float = 0.0

    has_roi: bool = False
    roi_x: int = 0
    roi_y: int = 0
    roi_w: int = 0
    roi_h: int = 0
    sensor_w: int = 0
    sensor_h: int = 0

    has_trigger: bool = False
    trigger_mode: str = "Off"

    pixel_format: str = ""
    available_pixel_formats: tuple = ()

    vendor: str = ""
    model: str = ""
    serial_number: str = ""
    device_id: str = ""


@dataclass(frozen=True)
class ImageStatistics:
    """Per-frame image analysis results."""
    mean_r: float
    mean_g: float
    mean_b: float
    mean_h: float
    mean_s: float
    mean_l: float
    brightness: float
    width: int
    height: int


@dataclass(frozen=True)
class CoverageResult:
    """Result from the background subtraction + coverage pipeline."""
    coverage_percent: float
    diff_image: np.ndarray        # BGR image with contours drawn
    alert_active: bool
    background_set: bool

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CoverageResult):
            return NotImplemented
        return self.coverage_percent == other.coverage_percent


@dataclass
class StreamStatistics:
    """Mutable streaming statistics – updated by the acquisition worker."""
    frames_completed: int = 0
    frames_failed: int = 0
    frames_timeout: int = 0
    frames_dropped: int = 0      # dropped because processing was busy
    acquisition_fps: float = 0.0
    display_fps: float = 0.0
    processing_fps: float = 0.0

    def reset(self) -> None:
        self.frames_completed = 0
        self.frames_failed = 0
        self.frames_timeout = 0
        self.frames_dropped = 0
        self.acquisition_fps = 0.0
        self.display_fps = 0.0
        self.processing_fps = 0.0
