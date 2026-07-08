"""設定の読み込み。YAML ファイル + デフォルト値。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATHS = [
    Path("~/.config/ja-voice-input/config.yaml"),
    Path("config.yaml"),
]


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    frame_ms: int = 30  # webrtcvad は 10/20/30ms のみ対応
    silence_duration: float = 1.2  # この秒数無音が続いたら入力終了
    start_timeout: float = 8.0  # 発話が始まらないまま経過したら中断
    max_duration: float = 90.0  # 録音の最大長(秒)
    vad_aggressiveness: int = 2  # webrtcvad: 0(緩い)〜3(厳しい)
    rms_threshold: float = 0.012  # RMS フォールバック時の発話判定しきい値


@dataclass
class SttConfig:
    backend: str = "whispercpp"  # whispercpp | mlx
    model: str = "small"  # whispercpp: tiny/base/small/medium, mlx: HF repo 名
    language: str = "ja"
    n_threads: int = 4
    initial_prompt: str = ""  # 認識のヒント(専門用語を並べると精度が上がる)


@dataclass
class LlmConfig:
    enabled: bool = True
    base_url: str = "http://localhost:11434"
    model: str = "gemma4:e4b"
    timeout: float = 30.0
    temperature: float = 0.0


@dataclass
class PasteConfig:
    method: str = "keystroke"  # keystroke: Cmd+V を送出 / clipboard: コピーのみ
    restore_clipboard: bool = True
    keystroke_delay: float = 0.15  # コピーからキー送出までの待ち(秒)


@dataclass
class Config:
    hotkey: str = "double:cmd"  # 左右どちらかの Cmd 2回。pynput 形式 "<ctrl>+<alt>+<space>" も可
    dictionary_path: str = "~/.config/ja-voice-input/terms.yaml"
    sounds: bool = True
    notifications: bool = True
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    paste: PasteConfig = field(default_factory=PasteConfig)


def _merge_section(dc_cls, data: dict):
    known = {f for f in dc_cls.__dataclass_fields__}
    return dc_cls(**{k: v for k, v in data.items() if k in known})


def load_config(path: str | os.PathLike | None = None) -> Config:
    """設定ファイルを読み込む。path 未指定時は既定の場所を順に探す。"""
    data: dict = {}
    candidates = [Path(path)] if path else [p.expanduser() for p in DEFAULT_CONFIG_PATHS]
    for p in candidates:
        if p.expanduser().is_file():
            with open(p.expanduser(), encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            break
        if path:  # 明示指定されたファイルが無いのはエラー
            raise FileNotFoundError(f"config file not found: {p}")

    cfg = Config()
    for key, value in data.items():
        if key == "audio" and isinstance(value, dict):
            cfg.audio = _merge_section(AudioConfig, value)
        elif key == "stt" and isinstance(value, dict):
            cfg.stt = _merge_section(SttConfig, value)
        elif key == "llm" and isinstance(value, dict):
            cfg.llm = _merge_section(LlmConfig, value)
        elif key == "paste" and isinstance(value, dict):
            cfg.paste = _merge_section(PasteConfig, value)
        elif key in Config.__dataclass_fields__:
            setattr(cfg, key, value)
    return cfg
