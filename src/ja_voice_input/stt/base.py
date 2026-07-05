from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class SttBackend(ABC):
    """音声認識バックエンドの共通インターフェース。"""

    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """float32 mono 波形をテキストに変換する。"""
