"""ホットキーの解釈。

2 つの形式をサポートする:

- pynput のコンビネーション形式: "<ctrl>+<alt>+<space>"
- 修飾キーのダブルタップ形式: "double:cmd_r"(右 Cmd 2回)、"double:cmd"(左右どちらでも)
"""
from __future__ import annotations

import time
from dataclasses import dataclass

DOUBLE_PREFIX = "double:"


def is_double_tap_spec(hotkey: str) -> bool:
    return hotkey.startswith(DOUBLE_PREFIX)


def double_tap_key_name(hotkey: str) -> str:
    return hotkey[len(DOUBLE_PREFIX):].strip()


def resolve_target_keys(name: str):
    """キー名を pynput の Key 集合に解決する。

    "cmd" のような素の修飾キー名は左右の変種 (cmd_l / cmd_r) も含める。
    "cmd_r" のように明示された場合はそのキーのみ。
    """
    from pynput import keyboard

    base = getattr(keyboard.Key, name, None)
    if base is None:
        raise ValueError(f"unknown key for double-tap hotkey: {name!r}")
    keys = {base}
    if not name.endswith(("_l", "_r")):
        for suffix in ("_l", "_r"):
            variant = getattr(keyboard.Key, name + suffix, None)
            if variant is not None:
                keys.add(variant)
    return keys


@dataclass
class DoubleTapDetector:
    """修飾キーのダブルタップを検出する状態機械。

    誤発火を防ぐため、次の条件を満たす「クリーンなタップ」だけを数える:
    - タップ中(押下〜解放)に他のキーが押されていない
    - 押しっぱなし(max_hold 超)ではない

    1 回目のクリーンなタップの解放から interval 以内に同じキーが再度
    押されたら発火する。Cmd+C → Cmd+V のような連続ショートカットは
    タップ中に文字キーが挟まるため発火しない。
    """

    interval: float = 0.4  # 1回目の解放から2回目の押下までの許容秒数
    max_hold: float = 0.5  # これより長い押下はタップとみなさない

    def __post_init__(self):
        self._press_time: float | None = None
        self._dirty = False  # 押下中に他のキーが押された
        self._last_clean_tap: float | None = None  # クリーンなタップの解放時刻

    def on_press(self, is_target: bool, now: float | None = None) -> bool:
        """キー押下イベント。ダブルタップ成立時に True を返す。"""
        now = time.monotonic() if now is None else now
        if not is_target:
            self._dirty = True
            self._last_clean_tap = None
            return False
        if (
            self._last_clean_tap is not None
            and now - self._last_clean_tap <= self.interval
        ):
            self.__post_init__()  # 状態リセット
            return True
        self._press_time = now
        self._dirty = False
        return False

    def on_release(self, is_target: bool, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        if not is_target:
            return
        if (
            not self._dirty
            and self._press_time is not None
            and now - self._press_time <= self.max_hold
        ):
            self._last_clean_tap = now
        else:
            self._last_clean_tap = None
        self._press_time = None
