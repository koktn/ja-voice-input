from unittest import mock

from ja_voice_input.app import App, SessionState


def make_app_for_state_test(state):
    app = App.__new__(App)
    app._state = state
    import threading
    app._state_lock = threading.Lock()
    app._stop_recording = threading.Event()
    app.feedback = mock.Mock()
    return app


def test_hotkey_during_recording_requests_stop():
    app = make_app_for_state_test(SessionState.RECORDING)
    app.on_hotkey()
    assert app._stop_recording.is_set()


def test_hotkey_during_processing_reports_busy():
    app = make_app_for_state_test(SessionState.PROCESSING)
    app.on_hotkey()
    app.feedback.notify.assert_called_once_with("ja-voice-input", "音声を変換中です")
