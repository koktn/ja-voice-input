"""発話区間検出。webrtcvad があれば使い、無ければ RMS ベースにフォールバック。"""
from __future__ import annotations

import numpy as np

try:
    import webrtcvad  # webrtcvad-wheels
    _HAS_WEBRTCVAD = True
except ImportError:
    _HAS_WEBRTCVAD = False


class VoiceDetector:
    """16kHz mono int16 のフレームが発話かどうかを判定する。"""

    def __init__(self, sample_rate: int, aggressiveness: int = 2, rms_threshold: float = 0.012):
        self.sample_rate = sample_rate
        self.rms_threshold = rms_threshold
        self._vad = webrtcvad.Vad(aggressiveness) if _HAS_WEBRTCVAD else None

    @property
    def backend(self) -> str:
        return "webrtcvad" if self._vad else "rms"

    def is_speech(self, frame: np.ndarray) -> bool:
        """frame: int16 の 1 フレーム(10/20/30ms 分)。"""
        if self._vad is not None:
            return self._vad.is_speech(frame.tobytes(), self.sample_rate)
        rms = float(np.sqrt(np.mean((frame.astype(np.float32) / 32768.0) ** 2)))
        return rms >= self.rms_threshold


class SilenceTracker:
    """フレームごとの発話判定から「入力終了」を決める状態機械。

    - 発話開始前: start_timeout 秒経っても発話が無ければ timeout
    - 発話開始後: silence_duration 秒の無音が続いたら stop
    - 全体: max_duration 秒で強制 stop
    """

    CONTINUE = "continue"
    STOP = "stop"
    TIMEOUT = "timeout"

    def __init__(self, frame_ms: int, silence_duration: float, start_timeout: float, max_duration: float):
        self.frame_sec = frame_ms / 1000.0
        self.silence_duration = silence_duration
        self.start_timeout = start_timeout
        self.max_duration = max_duration
        self.elapsed = 0.0
        self.trailing_silence = 0.0
        self.speech_started = False

    def feed(self, is_speech: bool) -> str:
        self.elapsed += self.frame_sec
        if is_speech:
            self.speech_started = True
            self.trailing_silence = 0.0
        elif self.speech_started:
            self.trailing_silence += self.frame_sec

        if self.elapsed >= self.max_duration:
            return self.STOP if self.speech_started else self.TIMEOUT
        if not self.speech_started:
            return self.TIMEOUT if self.elapsed >= self.start_timeout else self.CONTINUE
        if self.trailing_silence >= self.silence_duration:
            return self.STOP
        return self.CONTINUE
