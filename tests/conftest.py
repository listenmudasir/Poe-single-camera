# -*- coding: utf-8 -*-
"""
Shared pytest fixtures / bootstrap.

Ensures the Aravis GI bindings load (typelib path + shared-library preload)
without triggering the app's LD_LIBRARY_PATH re-exec, which would restart the
pytest process.  Qt is NOT imported here – unit tests are display-free.

Set ARV_FAKE_CAMERA_ENABLED=1 in the environment to also expose the Aravis
fake camera; by default only real cameras are used.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from poe_single_aravis.app import _bootstrap_aravis  # noqa: E402

# Aravis is a system dependency and may be absent (e.g. CI, a dev laptop
# without GenICam installed). The pure-imaging/settings unit tests don't need
# it, so a missing backend must not abort collection of the whole suite. Tests
# that genuinely require Aravis import it themselves and will error/skip on
# their own if it isn't available.
ARAVIS_AVAILABLE = True
try:
    _bootstrap_aravis()
except Exception:  # pragma: no cover - depends on the host environment
    ARAVIS_AVAILABLE = False
