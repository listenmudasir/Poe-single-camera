#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run.sh — launch the single-camera Aravis monitor.
#
# This strips the Hikvision MVS SDK directories from LD_LIBRARY_PATH because
# they ship an old Qt (5.6.3) that collides with PyQt5.  The app also does
# this itself (self-heal re-exec), but stripping it here avoids the re-exec.
#
# Usage:
#   ./run.sh                 # real camera
#   ./run.sh --fake          # Aravis fake camera (no hardware)
# ---------------------------------------------------------------------------
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# 1) Remove /opt/MVS* entries from LD_LIBRARY_PATH.
if [[ -n "${LD_LIBRARY_PATH:-}" ]]; then
    CLEAN=""
    IFS=':' read -ra PARTS <<< "$LD_LIBRARY_PATH"
    for p in "${PARTS[@]}"; do
        [[ "$p" == *"/opt/MVS"* || "$p" == *"MVS/lib"* ]] && continue
        [[ -z "$p" ]] && continue
        CLEAN="${CLEAN:+$CLEAN:}$p"
    done
    export LD_LIBRARY_PATH="$CLEAN"
fi

# 2) Point GI at the Aravis typelib (adjust ARAVIS_TYPELIB_DIR if needed).
export GI_TYPELIB_PATH="${ARAVIS_TYPELIB_DIR:-/usr/local/lib/x86_64-linux-gnu/girepository-1.0}${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"

# 3) Pick the interpreter (prefer the `train310` conda env on this machine because it has PyTorch/CUDA).
PY="${POE_PYTHON:-}"
if [[ -z "$PY" ]]; then
    if [[ -x "$HOME/miniconda3/envs/train310/bin/python" ]]; then
        PY="$HOME/miniconda3/envs/train310/bin/python"
    elif [[ -x "$HOME/miniconda3/envs/poe/bin/python" ]]; then
        PY="$HOME/miniconda3/envs/poe/bin/python"
    else
        PY="python3"
    fi
fi

export PYTHONPATH="$HERE/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m poe_single_aravis.app "$@"
