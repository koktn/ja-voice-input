"""mlx-whisper バックエンド(Apple Silicon 推奨)。"""
from __future__ import annotations

import logging

import numpy as np

from ..config import SttConfig
from .base import SttBackend

log = logging.getLogger(__name__)

# モデル名の短縮形 → HF リポジトリ
ALIASES = {
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
}


class MlxWhisperBackend(SttBackend):
    def __init__(self, cfg: SttConfig):
        import mlx_whisper  # 遅延 import(extras 依存)

        self._mlx_whisper = mlx_whisper
        self.cfg = cfg
        self.repo = ALIASES.get(cfg.model, cfg.model)
        log.info("mlx-whisper model: %s", self.repo)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if sample_rate != 16000:
            raise ValueError("mlx-whisper requires 16kHz audio")
        kwargs = {}
        if self.cfg.initial_prompt:
            kwargs["initial_prompt"] = self.cfg.initial_prompt
        result = self._mlx_whisper.transcribe(
            audio,
            path_or_hf_repo=self.repo,
            language=self.cfg.language,
            fp16=True,
            **kwargs,
        )
        return str(result.get("text", "")).strip()

    def warmup(self) -> None:
        # mlx-whisper は transcribe 初回呼び出し時にモデルをロードする。
        self._mlx_whisper.transcribe(
            np.zeros(1600, dtype=np.float32),
            path_or_hf_repo=self.repo,
            language=self.cfg.language,
            fp16=True,
            temperature=0.0,
            condition_on_previous_text=False,
        )
