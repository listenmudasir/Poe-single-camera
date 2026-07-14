# -*- coding: utf-8 -*-
import pytest
from poe_single_aravis.domain.camera_state import CameraState, CameraStateMachine


def test_initial_state():
    assert CameraStateMachine().state == CameraState.DISCONNECTED


def test_valid_connect_flow():
    sm = CameraStateMachine()
    sm.transition(CameraState.CONNECTING)
    sm.transition(CameraState.CONNECTED)
    sm.transition(CameraState.STARTING)
    sm.transition(CameraState.STREAMING)
    sm.transition(CameraState.STOPPING)
    sm.transition(CameraState.CONNECTED)
    assert sm.state == CameraState.CONNECTED


@pytest.mark.parametrize("bad", [
    CameraState.STREAMING,   # can't jump straight from DISCONNECTED
    CameraState.STOPPING,
    CameraState.CONNECTED,
])
def test_invalid_transition_raises(bad):
    sm = CameraStateMachine()
    with pytest.raises(ValueError):
        sm.transition(bad)


def test_force_error_from_any_state():
    sm = CameraStateMachine()
    sm.transition(CameraState.CONNECTING)
    sm.transition(CameraState.CONNECTED)
    sm.force_error()
    assert sm.state == CameraState.ERROR
    # ERROR → CONNECTING or DISCONNECTED are allowed
    sm.transition(CameraState.CONNECTING)


def test_derived_helpers():
    sm = CameraStateMachine()
    assert sm.can_connect()
    sm.transition(CameraState.CONNECTING)
    sm.transition(CameraState.CONNECTED)
    assert sm.can_start() and sm.can_disconnect() and not sm.can_stop()
    sm.transition(CameraState.STARTING)
    sm.transition(CameraState.STREAMING)
    assert sm.can_stop() and sm.is_streaming()


def test_listener_notified():
    sm = CameraStateMachine()
    seen = []
    sm.add_listener(lambda o, n: seen.append((o, n)))
    sm.transition(CameraState.CONNECTING)
    assert seen == [(CameraState.DISCONNECTED, CameraState.CONNECTING)]
