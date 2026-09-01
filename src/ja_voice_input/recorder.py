"""マイク録音。VAD による無音検出で自動終了する。"""
from __future__ import annotations

import logging
import queue
import threading
from collections import deque

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
        pre_roll_frames = max(0, round(cfg.pre_roll * 1000 / cfg.frame_ms))
        pending: deque[np.ndarray] = deque(maxlen=pre_roll_frames)

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
                is_speech = self.detector.is_speech(frame)
                was_started = tracker.speech_started
                state = tracker.feed(is_speech)
                if not was_started and is_speech:
                    chunks.extend(pending)
                    pending.clear()
                    chunks.append(frame)
                elif tracker.speech_started:
                    chunks.append(frame)
                elif pre_roll_frames:
                    pending.append(frame)
                if state == SilenceTracker.TIMEOUT:
                    log.info("no speech detected, aborting")
                    return None
                if state == SilenceTracker.STOP:
                    break

        if not chunks or not tracker.speech_started:
            return None
        # 終了判定に使った長い無音は認識に不要。語尾保護分だけ残す。
        trailing_frames = round(tracker.trailing_silence * 1000 / cfg.frame_ms)
        tail_frames = round(cfg.tail_padding * 1000 / cfg.frame_ms)
        trim_frames = max(0, trailing_frames - tail_frames)
        if trim_frames:
            chunks = chunks[:-trim_frames]
        if not chunks:
            return None
        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        log.info("audio prepared: %.2fs (trimmed %.2fs trailing silence)",
                 len(audio) / cfg.sample_rate, trim_frames * cfg.frame_ms / 1000)
        return audio
