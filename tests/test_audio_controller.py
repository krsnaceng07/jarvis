"""tests.test_audio_controller — Unit tests for AudioController."""

from src.system.audio_controller import AudioController


def test_audio_controller_get_volume():
    ctrl = AudioController.get_instance()
    state = ctrl.get_volume()
    assert isinstance(state, dict)
    assert state.get("ok") is True
    assert 0 <= state["volume_percent"] <= 100
    assert 0.0 <= state["volume_scalar"] <= 1.0
    assert isinstance(state["muted"], bool)
    assert state["verified"] is True


def test_audio_controller_adjust_and_set():
    ctrl = AudioController.get_instance()
    initial = ctrl.get_volume()
    assert initial.get("ok") is True

    try:
        # Test adjustment
        adjusted = ctrl.adjust_volume(5)
        assert adjusted.get("ok") is True
        assert 0 <= adjusted["volume_percent"] <= 100

        # Test set volume
        target_pct = min(100, max(0, initial["volume_percent"]))
        res = ctrl.set_volume(target_pct)
        assert res.get("ok") is True
        assert abs(res["volume_percent"] - target_pct) <= 1
    finally:
        # Restore initial state
        ctrl.set_volume(initial["volume_percent"])
        ctrl.set_mute(initial["muted"])
