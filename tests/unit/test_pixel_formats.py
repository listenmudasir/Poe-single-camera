# -*- coding: utf-8 -*-
import numpy as np
import pytest

import gi
gi.require_version("Aravis", "0.10")
from gi.repository import Aravis

from poe_single_aravis.aravis_backend.pixel_formats import (
    convert_payload, pixel_format_name, is_supported,
)
from poe_single_aravis.domain.errors import PixelFormatError

W, H = 8, 6


def test_mono8_to_bgr():
    raw = (np.arange(W * H) % 256).astype(np.uint8)
    bgr = convert_payload(Aravis.PIXEL_FORMAT_MONO_8, raw.tobytes(), W, H)
    assert bgr.shape == (H, W, 3) and bgr.dtype == np.uint8
    # grayscale replicated across channels
    assert np.array_equal(bgr[:, :, 0], bgr[:, :, 1])
    assert np.array_equal(bgr[:, :, 1], bgr[:, :, 2])


def test_mono16_downshifted_to_8bit():
    raw = np.full((H, W), 0xAB00, np.uint16)      # high byte 0xAB
    bgr = convert_payload(Aravis.PIXEL_FORMAT_MONO_16, raw.tobytes(), W, H)
    assert bgr.shape == (H, W, 3)
    assert int(bgr[0, 0, 0]) == 0xAB              # >>8


def test_rgb8_becomes_bgr():
    rgb = np.zeros((H, W, 3), np.uint8)
    rgb[:, :, 0] = 30; rgb[:, :, 1] = 60; rgb[:, :, 2] = 90   # R,G,B
    bgr = convert_payload(Aravis.PIXEL_FORMAT_RGB_8_PACKED, rgb.tobytes(), W, H)
    assert bgr[0, 0, 0] == 90 and bgr[0, 0, 2] == 30          # channels swapped


def test_bgr8_passthrough():
    bgr_in = np.zeros((H, W, 3), np.uint8)
    bgr_in[:, :, 0] = 10; bgr_in[:, :, 2] = 200
    bgr = convert_payload(Aravis.PIXEL_FORMAT_BGR_8_PACKED, bgr_in.tobytes(), W, H)
    assert bgr[0, 0, 0] == 10 and bgr[0, 0, 2] == 200


def test_bayer_rg8_demosaics_to_bgr():
    raw = (np.arange(W * H) % 256).astype(np.uint8)
    bgr = convert_payload(Aravis.PIXEL_FORMAT_BAYER_RG_8, raw.tobytes(), W, H)
    assert bgr.shape == (H, W, 3) and bgr.dtype == np.uint8


def test_unsupported_format_raises():
    with pytest.raises(PixelFormatError):
        convert_payload(0xDEADBEEF, b"\x00" * (W * H), W, H)


def test_format_helpers():
    assert is_supported(Aravis.PIXEL_FORMAT_MONO_8)
    assert not is_supported(0xDEADBEEF)
    assert pixel_format_name(Aravis.PIXEL_FORMAT_MONO_8) == "Mono8"
    assert "Unknown" in pixel_format_name(0xDEADBEEF)
