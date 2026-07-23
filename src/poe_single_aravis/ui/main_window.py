# -*- coding: utf-8 -*-
"""
ui/main_window.py
=================
Modernized single-camera main window.

Preserves the full POE_camera_20 feature set for one camera — hardware
monitor, camera control with CPU/CUDA compute mode, camera parameters
(exposure / gain / frame-rate + Get/Set), pixel format, trigger mode, ROI,
white balance, live image analysis (RGB/HSL/intensity), background-subtraction
coverage with flashing alerts, per-minute logging + history chart, difference
picture-in-picture, and fullscreen — on the Aravis backend, restyled with a
flat modern dark theme.

The window talks only to the CameraService and reacts to its Qt signals.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QComboBox, QPushButton, QLabel, QStackedWidget, QScrollArea, QDoubleSpinBox,
    QSpinBox, QSlider, QRadioButton, QButtonGroup, QProgressBar, QSizePolicy,
    QSplitter, QApplication,
)

from ..settings import Settings
from ..services.camera_service import CameraService
from ..domain.camera_state import CameraState
from ..domain.models import CameraCapabilities
from ..imaging.white_balance import WhiteBalanceController
from .i18n import tr, set_language, get_language
from .theme import (
    C, app_stylesheet, btn_primary, btn_ghost, btn_success, btn_danger,
    btn_toggle, Card, hline, key_label, value_label, icon, label,
    set_shadows_enabled,
)
from .video_widget import VideoWidget
from .chart_widget import ChartWidget
from .fullscreen_dialog import FullscreenDialog

try:
    import torch
    _HAS_CUDA = bool(torch.cuda.is_available())
except Exception:
    _HAS_CUDA = False


_STATUS = {
    CameraState.DISCONNECTED: ("status_disconnected", C.TEXT_FAINT),
    CameraState.DISCOVERED:   ("status_disconnected", C.TEXT_FAINT),
    CameraState.CONNECTING:   ("status_connecting", C.WARNING),
    CameraState.CONNECTED:    ("status_connected", C.ACCENT_2),
    CameraState.STARTING:     ("status_starting", C.WARNING),
    CameraState.STREAMING:    ("status_streaming", C.SUCCESS),
    CameraState.STOPPING:     ("status_stopping", C.WARNING),
    CameraState.ERROR:        ("status_error", C.DANGER),
}


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._settings = settings
        set_language(settings.language)

        self._svc = CameraService(settings)
        self._fullscreen: Optional[FullscreenDialog] = None
        self._last_acq = 0.0
        self._last_proc = 0.0
        self._last_display: Optional[np.ndarray] = None
        self._caps: Optional[CameraCapabilities] = None

        # Decide compact (small-screen / Raspberry Pi) layout before building.
        self._compact = self._resolve_compact(settings)
        self._cov_font_px = 22 if self._compact else 30
        set_shadows_enabled(self._resolve_shadows(settings))

        self.setWindowTitle(tr("win_title"))
        self._apply_window_geometry()
        self.setStyleSheet(app_stylesheet())

        self._build_ui()
        self._wire()

        self._svc.start_background_services()
        self._update_controls(CameraState.DISCONNECTED)
        self._svc.refresh_devices()
        if settings.auto_connect_first:
            self._auto_connect_first()

    # ══════════════════════════════════════════════════════════
    # responsive / Raspberry Pi layout
    # ══════════════════════════════════════════════════════════

    def _screen_size(self):
        """Available screen geometry, or None if it can't be determined."""
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                g = screen.availableGeometry()
                return g.width(), g.height()
        except Exception:
            pass
        return None

    def _resolve_compact(self, settings: Settings) -> bool:
        """Compact layout when forced by config, or auto-detected on a small
        screen (e.g. the official 7" Raspberry Pi touchscreen, 800×480)."""
        mode = settings.compact
        if mode == "on":
            return True
        if mode == "off":
            return False
        size = self._screen_size()
        if size is None:
            return False
        w, h = size
        return w <= 1024 or h <= 600

    def _resolve_shadows(self, settings: Settings) -> bool:
        mode = settings.card_shadows
        if mode == "on":
            return True
        if mode == "off":
            return False
        # auto: shadows off whenever we're in the compact/low-power layout.
        return not self._compact

    def _apply_window_geometry(self) -> None:
        if self._compact:
            size = self._screen_size()
            if size is not None:
                w, h = size
                self.resize(min(1024, w), min(600, h))
            else:
                self.resize(1024, 600)
            self.setMinimumSize(720, 440)
        else:
            self.resize(1440, 900)
            self.setMinimumSize(960, 600)

    # ══════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QWidget(); root.setObjectName("RootBg")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # A draggable splitter between the sidebar and the video/center pane so
        # the user can resize the left panel instead of the layout "跑版"
        # (breaking) when the window is resized.
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setObjectName("MainSplitter")
        self._splitter.setHandleWidth(6)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(self._build_sidebar())
        self._splitter.addWidget(self._build_center())
        self._splitter.setStretchFactor(0, 0)   # sidebar keeps its size
        self._splitter.setStretchFactor(1, 1)    # center absorbs extra space
        self._splitter.setSizes([240, 780] if self._compact else [340, 1100])
        outer.addWidget(self._splitter)

    # ── sidebar ───────────────────────────────────────────────

    def _build_sidebar(self) -> QWidget:
        wrap = QWidget(); wrap.setObjectName("Sidebar")
        # Min/max (instead of a fixed width) so the splitter handle can drag it.
        wrap.setMinimumWidth(210 if self._compact else 280)
        wrap.setMaximumWidth(480 if self._compact else 560)
        wl = QVBoxLayout(wrap); wl.setContentsMargins(0, 0, 0, 0); wl.setSpacing(0)

        # brand header
        header = QWidget(); header.setStyleSheet("background: transparent;")
        hb = QVBoxLayout(header); hb.setContentsMargins(18, 16, 18, 8); hb.setSpacing(2)
        self._brand = QLabel(tr("win_title"))
        self._brand.setStyleSheet(f"color: {C.TEXT}; font-size: 17px; font-weight: 800;")
        sub = QLabel(tr("subtitle"))
        sub.setStyleSheet(f"color: {C.ACCENT}; font-size: 11px; font-weight: 600; letter-spacing: 1px;")
        hb.addWidget(self._brand); hb.addWidget(sub)
        wl.addWidget(header)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget()
        col = QVBoxLayout(inner)
        if self._compact:
            col.setContentsMargins(10, 4, 10, 10); col.setSpacing(8)
        else:
            col.setContentsMargins(14, 6, 14, 16); col.setSpacing(12)

        col.addWidget(self._card_hardware())
        col.addWidget(self._card_camera_control())
        col.addWidget(self._card_params())
        col.addWidget(self._card_roi())
        col.addWidget(self._card_white_balance())
        col.addWidget(self._card_analysis())
        col.addStretch()

        scroll.setWidget(inner)
        wl.addWidget(scroll, 1)
        return wrap

    def _card_hardware(self) -> Card:
        card = Card(tr("hw_monitor"), icon("🖥"))
        self._hw_card = card
        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(8)
        self._cpu_bar = self._meter(); self._ram_bar = self._meter()
        grid.addWidget(key_label(tr("cpu")), 0, 0)
        grid.addWidget(self._cpu_bar, 0, 1)
        grid.addWidget(key_label(tr("ram")), 1, 0)
        grid.addWidget(self._ram_bar, 1, 1)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)
        card.add(hline())
        row = QHBoxLayout()
        self._gpu_lbl = QLabel("GPU  N/A"); self._gpu_lbl.setStyleSheet(f"color:{C.TEXT_DIM};font-size:12px;")
        self._vram_lbl = QLabel("VRAM  N/A"); self._vram_lbl.setStyleSheet(f"color:{C.TEXT_DIM};font-size:12px;")
        row.addWidget(self._gpu_lbl); row.addStretch(); row.addWidget(self._vram_lbl)
        card.add_layout(row)
        return card

    def _meter(self) -> QProgressBar:
        bar = QProgressBar(); bar.setRange(0, 100); bar.setValue(0); bar.setFixedHeight(16)
        bar.setStyleSheet(
            f"QProgressBar{{background:{C.SURFACE_2};border:none;border-radius:8px;"
            f"text-align:center;color:{C.TEXT};font-size:10px;}}"
            f"QProgressBar::chunk{{background:{C.ACCENT};border-radius:8px;}}")
        return bar

    def _card_camera_control(self) -> Card:
        card = Card(tr("cam_control"), icon("📷"))
        self._ctrl_card = card
        self._mode_lbl = key_label(tr("compute_mode"))
        card.add(self._mode_lbl)
        row = QHBoxLayout()
        self._rb_cpu = QRadioButton("CPU"); self._rb_cpu.setChecked(True)
        self._rb_cuda = QRadioButton("CUDA (GPU)")
        if not _HAS_CUDA:
            self._rb_cuda.setEnabled(False); self._rb_cuda.setToolTip(tr("cuda_na"))
        grp = QButtonGroup(self); grp.addButton(self._rb_cpu); grp.addButton(self._rb_cuda)
        self._rb_cpu.toggled.connect(self._on_mode_changed)
        row.addWidget(self._rb_cpu); row.addWidget(self._rb_cuda); row.addStretch()
        card.add_layout(row)
        return card

    def _card_params(self) -> Card:
        card = Card(tr("cam_params"), icon("⚙"))
        self._params_card = card
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft); form.setHorizontalSpacing(10); form.setVerticalSpacing(9)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self._exp_spin = QDoubleSpinBox(); self._exp_spin.setDecimals(0)
        self._exp_spin.setRange(1, 10_000_000); self._exp_spin.setSingleStep(500)
        self._gain_spin = QDoubleSpinBox(); self._gain_spin.setDecimals(2)
        self._gain_spin.setRange(0, 48); self._gain_spin.setSingleStep(0.5)
        self._fr_spin = QDoubleSpinBox(); self._fr_spin.setDecimals(1)
        self._fr_spin.setRange(0.1, 1000); self._fr_spin.setSingleStep(1)
        self._pf_combo = QComboBox()
        self._pf_combo.currentTextChanged.connect(self._on_pixel_format)

        self._lbl_exp = key_label(tr("exposure"))
        self._lbl_gain = key_label(tr("gain"))
        self._lbl_fr = key_label(tr("frame_rate"))
        self._lbl_pf = key_label(tr("pixel_format"))
        form.addRow(self._lbl_exp, self._exp_spin)
        form.addRow(self._lbl_gain, self._gain_spin)
        form.addRow(self._lbl_fr, self._fr_spin)
        form.addRow(self._lbl_pf, self._pf_combo)
        card.add_layout(form)

        # trigger mode
        self._lbl_trig = key_label(tr("trigger_mode"))
        card.add(self._lbl_trig)
        trow = QHBoxLayout()
        self._rb_cont = QRadioButton(tr("continuous")); self._rb_cont.setChecked(True)
        self._rb_soft = QRadioButton(tr("software_trigger"))
        tg = QButtonGroup(self); tg.addButton(self._rb_cont); tg.addButton(self._rb_soft)
        self._rb_soft.toggled.connect(self._on_trigger_mode)
        trow.addWidget(self._rb_cont); trow.addWidget(self._rb_soft); trow.addStretch()
        card.add_layout(trow)

        brow = QHBoxLayout()
        self._btn_get = QPushButton(label("📥", tr("get_param"))); self._btn_get.setStyleSheet(btn_ghost())
        self._btn_set = QPushButton(label("📤", tr("set_param"))); self._btn_set.setStyleSheet(btn_primary())
        self._btn_get.clicked.connect(self._on_get_params)
        self._btn_set.clicked.connect(self._on_set_params)
        brow.addWidget(self._btn_get); brow.addWidget(self._btn_set)
        card.add_layout(brow)
        self._param_status = QLabel(tr("param_ready"))
        self._param_status.setAlignment(Qt.AlignCenter)
        self._param_status.setStyleSheet(f"color:{C.TEXT_FAINT};font-size:11px;")
        card.add(self._param_status)
        return card

    def _card_roi(self) -> Card:
        card = Card(tr("roi"), icon("🔲"))
        self._roi_card = card
        grid = QGridLayout(); grid.setHorizontalSpacing(8); grid.setVerticalSpacing(8)
        self._roi_x = QSpinBox(); self._roi_y = QSpinBox()
        self._roi_w = QSpinBox(); self._roi_h = QSpinBox()
        for sp in (self._roi_x, self._roi_y, self._roi_w, self._roi_h):
            sp.setRange(0, 100000); sp.setSingleStep(4)
        self._lbl_rx = key_label(tr("roi_x")); self._lbl_ry = key_label(tr("roi_y"))
        self._lbl_rw = key_label(tr("roi_w")); self._lbl_rh = key_label(tr("roi_h"))
        grid.addWidget(self._lbl_rx, 0, 0); grid.addWidget(self._roi_x, 0, 1)
        grid.addWidget(self._lbl_ry, 0, 2); grid.addWidget(self._roi_y, 0, 3)
        grid.addWidget(self._lbl_rw, 1, 0); grid.addWidget(self._roi_w, 1, 1)
        grid.addWidget(self._lbl_rh, 1, 2); grid.addWidget(self._roi_h, 1, 3)
        card.add_layout(grid)
        brow = QHBoxLayout()
        self._btn_roi_apply = QPushButton(tr("roi_apply")); self._btn_roi_apply.setStyleSheet(btn_ghost())
        self._btn_roi_reset = QPushButton(tr("roi_reset")); self._btn_roi_reset.setStyleSheet(btn_ghost())
        self._btn_roi_apply.clicked.connect(self._on_roi_apply)
        self._btn_roi_reset.clicked.connect(self._on_roi_reset)
        brow.addWidget(self._btn_roi_apply); brow.addWidget(self._btn_roi_reset)
        card.add_layout(brow)
        return card

    def _card_white_balance(self) -> Card:
        card = Card(tr("white_balance"), icon("⚖"))
        self._wb_card = card
        self._btn_wb_hw = QPushButton(tr("wb_auto_hw")); self._btn_wb_hw.setStyleSheet(btn_ghost())
        self._btn_wb_hw.clicked.connect(self._svc.hardware_auto_white_balance)
        card.add(self._btn_wb_hw)
        row = QHBoxLayout()
        self._wb_preset = QComboBox(); self._wb_preset.addItems(WhiteBalanceController.preset_names())
        self._wb_preset.currentTextChanged.connect(self._on_wb_preset)
        self._btn_wb_sw = QPushButton(tr("wb_auto_sw")); self._btn_wb_sw.setStyleSheet(btn_ghost())
        self._btn_wb_reset = QPushButton(tr("wb_reset")); self._btn_wb_reset.setStyleSheet(btn_ghost())
        self._btn_wb_sw.clicked.connect(self._on_wb_gray)
        self._btn_wb_reset.clicked.connect(self._on_wb_reset)
        row.addWidget(self._wb_preset, 1); row.addWidget(self._btn_wb_sw); row.addWidget(self._btn_wb_reset)
        card.add_layout(row)
        return card

    def _card_analysis(self) -> Card:
        card = Card(tr("analysis"), icon("📊"))
        self._analysis_card = card
        grid = QGridLayout(); grid.setHorizontalSpacing(10); grid.setVerticalSpacing(7)
        self._an = {}
        rows = [
            ("rgb", tr("rgb")), ("hsl", tr("hsl")), ("intensity", tr("intensity")),
            ("brightness", tr("brightness")), ("resolution", tr("resolution")),
        ]
        self._an_key = {}
        for r, (k, label) in enumerate(rows):
            kl = key_label(label); vl = value_label("–")
            self._an_key[k] = kl; self._an[k] = vl
            grid.addWidget(kl, r, 0); grid.addWidget(vl, r, 1)
        grid.setColumnStretch(1, 1)
        card.add_layout(grid)
        card.add(hline())
        frow = QHBoxLayout()
        self._an_key["fps"] = key_label(tr("acq_fps") + " / " + tr("proc_fps"))
        self._an["fps"] = value_label("0.0 / 0.0")
        frow.addWidget(self._an_key["fps"]); frow.addStretch(); frow.addWidget(self._an["fps"])
        card.add_layout(frow)
        return card

    # ── center ────────────────────────────────────────────────

    def _build_center(self) -> QWidget:
        wrap = QWidget()
        cl = QVBoxLayout(wrap)
        if self._compact:
            cl.setContentsMargins(8, 8, 8, 8); cl.setSpacing(8)
        else:
            cl.setContentsMargins(16, 14, 16, 16); cl.setSpacing(12)

        cl.addLayout(self._build_topbar())
        cl.addLayout(self._build_view_header())

        min_size = (320, 240) if self._compact else (480, 360)
        self._video = VideoWidget(
            min_size=min_size, display_fps_cap=self._settings.display_fps_cap)
        self._video.set_show_pip(self._settings.show_difference_pip)
        self._video.double_clicked.connect(self._open_fullscreen)
        self._chart = ChartWidget()
        self._stack = QStackedWidget()
        self._stack.addWidget(self._video)
        self._stack.addWidget(self._chart)
        cl.addWidget(self._stack, 1)

        cl.addWidget(self._build_coverage_bar())
        return wrap

    def _build_topbar(self) -> QHBoxLayout:
        ctrl_h = 32 if self._compact else 36
        combo_w = 150 if self._compact else 300
        bar = QHBoxLayout(); bar.setSpacing(6 if self._compact else 8)
        self._combo = QComboBox(); self._combo.setMinimumWidth(combo_w); self._combo.setMinimumHeight(ctrl_h)
        self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bar.addWidget(self._combo, 1)
        self._btn_refresh = QPushButton(label("🔍", tr("refresh"))); self._btn_refresh.setStyleSheet(btn_ghost())
        self._btn_connect = QPushButton(tr("connect")); self._btn_connect.setStyleSheet(btn_primary())
        self._btn_startstop = QPushButton(label("▶", tr("start"))); self._btn_startstop.setStyleSheet(btn_success())
        self._btn_trigger = QPushButton(label("📸", tr("trigger_once"))); self._btn_trigger.setStyleSheet(btn_ghost())
        self._btn_snapshot = QPushButton(label("💾", tr("snapshot"))); self._btn_snapshot.setStyleSheet(btn_ghost())
        for b in (self._btn_refresh, self._btn_connect, self._btn_startstop,
                  self._btn_trigger, self._btn_snapshot):
            b.setMinimumHeight(ctrl_h); bar.addWidget(b)
        self._btn_refresh.clicked.connect(self._svc.refresh_devices)
        self._btn_connect.clicked.connect(self._on_connect_toggle)
        self._btn_startstop.clicked.connect(self._on_startstop)
        self._btn_trigger.clicked.connect(self._svc.software_trigger)
        self._btn_snapshot.clicked.connect(self._on_snapshot)
        bar.addStretch()
        self._status_pill = QLabel(tr("status_disconnected"))
        self._status_pill.setMinimumHeight(ctrl_h)
        self._set_status_pill(CameraState.DISCONNECTED)
        bar.addWidget(self._status_pill)
        self._btn_lang = QPushButton(label("🌐", tr("lang_btn"))); self._btn_lang.setStyleSheet(btn_ghost())
        self._btn_lang.setMinimumHeight(ctrl_h); self._btn_lang.clicked.connect(self._toggle_language)
        bar.addWidget(self._btn_lang)
        return bar

    def _build_view_header(self) -> QHBoxLayout:
        bar = QHBoxLayout(); bar.setSpacing(6)
        self._btn_live = QPushButton(label("🎥", tr("show_live"))); self._btn_live.setCheckable(True); self._btn_live.setChecked(True)
        self._btn_chart = QPushButton(label("📈", tr("show_chart"))); self._btn_chart.setCheckable(True)
        seg = QButtonGroup(self); seg.addButton(self._btn_live); seg.addButton(self._btn_chart)
        for b in (self._btn_live, self._btn_chart):
            b.setStyleSheet(btn_toggle()); b.setMinimumHeight(30)
        self._btn_live.clicked.connect(lambda: self._show_view(0))
        self._btn_chart.clicked.connect(lambda: self._show_view(1))
        bar.addWidget(self._btn_live); bar.addWidget(self._btn_chart)
        bar.addStretch()
        hint = QLabel(tr("dbl_fullscreen")); hint.setStyleSheet(f"color:{C.TEXT_FAINT};font-size:11px;")
        self._fs_hint = hint
        bar.addWidget(hint)
        return bar

    def _build_coverage_bar(self) -> Card:
        card = Card()
        self._cov_card = card
        row = QHBoxLayout(); row.setSpacing(14)

        # subtract toggle + bg buttons
        self._btn_sub = QPushButton(tr("subtraction")); self._btn_sub.setCheckable(True)
        self._btn_sub.setStyleSheet(btn_toggle()); self._btn_sub.setMinimumHeight(34)
        self._btn_sub.toggled.connect(self._on_subtraction)
        self._btn_cap_bg = QPushButton(tr("capture_bg")); self._btn_cap_bg.setStyleSheet(btn_ghost()); self._btn_cap_bg.setMinimumHeight(34)
        self._btn_reset_bg = QPushButton(tr("reset_bg")); self._btn_reset_bg.setStyleSheet(btn_ghost()); self._btn_reset_bg.setMinimumHeight(34)
        self._btn_cap_bg.clicked.connect(self._svc.capture_background)
        self._btn_reset_bg.clicked.connect(self._on_reset_bg)
        row.addWidget(self._btn_sub); row.addWidget(self._btn_cap_bg); row.addWidget(self._btn_reset_bg)

        row.addWidget(self._vsep())

        # threshold
        tcol = QVBoxLayout(); tcol.setSpacing(2)
        self._thr_lbl = key_label(tr("threshold") + "  5")
        self._thr = QSlider(Qt.Horizontal); self._thr.setRange(1, 100); self._thr.setValue(self._settings.difference_threshold)
        self._thr.setFixedWidth(150)
        self._thr.valueChanged.connect(self._on_threshold)
        tcol.addWidget(self._thr_lbl); tcol.addWidget(self._thr)
        row.addLayout(tcol)

        # alert threshold
        acol = QVBoxLayout(); acol.setSpacing(2)
        self._alert_lbl = key_label(tr("alert_threshold"))
        self._alert_spin = QDoubleSpinBox(); self._alert_spin.setRange(0, 100)
        self._alert_spin.setValue(self._settings.alert_threshold_percent); self._alert_spin.setSuffix(" %")
        self._alert_spin.setDecimals(0); self._alert_spin.setFixedWidth(90)
        self._alert_spin.valueChanged.connect(self._svc.set_alert_threshold)
        acol.addWidget(self._alert_lbl); acol.addWidget(self._alert_spin)
        row.addLayout(acol)

        row.addStretch()

        # coverage read-out
        self._bg_dot = QLabel("●"); self._bg_dot.setStyleSheet(f"color:{C.TEXT_FAINT};font-size:14px;")
        self._cov_val = QLabel("–")
        self._cov_val.setStyleSheet(f"color:{C.SUCCESS};font-size:{self._cov_font_px}px;font-weight:800;")
        self._cov_cap = key_label(tr("coverage_pct"))
        cvcol = QVBoxLayout(); cvcol.setSpacing(0)
        caprow = QHBoxLayout(); caprow.setSpacing(6); caprow.addWidget(self._bg_dot); caprow.addWidget(self._cov_cap); caprow.addStretch()
        cvcol.addLayout(caprow); cvcol.addWidget(self._cov_val)
        row.addLayout(cvcol)

        self._alert_badge = QLabel("")
        self._alert_badge.setAlignment(Qt.AlignCenter); self._alert_badge.setFixedWidth(96)
        row.addWidget(self._alert_badge)

        card.add_layout(row)
        return card

    def _vsep(self) -> QWidget:
        w = QWidget(); w.setFixedWidth(1); w.setStyleSheet(f"background:{C.BORDER};")
        w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        return w

    # ══════════════════════════════════════════════════════════
    # wiring
    # ══════════════════════════════════════════════════════════

    def _wire(self) -> None:
        s = self._svc
        s.devices_updated.connect(self._on_devices)
        s.state_changed.connect(lambda o, n: self._update_controls(n))
        s.capabilities_ready.connect(self._on_capabilities)
        s.frame_ready.connect(self._on_frame)
        s.fps_updated.connect(self._on_fps)
        s.error_message.connect(lambda m: self._param_status_msg(m, True))
        s.info_message.connect(lambda m: self._param_status_msg(m, False))
        s.hardware.stats_ready.connect(self._on_hw)

    # ══════════════════════════════════════════════════════════
    # slots
    # ══════════════════════════════════════════════════════════

    def _on_devices(self, devices) -> None:
        self._combo.clear()
        if not devices:
            self._combo.addItem(tr("no_device"), None); self._combo.setEnabled(False)
        else:
            self._combo.setEnabled(True)
            for d in devices:
                self._combo.addItem(str(d), d.device_id)
        self._update_controls(self._svc.state)

    def _auto_connect_first(self) -> None:
        if self._combo.count() and self._combo.itemData(0) is not None:
            self._on_connect_toggle()

    def _on_connect_toggle(self) -> None:
        st = self._svc.state
        if st in (CameraState.CONNECTED, CameraState.STREAMING, CameraState.STARTING, CameraState.STOPPING):
            self._svc.disconnect()      # service halts subtraction + clears bg
            self._reset_analysis_ui()   # and the UI must reflect that at once
            self._video.clear_view()
        else:
            dev = self._combo.currentData()
            if dev:
                self._svc.connect(dev)

    def _reset_analysis_ui(self) -> None:
        """Return the coverage/alert UI to its idle state (used on user
        disconnect, where the whole analysis session is torn down)."""
        if self._btn_sub.isChecked():
            self._btn_sub.blockSignals(True)
            self._btn_sub.setChecked(False)
            self._btn_sub.blockSignals(False)
        self._bg_dot.setStyleSheet(f"color:{C.TEXT_FAINT};font-size:14px;")
        self._cov_cap.setText(tr("coverage_pct"))
        self._cov_val.setText("–")
        self._cov_val.setStyleSheet(f"color:{C.SUCCESS};font-size:{self._cov_font_px}px;font-weight:800;")
        self._video.set_alert(False)
        self._alert_badge.setText("")
        self._alert_badge.setStyleSheet("")

    def _on_startstop(self) -> None:
        if self._svc.state == CameraState.STREAMING:
            self._svc.stop()
        elif self._svc.state == CameraState.CONNECTED:
            self._svc.start()

    def _on_snapshot(self) -> None:
        self._svc.save_snapshot(self._video.last_frame(), ext=".png")

    def _on_capabilities(self, caps: CameraCapabilities) -> None:
        self._caps = caps
        self._apply_caps_to_params(caps)
        if self._svc._logger is not None:
            self._chart.set_logger(self._svc._logger)

    def _apply_caps_to_params(self, caps: CameraCapabilities) -> None:
        for spin, has, mn, mx, cur in (
            (self._exp_spin, caps.has_exposure, caps.exposure_min, caps.exposure_max, caps.exposure_current),
            (self._gain_spin, caps.has_gain, caps.gain_min, caps.gain_max, caps.gain_current),
            (self._fr_spin, caps.has_frame_rate, caps.fps_min, caps.fps_max, caps.fps_current),
        ):
            spin.setEnabled(has)
            if has and mx > mn:
                spin.blockSignals(True); spin.setRange(mn, mx)
                spin.setValue(max(mn, min(mx, cur))); spin.blockSignals(False)
        self._pf_combo.blockSignals(True); self._pf_combo.clear()
        fmts = list(caps.available_pixel_formats) or ([caps.pixel_format] if caps.pixel_format else [])
        self._pf_combo.addItems(fmts)
        if caps.pixel_format in fmts:
            self._pf_combo.setCurrentText(caps.pixel_format)
        self._pf_combo.setEnabled(bool(fmts)); self._pf_combo.blockSignals(False)
        # ROI
        self._roi_card.setEnabled(caps.has_roi)
        if caps.has_roi:
            for sp, v in ((self._roi_x, caps.roi_x), (self._roi_y, caps.roi_y),
                          (self._roi_w, caps.roi_w), (self._roi_h, caps.roi_h)):
                sp.blockSignals(True); sp.setValue(v); sp.blockSignals(False)
        self._btn_wb_hw.setEnabled(True)
        # trigger
        soft = str(caps.trigger_mode).lower() in ("on", "software")
        self._rb_soft.setChecked(soft); self._rb_cont.setChecked(not soft)

    def _on_frame(self, display_bgr, stats, coverage) -> None:
        self._last_display = display_bgr
        diff = coverage.diff_image if coverage is not None else None
        self._video.update_frame(display_bgr, diff, self._last_acq, self._last_proc)
        if self._fullscreen is not None:
            self._fullscreen.update_frame(display_bgr)
        if stats is not None:
            self._an["rgb"].setText(f"{stats.mean_r:.0f}, {stats.mean_g:.0f}, {stats.mean_b:.0f}")
            self._an["hsl"].setText(f"{stats.mean_h:.0f}°, {stats.mean_s:.0f}%, {stats.mean_l:.0f}%")
            self._an["intensity"].setText(f"{stats.mean_l:.1f}")
            self._an["brightness"].setText(f"{stats.brightness:.1f}")
            self._an["resolution"].setText(f"{stats.width} × {stats.height}")
        if coverage is not None:
            self._update_coverage(coverage)

    def _update_coverage(self, cov) -> None:
        if not cov.background_set:
            self._bg_dot.setStyleSheet(f"color:{C.WARNING};font-size:14px;")
            self._cov_cap.setText(tr("bg_status_none"))
            self._cov_val.setText("–")
            self._video.set_alert(False); self._alert_badge.setText(""); self._alert_badge.setStyleSheet("")
            return
        self._bg_dot.setStyleSheet(f"color:{C.SUCCESS};font-size:14px;")
        self._cov_cap.setText(tr("coverage_pct"))
        self._cov_val.setText(f"{cov.coverage_percent:.1f}%")
        col = C.DANGER if cov.alert_active else C.SUCCESS
        self._cov_val.setStyleSheet(f"color:{col};font-size:{self._cov_font_px}px;font-weight:800;")
        self._video.set_alert(cov.alert_active)
        if cov.alert_active:
            self._alert_badge.setText(tr("alert_label"))
            self._alert_badge.setStyleSheet(
                f"background:{C.DANGER};color:#2a0808;border-radius:8px;padding:6px;font-weight:800;")
        else:
            self._alert_badge.setText(""); self._alert_badge.setStyleSheet("")

    def _on_fps(self, acq, proc, disp) -> None:
        self._last_acq = acq; self._last_proc = proc
        self._an["fps"].setText(f"{acq:.1f} / {proc:.1f}")

    def _on_hw(self, cpu, ram, gpu, vram) -> None:
        self._cpu_bar.setValue(int(cpu)); self._cpu_bar.setFormat(f"{cpu:.0f}%")
        self._ram_bar.setValue(int(ram)); self._ram_bar.setFormat(f"{ram:.0f}%")
        self._gpu_lbl.setText(f"GPU  {gpu}"); self._vram_lbl.setText(f"VRAM  {vram}")

    # ── parameter handlers ────────────────────────────────────

    def _on_get_params(self) -> None:
        p = self._svc.read_current_params()
        if not p:
            return
        if p.get("exposure"): self._exp_spin.setValue(float(p["exposure"]))
        if p.get("gain") is not None: self._gain_spin.setValue(float(p["gain"]))
        if p.get("frame_rate"): self._fr_spin.setValue(float(p["frame_rate"]))
        if p.get("pixel_format"):
            self._pf_combo.blockSignals(True); self._pf_combo.setCurrentText(p["pixel_format"]); self._pf_combo.blockSignals(False)
        for sp, key in ((self._roi_x, "roi_x"), (self._roi_y, "roi_y"), (self._roi_w, "roi_w"), (self._roi_h, "roi_h")):
            if key in p: sp.setValue(int(p[key]))
        self._param_status_msg(tr("param_read"), False)

    def _on_set_params(self) -> None:
        if self._caps is None:
            return
        if self._caps.has_exposure: self._svc.set_exposure(self._exp_spin.value())
        if self._caps.has_gain: self._svc.set_gain(self._gain_spin.value())
        if self._caps.has_frame_rate: self._svc.set_frame_rate(self._fr_spin.value())
        self._param_status_msg(tr("param_applied"), False)

    def _on_pixel_format(self, fmt: str) -> None:
        if fmt and self._caps is not None:
            self._svc.set_pixel_format(fmt)

    def _on_trigger_mode(self, _checked: bool) -> None:
        self._svc.set_trigger_mode(self._rb_soft.isChecked())
        self._update_controls(self._svc.state)

    def _on_mode_changed(self, _checked: bool) -> None:
        mode = "cuda" if self._rb_cuda.isChecked() else "cpu"
        effective = self._svc.set_processing_mode(mode)
        if effective != mode:
            self._rb_cpu.setChecked(True)

    def _on_roi_apply(self) -> None:
        self._svc.set_region(self._roi_x.value(), self._roi_y.value(),
                             self._roi_w.value(), self._roi_h.value())

    def _on_roi_reset(self) -> None:
        r = self._svc.reset_region_to_max()
        if r:
            self._roi_x.setValue(r[0]); self._roi_y.setValue(r[1])
            self._roi_w.setValue(r[2]); self._roi_h.setValue(r[3])

    # ── white balance ─────────────────────────────────────────

    def _on_wb_preset(self, name: str) -> None:
        self._svc.white_balance.set_preset(name)

    def _on_wb_gray(self) -> None:
        if self._last_display is not None:
            self._svc.white_balance.auto_gray_world(self._last_display)

    def _on_wb_reset(self) -> None:
        self._svc.white_balance.reset()
        self._wb_preset.setCurrentText("default")

    # ── coverage handlers ─────────────────────────────────────

    def _on_subtraction(self, on: bool) -> None:
        self._svc.set_subtraction_enabled(on)

    def _on_threshold(self, v: int) -> None:
        self._thr_lbl.setText(tr("threshold") + f"  {v}")
        self._svc.set_threshold(v)

    def _on_reset_bg(self) -> None:
        self._svc.reset_background()
        self._bg_dot.setStyleSheet(f"color:{C.WARNING};font-size:14px;")
        self._cov_cap.setText(tr("bg_status_none")); self._cov_val.setText("–")
        self._video.set_alert(False); self._alert_badge.setText(""); self._alert_badge.setStyleSheet("")

    # ── view toggle / fullscreen ──────────────────────────────

    def _show_view(self, index: int) -> None:
        if index == 1:
            self._chart.refresh()
        self._stack.setCurrentIndex(index)

    def _open_fullscreen(self) -> None:
        if self._last_display is None:
            return
        self._fullscreen = FullscreenDialog(parent=self)
        self._fullscreen.update_frame(self._last_display)
        self._fullscreen.finished.connect(lambda *_: setattr(self, "_fullscreen", None))
        self._fullscreen.show()

    # ── control state ─────────────────────────────────────────

    def _update_controls(self, state: CameraState) -> None:
        self._set_status_pill(state)
        connected = state in (CameraState.CONNECTED, CameraState.STREAMING, CameraState.STARTING, CameraState.STOPPING)
        streaming = state == CameraState.STREAMING
        has_dev = self._combo.count() > 0 and self._combo.currentData() is not None

        self._combo.setEnabled(not connected)
        self._btn_refresh.setEnabled(not connected)
        self._btn_connect.setEnabled(connected or has_dev)
        self._btn_connect.setText(tr("disconnect") if connected else tr("connect"))
        self._btn_connect.setStyleSheet(btn_danger() if connected else btn_primary())
        self._btn_startstop.setEnabled(state in (CameraState.CONNECTED, CameraState.STREAMING))
        self._btn_startstop.setText(label("■", tr("stop")) if streaming else label("▶", tr("start")))
        self._btn_startstop.setStyleSheet(btn_danger() if streaming else btn_success())
        self._btn_trigger.setEnabled(streaming and self._rb_soft.isChecked())
        self._btn_snapshot.setEnabled(streaming)

        # Alerts are only meaningful while live frames are flowing — never
        # keep a red border flashing over a frozen last frame.
        if not streaming:
            self._video.set_alert(False)
            self._alert_badge.setText("")
            self._alert_badge.setStyleSheet("")

        # Coverage actions need live frames (capture-bg freezes the *next*
        # frame); toggling them while stopped would be a silent no-op.
        for b in (self._btn_sub, self._btn_cap_bg, self._btn_reset_bg):
            b.setEnabled(streaming)

        self._params_card.setEnabled(connected)
        self._roi_card.setEnabled(connected and (self._caps.has_roi if self._caps else False))
        self._wb_card.setEnabled(connected)
        if not connected:
            self._caps = None

    def _set_status_pill(self, state: CameraState) -> None:
        key, col = _STATUS.get(state, ("status_disconnected", C.TEXT_FAINT))
        self._status_pill.setText("  ● " + tr(key) + "  ")
        self._status_pill.setStyleSheet(
            f"color:{col};background:{C.SURFACE};border:1px solid {C.BORDER};"
            f"border-radius:8px;padding:0 12px;font-weight:700;")

    def _param_status_msg(self, msg: str, error: bool) -> None:
        self._param_status.setText(msg)
        self._param_status.setStyleSheet(
            f"color:{C.DANGER if error else C.SUCCESS};font-size:11px;")

    # ── language ──────────────────────────────────────────────

    def _toggle_language(self) -> None:
        set_language("en" if get_language() == "zh" else "zh")
        self._settings.language = get_language()
        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(tr("win_title"))
        self._brand.setText(tr("win_title"))
        self._hw_card.set_title(tr("hw_monitor"))
        self._ctrl_card.set_title(tr("cam_control")); self._mode_lbl.setText(tr("compute_mode"))
        self._params_card.set_title(tr("cam_params"))
        self._lbl_exp.setText(tr("exposure")); self._lbl_gain.setText(tr("gain"))
        self._lbl_fr.setText(tr("frame_rate")); self._lbl_pf.setText(tr("pixel_format"))
        self._lbl_trig.setText(tr("trigger_mode")); self._rb_cont.setText(tr("continuous")); self._rb_soft.setText(tr("software_trigger"))
        self._btn_get.setText(label("📥", tr("get_param"))); self._btn_set.setText(label("📤", tr("set_param")))
        self._roi_card.set_title(tr("roi"))
        self._lbl_rx.setText(tr("roi_x")); self._lbl_ry.setText(tr("roi_y"))
        self._lbl_rw.setText(tr("roi_w")); self._lbl_rh.setText(tr("roi_h"))
        self._btn_roi_apply.setText(tr("roi_apply")); self._btn_roi_reset.setText(tr("roi_reset"))
        self._wb_card.set_title(tr("white_balance")); self._btn_wb_hw.setText(tr("wb_auto_hw"))
        self._btn_wb_sw.setText(tr("wb_auto_sw")); self._btn_wb_reset.setText(tr("wb_reset"))
        self._analysis_card.set_title(tr("analysis"))
        self._an_key["rgb"].setText(tr("rgb")); self._an_key["hsl"].setText(tr("hsl"))
        self._an_key["intensity"].setText(tr("intensity")); self._an_key["brightness"].setText(tr("brightness"))
        self._an_key["resolution"].setText(tr("resolution"))
        self._an_key["fps"].setText(tr("acq_fps") + " / " + tr("proc_fps"))
        self._btn_refresh.setText(label("🔍", tr("refresh")))
        self._btn_trigger.setText(label("📸", tr("trigger_once"))); self._btn_snapshot.setText(label("💾", tr("snapshot")))
        self._btn_lang.setText(label("🌐", tr("lang_btn")))
        self._btn_live.setText(label("🎥", tr("show_live"))); self._btn_chart.setText(label("📈", tr("show_chart")))
        self._fs_hint.setText(tr("dbl_fullscreen"))
        self._btn_sub.setText(tr("subtraction")); self._btn_cap_bg.setText(tr("capture_bg")); self._btn_reset_bg.setText(tr("reset_bg"))
        self._alert_lbl.setText(tr("alert_threshold"))
        self._thr_lbl.setText(tr("threshold") + f"  {self._thr.value()}")
        self._chart.retranslate()
        self._update_controls(self._svc.state)

    # ── shutdown ──────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        try:
            self._svc.shutdown()
        except Exception:
            pass
        super().closeEvent(event)
