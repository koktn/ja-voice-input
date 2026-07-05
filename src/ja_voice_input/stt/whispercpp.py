"""whisper.cpp (pywhispercpp) バックエンド。"""
from __future__ import annotations

import logging

import numpy as np

from ..config import SttConfig
from .base import SttBackend

log = logging.getLogger(__name__)


class WhisperCppBackend(SttBackend):
    def __init__(self, cfg: SttConfig):
        from pywhispercpp.model import Model  # 遅延 import(extras 依存)

        self.cfg = cfg
        log.info("loading whisper.cpp model: %s", cfg.model)
        kwargs = {"n_threads": cfg.n_threads}
        if cfg.initial_prompt:
            kwargs["initial_prompt"] = cfg.initial_prompt
        self.model = Model(cfg.model, language=cfg.language, print_progress=False, **kwargs)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if sample_rate != 16000:
            raise ValueError("whisper.cpp requires 16kHz audio")
        segments = self.model.transcribe(audio)
        return "".join(seg.text for seg in segments).strip()
