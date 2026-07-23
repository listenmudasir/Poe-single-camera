# -*- coding: utf-8 -*-
"""
settings.py
===========
Application configuration loader.
Reads config/default.yaml; validates each section;
provides typed defaults for any missing or invalid values.
"""

from __future__ import annotations

import os
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Defaults (spec §17) ───────────────────────────────────────
_DEFAULTS: dict[str, Any] = {
    "camera": {
        "auto_connect_first": False,
        "buffer_count": 24,
        "frame_timeout_ms": 500,
        "reconnect_enabled": True,
        "reconnect_interval_seconds": 3,
        "max_reconnect_attempts": 10,
        "consecutive_failure_threshold": 5,
    },
    "processing": {
        "mode": "cpu",
        "analysis_width": 640,
        "analysis_height": 480,
        "difference_threshold": 5,
        "gaussian_kernel": 21,
        "morphology_kernel": 5,
        "alert_threshold_percent": 20.0,
        # Max times per second the RGB/HSL/brightness statistics are recomputed.
        # Decouples the analysis CPU cost from the acquisition frame rate on the
        # Raspberry Pi; 0 means "every frame". The video display is unaffected.
        "analysis_fps": 8,
    },
    "logging": {
        "enabled": True,
        "interval_seconds": 60,
        "directory": "./data/coverage",
    },
    "monitoring": {
        "interval_seconds": 1.5,
    },
    "ui": {
        "language": "zh",
        "show_difference_pip": True,
        # ── Raspberry Pi / small-screen tuning ────────────────────
        # compact:         "auto" (detect small screen), True (force), False (off)
        # display_fps_cap: cap UI repaint rate; 0 = uncapped. Decouples the
        #                  expensive Qt render from the acquisition rate so a
        #                  low-power Pi GPU is not swamped.
        # card_shadows:    per-card drop shadows; "auto" disables them in
        #                  compact mode (soft shadows are costly on the Pi's
        #                  software-composited display).
        "compact": "auto",
        "display_fps_cap": 30,
        "card_shadows": "auto",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _load_yaml(path: str) -> dict:
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        log.warning("Config file not found: %s – using defaults", path)
        return {}
    except Exception as exc:
        log.warning("Failed to parse config %s: %s – using defaults", path, exc)
        return {}


class Settings:
    """
    Validated application settings.
    Access via typed properties; never raises on missing keys.
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        if config_path is None:
            # Locate config/default.yaml at the repository root.
            # __file__ = <repo>/src/poe_single_aravis/settings.py → up 2 = <repo>
            here = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(here, "..", "..", "config", "default.yaml")

        raw = _load_yaml(os.path.normpath(config_path))
        self._cfg: dict[str, Any] = _deep_merge(_DEFAULTS, raw)
        self._validate()

    def _validate(self) -> None:
        """Clamp and coerce obviously wrong values back to defaults."""
        cam = self._cfg["camera"]
        if cam["buffer_count"] < 4:
            log.warning("buffer_count too small, resetting to 24")
            cam["buffer_count"] = 24

        proc = self._cfg["processing"]
        if proc["mode"] not in ("cpu", "cuda"):
            log.warning("Invalid processing.mode '%s', using 'cpu'", proc["mode"])
            proc["mode"] = "cpu"
        kern = proc["gaussian_kernel"]
        if kern % 2 == 0 or kern < 3:
            log.warning("gaussian_kernel must be odd ≥ 3, resetting to 21")
            proc["gaussian_kernel"] = 21
        mkern = proc["morphology_kernel"]
        if mkern < 1:
            log.warning("morphology_kernel must be ≥ 1, resetting to 5")
            proc["morphology_kernel"] = 5

        ui = self._cfg["ui"]
        if ui["language"] not in ("zh", "en"):
            log.warning("Invalid language '%s', using 'zh'", ui["language"])
            ui["language"] = "zh"

    # ── camera ────────────────────────────────────────────────

    @property
    def auto_connect_first(self) -> bool:
        return bool(self._cfg["camera"]["auto_connect_first"])

    @property
    def buffer_count(self) -> int:
        return int(self._cfg["camera"]["buffer_count"])

    @property
    def frame_timeout_ms(self) -> int:
        return int(self._cfg["camera"]["frame_timeout_ms"])

    @property
    def reconnect_enabled(self) -> bool:
        return bool(self._cfg["camera"]["reconnect_enabled"])

    @property
    def reconnect_interval_seconds(self) -> float:
        return float(self._cfg["camera"]["reconnect_interval_seconds"])

    @property
    def max_reconnect_attempts(self) -> int:
        return int(self._cfg["camera"]["max_reconnect_attempts"])

    @property
    def consecutive_failure_threshold(self) -> int:
        return int(self._cfg["camera"]["consecutive_failure_threshold"])

    # ── processing ────────────────────────────────────────────

    @property
    def processing_mode(self) -> str:
        return str(self._cfg["processing"]["mode"])

    @property
    def analysis_width(self) -> int:
        return int(self._cfg["processing"]["analysis_width"])

    @property
    def analysis_height(self) -> int:
        return int(self._cfg["processing"]["analysis_height"])

    @property
    def difference_threshold(self) -> int:
        return int(self._cfg["processing"]["difference_threshold"])

    @property
    def gaussian_kernel(self) -> int:
        return int(self._cfg["processing"]["gaussian_kernel"])

    @property
    def morphology_kernel(self) -> int:
        return int(self._cfg["processing"]["morphology_kernel"])

    @property
    def alert_threshold_percent(self) -> float:
        return float(self._cfg["processing"]["alert_threshold_percent"])

    @property
    def analysis_fps(self) -> float:
        """Cap on how often image statistics are recomputed; 0 = every frame."""
        try:
            v = float(self._cfg["processing"].get("analysis_fps", 8))
        except (TypeError, ValueError):
            return 8.0
        return v if v >= 0 else 0.0

    # ── logging ───────────────────────────────────────────────

    @property
    def logging_enabled(self) -> bool:
        return bool(self._cfg["logging"]["enabled"])

    @property
    def log_interval_seconds(self) -> int:
        return int(self._cfg["logging"]["interval_seconds"])

    @property
    def log_directory(self) -> str:
        return str(self._cfg["logging"]["directory"])

    # ── monitoring ────────────────────────────────────────────

    @property
    def monitor_interval_seconds(self) -> float:
        return float(self._cfg["monitoring"]["interval_seconds"])

    # ── ui ────────────────────────────────────────────────────

    @property
    def language(self) -> str:
        return str(self._cfg["ui"]["language"])

    @language.setter
    def language(self, value: str) -> None:
        if value in ("zh", "en"):
            self._cfg["ui"]["language"] = value

    @property
    def show_difference_pip(self) -> bool:
        return bool(self._cfg["ui"]["show_difference_pip"])

    @property
    def compact(self) -> str:
        """'auto' | 'on' | 'off' — normalised from the raw config value."""
        v = self._cfg["ui"].get("compact", "auto")
        if isinstance(v, bool):
            return "on" if v else "off"
        return str(v).lower() if str(v).lower() in ("auto", "on", "off") else "auto"

    @property
    def display_fps_cap(self) -> int:
        try:
            cap = int(self._cfg["ui"].get("display_fps_cap", 30))
        except (TypeError, ValueError):
            return 30
        return cap if cap >= 0 else 0

    @property
    def card_shadows(self) -> str:
        """'auto' | 'on' | 'off' — whether cards draw a drop shadow."""
        v = self._cfg["ui"].get("card_shadows", "auto")
        if isinstance(v, bool):
            return "on" if v else "off"
        return str(v).lower() if str(v).lower() in ("auto", "on", "off") else "auto"
