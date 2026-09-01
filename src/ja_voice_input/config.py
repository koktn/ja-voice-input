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
    silence_duration: float = 0.8  # この秒数無音が続いたら入力終了
    start_timeout: float = 8.0  # 発話が始まらないまま経過したら中断
    max_duration: float = 90.0  # 録音の最大長(秒)
    vad_aggressiveness: int = 2  # webrtcvad: 0(緩い)〜3(厳しい)
    rms_threshold: float = 0.012  # RMS フォールバック時の発話判定しきい値
    pre_roll: float = 0.3  # 発話開始前に残す音声
    tail_padding: float = 0.15  # 発話終了後に残す音声


@dataclass
class SttConfig:
    backend: str = "whispercpp"  # whispercpp | mlx
    model: str = "small"  # whispercpp: tiny/base/small/medium, mlx: HF repo 名
    language: str = "ja"
    n_threads: int = 4
    initial_prompt: str = ""  # 認識のヒント(専門用語を並べると精度が上がる)
    warmup: bool = True  # 常駐開始時にモデルをバックグラウンドでロード


@dataclass
class LlmConfig:
    enabled: bool = True
    base_url: str = "http://localhost:11434"
    model: str = "gemma4:e4b"
    timeout: float = 10.0
    connect_timeout: float = 0.5
    temperature: float = 0.0
    warmup: bool = True
    keep_alive: str = "30m"
    failure_cooldown: float = 60.0
    mode: str = "always"  # always | auto（フィラー等がある場合だけ呼ぶ）


@dataclass
class PasteConfig:
    method: str = "keystroke"  # keystroke: Cmd+V を送出 / clipboard: コピーのみ
    restore_clipboard: bool = True
    keystroke_delay: float = 0.15  # コピーからキー送出までの待ち(秒)
    restore_delay: float = 0.3
    subprocess_timeout: float = 3.0
    cancel_on_focus_change: bool = True


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


class ConfigError(ValueError):
    """設定ファイルの値または構造が不正。"""


def _merge_section(dc_cls, data: dict, section: str):
    known = {f for f in dc_cls.__dataclass_fields__}
    unknown = set(data) - known
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ConfigError(f"unknown setting(s) in {section}: {names}")
    return dc_cls(**data)


def _positive(name: str, value: int | float, *, allow_zero: bool = False) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{name} must be a number")
    invalid = value < 0 if allow_zero else value <= 0
    if invalid:
        op = "0 or greater" if allow_zero else "greater than 0"
        raise ConfigError(f"{name} must be {op}")


def _boolean(name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise ConfigError(f"{name} must be true or false")


def _non_empty_string(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{name} must be a non-empty string")


def validate_config(cfg: Config) -> None:
    _non_empty_string("hotkey", cfg.hotkey)
    _non_empty_string("dictionary_path", cfg.dictionary_path)
    _boolean("sounds", cfg.sounds)
    _boolean("notifications", cfg.notifications)
    if cfg.audio.sample_rate != 16000:
        raise ConfigError("audio.sample_rate must be 16000 (required by the STT backends)")
    if cfg.audio.frame_ms not in {10, 20, 30}:
        raise ConfigError("audio.frame_ms must be one of 10, 20, 30")
    if not isinstance(cfg.audio.vad_aggressiveness, int) or not 0 <= cfg.audio.vad_aggressiveness <= 3:
        raise ConfigError("audio.vad_aggressiveness must be an integer from 0 to 3")
    for name in ("silence_duration", "start_timeout", "max_duration", "rms_threshold"):
        _positive(f"audio.{name}", getattr(cfg.audio, name))
    for name in ("pre_roll", "tail_padding"):
        _positive(f"audio.{name}", getattr(cfg.audio, name), allow_zero=True)
    if cfg.audio.tail_padding > cfg.audio.silence_duration:
        raise ConfigError("audio.tail_padding must not exceed audio.silence_duration")
    if cfg.stt.backend not in {"whispercpp", "mlx"}:
        raise ConfigError("stt.backend must be whispercpp or mlx")
    _non_empty_string("stt.model", cfg.stt.model)
    _non_empty_string("stt.language", cfg.stt.language)
    _boolean("stt.warmup", cfg.stt.warmup)
    if not isinstance(cfg.stt.n_threads, int) or cfg.stt.n_threads <= 0:
        raise ConfigError("stt.n_threads must be a positive integer")
    if cfg.llm.mode not in {"always", "auto"}:
        raise ConfigError("llm.mode must be always or auto")
    _boolean("llm.enabled", cfg.llm.enabled)
    _boolean("llm.warmup", cfg.llm.warmup)
    _non_empty_string("llm.base_url", cfg.llm.base_url)
    _non_empty_string("llm.model", cfg.llm.model)
    _non_empty_string("llm.keep_alive", cfg.llm.keep_alive)
    _positive("llm.temperature", cfg.llm.temperature, allow_zero=True)
    for name in ("timeout", "connect_timeout", "failure_cooldown"):
        _positive(f"llm.{name}", getattr(cfg.llm, name))
    if cfg.paste.method not in {"keystroke", "clipboard"}:
        raise ConfigError("paste.method must be keystroke or clipboard")
    _boolean("paste.restore_clipboard", cfg.paste.restore_clipboard)
    _boolean("paste.cancel_on_focus_change", cfg.paste.cancel_on_focus_change)
    for name in ("keystroke_delay", "restore_delay"):
        _positive(f"paste.{name}", getattr(cfg.paste, name), allow_zero=True)
    _positive("paste.subprocess_timeout", cfg.paste.subprocess_timeout)


def load_config(path: str | os.PathLike | None = None) -> Config:
    """設定ファイルを読み込む。path 未指定時は既定の場所を順に探す。"""
    data: dict = {}
    candidates = [Path(path)] if path else [p.expanduser() for p in DEFAULT_CONFIG_PATHS]
    for p in candidates:
        if p.expanduser().is_file():
            with open(p.expanduser(), encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                raise ConfigError("config file must contain a YAML mapping at the top level")
            break
        if path:  # 明示指定されたファイルが無いのはエラー
            raise FileNotFoundError(f"config file not found: {p}")

    cfg = Config()
    for key, value in data.items():
        if key in {"audio", "stt", "llm", "paste"} and not isinstance(value, dict):
            raise ConfigError(f"{key} must be a YAML mapping")
        if key == "audio":
            cfg.audio = _merge_section(AudioConfig, value, "audio")
        elif key == "stt":
            cfg.stt = _merge_section(SttConfig, value, "stt")
        elif key == "llm":
            cfg.llm = _merge_section(LlmConfig, value, "llm")
        elif key == "paste":
            cfg.paste = _merge_section(PasteConfig, value, "paste")
        elif key in Config.__dataclass_fields__:
            setattr(cfg, key, value)
        else:
            raise ConfigError(f"unknown setting: {key}")
    validate_config(cfg)
    return cfg
