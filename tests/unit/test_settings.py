# -*- coding: utf-8 -*-
import textwrap
from poe_single_aravis.settings import Settings


def _write(tmp_path, text):
    p = tmp_path / "cfg.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return str(p)


def test_defaults_when_missing(tmp_path):
    s = Settings(str(tmp_path / "does_not_exist.yaml"))
    assert s.buffer_count == 24
    assert s.processing_mode == "cpu"
    assert s.gaussian_kernel == 21


def test_invalid_values_clamped(tmp_path):
    cfg = _write(tmp_path, """
        camera:
          buffer_count: 1
        processing:
          mode: quantum
          gaussian_kernel: 20
          morphology_kernel: 0
        ui:
          language: martian
    """)
    s = Settings(cfg)
    assert s.buffer_count == 24            # too small → default
    assert s.processing_mode == "cpu"      # invalid → cpu
    assert s.gaussian_kernel == 21         # even → default
    assert s.morphology_kernel == 5        # <1 → default
    assert s.language == "zh"              # invalid → zh


def test_valid_overrides_applied(tmp_path):
    cfg = _write(tmp_path, """
        camera:
          buffer_count: 32
        processing:
          mode: cuda
          difference_threshold: 12
        ui:
          language: en
    """)
    s = Settings(cfg)
    assert s.buffer_count == 32
    assert s.processing_mode == "cuda"
    assert s.difference_threshold == 12
    assert s.language == "en"


def test_pi_ui_defaults(tmp_path):
    s = Settings(str(tmp_path / "missing.yaml"))
    assert s.compact == "auto"
    assert s.display_fps_cap == 30
    assert s.card_shadows == "auto"
    assert s.analysis_fps == 8.0


def test_pi_ui_normalization(tmp_path):
    cfg = _write(tmp_path, """
        ui:
          compact: true
          display_fps_cap: -5
          card_shadows: false
        processing:
          analysis_fps: bogus
    """)
    s = Settings(cfg)
    assert s.compact == "on"            # bool True → "on"
    assert s.display_fps_cap == 0       # negative → 0 (uncapped)
    assert s.card_shadows == "off"      # bool False → "off"
    assert s.analysis_fps == 8.0        # invalid → default


def test_pi_ui_explicit_values(tmp_path):
    cfg = _write(tmp_path, """
        ui:
          compact: "off"
          display_fps_cap: 15
          card_shadows: "on"
        processing:
          analysis_fps: 4
    """)
    s = Settings(cfg)
    assert s.compact == "off"
    assert s.display_fps_cap == 15
    assert s.card_shadows == "on"
    assert s.analysis_fps == 4.0
