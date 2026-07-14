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
