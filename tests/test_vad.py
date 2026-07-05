import numpy as np

from ja_voice_input.vad import SilenceTracker, VoiceDetector


def make_tracker(**overrides):
    params = dict(frame_ms=30, silence_duration=1.2, start_timeout=8.0, max_duration=90.0)
    params.update(overrides)
    return SilenceTracker(**params)


class TestSilenceTracker:
    def test_stops_after_trailing_silence(self):
        t = make_tracker(silence_duration=0.3)
        # 発話 10 フレーム
        for _ in range(10):
            assert t.feed(True) == SilenceTracker.CONTINUE
        # 無音 0.3 秒 = 10 フレームで停止
        results = [t.feed(False) for _ in range(10)]
        assert results[-1] == SilenceTracker.STOP
        assert SilenceTracker.STOP not in results[:-1]

    def test_speech_resets_silence_counter(self):
        t = make_tracker(silence_duration=0.3)
        t.feed(True)
        for _ in range(9):  # 0.27 秒の無音(しきい値未満)
            assert t.feed(False) == SilenceTracker.CONTINUE
        assert t.feed(True) == SilenceTracker.CONTINUE  # 発話でリセット
        for _ in range(9):
            assert t.feed(False) == SilenceTracker.CONTINUE

    def test_timeout_without_speech(self):
        t = make_tracker(start_timeout=0.3)
        results = [t.feed(False) for _ in range(10)]
        assert results[-1] == SilenceTracker.TIMEOUT

    def test_max_duration_caps_recording(self):
        t = make_tracker(max_duration=0.3)
        results = [t.feed(True) for _ in range(10)]
        assert results[-1] == SilenceTracker.STOP


class TestVoiceDetectorRmsFallback:
    def test_silence_vs_tone(self, monkeypatch):
        import ja_voice_input.vad as vad_mod

        monkeypatch.setattr(vad_mod, "_HAS_WEBRTCVAD", False)
        det = VoiceDetector(sample_rate=16000, rms_threshold=0.012)
        assert det.backend == "rms"
        n = 480  # 30ms @ 16kHz
        silence = np.zeros(n, dtype=np.int16)
        tone = (np.sin(np.linspace(0, 2 * np.pi * 10, n)) * 8000).astype(np.int16)
        assert det.is_speech(silence) is False
        assert det.is_speech(tone) is True
