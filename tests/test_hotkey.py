from ja_voice_input.hotkey import (
    DoubleTapDetector,
    double_tap_key_name,
    is_double_tap_spec,
)


class TestSpec:
    def test_double_tap_spec(self):
        assert is_double_tap_spec("double:cmd_r") is True
        assert double_tap_key_name("double: cmd_r ") == "cmd_r"

    def test_pynput_spec(self):
        assert is_double_tap_spec("<ctrl>+<alt>+<space>") is False


class TapSim:
    """タイムスタンプを進めながらイベントを流すヘルパー。"""

    def __init__(self, **kwargs):
        self.d = DoubleTapDetector(**kwargs)
        self.t = 0.0

    def tap(self, is_target=True, hold=0.1, wait=0.0):
        """wait 秒後に押して hold 秒後に離す。押下時の発火有無を返す。"""
        self.t += wait
        fired = self.d.on_press(is_target, self.t)
        self.t += hold
        self.d.on_release(is_target, self.t)
        return fired

    def press(self, is_target=True, wait=0.0):
        self.t += wait
        return self.d.on_press(is_target, self.t)


class TestDoubleTapDetector:
    def test_clean_double_tap_fires(self):
        s = TapSim(interval=0.4)
        assert s.tap() is False
        assert s.press(wait=0.2) is True  # 2回目の押下で発火

    def test_slow_second_tap_does_not_fire(self):
        s = TapSim(interval=0.4)
        s.tap()
        assert s.press(wait=1.0) is False

    def test_long_hold_is_not_a_tap(self):
        s = TapSim(max_hold=0.5)
        s.tap(hold=1.0)  # 長押しはタップ扱いしない
        assert s.press(wait=0.1) is False

    def test_other_key_during_hold_cancels(self):
        # Cmd+C のような通常ショートカット: Cmd 押下中に C が押される
        s = TapSim()
        s.press()  # Cmd down
        s.d.on_press(False, s.t)  # C down(dirty)
        s.d.on_release(True, s.t + 0.05)  # Cmd up
        assert s.press(wait=0.1) is False  # 直後の Cmd 押下では発火しない

    def test_shortcut_sequence_does_not_fire(self):
        # Cmd+C → Cmd+V の連続操作で発火しないこと
        s = TapSim()
        for _ in range(2):
            s.press(wait=0.1)
            s.d.on_press(False, s.t)  # 文字キー
            s.d.on_release(True, s.t + 0.05)
        assert s.d.on_press(True, s.t + 0.1) is False

    def test_other_key_between_taps_cancels(self):
        s = TapSim()
        s.tap()
        s.d.on_press(False, s.t + 0.05)  # タップ間に別キー
        assert s.press(wait=0.1) is False

    def test_fires_again_after_reset(self):
        s = TapSim()
        s.tap()
        assert s.press(wait=0.2) is True
        s.d.on_release(True, s.t + 0.1)
        # 発火後は状態がリセットされ、続けてもう一度ダブルタップできる
        s.tap(wait=0.5)
        assert s.press(wait=0.2) is True
