"""マイク録音。VAD による無音検出で自動終了する。"""
from __future__ import annotations

import logging
import queue
import threading

import numpy as np
import sounddevice as sd

from .config import AudioConfig
from .vad import SilenceTracker, VoiceDetector

log = logging.getLogger(__name__)


class Recorder:
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        self.detector = VoiceDetector(cfg.sample_rate, cfg.vad_aggressiveness, cfg.rms_threshold)
        log.info("VAD backend: %s", self.detector.backend)

    def record(self, stop_event: threading.Event | None = None) -> np.ndarray | None:
        """録音して float32 mono の波形を返す。発話が無ければ None。

        stop_event がセットされたら即座に録音を打ち切る(その時点までの音声は返す)。
        """
        cfg = self.cfg
        frame_len = int(cfg.sample_rate * cfg.frame_ms / 1000)
        frames_q: queue.Queue[np.ndarray] = queue.Queue()

        def callback(indata, _frames, _time, status):
            if status:
                log.warning("audio stream status: %s", status)
            frames_q.put(indata[:, 0].copy())

        tracker = SilenceTracker(
            cfg.frame_ms, cfg.silence_duration, cfg.start_timeout, cfg.max_duration
        )
        chunks: list[np.ndarray] = []

        with sd.InputStream(
            samplerate=cfg.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_len,
            callback=callback,
        ):
            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    frame = frames_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                chunks.append(frame)
                state = tracker.feed(self.detector.is_speech(frame))
                if state == SilenceTracker.TIMEOUT:
                    log.info("no speech detected, aborting")
                    return None
                if state == SilenceTracker.STOP:
                    break

        if not chunks or not tracker.speech_started:
            return None
        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        log.info("recorded %.1fs of audio", len(audio) / cfg.sample_rate)
        return audio
