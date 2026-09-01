from unittest import mock

from ja_voice_input.config import PasteConfig
from ja_voice_input.paste import FocusTarget, PasteResult, paste_text


def test_focus_target_rejects_different_app():
    target = FocusTarget(pid=10)
    with mock.patch.object(FocusTarget, "capture", return_value=FocusTarget(pid=20)):
        assert target.matches_current() is False


def test_focus_target_rejects_different_element():
    target = FocusTarget(pid=10, window="w", element="first")
    current = FocusTarget(pid=10, window="w", element="second")
    with mock.patch.object(FocusTarget, "capture", return_value=current):
        assert target.matches_current() is False


def test_focus_target_rejects_different_window_id():
    target = FocusTarget(pid=10, window_id=100)
    current = FocusTarget(pid=10, window_id=200)
    with mock.patch.object(FocusTarget, "capture", return_value=current):
        assert target.matches_current() is False


def test_changed_target_copies_without_sending_paste():
    cfg = PasteConfig(restore_clipboard=False, keystroke_delay=0)
    target = mock.Mock()
    target.matches_current.return_value = False
    with (
        mock.patch("ja_voice_input.paste._pbcopy") as copy,
        mock.patch("ja_voice_input.paste._pasteboard_change_count", return_value=1),
        mock.patch("ja_voice_input.paste._send_cmd_v") as send,
    ):
        result = paste_text("結果", cfg, target)
    copy.assert_called_once_with("結果", cfg.subprocess_timeout)
    send.assert_not_called()
    assert result is PasteResult.TARGET_CHANGED


def test_does_not_restore_over_new_user_clipboard():
    cfg = PasteConfig(restore_clipboard=True, keystroke_delay=0, restore_delay=0)
    snapshot = mock.Mock()
    with (
        mock.patch("ja_voice_input.paste.ClipboardSnapshot.capture", return_value=snapshot),
        mock.patch("ja_voice_input.paste._pbcopy"),
        mock.patch("ja_voice_input.paste._send_cmd_v"),
        mock.patch("ja_voice_input.paste._pasteboard_change_count", side_effect=[1, 2]),
    ):
        assert paste_text("結果", cfg) is PasteResult.PASTED
    snapshot.restore.assert_not_called()
