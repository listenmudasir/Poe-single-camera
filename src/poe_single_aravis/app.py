# -*- coding: utf-8 -*-
"""
app.py
======
Application entry point for the single-camera POE Aravis monitor.

Usage:
    python -m poe_single_aravis.app [--config PATH] [--fake] [--log-level LEVEL]

The `--fake` flag (or ARV_FAKE_CAMERA_ENABLED=1) enables the Aravis
fake-camera interface for demo / test runs without real hardware.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


# ── Aravis runtime bootstrap ──────────────────────────────────
# Aravis may be installed under a non-standard prefix (e.g. /usr/local).
# We add its GI typelib dir and pre-load the shared library so the
# GObject-Introspection import succeeds regardless of LD_LIBRARY_PATH.
# Override with ARAVIS_PREFIX / ARAVIS_TYPELIB_DIR if your layout differs.
_DEFAULT_TYPELIB_DIRS = [
    os.environ.get("ARAVIS_TYPELIB_DIR", ""),
    "/usr/local/lib/x86_64-linux-gnu/girepository-1.0",
    "/usr/local/lib/girepository-1.0",
    "/usr/lib/x86_64-linux-gnu/girepository-1.0",
]
_DEFAULT_LIB_CANDIDATES = [
    "/usr/local/lib/x86_64-linux-gnu/libaravis-0.10.so.0",
    "/usr/local/lib/libaravis-0.10.so.0",
    "/usr/lib/x86_64-linux-gnu/libaravis-0.10.so.0",
    "/usr/local/lib/x86_64-linux-gnu/libaravis-0.8.so.0",
]


def _bootstrap_aravis() -> None:
    # 1) GI typelib search path
    existing = os.environ.get("GI_TYPELIB_PATH", "")
    dirs = [d for d in _DEFAULT_TYPELIB_DIRS if d and os.path.isdir(d)]
    if dirs:
        parts = existing.split(os.pathsep) if existing else []
        for d in dirs:
            if d not in parts:
                parts.append(d)
        os.environ["GI_TYPELIB_PATH"] = os.pathsep.join(parts)

    # 2) Pre-load the shared library (handles missing LD_LIBRARY_PATH)
    import ctypes
    for cand in _DEFAULT_LIB_CANDIDATES:
        if os.path.exists(cand):
            try:
                ctypes.CDLL(cand, mode=ctypes.RTLD_GLOBAL)
                break
            except OSError:
                continue

    # 3) Import gi + Aravis NOW, before PyQt5 is ever imported.
    #    PyQt5 ships its own GLib; if it loads first, the system libgobject
    #    that gi needs fails with an undefined-symbol error.  Importing gi
    #    first makes the system GLib win.
    try:
        import gi
        gi.require_version("Aravis", "0.10")
        from gi.repository import Aravis  # noqa: F401
    except Exception as exc:  # pragma: no cover - surfaced to the user below
        raise ImportError(
            "Failed to load the Aravis GObject-Introspection bindings. "
            "Ensure Aravis 0.10 and its typelib are installed, or set "
            "ARAVIS_TYPELIB_DIR / GI_TYPELIB_PATH. Original error: %s" % exc
        ) from exc


def _sanitize_ld_library_path() -> None:
    """Remove Qt-bundling SDK dirs (e.g. the Hikvision MVS SDK) from
    LD_LIBRARY_PATH and re-exec once, so the wrong libQt5Core cannot hijack
    PyQt5.  The dynamic linker reads LD_LIBRARY_PATH only at process start,
    so a clean value requires a re-exec.  Guarded to run at most once.
    """
    if os.environ.get("_POE_LD_SANITIZED") == "1":
        return
    ldp = os.environ.get("LD_LIBRARY_PATH", "")
    if not ldp:
        os.environ["_POE_LD_SANITIZED"] = "1"
        return
    bad_markers = ("/opt/MVS", "MVS/lib")
    kept = [p for p in ldp.split(os.pathsep)
            if p and not any(m in p for m in bad_markers)]
    os.environ["_POE_LD_SANITIZED"] = "1"
    new_ldp = os.pathsep.join(kept)
    if new_ldp == ldp:
        return
    if new_ldp:
        os.environ["LD_LIBRARY_PATH"] = new_ldp
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
    # Re-exec with the cleaned environment before PyQt5/gi are loaded.
    # Preserve how the *actual* entry point was launched: `-m pkg.mod` keeps
    # relative imports working; a plain script path re-execs as-is.
    main_mod = sys.modules.get("__main__")
    spec = getattr(main_mod, "__spec__", None)
    if spec is not None and getattr(spec, "name", None):
        os.execv(sys.executable, [sys.executable, "-m", spec.name] + sys.argv[1:])
    else:
        os.execv(sys.executable, [sys.executable] + sys.argv)


def _pin_qt_plugin_path() -> None:
    """Point Qt at PyQt5's own platform plugins.

    Some opencv-python wheels bundle their own Qt plugins (cv2/qt/plugins) and
    register that directory globally; when cv2 is imported alongside PyQt5 the
    wrong 'xcb' plugin loads and QApplication aborts.  Pinning the environment
    variable to PyQt5's bundled plugins makes the correct one win regardless of
    import order or which conda env is active.
    """
    # Import cv2 FIRST: its loader sets QT_QPA_PLATFORM_PLUGIN_PATH to its own
    # bundled plugins at import time, so we must import it before overriding.
    try:
        import cv2  # noqa: F401
    except Exception:
        pass
    try:
        import PyQt5  # noqa: WPS433
        base = os.path.dirname(PyQt5.__file__)
        for sub in ("Qt5/plugins", "Qt/plugins"):
            plugins = os.path.join(base, sub)
            if os.path.isdir(plugins):
                os.environ["QT_PLUGIN_PATH"] = plugins
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
                    plugins, "platforms")
                break
    except Exception:
        pass


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="POE single-camera Aravis monitor")
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument("--fake", action="store_true",
                        help="Enable the Aravis fake-camera interface")
    parser.add_argument("--log-level", default="INFO",
                        help="DEBUG / INFO / WARNING / ERROR")
    args = parser.parse_args(argv)

    _sanitize_ld_library_path()   # may re-exec; must precede PyQt5/gi imports
    _configure_logging(args.log_level)
    if args.fake:
        os.environ["ARV_FAKE_CAMERA_ENABLED"] = "1"

    _bootstrap_aravis()
    _pin_qt_plugin_path()

    # Import Qt / Settings AFTER the Aravis bootstrap so the backend loads.
    from PyQt5.QtWidgets import QApplication
    from .settings import Settings
    from .ui.main_window import MainWindow

    settings = Settings(args.config)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("POE Single-Camera Monitor")

    window = MainWindow(settings)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
