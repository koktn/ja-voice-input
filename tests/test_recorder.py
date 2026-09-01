from unittest import mock

import numpy as np

from ja_voice_input.config import AudioConfig
from ja_voice_input.recorder import Recorder


def test_record_trims_leading_and_trailing_silence(monkeypatch):
    cfg = AudioConfig(
        frame_ms=30,
        silence_duration=0.3,
        pre_roll=0.09,
        tail_padding=0.06,
    )
    recorder = Recorder(cfg)
    speech_flags = [False] * 5 + [True] * 2 + [False] * 10
    recorder.detector = mock.Mock()
    recorder.detector.is_speech.side_effect = speech_flags
    frame_len = int(cfg.sample_rate * cfg.frame_ms / 1000)
    frames = [np.full((frame_len, 1), i, dtype=np.int16) for i in range(len(speech_flags))]

    class FakeInputStream:
        def __init__(self, callback, **_kwargs):
            self.callback = callback

        def __enter__(self):
            for frame in frames:
                self.callback(frame, len(frame), None, None)
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("ja_voice_input.recorder.sd.InputStream", FakeInputStream)
    audio = recorder.record()

    # pre-roll 3 + speech 2 + tail padding 2 frames
    assert audio is not None
    assert len(audio) == frame_len * 7
