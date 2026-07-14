# -*- coding: utf-8 -*-
"""
ui/i18n.py
===========
Chinese / English localisation for the single-camera app.
Switch language at runtime; the main window re-translates all labels.
"""

from __future__ import annotations

_LANG = "zh"

TR: dict[str, tuple[str, str]] = {
    # Window / top bar
    "win_title":          ("POE 單相機監控系統", "POE Single-Camera Monitor"),
    "subtitle":           ("Aravis GigE Vision", "Aravis GigE Vision"),
    "refresh":            ("刷新", "Refresh"),
    "connect":            ("連線", "Connect"),
    "disconnect":         ("斷線", "Disconnect"),
    "start":              ("開始取像", "Start"),
    "stop":               ("停止", "Stop"),
    "trigger_once":       ("單次觸發", "Trigger"),
    "snapshot":           ("擷圖", "Snapshot"),
    "lang_btn":           ("EN", "中"),
    "select_camera":      ("選擇相機", "Select camera"),
    "no_device":          ("未偵測到設備", "No devices found"),

    # Status
    "status_disconnected": ("未連線", "Disconnected"),
    "status_connected":    ("已連線", "Connected"),
    "status_streaming":    ("串流中", "Streaming"),
    "status_error":        ("錯誤", "Error"),
    "status_connecting":   ("連線中…", "Connecting…"),
    "status_stopping":     ("停止中…", "Stopping…"),
    "status_starting":     ("啟動中…", "Starting…"),

    # Hardware monitor
    "hw_monitor":         ("硬體監控", "Hardware Monitor"),
    "cpu":                ("CPU", "CPU"),
    "ram":                ("RAM", "RAM"),
    "gpu":                ("GPU", "GPU"),
    "vram":               ("VRAM", "VRAM"),

    # Camera control
    "cam_control":        ("相機控制", "Camera Control"),
    "compute_mode":       ("運算模式", "Compute Mode"),
    "cuda_na":            ("未偵測到 CUDA", "CUDA not detected"),

    # Camera parameters
    "cam_params":         ("相機參數", "Camera Parameters"),
    "exposure":           ("曝光 (µs)", "Exposure (µs)"),
    "gain":               ("增益 (dB)", "Gain (dB)"),
    "frame_rate":         ("幀率 (FPS)", "Frame Rate (FPS)"),
    "pixel_format":       ("像素格式", "Pixel Format"),
    "get_param":          ("讀取參數", "Get"),
    "set_param":          ("套用參數", "Apply"),
    "param_ready":        ("就緒", "Ready"),
    "param_applied":      ("已套用", "Applied"),
    "param_read":         ("已讀取", "Read from camera"),
    "trigger_mode":       ("觸發模式", "Trigger Mode"),
    "continuous":         ("連續", "Continuous"),
    "software_trigger":   ("軟體觸發", "Software"),

    # ROI
    "roi":                ("感興趣區域 (ROI)", "Region of Interest"),
    "roi_x":              ("Offset X", "Offset X"),
    "roi_y":              ("Offset Y", "Offset Y"),
    "roi_w":              ("寬度", "Width"),
    "roi_h":              ("高度", "Height"),
    "roi_apply":          ("套用 ROI", "Apply ROI"),
    "roi_reset":          ("重置全圖", "Reset Full"),

    # White balance
    "white_balance":      ("白平衡", "White Balance"),
    "wb_auto_hw":         ("單次自動白平衡", "Auto White Balance"),
    "wb_preset":          ("軟體預設", "Software Preset"),
    "wb_auto_sw":         ("灰世界", "Gray-World"),
    "wb_reset":           ("重設", "Reset"),

    # Image analysis
    "analysis":           ("影像分析", "Image Analysis"),
    "rgb":                ("RGB 平均", "RGB Mean"),
    "hsl":                ("HSL 平均", "HSL Mean"),
    "intensity":          ("平均光強", "Intensity"),
    "brightness":         ("亮度", "Brightness"),
    "exposure_val":       ("曝光值", "Exposure"),
    "resolution":         ("解析度", "Resolution"),
    "acq_fps":            ("取像", "Acq"),
    "proc_fps":           ("處理", "Proc"),

    # Coverage / background
    "coverage":           ("覆蓋率分析", "Coverage Analysis"),
    "subtraction":        ("影像相減", "Subtraction"),
    "sub_on":             ("相減 ON", "Subtract ON"),
    "capture_bg":         ("拍攝背景", "Capture BG"),
    "reset_bg":           ("重設背景", "Reset BG"),
    "bg_status_none":     ("背景未設定", "Background: not set"),
    "bg_status_set":      ("背景已設定", "Background: set"),
    "threshold":          ("相減靈敏度", "Sensitivity"),
    "alert_threshold":    ("警示閾值", "Alert Threshold"),
    "coverage_pct":       ("覆蓋率", "Coverage"),
    "alert_label":        ("⚠ 警示", "⚠ ALERT"),
    "processing_mode":    ("運算模式", "Mode"),

    # Chart / view
    "show_chart":         ("折線圖", "Chart"),
    "show_live":          ("即時畫面", "Live"),
    "chart_days":         ("顯示天數", "Days"),
    "day_n":              ("{d} 天", "{d} d"),
    "chart_ylabel":       ("覆蓋率 (%)", "Coverage (%)"),
    "chart_title":        ("每分鐘平均覆蓋率", "Per-minute Avg Coverage"),
    "chart_no_data":      ("尚無紀錄\n（開啟影像相減後每分鐘自動記錄）",
                           "No data yet\n(records every minute once subtraction is ON)"),

    # Fullscreen / video
    "waiting_conn":       ("等待連線…", "Waiting for connection…"),
    "waiting_img":        ("等待影像…", "Waiting for image…"),
    "diff":               ("差異", "Diff"),
    "fs_hint":            ("按 Esc 或雙擊關閉全螢幕", "Press Esc or double-click to exit"),
    "dbl_fullscreen":     ("雙擊全螢幕", "Double-click for fullscreen"),

    # Messages
    "err":                ("錯誤", "Error"),
    "unsupported_feat":   ("此相機不支援此功能", "Not supported by this camera"),
    "connect_first":      ("請先連線至相機", "Please connect to a camera first"),
}


def set_language(lang: str) -> None:
    global _LANG
    if lang in ("zh", "en"):
        _LANG = lang


def get_language() -> str:
    return _LANG


def tr(key: str, **kwargs) -> str:
    entry = TR.get(key)
    if entry is None:
        return key
    text = entry[1 if _LANG == "en" else 0]
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text
