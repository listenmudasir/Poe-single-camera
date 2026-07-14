#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_aravis.py
===============
Verify that the Aravis GObject-Introspection bindings load correctly and
report the Aravis version.  Run this first when diagnosing a setup problem.

    python scripts/check_aravis.py
"""
import os
import sys

# Make the package importable when run from a source checkout.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main() -> int:
    try:
        from poe_single_aravis.app import _bootstrap_aravis
        _bootstrap_aravis()
    except Exception as exc:
        print("FAIL: could not bootstrap Aravis:", exc)
        print("      Install Aravis 0.10 + its typelib, or set ARAVIS_TYPELIB_DIR.")
        return 1

    import gi
    gi.require_version("Aravis", "0.10")
    from gi.repository import Aravis

    ver = getattr(Aravis, "_version", None) or "0.10"
    # Prove the binding is functional, not just importable.
    Aravis.get_n_devices  # attribute access
    print("OK: Aravis %s loaded successfully" % ver)
    print("    GI_TYPELIB_PATH =", os.environ.get("GI_TYPELIB_PATH", "(unset)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
