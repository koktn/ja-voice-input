from __future__ import annotations

from ..config import SttConfig
from .base import SttBackend


def create_backend(cfg: SttConfig) -> SttBackend:
    if cfg.backend == "whispercpp":
        from .whispercpp import WhisperCppBackend

        return WhisperCppBackend(cfg)
    if cfg.backend == "mlx":
        from .mlx import MlxWhisperBackend

        return MlxWhisperBackend(cfg)
    raise ValueError(f"unknown stt backend: {cfg.backend} (whispercpp | mlx)")
