# -*- coding: utf-8 -*-
"""
services/coverage_logger.py
============================
Per-minute CSV coverage logger for a single camera.
File identity is derived from the camera serial number.
Writes are atomic (append-safe); never blocks the UI thread.
"""

from __future__ import annotations

import csv
import logging
import os
import threading
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


class CoverageLogger:
    """
    Logs coverage data once per (configurable) interval.
    All I/O happens on an internal background thread, never on the
    Qt main thread.

    CSV format:
        timestamp, camera_id, coverage_percent, acq_fps, proc_fps,
        processing_mode, alert_active
    """

    FIELDNAMES = [
        "timestamp", "camera_id", "coverage_percent",
        "acquisition_fps", "processing_fps",
        "processing_mode", "alert_active",
    ]

    def __init__(
        self,
        camera_id: str,
        log_dir: str = "./data/coverage",
        interval_seconds: int = 60,
    ) -> None:
        self._camera_id  = camera_id
        self._log_dir    = log_dir
        self._interval   = interval_seconds
        self._enabled    = True

        self._lock           = threading.Lock()
        self._last_logged_ts: Optional[datetime] = None

        # Sanitise camera_id for use in filenames
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in camera_id)
        self._filepath = os.path.join(log_dir, f"{safe_id}.csv")

        self._ensure_file()

    # ── public API ────────────────────────────────────────────

    def try_log(
        self,
        coverage_percent: float,
        acquisition_fps: float,
        processing_fps: float,
        processing_mode: str,
        alert_active: bool,
        when: Optional[datetime] = None,
    ) -> bool:
        """
        Log a data point if the interval has elapsed.

        Returns True if a record was written, False otherwise.
        """
        if not self._enabled:
            return False

        now = when or datetime.now()
        with self._lock:
            if self._last_logged_ts is not None:
                if (now - self._last_logged_ts).total_seconds() < self._interval:
                    return False
            self._last_logged_ts = now

        # Write on the calling thread (which is the processing thread, not Qt)
        threading.Thread(
            target=self._write_row,
            args=(now, coverage_percent, acquisition_fps,
                  processing_fps, processing_mode, alert_active),
            daemon=True,
        ).start()
        return True

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_interval(self, seconds: int) -> None:
        self._interval = max(10, seconds)

    def get_filepath(self) -> str:
        return self._filepath

    # ── reading for chart ─────────────────────────────────────

    def read_recent(self, days: int) -> list[dict]:
        """Read rows from the last N days. Returns list of dicts."""
        rows = []
        cutoff = datetime.now() - timedelta(days=days)
        try:
            if not os.path.exists(self._filepath):
                return rows
            with open(self._filepath, "r", newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M")
                        if ts >= cutoff:
                            row["_ts"] = ts
                            rows.append(row)
                    except Exception:
                        pass
        except Exception as exc:
            log.warning("Failed to read coverage log: %s", exc)
        return rows

    # ── private ───────────────────────────────────────────────

    def _ensure_file(self) -> None:
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            if not os.path.exists(self._filepath):
                with open(self._filepath, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.DictWriter(fh, fieldnames=self.FIELDNAMES)
                    writer.writeheader()
        except Exception as exc:
            log.warning("Cannot create coverage log file: %s", exc)

    def _write_row(
        self,
        when: datetime,
        coverage: float,
        acq_fps: float,
        proc_fps: float,
        mode: str,
        alert: bool,
    ) -> None:
        try:
            with open(self._filepath, "a", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=self.FIELDNAMES)
                writer.writerow({
                    "timestamp":        when.strftime("%Y-%m-%d %H:%M"),
                    "camera_id":        self._camera_id,
                    "coverage_percent": f"{coverage:.2f}",
                    "acquisition_fps":  f"{acq_fps:.1f}",
                    "processing_fps":   f"{proc_fps:.1f}",
                    "processing_mode":  mode,
                    "alert_active":     "1" if alert else "0",
                })
        except Exception as exc:
            log.warning("Failed to write coverage log row: %s", exc)
