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
        self._model_class = Model
        self.model = None

    def _load_model(self):
        if self.model is not None:
            return self.model
        log.info("loading whisper.cpp model: %s", self.cfg.model)
        kwargs = {"n_threads": self.cfg.n_threads}
        if self.cfg.initial_prompt:
            kwargs["initial_prompt"] = self.cfg.initial_prompt
        self.model = self._model_class(
            self.cfg.model,
            language=self.cfg.language,
            print_progress=False,
            **kwargs,
        )
        return self.model

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if sample_rate != 16000:
            raise ValueError("whisper.cpp requires 16kHz audio")
        segments = self._load_model().transcribe(audio)
        return "".join(seg.text for seg in segments).strip()

    def warmup(self) -> None:
        self._load_model()
